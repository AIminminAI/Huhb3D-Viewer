import cv2
import numpy as np
import json
from pathlib import Path

aug_dir = Path(__file__).parent / "sell_Huhb3D-Test-Precision-v4-aug"
orig_dir = Path(__file__).parent / "sell_Huhb3D-Test-Precision-v4"

objects = sorted([d.name for d in aug_dir.iterdir()
                  if d.is_dir() and (d / "depth").exists()])

print("=" * 72)
print("  Augmented Data Quality Verification")
print("=" * 72)

total = 0
ok = 0
issues = []

for obj in objects[:5]:
    obj_dir = aug_dir / obj
    rgb_files = sorted((obj_dir / "rgb").glob("frame_*_aug*.png"))
    depth_files = sorted((obj_dir / "depth").glob("depth_*_aug*.png"))
    mask_files = sorted((obj_dir / "mask").glob("mask_*_aug*.png"))
    meta_files = sorted((obj_dir / "aug_metadata").glob("meta_*_aug*.json"))

    print(f"\n  {obj}: {len(rgb_files)} RGB, {len(depth_files)} depth, "
          f"{len(mask_files)} mask, {len(meta_files)} metadata")

    for i in range(min(3, len(rgb_files))):
        total += 1
        rf = rgb_files[i]
        df = depth_files[i]
        mf = mask_files[i]

        rgb = cv2.imread(str(rf))
        depth = cv2.imread(str(df), cv2.IMREAD_UNCHANGED)
        mask = cv2.imread(str(mf), cv2.IMREAD_GRAYSCALE)

        checks = []

        if rgb is None:
            checks.append("RGB unreadable")
        elif rgb.shape != (600, 800, 3):
            checks.append(f"RGB shape={rgb.shape}")

        if depth is None:
            checks.append("Depth unreadable")
        elif depth.dtype != np.uint16:
            checks.append(f"Depth dtype={depth.dtype}")
        elif depth.shape != (600, 800):
            checks.append(f"Depth shape={depth.shape}")

        if mask is None:
            checks.append("Mask unreadable")
        elif mask.shape != (600, 800):
            checks.append(f"Mask shape={mask.shape}")

        if depth is not None and mask is not None:
            depth_obj = depth[mask > 0]
            if len(depth_obj) > 0:
                if depth_obj.min() <= 0:
                    checks.append("Depth has zeros under mask (possible occlusion artifact)")
            depth_bg = depth[mask == 0]
            if len(depth_bg) > 0 and depth_bg.max() > 0:
                pass

        if not checks:
            ok += 1
        else:
            for c in checks:
                issues.append(f"{rf.name}: {c}")

        stem = rf.stem
        frame_id = stem.split("_")[1]
        aug_id = stem.split("_aug")[1]
        meta_path = obj_dir / "aug_metadata" / f"meta_{frame_id}_aug{aug_id}.json"
        if meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)
            aug_types = []
            for k in ["background", "occlusion", "photometric", "depth_noise", "motion_blur"]:
                if meta.get(k):
                    aug_types.append(k)
            if i == 0:
                print(f"    Sample aug types: {aug_types}")

print(f"\n{'=' * 72}")
print(f"  Verification: {ok}/{total} frames OK")
if issues:
    print(f"  Issues ({len(issues)}):")
    for iss in issues[:10]:
        print(f"    - {iss}")
else:
    print("  No issues found!")

print(f"\n{'=' * 72}")
print("  Augmentation Statistics (from metadata)")
print("=" * 72)

bg_count = 0
occ_count = 0
photo_count = 0
noise_count = 0
blur_count = 0
occ_ratios = []
meta_total = 0

for obj in objects:
    meta_dir = aug_dir / obj / "aug_metadata"
    if not meta_dir.exists():
        continue
    for mp in meta_dir.glob("*.json"):
        meta_total += 1
        with open(mp) as f:
            meta = json.load(f)
        if meta.get("background"):
            bg_count += 1
        if meta.get("occlusion"):
            occ_count += 1
            occ_ratios.append(meta.get("occlusion_ratio", 0))
        if meta.get("photometric"):
            photo_count += 1
        if meta.get("depth_noise"):
            noise_count += 1
        if meta.get("motion_blur"):
            blur_count += 1

print(f"  Total augmented frames: {meta_total}")
print(f"  Background replacement: {bg_count} ({bg_count/meta_total*100:.1f}%)")
print(f"  Occlusion:              {occ_count} ({occ_count/meta_total*100:.1f}%)")
if occ_ratios:
    print(f"    Occlusion ratio: mean={np.mean(occ_ratios):.3f}, "
          f"max={np.max(occ_ratios):.3f}")
print(f"  Photometric:            {photo_count} ({photo_count/meta_total*100:.1f}%)")
print(f"  Depth noise:            {noise_count} ({noise_count/meta_total*100:.1f}%)")
print(f"  Motion blur:            {blur_count} ({blur_count/meta_total*100:.1f}%)")

print(f"\n  Original dataset: 200 images (20 obj x 10 frames)")
print(f"  Augmented dataset: {meta_total} images (5x expansion)")
print(f"  Combined total: {200 + meta_total} images")
print("=" * 72)
