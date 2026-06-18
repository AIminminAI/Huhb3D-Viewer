"""
Huhb3D Industrial Data Augmentation Pipeline
=============================================
Adds realistic industrial variations to synthetic data while preserving
GT consistency across RGB/depth/mask/pose.

Augmentation types:
  1. Background replacement (industrial textures / random patterns)
  2. Random occlusion (rectangular / irregular shapes)
  3. Photometric changes (brightness / contrast / gamma / color shift)
  4. Sensor noise (Gaussian + Poisson + speckle for depth)
  5. Depth-specific noise (Kinect-style hole filling, flying pixels)
  6. Motion blur (directional kernel)

CRITICAL: All augmentations maintain GT consistency:
  - Background replacement: only affects pixels where mask == 0
  - Occlusion: updates mask (sets occluded pixels to 0), updates depth (sets to 0)
  - Photometric: only affects RGB, depth unchanged
  - Sensor noise: adds noise to depth, updates depth accordingly
  - BOP scene_gt/scene_camera remain unchanged (pose is still correct for visible parts)

Usage:
  python augment_industrial.py --dataset sell_Huhb3D-Test-Precision-v4 \
    --output sell_Huhb3D-Test-Precision-v4-aug \
    --aug-per-image 5 --seed 42
"""

import cv2
import numpy as np
import json
import argparse
import os
import sys
import shutil
from pathlib import Path
from copy import deepcopy


class IndustrialBackgroundGenerator:
    def __init__(self, width, height, seed=None):
        self.rng = np.random.RandomState(seed)
        self.width = width
        self.height = height
        self._cache = []

    def generate_concrete(self):
        bg = np.ones((self.height, self.width, 3), dtype=np.uint8) * 160
        noise = self.rng.randint(0, 40, (self.height, self.width, 3), dtype=np.uint8)
        bg = cv2.add(bg, noise)
        for _ in range(self.rng.randint(3, 8)):
            x1 = self.rng.randint(0, self.width)
            y1 = self.rng.randint(0, self.height)
            x2 = min(x1 + self.rng.randint(50, 300), self.width)
            y2 = min(y1 + self.rng.randint(2, 8), self.height)
            shade = self.rng.randint(80, 200)
            bg[y1:y2, x1:x2] = shade
        return bg

    def generate_metal_floor(self):
        bg = np.ones((self.height, self.width, 3), dtype=np.uint8) * 120
        noise = self.rng.randint(0, 25, (self.height, self.width, 3), dtype=np.uint8)
        bg = cv2.add(bg, noise)
        grid_color = self.rng.randint(90, 140)
        spacing = self.rng.randint(40, 80)
        for x in range(0, self.width, spacing):
            bg[:, x:x+1] = grid_color
        for y in range(0, self.height, spacing):
            bg[y:y+1, :] = grid_color
        return bg

    def generate_workshop(self):
        bg = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        upper_h = self.height * 2 // 3
        wall_color = self.rng.randint(140, 200, 3).astype(np.uint8)
        bg[:upper_h, :] = wall_color
        noise = self.rng.randint(0, 15, (upper_h, self.width, 3), dtype=np.uint8)
        bg[:upper_h] = cv2.add(bg[:upper_h], noise)
        floor_color = self.rng.randint(60, 120, 3).astype(np.uint8)
        bg[upper_h:, :] = floor_color
        return bg

    def generate_gradient(self):
        bg = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        base = self.rng.randint(30, 120, 3)
        for y in range(self.height):
            factor = 1.0 - 0.4 * (y / self.height)
            bg[y, :] = (base * factor).astype(np.uint8)
        noise = self.rng.randint(0, 10, bg.shape, dtype=np.uint8)
        bg = cv2.add(bg, noise)
        return bg

    def generate_random(self):
        generators = [
            self.generate_concrete,
            self.generate_metal_floor,
            self.generate_workshop,
            self.generate_gradient,
        ]
        gen = self.rng.choice(generators)
        return gen()


class OcclusionGenerator:
    def __init__(self, seed=None):
        self.rng = np.random.RandomState(seed)

    def generate_rect_occlusion(self, h, w, mask):
        obj_pixels = np.where(mask > 0)
        if len(obj_pixels[0]) == 0:
            return None
        min_y, max_y = obj_pixels[0].min(), obj_pixels[0].max()
        min_x, max_x = obj_pixels[1].min(), obj_pixels[1].max()

        obj_range_x = max_x - min_x
        obj_range_y = max_y - min_y
        if obj_range_x < 30 or obj_range_y < 30:
            return None

        occ_w = self.rng.randint(30, max(31, obj_range_x // 2))
        occ_h = self.rng.randint(30, max(31, obj_range_y // 2))

        x_high = max(min_x + 1, max_x - occ_w)
        y_high = max(min_y + 1, max_y - occ_h)
        occ_x = self.rng.randint(min_x, x_high)
        occ_y = self.rng.randint(min_y, y_high)

        occ_mask = np.zeros((h, w), dtype=np.uint8)
        occ_mask[occ_y:occ_y+occ_h, occ_x:occ_x+occ_w] = 255

        overlap = np.logical_and(mask > 0, occ_mask > 0)
        total_obj = max(mask.sum(), 1)
        overlap_ratio = overlap.sum() / total_obj
        if overlap.sum() < 50 or overlap_ratio > 0.5:
            return None

        shade = self.rng.randint(40, 200, 3).astype(np.uint8)
        occ_rgb = np.zeros((h, w, 3), dtype=np.uint8)
        occ_rgb[occ_mask > 0] = shade

        return occ_mask, occ_rgb

    def generate_irregular_occlusion(self, h, w, mask):
        obj_pixels = np.where(mask > 0)
        if len(obj_pixels[0]) == 0:
            return None
        center_y = int(np.mean(obj_pixels[0]))
        center_x = int(np.mean(obj_pixels[1]))

        n_pts = self.rng.randint(6, 12)
        angles = np.sort(self.rng.uniform(0, 2 * np.pi, n_pts))
        radii = self.rng.uniform(20, 80, n_pts)
        pts = np.column_stack([
            center_x + radii * np.cos(angles),
            center_y + radii * np.sin(angles)
        ]).astype(np.int32)

        occ_mask = np.zeros((h, w), dtype=np.uint8)
        cv2.fillPoly(occ_mask, [pts], 255)

        overlap = np.logical_and(mask > 0, occ_mask > 0)
        total_obj = max(mask.sum(), 1)
        overlap_ratio = overlap.sum() / total_obj
        if overlap.sum() < 50 or overlap_ratio > 0.5:
            return None

        shade = self.rng.randint(40, 200, 3).astype(np.uint8)
        occ_rgb = np.zeros((h, w, 3), dtype=np.uint8)
        occ_rgb[occ_mask > 0] = shade

        return occ_mask, occ_rgb

    def generate(self, h, w, mask):
        if self.rng.random() < 0.5:
            return self.generate_rect_occlusion(h, w, mask)
        else:
            return self.generate_irregular_occlusion(h, w, mask)


class PhotometricAugmentor:
    def __init__(self, seed=None):
        self.rng = np.random.RandomState(seed)

    def augment(self, rgb):
        rgb = rgb.astype(np.float32)

        brightness = self.rng.uniform(0.7, 1.3)
        rgb *= brightness

        contrast = self.rng.uniform(0.8, 1.2)
        mean = rgb.mean()
        rgb = (rgb - mean) * contrast + mean

        gamma = self.rng.uniform(0.7, 1.5)
        rgb = np.power(np.clip(rgb / 255.0, 0, 1), 1.0 / gamma) * 255.0

        color_shift = self.rng.uniform(-15, 15, 3).astype(np.float32)
        rgb += color_shift

        rgb = np.clip(rgb, 0, 255).astype(np.uint8)
        return rgb


class DepthNoiseSimulator:
    def __init__(self, seed=None):
        self.rng = np.random.RandomState(seed)

    def add_kinect_noise(self, depth, mask):
        depth_f = depth.astype(np.float64)
        h, w = depth.shape

        gaussian_std = self.rng.uniform(1.0, 5.0)
        noise = self.rng.normal(0, gaussian_std, (h, w))
        depth_f[mask > 0] += noise[mask > 0]

        quant_step = 0.5
        depth_f[mask > 0] = np.round(depth_f[mask > 0] / quant_step) * quant_step

        hole_prob = self.rng.uniform(0.001, 0.02)
        hole_mask = self.rng.random((h, w)) < hole_prob
        hole_mask = np.logical_and(hole_mask, mask > 0)
        depth_f[hole_mask] = 0

        flying_prob = self.rng.uniform(0.0005, 0.005)
        flying_mask = self.rng.random((h, w)) < flying_prob
        flying_mask = np.logical_and(flying_mask, mask > 0)
        flying_offset = self.rng.uniform(50, 200, flying_mask.sum())
        depth_f[flying_mask] += flying_offset

        edge_mask = np.zeros_like(mask, dtype=bool)
        if mask.any():
            kernel = np.ones((3, 3), dtype=np.uint8)
            dilated = cv2.dilate(mask, kernel, iterations=1)
            edge_mask = np.logical_and(dilated > 0, mask == 0)
            edge_mask = np.logical_and(edge_mask, depth_f > 0)
        depth_f[edge_mask] = 0

        depth_f = np.clip(depth_f, 0, 65535)
        result = depth_f.astype(np.uint16)
        result[(mask > 0) & (depth_f <= 0)] = 0

        return result


class MotionBlurSimulator:
    def __init__(self, seed=None):
        self.rng = np.random.RandomState(seed)

    def apply(self, rgb):
        kernel_size = self.rng.choice([0, 0, 0, 3, 5, 7])
        if kernel_size == 0:
            return rgb

        angle = self.rng.uniform(0, 180)
        kernel = np.zeros((kernel_size, kernel_size))
        mid = kernel_size // 2
        cos_a = np.cos(np.radians(angle))
        sin_a = np.sin(np.radians(angle))
        for i in range(kernel_size):
            offset = i - mid
            x = int(round(mid + offset * cos_a))
            y = int(round(mid + offset * sin_a))
            if 0 <= x < kernel_size and 0 <= y < kernel_size:
                kernel[y, x] = 1
        kernel /= kernel.sum() if kernel.sum() > 0 else 1

        result = cv2.filter2D(rgb, -1, kernel)
        return result


def augment_single_frame(rgb, depth, mask, mask_instance,
                         bg_gen, occ_gen, photo_aug, depth_noise, blur_sim,
                         rng, aug_id):
    h, w = rgb.shape[:2]
    obj_mask = (mask > 0).astype(np.uint8)

    aug_rgb = rgb.copy()
    aug_depth = depth.copy()
    aug_mask = mask.copy()
    aug_mask_instance = mask_instance.copy() if mask_instance is not None else mask.copy()

    aug_meta = {
        "aug_id": aug_id,
        "background": False,
        "occlusion": False,
        "occlusion_ratio": 0.0,
        "photometric": False,
        "depth_noise": False,
        "motion_blur": False,
    }

    if rng.random() < 0.8:
        bg = bg_gen.generate_random()
        bg_region = obj_mask == 0
        aug_rgb[bg_region] = bg[bg_region]
        aug_meta["background"] = True

    if rng.random() < 0.4:
        occ_result = occ_gen.generate(h, w, obj_mask)
        if occ_result is not None:
            occ_mask, occ_rgb = occ_result
            occ_on_obj = np.logical_and(obj_mask > 0, occ_mask > 0)
            aug_rgb[occ_mask > 0] = occ_rgb[occ_mask > 0]
            aug_depth[occ_on_obj] = 0
            aug_mask[occ_on_obj] = 0
            if aug_mask_instance is not None:
                aug_mask_instance[occ_on_obj] = 0
            total_obj = max(obj_mask.sum(), 1)
            aug_meta["occlusion"] = True
            aug_meta["occlusion_ratio"] = float(occ_on_obj.sum() / total_obj)

    if rng.random() < 0.7:
        aug_rgb = photo_aug.augment(aug_rgb)
        aug_meta["photometric"] = True

    if rng.random() < 0.5:
        aug_depth = depth_noise.add_kinect_noise(aug_depth, aug_mask)
        aug_meta["depth_noise"] = True

    if rng.random() < 0.3:
        aug_rgb = blur_sim.apply(aug_rgb)
        aug_meta["motion_blur"] = True

    return aug_rgb, aug_depth, aug_mask, aug_mask_instance, aug_meta


def process_object(obj_name, dataset_dir, output_dir, aug_per_image, seed):
    obj_dir = dataset_dir / obj_name
    out_obj_dir = output_dir / obj_name

    if not (obj_dir / "depth").exists():
        return 0

    rng = np.random.RandomState(seed + hash(obj_name) % 10000)

    bg_gen = IndustrialBackgroundGenerator(800, 600, seed=seed + 1)
    occ_gen = OcclusionGenerator(seed=seed + 2)
    photo_aug = PhotometricAugmentor(seed=seed + 3)
    depth_noise = DepthNoiseSimulator(seed=seed + 4)
    blur_sim = MotionBlurSimulator(seed=seed + 5)

    for subdir in ["rgb", "depth", "mask", "mask_instance"]:
        (out_obj_dir / subdir).mkdir(parents=True, exist_ok=True)

    rgb_files = sorted((obj_dir / "rgb").glob("frame_*.png"))
    total_aug = 0

    for rgb_path in rgb_files:
        stem = rgb_path.stem
        frame_id = stem.replace("frame_", "")
        depth_path = obj_dir / "depth" / f"depth_{frame_id}.png"
        mask_path = obj_dir / "mask" / f"mask_{frame_id}.png"
        inst_path = obj_dir / "mask_instance" / f"instance_{frame_id}.png"

        if not depth_path.exists() or not mask_path.exists():
            continue

        rgb = cv2.imread(str(rgb_path), cv2.IMREAD_COLOR)
        depth = cv2.imread(str(depth_path), cv2.IMREAD_UNCHANGED)
        mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
        mask_instance = None
        if inst_path.exists():
            mask_instance = cv2.imread(str(inst_path), cv2.IMREAD_UNCHANGED)

        if rgb is None or depth is None or mask is None:
            continue

        for aug_i in range(aug_per_image):
            aug_rgb, aug_depth, aug_mask, aug_mask_inst, aug_meta = augment_single_frame(
                rgb, depth, mask, mask_instance,
                bg_gen, occ_gen, photo_aug, depth_noise, blur_sim,
                rng, aug_i
            )

            aug_suffix = f"{frame_id}_aug{aug_i:03d}"

            cv2.imwrite(str(out_obj_dir / "rgb" / f"frame_{aug_suffix}.png"), aug_rgb)

            from PIL import Image as PILImage
            if aug_depth.dtype == np.uint16:
                pil_img = PILImage.fromarray(aug_depth, mode='I;16')
            else:
                pil_img = PILImage.fromarray(aug_depth.astype(np.uint16), mode='I;16')
            pil_img.save(str(out_obj_dir / "depth" / f"depth_{aug_suffix}.png"))

            cv2.imwrite(str(out_obj_dir / "mask" / f"mask_{aug_suffix}.png"), aug_mask)
            if aug_mask_inst is not None:
                cv2.imwrite(str(out_obj_dir / "mask_instance" / f"instance_{aug_suffix}.png"), aug_mask_inst)

            aug_meta["source_frame"] = int(frame_id)
            aug_meta["object"] = obj_name
            meta_path = out_obj_dir / "aug_metadata" / f"meta_{aug_suffix}.json"
            meta_path.parent.mkdir(parents=True, exist_ok=True)
            with open(meta_path, "w") as f:
                json.dump(aug_meta, f, indent=2)

            total_aug += 1

    for json_file in ["scene_camera.json", "scene_gt.json",
                       "coco_annotations.json", "coco_instance_annotations.json",
                       "camera_poses.json", "gt_6dof.json"]:
        src = obj_dir / json_file
        if src.exists():
            shutil.copy2(str(src), str(out_obj_dir / json_file))

    yolo_dir = obj_dir / "yolo_labels"
    if yolo_dir.exists():
        shutil.copytree(str(yolo_dir), str(out_obj_dir / "yolo_labels"),
                        dirs_exist_ok=True)

    legend = obj_dir / "label_legend.txt"
    if legend.exists():
        shutil.copy2(str(legend), str(out_obj_dir / "label_legend.txt"))

    return total_aug


def main():
    parser = argparse.ArgumentParser(description="Huhb3D Industrial Data Augmentation")
    parser.add_argument("--dataset", type=str,
                        default="sell_Huhb3D-Test-Precision-v4",
                        help="Source dataset directory")
    parser.add_argument("--output", type=str,
                        default="sell_Huhb3D-Test-Precision-v4-aug",
                        help="Output directory for augmented data")
    parser.add_argument("--aug-per-image", type=int, default=5,
                        help="Number of augmented versions per original image")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducibility")
    parser.add_argument("--objects", type=str, nargs="*", default=None,
                        help="Specific objects to augment (default: all)")
    args = parser.parse_args()

    dataset_dir = Path(args.dataset)
    output_dir = Path(args.output)

    if not dataset_dir.exists():
        print(f"[ERROR] Dataset not found: {dataset_dir}")
        sys.exit(1)

    if args.objects:
        objects = args.objects
    else:
        objects = sorted([d.name for d in dataset_dir.iterdir()
                          if d.is_dir() and (d / "depth").exists()])

    print("=" * 72)
    print("  Huhb3D Industrial Data Augmentation Pipeline")
    print("=" * 72)
    print(f"  Source:       {dataset_dir}")
    print(f"  Output:       {output_dir}")
    print(f"  Objects:      {len(objects)}")
    print(f"  Aug/image:    {args.aug_per_image}")
    print(f"  Seed:         {args.seed}")
    print(f"  Expected:     {len(objects)} x 10 x {args.aug_per_image} = "
          f"{len(objects) * 10 * args.aug_per_image} augmented images")
    print("=" * 72)

    output_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    for i, obj in enumerate(objects):
        print(f"  [{i+1}/{len(objects)}] Augmenting {obj}...", end=" ", flush=True)
        n = process_object(obj, dataset_dir, output_dir, args.aug_per_image, args.seed)
        total += n
        print(f"{n} images")

    print()
    print("=" * 72)
    print(f"  DONE: {total} augmented images generated")
    print(f"  Output: {output_dir}")
    print("=" * 72)

    print()
    print("  Augmentation types applied:")
    print("  - Background replacement (80% probability): concrete/metal/workshop/gradient")
    print("  - Random occlusion (40% probability): rectangular/irregular shapes")
    print("  - Photometric changes (70% probability): brightness/contrast/gamma/color")
    print("  - Depth sensor noise (50% probability): Kinect-style holes/flying pixels")
    print("  - Motion blur (30% probability): directional kernel")
    print()
    print("  GT consistency preserved:")
    print("  - BOP scene_gt/scene_camera: unchanged (pose still correct)")
    print("  - Mask: occluded pixels set to 0")
    print("  - Depth: occluded pixels set to 0, noise added where applicable")
    print("  - aug_metadata/: per-frame augmentation record")


if __name__ == "__main__":
    main()
