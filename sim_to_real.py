"""
sim_to_real.py - Sim-to-Real Enhancement Post-Processor
=======================================================
Applies realistic image augmentations to synthetic rendered data
to bridge the simulation-to-reality gap for robot vision training.

Augmentations:
  1. Gaussian Noise - sensor noise simulation
  2. Motion Blur - camera/object movement blur
  3. Occlusion Simulation - random object occlusion
  4. Color Jitter - brightness/contrast/saturation/hue variation
  5. Depth Noise - depth sensor noise simulation

Usage:
    python sim_to_real.py --input-dir ./synthetic_output --output-dir ./augmented_output
    python sim_to_real.py --input-dir ./synthetic_output --output-dir ./augmented_output \
        --gaussian-noise --motion-blur --occlusion --color-jitter --depth-noise

Requirements:
    pip install opencv-python numpy
"""

import argparse
import json
import math
import os
import random
import sys
from pathlib import Path


def apply_gaussian_noise(image, mean=0, sigma_range=(5, 25)):
    sigma = random.uniform(sigma_range[0], sigma_range[1])
    import numpy as np
    noise = np.random.normal(mean, sigma, image.shape).astype(np.float32)
    noisy = image.astype(np.float32) + noise
    return np.clip(noisy, 0, 255).astype(np.uint8)


def apply_motion_blur(image, kernel_size_range=(3, 15), angle_range=(0, 360)):
    import cv2
    import numpy as np
    kernel_size = random.randint(kernel_size_range[0], kernel_size_range[1])
    if kernel_size % 2 == 0:
        kernel_size += 1
    angle = random.uniform(angle_range[0], angle_range[1])
    kernel = np.zeros((kernel_size, kernel_size), dtype=np.float32)
    mid = kernel_size // 2
    cos_a = math.cos(math.radians(angle))
    sin_a = math.sin(math.radians(angle))
    for i in range(kernel_size):
        offset = i - mid
        x = int(mid + offset * cos_a + 0.5)
        y = int(mid + offset * sin_a + 0.5)
        if 0 <= x < kernel_size and 0 <= y < kernel_size:
            kernel[y, x] = 1.0
    kernel /= kernel.sum() if kernel.sum() > 0 else 1.0
    return cv2.filter2D(image, -1, kernel)


def apply_occlusion(image, mask_image, num_occlusions_range=(1, 3),
                    size_range=(0.05, 0.25), occlusion_colors=None):
    import cv2
    import numpy as np
    h, w = image.shape[:2]
    num_occlusions = random.randint(num_occlusions_range[0], num_occlusions_range[1])
    result = image.copy()
    result_mask = mask_image.copy() if mask_image is not None else None
    for _ in range(num_occlusions):
        occ_h = int(h * random.uniform(size_range[0], size_range[1]))
        occ_w = int(w * random.uniform(size_range[0], size_range[1]))
        y = random.randint(0, h - occ_h)
        x = random.randint(0, w - occ_w)
        if occlusion_colors:
            color = random.choice(occlusion_colors)
        else:
            color = [random.randint(30, 220) for _ in range(3)]
        occ_block = np.full((occ_h, occ_w, 3), color, dtype=np.uint8)
        result[y:y+occ_h, x:x+occ_w] = occ_block
        if result_mask is not None:
            occ_mask = np.full((occ_h, occ_w, 3), [0, 0, 0], dtype=np.uint8)
            result_mask[y:y+occ_h, x:x+occ_w] = occ_mask
    return result, result_mask


def apply_color_jitter(image, brightness_range=(0.7, 1.3),
                       contrast_range=(0.7, 1.3),
                       saturation_range=(0.7, 1.3),
                       hue_range=(-10, 10)):
    import cv2
    import numpy as np
    result = image.astype(np.float32)
    brightness = random.uniform(brightness_range[0], brightness_range[1])
    result *= brightness
    contrast = random.uniform(contrast_range[0], contrast_range[1])
    mean_val = result.mean()
    result = (result - mean_val) * contrast + mean_val
    hsv = cv2.cvtColor(np.clip(result, 0, 255).astype(np.uint8), cv2.COLOR_BGR2HSV)
    hsv = hsv.astype(np.float32)
    saturation = random.uniform(saturation_range[0], saturation_range[1])
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * saturation, 0, 255)
    hue_shift = random.uniform(hue_range[0], hue_range[1])
    hsv[:, :, 0] = np.clip(hsv[:, :, 0] + hue_shift, 0, 179)
    result = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    return result


def apply_depth_noise(depth_image, noise_sigma_range=(0.5, 3.0),
                      hole_probability=0.002, hole_size_range=(1, 5)):
    import numpy as np
    result = depth_image.copy().astype(np.float32)
    sigma = random.uniform(noise_sigma_range[0], noise_sigma_range[1])
    noise = np.random.normal(0, sigma, result.shape).astype(np.float32)
    result += noise
    h, w = result.shape[:2]
    num_holes = int(h * w * hole_probability)
    for _ in range(num_holes):
        hy = random.randint(0, h - 1)
        hx = random.randint(0, w - 1)
        hs = random.randint(hole_size_range[0], hole_size_range[1])
        y1 = max(0, hy - hs // 2)
        y2 = min(h, hy + hs // 2 + 1)
        x1 = max(0, hx - hs // 2)
        x2 = min(w, hx + hs // 2 + 1)
        result[y1:y2, x1:x2] = 0
    return np.clip(result, 0, 65535).astype(np.uint16)


def process_directory(input_dir, output_dir, augmentations):
    import cv2
    import numpy as np

    input_path = Path(input_dir)
    output_path = Path(output_dir)

    rgb_dir = input_path / "rgb"
    mask_dir = input_path / "mask"
    mask_instance_dir = input_path / "mask_instance"
    depth_dir = input_path / "depth"

    out_rgb_dir = output_path / "rgb"
    out_mask_dir = output_path / "mask"
    out_mask_instance_dir = output_path / "mask_instance"
    out_depth_dir = output_path / "depth"

    out_rgb_dir.mkdir(parents=True, exist_ok=True)
    if mask_dir.exists():
        out_mask_dir.mkdir(parents=True, exist_ok=True)
    if mask_instance_dir.exists():
        out_mask_instance_dir.mkdir(parents=True, exist_ok=True)
    if depth_dir.exists():
        out_depth_dir.mkdir(parents=True, exist_ok=True)

    if not rgb_dir.exists():
        print(f"ERROR: RGB directory not found: {rgb_dir}")
        return False

    rgb_files = sorted(list(rgb_dir.glob("*.png")))
    if not rgb_files:
        print(f"ERROR: No PNG files found in {rgb_dir}")
        return False

    print(f"[SimToReal] Processing {len(rgb_files)} images")
    print(f"[SimToReal] Augmentations: {', '.join(k for k, v in augmentations.items() if v)}")

    aug_config = {
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "augmentations": augmentations,
        "total_images": len(rgb_files),
    }

    for idx, rgb_file in enumerate(rgb_files):
        stem = rgb_file.stem
        image = cv2.imread(str(rgb_file))
        if image is None:
            print(f"  WARNING: Cannot read {rgb_file}")
            continue

        mask_image = None
        mask_file = mask_dir / f"{stem}.png"
        if mask_dir.exists() and mask_file.exists():
            mask_image = cv2.imread(str(mask_file))

        instance_image = None
        instance_file = mask_instance_dir / f"instance_{stem.replace('frame_', '')}.png"
        if mask_instance_dir.exists():
            inst_files = list(mask_instance_dir.glob(f"*{stem.replace('frame_', '')}*.png"))
            if inst_files:
                instance_image = cv2.imread(str(inst_files[0]))

        depth_image = None
        depth_file = depth_dir / f"{stem}.png"
        if depth_dir.exists() and depth_file.exists():
            depth_image = cv2.imread(str(depth_file), cv2.IMREAD_UNCHANGED)

        augmented = image.copy()
        aug_mask = mask_image.copy() if mask_image is not None else None
        aug_instance = instance_image.copy() if instance_image is not None else None
        aug_depth = depth_image.copy() if depth_image is not None else None

        if augmentations.get("color_jitter", False):
            augmented = apply_color_jitter(augmented)

        if augmentations.get("gaussian_noise", False):
            augmented = apply_gaussian_noise(augmented)

        if augmentations.get("motion_blur", False):
            if random.random() < 0.3:
                augmented = apply_motion_blur(augmented)

        if augmentations.get("occlusion", False):
            if random.random() < 0.2:
                augmented, aug_mask = apply_occlusion(augmented, aug_mask)
                if aug_instance is not None:
                    h, w = augmented.shape[:2]
                    num_occlusions = random.randint(1, 3)
                    for _ in range(num_occlusions):
                        occ_h = int(h * random.uniform(0.05, 0.15))
                        occ_w = int(w * random.uniform(0.05, 0.15))
                        y = random.randint(0, h - occ_h)
                        x = random.randint(0, w - occ_w)
                        aug_instance[y:y+occ_h, x:x+occ_w] = [0, 0, 0]

        if augmentations.get("depth_noise", False) and aug_depth is not None:
            aug_depth = apply_depth_noise(aug_depth)

        cv2.imwrite(str(out_rgb_dir / f"{stem}.png"), augmented)
        if aug_mask is not None:
            cv2.imwrite(str(out_mask_dir / f"{stem}.png"), aug_mask)
        if aug_instance is not None:
            inst_stem = stem.replace("frame_", "instance_")
            cv2.imwrite(str(out_mask_instance_dir / f"{inst_stem}.png"), aug_instance)
        if aug_depth is not None:
            cv2.imwrite(str(out_depth_dir / f"{stem}.png"), aug_depth)

        if (idx + 1) % 100 == 0:
            print(f"  Processed {idx + 1}/{len(rgb_files)}")

    config_path = output_path / "augmentation_config.json"
    with open(config_path, 'w') as f:
        json.dump(aug_config, f, indent=2)

    for json_name in ["camera_poses.json", "scene_camera.json", "scene_gt.json",
                       "gt_6dof.json", "manifest.json", "label_legend.txt",
                       "topology_labels.json", "topology_summary.json",
                       "coco_annotations.json", "coco_instance_annotations.json"]:
        src = input_path / json_name
        if src.exists():
            import shutil
            shutil.copy2(str(src), str(output_path / json_name))

    print(f"[SimToReal] Complete! {len(rgb_files)} images processed")
    print(f"[SimToReal] Output: {output_dir}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Sim-to-Real Enhancement Post-Processor"
    )
    parser.add_argument("--input-dir", "-i", required=True,
                        help="Input directory (synthetic_output)")
    parser.add_argument("--output-dir", "-o", default=None,
                        help="Output directory (default: <input-dir>_augmented)")
    parser.add_argument("--gaussian-noise", action="store_true",
                        help="Apply Gaussian noise (sensor noise simulation)")
    parser.add_argument("--motion-blur", action="store_true",
                        help="Apply motion blur (camera movement)")
    parser.add_argument("--occlusion", action="store_true",
                        help="Apply random occlusion")
    parser.add_argument("--color-jitter", action="store_true",
                        help="Apply color jitter (brightness/contrast/saturation/hue)")
    parser.add_argument("--depth-noise", action="store_true",
                        help="Apply depth sensor noise")
    parser.add_argument("--all", action="store_true",
                        help="Apply all augmentations")
    args = parser.parse_args()

    augmentations = {
        "gaussian_noise": args.gaussian_noise or args.all,
        "motion_blur": args.motion_blur or args.all,
        "occlusion": args.occlusion or args.all,
        "color_jitter": args.color_jitter or args.all,
        "depth_noise": args.depth_noise or args.all,
    }

    output_dir = args.output_dir or (str(args.input_dir) + "_augmented")

    success = process_directory(args.input_dir, output_dir, augmentations)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
