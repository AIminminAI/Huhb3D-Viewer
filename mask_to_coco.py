"""
mask_to_coco.py - Convert Huhb3D semantic/instance masks to COCO JSON format
=============================================================================

Usage:
    python mask_to_coco.py --input <run_directory> [--output coco_annotations.json]
    python mask_to_coco.py --input <run_directory> --instance

This script reads the mask PNG images and label_legend.txt from a Huhb3D
synthetic data run directory, and produces a COCO-format JSON annotation
file that can be directly used by Detectron2, MMDetection, YOLOv8-seg, etc.

Supports both semantic segmentation and instance segmentation masks.
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


def instance_mask_to_binary_masks(mask_array):
    h, w, _ = mask_array.shape
    instance_pixels = {}

    unique_colors = np.unique(mask_array.reshape(-1, 3), axis=0)
    for color in unique_colors:
        r, g, b = int(color[0]), int(color[1]), int(color[2])
        if r == 0 and g == 0 and b == 0:
            continue
        instance_id = r
        feature_type_id = g
        feature_index = b
        match = (mask_array[:, :, 0] == r) & (mask_array[:, :, 1] == g) & (mask_array[:, :, 2] == b)
        key = (instance_id, feature_type_id, feature_index)
        instance_pixels[key] = match

    return instance_pixels


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
    contours = []
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


def load_manifest(manifest_path):
    if not manifest_path.exists():
        return None
    with open(manifest_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def convert_instance_run_to_coco(run_dir, output_path=None):
    run_path = Path(run_dir)
    instance_mask_dir = run_path / "mask_instance"
    semantic_mask_dir = run_path / "mask"
    rgb_dir = run_path / "rgb"
    legend_path = run_path / "label_legend.txt"
    manifest_path = run_path / "manifest.json"
    camera_poses_path = run_path / "camera_poses.json"

    if not instance_mask_dir.exists():
        print(f"ERROR: instance mask directory not found: {instance_mask_dir}")
        return False

    if not legend_path.exists():
        print(f"ERROR: label_legend.txt not found: {legend_path}")
        return False

    categories, _ = parse_label_legend(legend_path)
    cat_id_to_name = {cat["id"]: cat["name"] for cat in categories}
    print(f"Loaded {len(categories)} categories from label_legend.txt")

    manifest = load_manifest(manifest_path)
    object_info = {}
    if manifest and "objects" in manifest:
        for obj in manifest["objects"]:
            object_info[obj["instance_id"]] = obj
        print(f"Loaded manifest with {len(object_info)} objects")

    mask_files = sorted(instance_mask_dir.glob("instance_*.png"))
    if not mask_files:
        print("ERROR: No instance mask files found")
        return False

    print(f"Found {len(mask_files)} instance mask files")

    instance_categories = []
    instance_cat_id_map = {}
    next_cat_id = 1

    if manifest and "objects" in manifest:
        for obj in manifest["objects"]:
            obj_name = obj["name"]
            obj_inst_id = obj["instance_id"]
            if obj_inst_id not in instance_cat_id_map:
                instance_cat_id_map[obj_inst_id] = next_cat_id
                instance_categories.append({
                    "id": next_cat_id,
                    "name": obj_name,
                    "supercategory": "object"
                })
                next_cat_id += 1

            if "features" in obj:
                for feat in obj["features"]:
                    feat_type = feat["feature_type"]
                    feat_type_id = feat["feature_type_id"]
                    for inst_idx in feat.get("instance_ids", [0]):
                        key = (obj_inst_id, feat_type_id, inst_idx)
                        if key not in instance_cat_id_map:
                            instance_cat_id_map[key] = next_cat_id
                            instance_categories.append({
                                "id": next_cat_id,
                                "name": f"{obj_name}_{feat_type}_{inst_idx}",
                                "supercategory": feat_type
                            })
                            next_cat_id += 1

    if not instance_categories:
        instance_categories.append({"id": 1, "name": "object", "supercategory": "object"})

    coco_images = []
    coco_annotations = []
    annotation_id = 1

    camera_poses = {}
    if camera_poses_path.exists():
        with open(camera_poses_path, 'r') as f:
            camera_poses = json.load(f)
        print(f"Loaded camera poses for {len(camera_poses)} frames")

    for idx, mask_file in enumerate(mask_files):
        frame_num = mask_file.stem.replace("instance_", "")
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
            if "scene_objects" in pose:
                image_info["scene_objects"] = pose["scene_objects"]

        coco_images.append(image_info)

        instance_pixels = instance_mask_to_binary_masks(mask_array)

        for (inst_id, feat_type_id, feat_idx), binary_mask in instance_pixels.items():
            pixel_count = binary_mask.sum()
            if pixel_count < 10:
                continue

            key = (inst_id, feat_type_id, feat_idx)
            coco_cat_id = instance_cat_id_map.get(key, 1)

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
                "category_id": coco_cat_id,
                "segmentation": rle,
                "area": area,
                "bbox": [x_min, y_min, bbox_w, bbox_h],
                "iscrowd": 0,
                "instance_id": inst_id,
                "feature_type_id": feat_type_id,
                "feature_index": feat_idx,
            }

            if feat_type_id in cat_id_to_name:
                annotation["feature_type_name"] = cat_id_to_name[feat_type_id]

            if inst_id in object_info:
                annotation["object_name"] = object_info[inst_id]["name"]

            try:
                polygons = binary_mask_to_polygon(binary_mask)
                if polygons:
                    annotation["segmentation_polygon"] = polygons
            except Exception:
                pass

            coco_annotations.append(annotation)
            annotation_id += 1

        if (idx + 1) % 20 == 0:
            print(f"  Processed {idx + 1}/{len(mask_files)} instance masks, {len(coco_annotations)} annotations")

    coco_json = {
        "info": {
            "description": "Huhb3D Synthetic Data - COCO Instance Segmentation Format",
            "version": "2.0",
            "contributor": "Huhb3D Synthetic Data Generator",
        },
        "licenses": [{"id": 1, "name": "AGPL-3.0", "url": "https://www.gnu.org/licenses/agpl-3.0"}],
        "categories": instance_categories,
        "images": coco_images,
        "annotations": coco_annotations,
    }

    if output_path is None:
        output_path = str(run_path / "coco_instance_annotations.json")

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(coco_json, f, indent=2, ensure_ascii=False)

    print(f"\n✅ COCO Instance JSON saved to: {output_path}")
    print(f"   Images: {len(coco_images)}")
    print(f"   Annotations: {len(coco_annotations)}")
    print(f"   Instance Categories: {len(instance_categories)}")

    return True


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
    seg_labels_dir = output_path / "seg_labels"
    labels_dir.mkdir(parents=True, exist_ok=True)
    seg_labels_dir.mkdir(parents=True, exist_ok=True)

    mask_files = sorted(mask_dir.glob("mask_*.png"))

    for idx, mask_file in enumerate(mask_files):
        frame_num = mask_file.stem.replace("mask_", "")
        mask_img = Image.open(mask_file).convert("RGB")
        mask_array = np.array(mask_img)
        img_h, img_w = mask_array.shape[:2]

        category_pixels = mask_to_binary_masks(mask_array, color_to_id)

        yolo_lines = []
        yolo_seg_lines = []
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

            try:
                polygons = binary_mask_to_polygon(binary_mask)
                if polygons:
                    seg_parts = [f"{yolo_id}"]
                    for poly in polygons:
                        norm_pts = []
                        for pi in range(0, len(poly), 2):
                            px = poly[pi] / img_w
                            py = poly[pi + 1] / img_h
                            norm_pts.append(f"{px:.6f}")
                            norm_pts.append(f"{py:.6f}")
                        seg_parts.extend(norm_pts)
                    yolo_seg_lines.append(" ".join(seg_parts))
            except Exception:
                pass

        label_file = labels_dir / f"frame_{frame_num}.txt"
        with open(label_file, 'w') as f:
            f.write("\n".join(yolo_lines))

        seg_label_file = seg_labels_dir / f"frame_{frame_num}.txt"
        with open(seg_label_file, 'w') as f:
            f.write("\n".join(yolo_seg_lines))

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
    print(f"   BBox labels: {labels_dir} ({len(mask_files)} files)")
    print(f"   Seg labels:  {seg_labels_dir} ({len(mask_files)} files)")
    print(f"   Classes: {yolo_names}")

    return True


def convert_instance_to_yolo(run_dir, output_dir=None):
    run_path = Path(run_dir)
    instance_mask_dir = run_path / "mask_instance"
    legend_path = run_path / "label_legend.txt"
    manifest_path = run_path / "manifest.json"

    if not instance_mask_dir.exists():
        print(f"ERROR: instance mask directory not found: {instance_mask_dir}")
        return False

    categories, _ = parse_label_legend(legend_path) if legend_path.exists() else ([], {})
    cat_id_to_name = {cat["id"]: cat["name"] for cat in categories}

    manifest = load_manifest(manifest_path)

    yolo_names = ["background"]
    inst_cat_to_yolo = {}

    if manifest and "objects" in manifest:
        for obj in manifest["objects"]:
            obj_name = obj["name"]
            inst_id = obj["instance_id"]
            key = f"obj_{inst_id}"
            if key not in inst_cat_to_yolo:
                inst_cat_to_yolo[key] = len(yolo_names)
                yolo_names.append(obj_name)
            if "features" in obj:
                for feat in obj["features"]:
                    feat_type = feat["feature_type"]
                    feat_type_id = feat["feature_type_id"]
                    fkey = f"feat_{feat_type_id}"
                    if fkey not in inst_cat_to_yolo:
                        inst_cat_to_yolo[fkey] = len(yolo_names)
                        yolo_names.append(feat_type)
    else:
        for cat in categories:
            if cat["id"] not in [0, 7]:
                inst_cat_to_yolo[str(cat["id"])] = len(yolo_names)
                yolo_names.append(cat["name"])

    if output_dir is None:
        output_dir = str(run_path / "yolo_instance_labels")
    output_path = Path(output_dir)
    labels_dir = output_path / "labels"
    labels_dir.mkdir(parents=True, exist_ok=True)

    mask_files = sorted(instance_mask_dir.glob("instance_*.png"))

    for idx, mask_file in enumerate(mask_files):
        frame_num = mask_file.stem.replace("instance_", "")
        mask_img = Image.open(mask_file).convert("RGB")
        mask_array = np.array(mask_img)
        img_h, img_w = mask_array.shape[:2]

        instance_pixels = instance_mask_to_binary_masks(mask_array)

        yolo_lines = []
        for (inst_id, feat_type_id, feat_idx), binary_mask in instance_pixels.items():
            pixel_count = binary_mask.sum()
            if pixel_count < 10:
                continue

            fkey = f"feat_{feat_type_id}"
            yolo_id = inst_cat_to_yolo.get(fkey, inst_cat_to_yolo.get(f"obj_{inst_id}", 0))

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

    print(f"\n✅ YOLO instance labels saved to: {output_dir}")
    print(f"   Labels: {len(mask_files)} files")
    print(f"   Classes: {yolo_names}")

    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert Huhb3D masks to COCO JSON / YOLO format")
    parser.add_argument("--input", required=True, help="Path to run directory (e.g., streamlit_output/run_xxx)")
    parser.add_argument("--output", default=None, help="Output COCO JSON path (default: <input>/coco_annotations.json)")
    parser.add_argument("--yolo", action="store_true", help="Also generate YOLO format labels")
    parser.add_argument("--yolo-instance", action="store_true", help="Generate YOLO instance segmentation labels")
    parser.add_argument("--instance", action="store_true", help="Convert instance segmentation masks instead of semantic")
    args = parser.parse_args()

    if args.instance:
        convert_instance_run_to_coco(args.input, args.output)
    else:
        convert_run_to_coco(args.input, args.output)

    if args.yolo:
        convert_to_yolo(args.input)

    if args.yolo_instance:
        convert_instance_to_yolo(args.input)
