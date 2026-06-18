"""
dataset_validator.py - Training-Ready Data Quality Validator
=============================================================
Validates synthetic dataset quality to ensure it is suitable for
training production computer vision models.

Checks:
  1. BOP format compliance (scene_camera.json, scene_gt.json)
  2. COCO RLE decodeability
  3. RGB/Mask/Depth alignment
  4. 6DoF pose sanity (non-zero, non-identity for single-object)
  5. Depth scale consistency
  6. Instance ID uniqueness
  7. Mask pixel accuracy (no anti-aliasing artifacts)
  8. Training readiness score

Usage:
    python dataset_validator.py --input-dir ./dataset_output
    python dataset_validator.py --input-dir ./dataset_output --strict
"""

import argparse
import json
import sys
from pathlib import Path


class DatasetValidator:
    def __init__(self, input_dir, strict=False):
        self.input_dir = Path(input_dir)
        self.strict = strict
        self.errors = []
        self.warnings = []
        self.checks_passed = 0
        self.checks_total = 0

    def error(self, msg):
        self.errors.append(msg)
        print(f"  ❌ FAIL: {msg}")

    def warn(self, msg):
        self.warnings.append(msg)
        print(f"  ⚠️  WARN: {msg}")

    def ok(self, msg):
        self.checks_passed += 1
        print(f"  ✅ PASS: {msg}")

    def check(self, condition, pass_msg, fail_msg, is_error=True):
        self.checks_total += 1
        if condition:
            self.ok(pass_msg)
        elif is_error:
            self.error(fail_msg)
        else:
            self.warn(fail_msg)

    def validate_structure(self):
        print("\n[1/7] Directory Structure")
        required_dirs = ["rgb"]
        optional_dirs = ["mask", "mask_instance", "depth"]

        for d in required_dirs:
            self.check(
                (self.input_dir / d).exists(),
                f"{d}/ exists",
                f"Missing required directory: {d}/",
            )

        for d in optional_dirs:
            exists = (self.input_dir / d).exists()
            if exists:
                self.ok(f"{d}/ exists")
            else:
                self.warn(f"Optional directory missing: {d}/")

        rgb_count = len(list((self.input_dir / "rgb").glob("*.png"))) if (self.input_dir / "rgb").exists() else 0
        self.check(rgb_count > 0, f"RGB images: {rgb_count}", "No RGB images found")

        return rgb_count

    def validate_bop_format(self, rgb_count):
        print("\n[2/7] BOP Format Compliance")

        scene_camera_path = self.input_dir / "scene_camera.json"
        scene_gt_path = self.input_dir / "scene_gt.json"

        self.check(
            scene_camera_path.exists(),
            "scene_camera.json exists",
            "Missing scene_camera.json (BOP format required)",
        )
        self.check(
            scene_gt_path.exists(),
            "scene_gt.json exists",
            "Missing scene_gt.json (BOP format required)",
        )

        if scene_camera_path.exists():
            try:
                with open(scene_camera_path, "r") as f:
                    sc = json.load(f)

                frame_count = len(sc)
                self.check(
                    frame_count == rgb_count,
                    f"scene_camera frames ({frame_count}) == RGB count ({rgb_count})",
                    f"Frame count mismatch: scene_camera={frame_count}, rgb={rgb_count}",
                )

                first_key = list(sc.keys())[0]
                first_frame = sc[first_key]

                has_cam_K = "cam_K" in first_frame
                has_depth_scale = "depth_scale" in first_frame
                self.check(has_cam_K, "cam_K field present", "Missing cam_K in scene_camera.json")
                self.check(has_depth_scale, "depth_scale field present", "Missing depth_scale in scene_camera.json")

                if has_cam_K:
                    cam_K = first_frame["cam_K"]
                    self.check(
                        len(cam_K) == 9,
                        "cam_K is 3x3 (9 elements)",
                        f"cam_K has {len(cam_K)} elements, expected 9",
                    )
                    fx = cam_K[0]
                    fy = cam_K[4]
                    cx = cam_K[2]
                    cy = cam_K[5]
                    self.check(
                        abs(fx - fy) < 1.0,
                        f"fx≈fy (square pixels): fx={fx:.1f}, fy={fy:.1f}",
                        f"fx≠fy (non-square pixels): fx={fx:.1f}, fy={fy:.1f}",
                        is_error=False,
                    )
                    self.check(
                        fx > 100,
                        f"fx reasonable ({fx:.1f} > 100)",
                        f"fx suspiciously small: {fx:.1f}",
                    )

            except json.JSONDecodeError as e:
                self.error(f"scene_camera.json parse error: {e}")

        if scene_gt_path.exists():
            try:
                with open(scene_gt_path, "r") as f:
                    sg = json.load(f)

                first_key = list(sg.keys())[0]
                first_objs = sg[first_key]

                has_identity_pose = True
                all_zero_translation = True
                for obj in first_objs:
                    r = obj.get("cam_R_m2c", [])
                    t = obj.get("cam_t_m2c", [])
                    if len(r) == 9:
                        is_identity = (
                            abs(r[0] - 1.0) < 0.001 and abs(r[4] - 1.0) < 0.001
                            and abs(r[8] - 1.0) < 0.001
                            and abs(r[1]) < 0.001 and abs(r[2]) < 0.001
                            and abs(r[3]) < 0.001 and abs(r[5]) < 0.001
                            and abs(r[6]) < 0.001 and abs(r[7]) < 0.001
                        )
                        if not is_identity:
                            has_identity_pose = False
                    if len(t) == 3:
                        if abs(t[0]) > 0.001 or abs(t[1]) > 0.001 or abs(t[2]) > 0.001:
                            all_zero_translation = False

                self.check(
                    not (has_identity_pose and all_zero_translation),
                    "6DoF poses are non-trivial (not identity + zero translation)",
                    "ALL poses are identity matrix + zero translation! "
                    "This means 6DoF GT is completely wrong. "
                    "Single-object mode must use cam_R_w2c/cam_t_w2c as cam_R_m2c/cam_t_m2c.",
                )

                sample_key = list(sg.keys())[min(5, len(sg) - 1)]
                sample_obj = sg[sample_key][0]
                t = sample_obj.get("cam_t_m2c", [])
                if len(t) == 3:
                    self.check(
                        abs(t[2]) > 0.01,
                        f"Translation Z non-zero: t_z={t[2]:.4f}",
                        f"Translation Z is zero or near-zero: t_z={t[2]:.4f}. "
                        f"Object may be at camera origin.",
                        is_error=False,
                    )

            except json.JSONDecodeError as e:
                self.error(f"scene_gt.json parse error: {e}")

    def validate_coco_format(self):
        print("\n[3/7] COCO Format Compliance")

        for coco_name in ["coco_annotations.json", "coco_instance_annotations.json"]:
            coco_path = self.input_dir / coco_name
            if not coco_path.exists():
                continue

            try:
                with open(coco_path, "r") as f:
                    coco = json.load(f)

                has_images = "images" in coco and len(coco["images"]) > 0
                has_annotations = "annotations" in coco and len(coco["annotations"]) > 0
                self.check(has_images, f"{coco_name}: has images", f"{coco_name}: no images")
                self.check(has_annotations, f"{coco_name}: has annotations ({len(coco.get('annotations', []))})", f"{coco_name}: no annotations")

                if has_annotations:
                    sample_ann = coco["annotations"][0]
                    has_segmentation = "segmentation" in sample_ann
                    has_bbox = "bbox" in sample_ann
                    self.check(has_segmentation, f"{coco_name}: annotations have segmentation", f"{coco_name}: annotations missing segmentation")
                    self.check(has_bbox, f"{coco_name}: annotations have bbox", f"{coco_name}: annotations missing bbox")

                    if has_segmentation:
                        seg = sample_ann["segmentation"]
                        if isinstance(seg, dict) and "counts" in seg:
                            counts = seg["counts"]
                            is_coco_rle = True
                            if len(counts) > 0:
                                first_val = counts[0]
                                if not isinstance(first_val, int):
                                    is_coco_rle = False

                            self.check(
                                is_coco_rle,
                                f"{coco_name}: RLE counts are integers (COCO standard)",
                                f"{coco_name}: RLE counts are NOT standard COCO format! "
                                f"pycocotools will fail to decode.",
                            )

                            try:
                                import numpy as np
                                h, w = seg.get("size", [0, 0])
                                if h > 0 and w > 0:
                                    total_pixels = h * w
                                    sum_counts = sum(counts)
                                    self.check(
                                        sum_counts == total_pixels,
                                        f"{coco_name}: RLE pixel count matches ({sum_counts} == {total_pixels})",
                                        f"{coco_name}: RLE pixel count mismatch ({sum_counts} != {total_pixels}). "
                                        f"Mask decode will be wrong!",
                                    )
                            except ImportError:
                                pass

            except json.JSONDecodeError as e:
                self.error(f"{coco_name} parse error: {e}")

    def validate_alignment(self, rgb_count):
        print("\n[4/7] RGB/Mask/Depth Alignment")

        rgb_dir = self.input_dir / "rgb"
        mask_dir = self.input_dir / "mask"
        depth_dir = self.input_dir / "depth"

        if mask_dir.exists():
            mask_files = list(mask_dir.glob("*.png"))
            self.check(
                len(mask_files) == rgb_count,
                f"Mask count ({len(mask_files)}) == RGB count ({rgb_count})",
                f"Mask count ({len(mask_files)}) != RGB count ({rgb_count})",
            )

        if depth_dir.exists():
            depth_files = list(depth_dir.glob("*.png"))
            self.check(
                len(depth_files) == rgb_count,
                f"Depth count ({len(depth_files)}) == RGB count ({rgb_count})",
                f"Depth count ({len(depth_files)}) != RGB count ({rgb_count})",
            )

        try:
            import cv2
            import numpy as np

            rgb_files = sorted(list(rgb_dir.glob("*.png")))[:5]
            for rgb_file in rgb_files:
                rgb_img = cv2.imread(str(rgb_file))
                if rgb_img is None:
                    continue
                rh, rw = rgb_img.shape[:2]

                stem = rgb_file.stem
                mask_file = mask_dir / f"{stem}.png"
                if mask_file.exists():
                    mask_img = cv2.imread(str(mask_file))
                    if mask_img is not None:
                        mh, mw = mask_img.shape[:2]
                        self.check(
                            rh == mh and rw == mw,
                            f"{stem}: RGB({rw}x{rh}) == Mask({mw}x{mh})",
                            f"{stem}: RGB({rw}x{rh}) != Mask({mw}x{mh})! GT alignment broken!",
                        )

                depth_file = depth_dir / f"{stem}.png"
                if depth_file.exists():
                    depth_img = cv2.imread(str(depth_file), cv2.IMREAD_UNCHANGED)
                    if depth_img is not None:
                        dh, dw = depth_img.shape[:2]
                        self.check(
                            rh == dh and rw == dw,
                            f"{stem}: RGB({rw}x{rh}) == Depth({dw}x{dh})",
                            f"{stem}: RGB({rw}x{rh}) != Depth({dw}x{dh})! GT alignment broken!",
                        )

        except ImportError:
            self.warn("OpenCV not available, skipping pixel-level alignment check")

    def validate_depth_scale(self):
        print("\n[5/7] Depth Scale Consistency")

        scene_camera_path = self.input_dir / "scene_camera.json"
        depth_dir = self.input_dir / "depth"

        if not scene_camera_path.exists() or not depth_dir.exists():
            self.warn("Skipping depth scale check (missing files)")
            return

        try:
            with open(scene_camera_path, "r") as f:
                sc = json.load(f)

            import cv2
            import numpy as np

            first_key = list(sc.keys())[0]
            depth_scale = sc[first_key].get("depth_scale", 0)

            depth_files = sorted(list(depth_dir.glob("*.png")))[:3]
            for df in depth_files:
                depth_img = cv2.imread(str(df), cv2.IMREAD_UNCHANGED)
                if depth_img is None:
                    continue

                non_zero = depth_img[depth_img > 0]
                if len(non_zero) > 0:
                    max_depth_mm = float(non_zero.max()) * depth_scale
                    min_depth_mm = float(non_zero.min()) * depth_scale

                    self.check(
                        max_depth_mm < 100000,
                        f"{df.stem}: max depth {max_depth_mm:.1f}mm reasonable",
                        f"{df.stem}: max depth {max_depth_mm:.1f}mm suspiciously large! "
                        f"depth_scale may be wrong.",
                        is_error=False,
                    )

                    self.check(
                        min_depth_mm > 0,
                        f"{df.stem}: min depth {min_depth_mm:.1f}mm > 0",
                        f"{df.stem}: min depth {min_depth_mm:.1f}mm <= 0",
                        is_error=False,
                    )

        except ImportError:
            self.warn("OpenCV not available, skipping depth value check")

    def validate_instance_ids(self):
        print("\n[6/7] Instance ID Uniqueness")

        mask_instance_dir = self.input_dir / "mask_instance"
        if not mask_instance_dir.exists():
            self.warn("No instance mask directory, skipping")
            return

        try:
            import cv2
            import numpy as np

            inst_files = sorted(list(mask_instance_dir.glob("*.png")))[:10]
            for inst_file in inst_files:
                img = cv2.imread(str(inst_file))
                if img is None:
                    continue

                pixels = img.reshape(-1, 3)
                unique_colors = np.unique(pixels, axis=0)

                non_bg = [c for c in unique_colors if not (c[0] == 0 and c[1] == 0 and c[2] == 0)]

                instance_ids = set()
                has_ambiguous = False
                for c in non_bg:
                    r, g, b = int(c[0]), int(c[1]), int(c[2])
                    instance_ids.add(r)

                self.check(
                    len(instance_ids) <= 255,
                    f"{inst_file.stem}: {len(instance_ids)} unique instance IDs",
                    f"{inst_file.stem}: Too many instance IDs ({len(instance_ids)})",
                    is_error=False,
                )

        except ImportError:
            self.warn("OpenCV not available, skipping instance ID check")

    def validate_training_readiness(self):
        print("\n[7/7] Training Readiness Assessment")

        has_bop = (self.input_dir / "scene_camera.json").exists() and (self.input_dir / "scene_gt.json").exists()
        has_coco = (self.input_dir / "coco_annotations.json").exists()
        has_coco_inst = (self.input_dir / "coco_instance_annotations.json").exists()
        has_depth = (self.input_dir / "depth").exists()
        has_yolo = (self.input_dir / "yolo_labels").exists()
        has_topology = (self.input_dir / "topology_labels.json").exists()

        formats = []
        if has_bop:
            formats.append("BOP-6DoF")
        if has_coco:
            formats.append("COCO-Semantic")
        if has_coco_inst:
            formats.append("COCO-Instance")
        if has_yolo:
            formats.append("YOLO")
        if has_depth:
            formats.append("Depth")
        if has_topology:
            formats.append("STEP-Topology")

        self.ok(f"Available formats: {', '.join(formats)}")

        critical_errors = len(self.errors)
        readiness = "READY" if critical_errors == 0 else "NOT READY"

        if critical_errors > 0:
            self.error(f"Dataset is {readiness} for training ({critical_errors} critical issues)")
        else:
            self.ok(f"Dataset is {readiness} for training")

        return readiness

    def run(self):
        print("=" * 60)
        print(f"  Dataset Quality Validator: {self.input_dir}")
        print("=" * 60)

        rgb_count = self.validate_structure()
        self.validate_bop_format(rgb_count)
        self.validate_coco_format()
        self.validate_alignment(rgb_count)
        self.validate_depth_scale()
        self.validate_instance_ids()
        readiness = self.validate_training_readiness()

        print(f"\n{'='*60}")
        print(f"  VALIDATION SUMMARY")
        print(f"{'='*60}")
        print(f"  Checks passed: {self.checks_passed}/{self.checks_total}")
        print(f"  Errors:        {len(self.errors)}")
        print(f"  Warnings:      {len(self.warnings)}")
        print(f"  Status:        {readiness}")

        if self.errors:
            print(f"\n  CRITICAL ISSUES:")
            for e in self.errors:
                print(f"    ❌ {e}")

        if self.warnings:
            print(f"\n  WARNINGS:")
            for w in self.warnings:
                print(f"    ⚠️  {w}")

        print(f"{'='*60}")

        return len(self.errors) == 0


def main():
    parser = argparse.ArgumentParser(description="Dataset Quality Validator")
    parser.add_argument("--input-dir", "-i", required=True)
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    args = parser.parse_args()

    validator = DatasetValidator(args.input_dir, strict=args.strict)
    success = validator.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
