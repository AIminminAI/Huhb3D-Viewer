"""
Huhb3D Original vs Augmented Data Comparison Report
====================================================
Quantitative comparison across 5 dimensions:
  1. RGB Brightness Distribution
  2. RGB Color Distribution
  3. Depth Noise Level
  4. Occlusion Ratio
  5. Mask Coverage Change
"""

import cv2
import numpy as np
import json
import sys
import time
from pathlib import Path
from collections import defaultdict

ORIG_DIR = Path(__file__).parent / "sell_Huhb3D-Test-Precision-v4"
AUG_DIR = Path(__file__).parent / "sell_Huhb3D-Test-Precision-v4-aug"

SAMPLE_OBJECTS = 5
SAMPLE_FRAMES_PER_OBJ = 3
SAMPLE_AUG_PER_FRAME = 3


def get_objects(ds_dir):
    return sorted([d.name for d in ds_dir.iterdir()
                   if d.is_dir() and (d / "depth").exists()])


def analyze_rgb_brightness(rgb, mask=None):
    if mask is not None and mask.any():
        pixels = rgb[mask > 0]
    else:
        pixels = rgb.reshape(-1, 3)

    gray = cv2.cvtColor(rgb, cv2.COLOR_BGR2GRAY)
    if mask is not None and mask.any():
        gray_vals = gray[mask > 0].astype(float)
    else:
        gray_vals = gray.astype(float).ravel()

    return {
        "mean_brightness": float(gray_vals.mean()),
        "std_brightness": float(gray_vals.std()),
        "min_brightness": float(gray_vals.min()),
        "max_brightness": float(gray_vals.max()),
        "p10": float(np.percentile(gray_vals, 10)),
        "p25": float(np.percentile(gray_vals, 25)),
        "p50": float(np.percentile(gray_vals, 50)),
        "p75": float(np.percentile(gray_vals, 75)),
        "p90": float(np.percentile(gray_vals, 90)),
        "mean_b": float(pixels[:, 0].mean()),
        "mean_g": float(pixels[:, 1].mean()),
        "mean_r": float(pixels[:, 2].mean()),
    }


def analyze_depth_noise(depth, mask=None):
    if mask is not None and mask.any():
        vals = depth[mask > 0].astype(float)
    else:
        vals = depth[depth > 0].astype(float)

    if len(vals) == 0:
        return {"mean": 0, "std": 0, "min": 0, "max": 0, "zero_pct": 100,
                "nonzero_pct": 0, "range": 0}

    zero_count = (depth == 0).sum()
    total = depth.size

    return {
        "mean": float(vals.mean()),
        "std": float(vals.std()),
        "min": float(vals.min()),
        "max": float(vals.max()),
        "zero_pct": float(zero_count / total * 100),
        "nonzero_pct": float((total - zero_count) / total * 100),
        "range": float(vals.max() - vals.min()),
    }


def analyze_mask_coverage(mask):
    total = mask.size
    obj_pixels = (mask > 0).sum()
    return {
        "coverage_pct": float(obj_pixels / total * 100),
        "obj_pixels": int(obj_pixels),
        "bg_pixels": int(total - obj_pixels),
    }


def compute_depth_diff(orig_depth, aug_depth, mask):
    obj_mask = mask > 0
    if not obj_mask.any():
        return {"mean_abs_diff": 0, "max_abs_diff": 0, "pct_changed": 0}

    orig_obj = orig_depth[obj_mask].astype(float)
    aug_obj = aug_depth[obj_mask].astype(float)

    valid = (orig_obj > 0) & (aug_obj > 0)
    if not valid.any():
        return {"mean_abs_diff": 0, "max_abs_diff": 0, "pct_changed": 0}

    diff = np.abs(orig_obj[valid] - aug_obj[valid])
    changed = (orig_obj > 0).sum() - valid.sum()
    pct_changed = changed / max((orig_obj > 0).sum(), 1) * 100

    return {
        "mean_abs_diff": float(diff.mean()),
        "max_abs_diff": float(diff.max()),
        "pct_pixels_changed_to_zero": float(pct_changed),
    }


def main():
    print("=" * 78)
    print("  Huhb3D Original vs Augmented Data Comparison Report")
    print("=" * 78)

    orig_objects = get_objects(ORIG_DIR)
    aug_objects = get_objects(AUG_DIR)

    print(f"\n  Original dataset: {ORIG_DIR}")
    print(f"  Augmented dataset: {AUG_DIR}")
    print(f"  Objects (orig): {len(orig_objects)}")
    print(f"  Objects (aug):  {len(aug_objects)}")

    sample_objs = orig_objects[:SAMPLE_OBJECTS]

    orig_brightness = []
    aug_brightness = []
    orig_depth_stats = []
    aug_depth_stats = []
    orig_coverage = []
    aug_coverage = []
    depth_diffs = []
    aug_meta_stats = defaultdict(int)
    occ_ratios = []
    total_aug_meta = 0

    for obj in sample_objs:
        orig_obj_dir = ORIG_DIR / obj
        aug_obj_dir = AUG_DIR / obj

        rgb_files = sorted((orig_obj_dir / "rgb").glob("frame_*.png"))
        for rf in rgb_files[:SAMPLE_FRAMES_PER_OBJ]:
            frame_id = rf.stem.replace("frame_", "")

            rgb = cv2.imread(str(rf))
            depth_path = orig_obj_dir / "depth" / f"depth_{frame_id}.png"
            mask_path = orig_obj_dir / "mask" / f"mask_{frame_id}.png"

            depth = cv2.imread(str(depth_path), cv2.IMREAD_UNCHANGED)
            mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)

            if rgb is None or depth is None or mask is None:
                continue

            orig_brightness.append(analyze_rgb_brightness(rgb, mask))
            orig_depth_stats.append(analyze_depth_noise(depth, mask))
            orig_coverage.append(analyze_mask_coverage(mask))

            aug_rgb_files = sorted(
                (aug_obj_dir / "rgb").glob(f"frame_{frame_id}_aug*.png")
            )

            for aug_rf in aug_rgb_files[:SAMPLE_AUG_PER_FRAME]:
                aug_stem = aug_rf.stem
                aug_suffix = aug_stem.replace(f"frame_{frame_id}_", "")

                aug_df = aug_obj_dir / "depth" / f"depth_{frame_id}_{aug_suffix}.png"
                aug_mf = aug_obj_dir / "mask" / f"mask_{frame_id}_{aug_suffix}.png"

                aug_rgb = cv2.imread(str(aug_rf))
                aug_depth = cv2.imread(str(aug_df), cv2.IMREAD_UNCHANGED)
                aug_mask = cv2.imread(str(aug_mf), cv2.IMREAD_GRAYSCALE)

                if aug_rgb is None or aug_depth is None or aug_mask is None:
                    continue

                aug_brightness.append(analyze_rgb_brightness(aug_rgb, aug_mask))
                aug_depth_stats.append(analyze_depth_noise(aug_depth, aug_mask))
                aug_coverage.append(analyze_mask_coverage(aug_mask))
                depth_diffs.append(compute_depth_diff(depth, aug_depth, mask))

    for obj in aug_objects:
        meta_dir = AUG_DIR / obj / "aug_metadata"
        if not meta_dir.exists():
            continue
        for mp in meta_dir.glob("*.json"):
            total_aug_meta += 1
            with open(mp) as f:
                meta = json.load(f)
            for k in ["background", "occlusion", "photometric", "depth_noise", "motion_blur"]:
                if meta.get(k):
                    aug_meta_stats[k] += 1
            if meta.get("occlusion"):
                occ_ratios.append(meta.get("occlusion_ratio", 0))

    def stats_summary(data_list, key):
        vals = [d[key] for d in data_list if key in d]
        if not vals:
            return {"mean": 0, "std": 0, "min": 0, "max": 0}
        return {
            "mean": float(np.mean(vals)),
            "std": float(np.std(vals)),
            "min": float(np.min(vals)),
            "max": float(np.max(vals)),
        }

    print("\n" + "=" * 78)
    print("  SECTION 1: RGB Brightness Distribution Comparison")
    print("=" * 78)

    for metric, label in [
        ("mean_brightness", "Mean Brightness"),
        ("std_brightness", "Brightness Std Dev"),
        ("p10", "P10 Brightness"),
        ("p50", "P50 (Median) Brightness"),
        ("p90", "P90 Brightness"),
    ]:
        orig_s = stats_summary(orig_brightness, metric)
        aug_s = stats_summary(aug_brightness, metric)
        delta = aug_s["mean"] - orig_s["mean"]
        print(f"\n  {label}:")
        print(f"    Original:  mean={orig_s['mean']:.1f}  std={orig_s['std']:.1f}  "
              f"range=[{orig_s['min']:.1f}, {orig_s['max']:.1f}]")
        print(f"    Augmented: mean={aug_s['mean']:.1f}  std={aug_s['std']:.1f}  "
              f"range=[{aug_s['min']:.1f}, {aug_s['max']:.1f}]")
        print(f"    Delta:     {delta:+.1f}  ({delta/max(abs(orig_s['mean']),1)*100:+.1f}%)")

    print("\n" + "=" * 78)
    print("  SECTION 2: RGB Color Distribution Comparison")
    print("=" * 78)

    for ch, label in [("mean_b", "Blue"), ("mean_g", "Green"), ("mean_r", "Red")]:
        orig_s = stats_summary(orig_brightness, ch)
        aug_s = stats_summary(aug_brightness, ch)
        print(f"\n  {label} Channel Mean:")
        print(f"    Original:  {orig_s['mean']:.1f}")
        print(f"    Augmented: {aug_s['mean']:.1f}")
        print(f"    Delta:     {aug_s['mean']-orig_s['mean']:+.1f}")

    print("\n" + "=" * 78)
    print("  SECTION 3: Depth Noise Level Comparison")
    print("=" * 78)

    for metric, label in [
        ("mean", "Mean Depth (mm)"),
        ("std", "Depth Std Dev (mm)"),
        ("range", "Depth Range (mm)"),
        ("zero_pct", "Zero Pixel %"),
    ]:
        orig_s = stats_summary(orig_depth_stats, metric)
        aug_s = stats_summary(aug_depth_stats, metric)
        delta = aug_s["mean"] - orig_s["mean"]
        print(f"\n  {label}:")
        print(f"    Original:  mean={orig_s['mean']:.2f}  range=[{orig_s['min']:.2f}, {orig_s['max']:.2f}]")
        print(f"    Augmented: mean={aug_s['mean']:.2f}  range=[{aug_s['min']:.2f}, {aug_s['max']:.2f}]")
        print(f"    Delta:     {delta:+.2f}")

    if depth_diffs:
        mean_diffs = [d["mean_abs_diff"] for d in depth_diffs]
        max_diffs = [d["max_abs_diff"] for d in depth_diffs]
        pct_zeros = [d["pct_pixels_changed_to_zero"] for d in depth_diffs]
        print(f"\n  Depth Pixel-Level Difference (same-frame orig vs aug):")
        print(f"    Mean abs diff:     {np.mean(mean_diffs):.2f} mm")
        print(f"    Max abs diff:      {np.mean(max_diffs):.2f} mm")
        print(f"    Pixels -> zero:    {np.mean(pct_zeros):.1f}% (occlusion + noise holes)")

    print("\n" + "=" * 78)
    print("  SECTION 4: Occlusion Statistics")
    print("=" * 78)

    print(f"\n  Total augmented frames: {total_aug_meta}")
    for k in ["background", "occlusion", "photometric", "depth_noise", "motion_blur"]:
        count = aug_meta_stats.get(k, 0)
        pct = count / max(total_aug_meta, 1) * 100
        print(f"  {k:20s}: {count:5d} ({pct:5.1f}%)")

    if occ_ratios:
        print(f"\n  Occlusion Ratio (among occluded frames):")
        print(f"    Mean:   {np.mean(occ_ratios):.3f} ({np.mean(occ_ratios)*100:.1f}%)")
        print(f"    Std:    {np.std(occ_ratios):.3f}")
        print(f"    Min:    {np.min(occ_ratios):.3f} ({np.min(occ_ratios)*100:.1f}%)")
        print(f"    Max:    {np.max(occ_ratios):.3f} ({np.max(occ_ratios)*100:.1f}%)")
        print(f"    P25:    {np.percentile(occ_ratios, 25):.3f}")
        print(f"    P50:    {np.percentile(occ_ratios, 50):.3f}")
        print(f"    P75:    {np.percentile(occ_ratios, 75):.3f}")

    print("\n" + "=" * 78)
    print("  SECTION 5: Mask Coverage Change")
    print("=" * 78)

    orig_cov_vals = [c["coverage_pct"] for c in orig_coverage]
    aug_cov_vals = [c["coverage_pct"] for c in aug_coverage]

    print(f"\n  Object Mask Coverage (% of image):")
    print(f"    Original:  mean={np.mean(orig_cov_vals):.2f}%  std={np.std(orig_cov_vals):.2f}%  "
          f"range=[{np.min(orig_cov_vals):.2f}%, {np.max(orig_cov_vals):.2f}%]")
    print(f"    Augmented: mean={np.mean(aug_cov_vals):.2f}%  std={np.std(aug_cov_vals):.2f}%  "
          f"range=[{np.min(aug_cov_vals):.2f}%, {np.max(aug_cov_vals):.2f}%]")
    delta_cov = np.mean(aug_cov_vals) - np.mean(orig_cov_vals)
    print(f"    Delta:     {delta_cov:+.2f}% (reduction due to occlusion)")

    print("\n" + "=" * 78)
    print("  SECTION 6: Summary & Effectiveness Assessment")
    print("=" * 78)

    orig_bright_mean = stats_summary(orig_brightness, "mean_brightness")["mean"]
    aug_bright_mean = stats_summary(aug_brightness, "mean_brightness")["mean"]
    orig_bright_std = stats_summary(orig_brightness, "std_brightness")["mean"]
    aug_bright_std = stats_summary(aug_brightness, "std_brightness")["mean"]

    orig_zero_pct = stats_summary(orig_depth_stats, "zero_pct")["mean"]
    aug_zero_pct = stats_summary(aug_depth_stats, "zero_pct")["mean"]

    print(f"\n  Brightness diversity:")
    print(f"    Original std:  {orig_bright_std:.1f}")
    print(f"    Augmented std: {aug_bright_std:.1f}")
    print(f"    Diversity gain: {(aug_bright_std/max(orig_bright_std,0.1)-1)*100:+.1f}%")

    print(f"\n  Depth noise injection:")
    print(f"    Original zero%:  {orig_zero_pct:.1f}%")
    print(f"    Augmented zero%: {aug_zero_pct:.1f}%")
    print(f"    Noise holes added: {aug_zero_pct-orig_zero_pct:+.1f}%")

    print(f"\n  Occlusion simulation:")
    print(f"    Frames with occlusion: {aug_meta_stats.get('occlusion',0)}/{total_aug_meta} "
          f"({aug_meta_stats.get('occlusion',0)/max(total_aug_meta,1)*100:.1f}%)")
    if occ_ratios:
        print(f"    Average occlusion: {np.mean(occ_ratios)*100:.1f}% of object")

    print(f"\n  Data volume:")
    print(f"    Original:  200 images")
    print(f"    Augmented: {total_aug_meta} images")
    print(f"    Total:     {200+total_aug_meta} images ({(200+total_aug_meta)/200:.1f}x)")

    print(f"\n  Assessment:")
    bright_diverse = aug_bright_std > orig_bright_std * 1.1
    noise_added = aug_zero_pct > orig_zero_pct
    occ_present = len(occ_ratios) > 0

    if bright_diverse and noise_added and occ_present:
        print(f"    [OK] Augmentation is EFFECTIVE - all 3 diversity axes increased")
    else:
        print(f"    [WARN] Some augmentation axes may be insufficient:")
        if not bright_diverse:
            print(f"      - Brightness diversity not significantly increased")
        if not noise_added:
            print(f"      - Depth noise not significantly added")
        if not occ_present:
            print(f"      - No occlusion generated")

    report_path = AUG_DIR / "augmentation_comparison_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("Huhb3D Augmentation Comparison Report\n")
        f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Original: {ORIG_DIR}\n")
        f.write(f"Augmented: {AUG_DIR}\n")
        f.write(f"Original images: 200, Augmented: {total_aug_meta}\n\n")
        f.write(f"Brightness diversity gain: {(aug_bright_std/max(orig_bright_std,0.1)-1)*100:+.1f}%\n")
        f.write(f"Depth noise holes added: {aug_zero_pct-orig_zero_pct:+.1f}%\n")
        f.write(f"Occlusion frames: {aug_meta_stats.get('occlusion',0)} ({aug_meta_stats.get('occlusion',0)/max(total_aug_meta,1)*100:.1f}%)\n")
        if occ_ratios:
            f.write(f"Mean occlusion ratio: {np.mean(occ_ratios)*100:.1f}%\n")
    print(f"\n  Report saved: {report_path}")
    print("=" * 78)


if __name__ == "__main__":
    main()
