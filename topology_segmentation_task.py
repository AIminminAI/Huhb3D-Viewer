import json
import os
import struct
import numpy as np
from pathlib import Path
from collections import OrderedDict

try:
    import cv2
except ImportError:
    cv2 = None
    print("WARNING: opencv-python not installed. Install with: pip install opencv-python")

try:
    import torch
    from torch.utils.data import Dataset
except ImportError:
    torch = None
    Dataset = object
    print("WARNING: PyTorch not installed. Install with: pip install torch torchvision")

try:
    from torchvision import transforms
except ImportError:
    transforms = None

CATEGORY_NAMES = OrderedDict([
    (0, "FreeSurface"),
    (1, "HorizontalPlane"),
    (2, "LateralPlane_X"),
    (3, "LateralPlane_Z"),
    (4, "NearHorizontal"),
    (5, "NearLateral_X"),
    (6, "NearLateral_Z"),
    (7, "Degenerate"),
    (8, "ConvexFeature_Bolt"),
    (9, "ConcaveFeature_Hole"),
    (10, "Flange"),
    (11, "Boss"),
    (12, "Chamfer"),
    (13, "Fillet"),
    (14, "SphericalSurface"),
    (255, "Background"),
])

CATEGORY_COLORS = {
    0: (127, 127, 127),
    1: (0, 0, 255),
    2: (0, 255, 0),
    3: (255, 0, 0),
    4: (255, 255, 0),
    5: (255, 0, 255),
    6: (0, 255, 255),
    7: (255, 127, 0),
    8: (200, 50, 50),
    9: (50, 50, 200),
    10: (200, 150, 50),
    11: (150, 50, 200),
    12: (100, 200, 100),
    13: (200, 100, 200),
    14: (100, 200, 200),
    255: (0, 0, 0),
}

NUM_CLASSES = 16
IGNORE_INDEX = 255
IMAGE_WIDTH = 800
IMAGE_HEIGHT = 600


def parse_stl_binary(stl_path):
    with open(stl_path, 'rb') as f:
        header = f.read(80)
    if header.lstrip().lower().startswith(b'solid'):
        return _parse_stl_ascii(stl_path)
    triangles = []
    with open(stl_path, 'rb') as f:
        header = f.read(80)
        num_triangles_bytes = f.read(4)
        if len(num_triangles_bytes) < 4:
            return _parse_stl_ascii(stl_path)
        num_triangles = struct.unpack('<I', num_triangles_bytes)[0]
        for _ in range(num_triangles):
            data = f.read(50)
            if len(data) < 50:
                break
            nx, ny, nz = struct.unpack('<fff', data[0:12])
            v1 = struct.unpack('<fff', data[12:24])
            v2 = struct.unpack('<fff', data[24:36])
            v3 = struct.unpack('<fff', data[36:48])
            attr = struct.unpack('<H', data[48:50])[0]
            triangles.append({
                "normal": [nx, ny, nz],
                "v1": list(v1),
                "v2": list(v2),
                "v3": list(v3),
            })
    return triangles


def _parse_stl_ascii(stl_path):
    triangles = []
    with open(stl_path, 'r') as f:
        lines = f.readlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('facet normal'):
            parts = line.split()
            nx, ny, nz = float(parts[2]), float(parts[3]), float(parts[4])
            verts = []
            i += 1
            while i < len(lines):
                vline = lines[i].strip()
                if vline.startswith('vertex'):
                    vp = vline.split()
                    verts.append([float(vp[1]), float(vp[2]), float(vp[3])])
                elif vline.startswith('endfacet'):
                    break
                i += 1
            if len(verts) == 3:
                triangles.append({
                    "normal": [nx, ny, nz],
                    "v1": verts[0],
                    "v2": verts[1],
                    "v3": verts[2],
                })
        i += 1
    return triangles


def load_topology_labels(json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data


def project_point_opengl(point_3d, view_matrix, proj_matrix, width, height):
    p = np.array([point_3d[0], point_3d[1], point_3d[2], 1.0], dtype=np.float64)
    vm = np.array(view_matrix, dtype=np.float64).reshape(4, 4)
    pm = np.array(proj_matrix, dtype=np.float64).reshape(4, 4)
    p_view = vm @ p
    p_clip = pm @ p_view
    if p_clip[3] <= 1e-6:
        return None, p_view[2]
    ndc_x = p_clip[0] / p_clip[3]
    ndc_y = p_clip[1] / p_clip[3]
    screen_x = (ndc_x * 0.5 + 0.5) * width
    screen_y = (1.0 - (ndc_y * 0.5 + 0.5)) * height
    return (int(round(screen_x)), int(round(screen_y))), p_view[2]


def generate_topology_gt_gl(triangles, triangle_labels, view_matrix, proj_matrix,
                            width=IMAGE_WIDTH, height=IMAGE_HEIGHT):
    if cv2 is None:
        raise RuntimeError("OpenCV is required for generate_topology_gt")

    seg_map = np.full((height, width), IGNORE_INDEX, dtype=np.uint8)
    depth_buffer = np.full((height, width), np.inf, dtype=np.float64)

    tri_depths = []
    for tri, label in zip(triangles, triangle_labels):
        v1 = np.array(tri["v1"], dtype=np.float64)
        v2 = np.array(tri["v2"], dtype=np.float64)
        v3 = np.array(tri["v3"], dtype=np.float64)
        center = (v1 + v2 + v3) / 3.0
        pt, d = project_point_opengl(center, view_matrix, proj_matrix, width, height)
        if pt is not None:
            tri_depths.append((d, tri, label))
        else:
            tri_depths.append((float('inf'), tri, label))

    tri_depths.sort(key=lambda x: x[0])

    for _, tri, label in tri_depths:
        pts_2d = []
        depths = []
        skip = False
        for vk in ("v1", "v2", "v3"):
            pt, d = project_point_opengl(tri[vk], view_matrix, proj_matrix, width, height)
            if pt is None:
                skip = True
                break
            pts_2d.append(pt)
            depths.append(d)
        if skip:
            continue

        pts_arr = np.array(pts_2d, dtype=np.int32)
        cv2.fillPoly(seg_map, [pts_arr], label)

    return seg_map


def project_point_to_image(point_3d, cam_K, cam_R_w2c, cam_t_w2c):
    p = np.array(point_3d, dtype=np.float64)
    R = np.array(cam_R_w2c, dtype=np.float64).reshape(3, 3)
    t = np.array(cam_t_w2c, dtype=np.float64).reshape(3, 1)
    K = np.array(cam_K, dtype=np.float64).reshape(3, 3)
    p_cam = R @ p.reshape(3, 1) + t
    if p_cam[2, 0] <= 0:
        return None, p_cam[2, 0]
    p_pix = K @ p_cam
    px = p_pix[0, 0] / p_pix[2, 0]
    py = p_pix[1, 0] / p_pix[2, 0]
    depth = p_cam[2, 0]
    return (int(round(px)), int(round(py))), depth


def generate_topology_gt(triangles, triangle_labels, cam_K, cam_R_w2c, cam_t_w2c,
                         width=IMAGE_WIDTH, height=IMAGE_HEIGHT):
    if cv2 is None:
        raise RuntimeError("OpenCV is required for generate_topology_gt")

    seg_map = np.full((height, width), IGNORE_INDEX, dtype=np.uint8)
    depth_buffer = np.full((height, width), np.inf, dtype=np.float64)

    tri_depths = []
    for tri, label in zip(triangles, triangle_labels):
        v1 = np.array(tri["v1"], dtype=np.float64)
        v2 = np.array(tri["v2"], dtype=np.float64)
        v3 = np.array(tri["v3"], dtype=np.float64)
        center = (v1 + v2 + v3) / 3.0
        R = np.array(cam_R_w2c, dtype=np.float64).reshape(3, 3)
        t = np.array(cam_t_w2c, dtype=np.float64).reshape(3, 1)
        p_cam = R @ center.reshape(3, 1) + t
        avg_depth = p_cam[2, 0]
        tri_depths.append((avg_depth, tri, label))

    tri_depths.sort(key=lambda x: -x[0])

    for avg_depth, tri, label in tri_depths:
        pts_2d = []
        depths = []
        skip = False
        for vk in ("v1", "v2", "v3"):
            pt, d = project_point_to_image(tri[vk], cam_K, cam_R_w2c, cam_t_w2c)
            if pt is None:
                skip = True
                break
            pts_2d.append(pt)
            depths.append(d)
        if skip:
            continue
        if any(d <= 0 for d in depths):
            continue

        pts_arr = np.array(pts_2d, dtype=np.int32)
        cv2.fillPoly(seg_map, [pts_arr], label)

    return seg_map


def generate_topology_gt_for_view(stl_path, labels_json_path, cam_K, cam_R_w2c, cam_t_w2c,
                                  width=IMAGE_WIDTH, height=IMAGE_HEIGHT):
    triangles = parse_stl_binary(stl_path)
    labels_data = load_topology_labels(labels_json_path)
    triangle_labels = labels_data["triangle_labels"]
    if len(triangles) != len(triangle_labels):
        if len(labels_data.get("faces", [])) > 0:
            triangle_labels_extended = []
            for face in labels_data["faces"]:
                start = face["triangle_start"]
                count = face["triangle_count"]
                cat_id = face["category_id"]
                for _ in range(count):
                    triangle_labels_extended.append(cat_id)
            triangle_labels = triangle_labels_extended
        else:
            min_len = min(len(triangles), len(triangle_labels))
            triangles = triangles[:min_len]
            triangle_labels = triangle_labels[:min_len]

    return generate_topology_gt(triangles, triangle_labels, cam_K, cam_R_w2c, cam_t_w2c, width, height)


def generate_topology_gt_for_view_gl(stl_path, labels_json_path, view_matrix, proj_matrix,
                                     width=IMAGE_WIDTH, height=IMAGE_HEIGHT):
    triangles = parse_stl_binary(stl_path)
    labels_data = load_topology_labels(labels_json_path)
    triangle_labels = labels_data["triangle_labels"]
    if len(triangles) != len(triangle_labels):
        if len(labels_data.get("faces", [])) > 0:
            triangle_labels_extended = []
            for face in labels_data["faces"]:
                start = face["triangle_start"]
                count = face["triangle_count"]
                cat_id = face["category_id"]
                for _ in range(count):
                    triangle_labels_extended.append(cat_id)
            triangle_labels = triangle_labels_extended
        else:
            min_len = min(len(triangles), len(triangle_labels))
            triangles = triangles[:min_len]
            triangle_labels = triangle_labels[:min_len]

    return generate_topology_gt_gl(triangles, triangle_labels, view_matrix, proj_matrix, width, height)


def compute_miou(pred, target, num_classes=NUM_CLASSES, ignore_index=IGNORE_INDEX):
    valid = target != ignore_index
    pred_valid = pred[valid]
    target_valid = target[valid]
    iou_per_class = []
    for cls in range(num_classes):
        pred_cls = pred_valid == cls
        target_cls = target_valid == cls
        intersection = np.logical_and(pred_cls, target_cls).sum()
        union = np.logical_or(pred_cls, target_cls).sum()
        if union == 0:
            continue
        iou_per_class.append(intersection / union)
    if len(iou_per_class) == 0:
        return 0.0
    return float(np.mean(iou_per_class))


def compute_per_class_iou(pred, target, num_classes=NUM_CLASSES, ignore_index=IGNORE_INDEX):
    valid = target != ignore_index
    pred_valid = pred[valid]
    target_valid = target[valid]
    results = {}
    for cls in range(num_classes):
        pred_cls = pred_valid == cls
        target_cls = target_valid == cls
        intersection = np.logical_and(pred_cls, target_cls).sum()
        union = np.logical_or(pred_cls, target_cls).sum()
        if union == 0:
            results[cls] = None
        else:
            results[cls] = float(intersection / union)
    return results


def compute_pixel_accuracy(pred, target, ignore_index=IGNORE_INDEX):
    valid = target != ignore_index
    pred_valid = pred[valid]
    target_valid = target[valid]
    if len(target_valid) == 0:
        return 0.0
    return float((pred_valid == target_valid).sum() / len(target_valid))


def compute_fw_iou(pred, target, num_classes=NUM_CLASSES, ignore_index=IGNORE_INDEX):
    valid = target != ignore_index
    pred_valid = pred[valid]
    target_valid = target[valid]
    total_pixels = len(target_valid)
    if total_pixels == 0:
        return 0.0
    fw_iou = 0.0
    for cls in range(num_classes):
        pred_cls = pred_valid == cls
        target_cls = target_valid == cls
        intersection = np.logical_and(pred_cls, target_cls).sum()
        union = np.logical_or(pred_cls, target_cls).sum()
        if union > 0:
            cls_count = target_cls.sum()
            fw_iou += (cls_count / total_pixels) * (intersection / union)
    return float(fw_iou)


def evaluate_segmentation(pred, target, num_classes=NUM_CLASSES, ignore_index=IGNORE_INDEX):
    miou = compute_miou(pred, target, num_classes, ignore_index)
    per_class = compute_per_class_iou(pred, target, num_classes, ignore_index)
    pixel_acc = compute_pixel_accuracy(pred, target, ignore_index)
    fw_iou = compute_fw_iou(pred, target, num_classes, ignore_index)
    return {
        "mIoU": miou,
        "per_class_IoU": per_class,
        "pixel_accuracy": pixel_acc,
        "frequency_weighted_IoU": fw_iou,
    }


class TopologySegmentationDataset(Dataset):
    def __init__(self, dataset_dir, split="train", train_ratio=0.8,
                 target_size=(400, 300), augment=True):
        if torch is None:
            raise RuntimeError("PyTorch is required. Install with: pip install torch torchvision")

        self.dataset_dir = Path(dataset_dir)
        self.split = split
        self.target_size = target_size
        self.augment = augment and (split == "train")
        self.samples = []

        self._scan_dataset()
        total = len(self.samples)
        split_idx = int(total * train_ratio)
        if split == "train":
            self.samples = self.samples[:split_idx]
        else:
            self.samples = self.samples[split_idx:]

        self.color_jitter = transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3, hue=0.1) if transforms else None

    def _scan_dataset(self):
        if not self.dataset_dir.exists():
            print(f"WARNING: Dataset directory not found: {self.dataset_dir}")
            return

        for obj_dir in sorted(self.dataset_dir.iterdir()):
            if not obj_dir.is_dir():
                continue
            rgb_dir = obj_dir / "rgb"
            depth_dir = obj_dir / "depth"
            topology_dir = obj_dir / "topology_hd"
            if not topology_dir.exists():
                topology_dir = obj_dir / "topology"
            scene_camera_path = obj_dir / "scene_camera.json"
            camera_poses_path = obj_dir / "camera_poses.json"

            if not rgb_dir.exists():
                continue

            stl_path = topology_dir / "tessellated.stl" if topology_dir.exists() else None
            labels_json_path = topology_dir / "topology_labels.json" if topology_dir.exists() else None

            camera_data = None
            use_gl = False
            if camera_poses_path.exists():
                with open(camera_poses_path, 'r') as f:
                    camera_data = json.load(f)
                use_gl = True
            elif scene_camera_path.exists():
                with open(scene_camera_path, 'r') as f:
                    camera_data = json.load(f)

            rgb_files = sorted(rgb_dir.glob("frame_*.png"))
            for rgb_path in rgb_files:
                frame_id = rgb_path.stem.replace("frame_", "")
                depth_path = depth_dir / f"depth_{frame_id}.png" if depth_dir.exists() else None
                depth_npy_path = depth_dir / f"depth_{frame_id}.npy" if depth_dir.exists() else None

                if depth_path is None or not depth_path.exists():
                    if depth_npy_path is not None and depth_npy_path.exists():
                        depth_path = depth_npy_path
                    else:
                        continue

                cam_K = None
                cam_R_w2c = None
                cam_t_w2c = None
                view_matrix = None
                proj_matrix = None
                img_w = IMAGE_WIDTH
                img_h = IMAGE_HEIGHT

                if camera_data is not None:
                    view_id = str(int(frame_id))
                    if view_id in camera_data:
                        cam_info = camera_data[view_id]
                        if use_gl and "view_matrix" in cam_info:
                            view_matrix = cam_info["view_matrix"]
                            proj_matrix = cam_info.get("projection_matrix", None)
                            img_w = cam_info.get("image_width", IMAGE_WIDTH)
                            img_h = cam_info.get("image_height", IMAGE_HEIGHT)
                        elif "cam_K" in cam_info:
                            cam_K = cam_info["cam_K"]
                            cam_R_w2c = cam_info.get("cam_R_w2c", None)
                            cam_t_w2c = cam_info.get("cam_t_w2c", None)

                self.samples.append({
                    "rgb_path": str(rgb_path),
                    "depth_path": str(depth_path),
                    "stl_path": str(stl_path) if stl_path and stl_path.exists() else None,
                    "labels_json_path": str(labels_json_path) if labels_json_path and labels_json_path.exists() else None,
                    "cam_K": cam_K,
                    "cam_R_w2c": cam_R_w2c,
                    "cam_t_w2c": cam_t_w2c,
                    "view_matrix": view_matrix,
                    "proj_matrix": proj_matrix,
                    "img_w": img_w,
                    "img_h": img_h,
                    "object_name": obj_dir.name,
                    "frame_id": frame_id,
                })

    def _infer_intrinsics_from_projection(self, proj_matrix, width, height, fov_deg):
        if proj_matrix is None:
            fx = fy = (width / 2.0) / np.tan(np.radians(fov_deg / 2.0))
            return [fx, 0, width / 2.0, 0, fy, height / 2.0, 0, 0, 1]
        P = np.array(proj_matrix, dtype=np.float64).reshape(4, 4)
        fx = P[0, 0]
        fy = P[1, 1]
        cx = P[0, 2]
        cy = P[1, 2]
        return [fx, 0, cx, 0, fy, cy, 0, 0, 1]

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        sample = self.samples[idx]
        rgb = cv2.imread(sample["rgb_path"], cv2.IMREAD_COLOR)
        if rgb is None:
            rgb = np.zeros((IMAGE_HEIGHT, IMAGE_WIDTH, 3), dtype=np.uint8)
        rgb = cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB)

        depth_path = sample["depth_path"]
        if depth_path.endswith(".npy"):
            depth = np.load(depth_path).astype(np.float32)
        else:
            depth_raw = cv2.imread(depth_path, cv2.IMREAD_UNCHANGED)
            if depth_raw is not None:
                depth = depth_raw.astype(np.float32)
            else:
                depth = np.zeros((IMAGE_HEIGHT, IMAGE_WIDTH), dtype=np.float32)

        gt_seg = self._get_or_generate_gt(sample)

        rgb = cv2.resize(rgb, (self.target_size[0], self.target_size[1]), interpolation=cv2.INTER_LINEAR)
        depth = cv2.resize(depth, (self.target_size[0], self.target_size[1]), interpolation=cv2.INTER_NEAREST)
        gt_seg = cv2.resize(gt_seg, (self.target_size[0], self.target_size[1]), interpolation=cv2.INTER_NEAREST)

        if self.augment:
            do_flip = np.random.rand() > 0.5
            if do_flip:
                rgb = np.flip(rgb, axis=1).copy()
                depth = np.flip(depth, axis=1).copy()
                gt_seg = np.flip(gt_seg, axis=1).copy()

            crop_h = int(self.target_size[1] * 0.9)
            crop_w = int(self.target_size[0] * 0.9)
            y0 = np.random.randint(0, self.target_size[1] - crop_h + 1)
            x0 = np.random.randint(0, self.target_size[0] - crop_w + 1)
            rgb = rgb[y0:y0+crop_h, x0:x0+crop_w]
            depth = depth[y0:y0+crop_h, x0:x0+crop_w]
            gt_seg = gt_seg[y0:y0+crop_h, x0:x0+crop_w]
            rgb = cv2.resize(rgb, (self.target_size[0], self.target_size[1]), interpolation=cv2.INTER_LINEAR)
            depth = cv2.resize(depth, (self.target_size[0], self.target_size[1]), interpolation=cv2.INTER_NEAREST)
            gt_seg = cv2.resize(gt_seg, (self.target_size[0], self.target_size[1]), interpolation=cv2.INTER_NEAREST)

            if self.color_jitter is not None:
                rgb_pil = transforms.functional.to_pil_image(rgb)
                rgb_pil = self.color_jitter(rgb_pil)
                rgb = np.array(rgb_pil)

        depth_norm = depth.copy()
        valid_depth = depth_norm > 0
        if valid_depth.any():
            d_min = depth_norm[valid_depth].min()
            d_max = depth_norm[valid_depth].max()
            if d_max > d_min:
                depth_norm[valid_depth] = (depth_norm[valid_depth] - d_min) / (d_max - d_min)
            else:
                depth_norm[valid_depth] = 0.5
        depth_norm[~valid_depth] = 0.0

        rgb_tensor = torch.from_numpy(rgb.astype(np.float32)).permute(2, 0, 1) / 255.0
        depth_tensor = torch.from_numpy(depth_norm.astype(np.float32)).unsqueeze(0)
        input_tensor = torch.cat([rgb_tensor, depth_tensor], dim=0)
        gt_tensor = torch.from_numpy(gt_seg.astype(np.int64))

        return input_tensor, gt_tensor

    def _get_or_generate_gt(self, sample):
        obj_name = sample["object_name"]
        frame_id = sample["frame_id"]
        gt_dir = self.dataset_dir / obj_name / "topology_gt"
        gt_path = gt_dir / f"topology_gt_{frame_id}.png"

        if gt_path.exists():
            gt = cv2.imread(str(gt_path), cv2.IMREAD_UNCHANGED)
            if gt is not None:
                return gt

        if sample["stl_path"] is None or sample["labels_json_path"] is None:
            return np.full((IMAGE_HEIGHT, IMAGE_WIDTH), IGNORE_INDEX, dtype=np.uint8)

        if sample["view_matrix"] is not None and sample["proj_matrix"] is not None:
            gt_seg = generate_topology_gt_for_view_gl(
                sample["stl_path"],
                sample["labels_json_path"],
                sample["view_matrix"],
                sample["proj_matrix"],
                sample["img_w"],
                sample["img_h"],
            )
        elif sample["cam_K"] is not None and sample["cam_R_w2c"] is not None and sample["cam_t_w2c"] is not None:
            gt_seg = generate_topology_gt_for_view(
                sample["stl_path"],
                sample["labels_json_path"],
                sample["cam_K"],
                sample["cam_R_w2c"],
                sample["cam_t_w2c"],
            )
        else:
            return np.full((IMAGE_HEIGHT, IMAGE_WIDTH), IGNORE_INDEX, dtype=np.uint8)

        gt_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(gt_path), gt_seg)

        return gt_seg


def visualize_segmentation(seg_map, output_path=None):
    if cv2 is None:
        return None
    h, w = seg_map.shape
    vis = np.zeros((h, w, 3), dtype=np.uint8)
    for cls_id, color in CATEGORY_COLORS.items():
        mask = seg_map == cls_id
        vis[mask] = color
    if output_path is not None:
        cv2.imwrite(str(output_path), vis)
    return vis
