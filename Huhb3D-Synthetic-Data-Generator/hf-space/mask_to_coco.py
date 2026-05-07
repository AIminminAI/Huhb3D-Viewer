"""
mask_to_coco.py - Convert Huhb3D semantic masks to COCO JSON format
===================================================================

Usage:
    python mask_to_coco.py --input <run_directory> [--output coco_annotations.json]

This script reads the mask PNG images and label_legend.txt from a Huhb3D
synthetic data run directory, and produces a COCO-format JSON annotation
file that can be directly used by Detectron2, MMDetection, YOLOv8-seg, etc.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from collections import defaultdict

import numpy as np

try:
    from PIL import Image
except ImportError:
    print("ERROR: Pillow is required. Install with: pip install Pillow")
    sys.exit(1)


def parse_label_legend(legend_path):
    categories = []
    color_to_id = {}
    with open(legend_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split()
            if len(parts) >= 4:
                cat_id = int(parts[0])
                cat_name = parts[1]
                r, g, b = int(parts[2]), int(parts[3]), int(parts[4])
                categories.append({
                    "id": cat_id,
                    "name": cat_name,
                    "supercategory": "surface"
                })
                color_to_id[(r, g, b)] = cat_id
    return categories, color_to_id


def mask_to_binary_masks(mask_array, color_to_id):
    h, w, _ = mask_array.shape
    category_pixels = defaultdict(lambda: np.zeros((h, w), dtype=bool))

    for (r, g, b), cat_id in color_to_id.items():
        match = (mask_array[:, :, 0] == r) & (mask_array[:, :, 1] == g) & (mask_array[:, :, 2] == b)
        category_pixels[cat_id] = match

    return category_pixels


def binary_mask_to_rle(binary_mask):
    h, w = binary_mask.shape
    flat = binary_mask.flatten(order='F')
    runs = []
    prev = False
    start = 0
    for i, val in enumerate(flat):
        if val and not prev:
            start = i
            prev = True
        elif not val and prev:
            runs.append(i - start)
            prev = False
    if prev:
        runs.append(len(flat) - start)

    if len(runs) % 2 == 1:
        runs.append(0)

    return {"counts": runs, "size": [h, w]}


def binary_mask_to_polygon(binary_mask, tolerance=2.0):
    from PIL import Image as PILImage
    contours = []
    h, w = binary_mask.shape

    try:
        import cv2
        mask_uint8 = (binary_mask.astype(np.uint8)) * 255
        cnts, _ = cv2.findContours(mask_uint8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_TC89_L1)
        for cnt in cnts:
            if len(cnt) < 3:
                continue
            poly = cnt.flatten().tolist()
            if len(poly) >= 6:
                contours.append(poly)
    except ImportError:
        pass

    return contours


def convert_run_to_coco(run_dir, output_path=None):
    run_path = Path(run_dir)
    mask_dir = run_path / "mask"
    rgb_dir = run_path / "rgb"
    legend_path = run_path / "label_legend.txt"
    camera_poses_path = run_path / "camera_poses.json"

    if not mask_dir.exists():
        print(f"ERROR: mask directory not found: {mask_dir}")
        return False

    if not legend_path.exists():
        print(f"ERROR: label_legend.txt not found: {legend_path}")
        return False

    categories, color_to_id = parse_label_legend(legend_path)
    print(f"Loaded {len(categories)} categories from label_legend.txt")

    mask_files = sorted(mask_dir.glob("mask_*.png"))
    if not mask_files:
        print("ERROR: No mask files found")
        return False

    print(f"Found {len(mask_files)} mask files")

    coco_categories = []
    for cat in categories:
        coco_categories.append({
            "id": cat["id"],
            "name": cat["name"],
            "supercategory": cat.get("supercategory", "surface")
        })

    coco_images = []
    coco_annotations = []
    annotation_id = 1

    camera_poses = {}
    if camera_poses_path.exists():
        with open(camera_poses_path, 'r') as f:
            camera_poses = json.load(f)
        print(f"Loaded camera poses for {len(camera_poses)} frames")

    for idx, mask_file in enumerate(mask_files):
        frame_num = mask_file.stem.replace("mask_", "")
        rgb_file = rgb_dir / f"frame_{frame_num}.png"

        mask_img = Image.open(mask_file).convert("RGB")
        mask_array = np.array(mask_img)
        img_h, img_w = mask_array.shape[:2]

        image_info = {
            "id": idx + 1,
            "file_name": f"rgb/frame_{frame_num}.png",
            "width": img_w,
            "height": img_h,
        }

        if str(idx) in camera_poses or str(idx + 1) in camera_poses:
            pose_key = str(idx) if str(idx) in camera_poses else str(idx + 1)
            pose = camera_poses[pose_key]
            image_info["camera_position"] = pose.get("position", [])
            image_info["camera_rotation"] = pose.get("rotation", [])
            if "view_matrix" in pose:
                image_info["view_matrix"] = pose["view_matrix"]
            if "projection_matrix" in pose:
                image_info["projection_matrix"] = pose["projection_matrix"]

        coco_images.append(image_info)

        category_pixels = mask_to_binary_masks(mask_array, color_to_id)

        for cat_id, binary_mask in category_pixels.items():
            pixel_count = binary_mask.sum()
            if pixel_count < 10:
                continue

            rle = binary_mask_to_rle(binary_mask)
            area = int(pixel_count)

            bbox_x = np.where(binary_mask.any(axis=0))[0]
            bbox_y = np.where(binary_mask.any(axis=1))[0]
            if len(bbox_x) == 0 or len(bbox_y) == 0:
                continue
            x_min, x_max = int(bbox_x.min()), int(bbox_x.max())
            y_min, y_max = int(bbox_y.min()), int(bbox_y.max())
            bbox_w = x_max - x_min + 1
            bbox_h = y_max - y_min + 1

            annotation = {
                "id": annotation_id,
                "image_id": idx + 1,
                "category_id": cat_id,
                "segmentation": rle,
                "area": area,
                "bbox": [x_min, y_min, bbox_w, bbox_h],
                "iscrowd": 0,
            }

            try:
                polygons = binary_mask_to_polygon(binary_mask)
                if polygons:
                    annotation["segmentation_polygon"] = polygons
            except Exception:
                pass

            coco_annotations.append(annotation)
            annotation_id += 1

        if (idx + 1) % 20 == 0:
            print(f"  Processed {idx + 1}/{len(mask_files)} masks, {len(coco_annotations)} annotations so far")

    coco_json = {
        "info": {
            "description": "Huhb3D Synthetic Data - COCO Format",
            "version": "1.0",
            "contributor": "Huhb3D Synthetic Data Generator",
        },
        "licenses": [{"id": 1, "name": "AGPL-3.0", "url": "https://www.gnu.org/licenses/agpl-3.0"}],
        "categories": coco_categories,
        "images": coco_images,
        "annotations": coco_annotations,
    }

    if output_path is None:
        output_path = str(run_path / "coco_annotations.json")

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(coco_json, f, indent=2, ensure_ascii=False)

    print(f"\n✅ COCO JSON saved to: {output_path}")
    print(f"   Images: {len(coco_images)}")
    print(f"   Annotations: {len(coco_annotations)}")
    print(f"   Categories: {len(coco_categories)}")

    return True


def convert_to_yolo(run_dir, output_dir=None):
    run_path = Path(run_dir)
    mask_dir = run_path / "mask"
    legend_path = run_path / "label_legend.txt"

    if not mask_dir.exists() or not legend_path.exists():
        print("ERROR: mask directory or label_legend.txt not found")
        return False

    categories, color_to_id = parse_label_legend(legend_path)
    cat_id_to_yolo_id = {}
    yolo_names = []
    for yolo_id, cat in enumerate(categories):
        cat_id_to_yolo_id[cat["id"]] = yolo_id
        yolo_names.append(cat["name"])

    if output_dir is None:
        output_dir = str(run_path / "yolo_labels")
    output_path = Path(output_dir)
    labels_dir = output_path / "labels"
    labels_dir.mkdir(parents=True, exist_ok=True)

    mask_files = sorted(mask_dir.glob("mask_*.png"))

    for idx, mask_file in enumerate(mask_files):
        frame_num = mask_file.stem.replace("mask_", "")
        mask_img = Image.open(mask_file).convert("RGB")
        mask_array = np.array(mask_img)
        img_h, img_w = mask_array.shape[:2]

        category_pixels = mask_to_binary_masks(mask_array, color_to_id)

        yolo_lines = []
        for cat_id, binary_mask in category_pixels.items():
            pixel_count = binary_mask.sum()
            if pixel_count < 10:
                continue

            yolo_id = cat_id_to_yolo_id.get(cat_id, 0)

            bbox_x = np.where(binary_mask.any(axis=0))[0]
            bbox_y = np.where(binary_mask.any(axis=1))[0]
            if len(bbox_x) == 0 or len(bbox_y) == 0:
                continue
            x_min, x_max = int(bbox_x.min()), int(bbox_x.max())
            y_min, y_max = int(bbox_y.min()), int(bbox_y.max())

            cx = ((x_min + x_max) / 2.0) / img_w
            cy = ((y_min + y_max) / 2.0) / img_h
            bw = (x_max - x_min + 1) / img_w
            bh = (y_max - y_min + 1) / img_h

            yolo_lines.append(f"{yolo_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")

        label_file = labels_dir / f"frame_{frame_num}.txt"
        with open(label_file, 'w') as f:
            f.write("\n".join(yolo_lines))

    names_file = output_path / "classes.txt"
    with open(names_file, 'w') as f:
        f.write("\n".join(yolo_names))

    data_yaml = output_path / "data.yaml"
    with open(data_yaml, 'w') as f:
        f.write(f"path: {run_path.resolve()}\n")
        f.write("train: rgb\n")
        f.write("val: rgb\n")
        f.write(f"names: {yolo_names}\n")
        f.write(f"nc: {len(yolo_names)}\n")

    print(f"\n✅ YOLO labels saved to: {output_dir}")
    print(f"   Labels: {len(mask_files)} files")
    print(f"   Classes: {yolo_names}")

    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert Huhb3D masks to COCO JSON / YOLO format")
    parser.add_argument("--input", required=True, help="Path to run directory (e.g., streamlit_output/run_xxx)")
    parser.add_argument("--output", default=None, help="Output COCO JSON path (default: <input>/coco_annotations.json)")
    parser.add_argument("--yolo", action="store_true", help="Also generate YOLO format labels")
    args = parser.parse_args()

    convert_run_to_coco(args.input, args.output)

    if args.yolo:
        convert_to_yolo(args.input)
