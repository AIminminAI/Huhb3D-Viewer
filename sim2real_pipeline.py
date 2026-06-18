import os
import sys
import json
import argparse
import random
import math
from pathlib import Path
from copy import deepcopy

import cv2
import numpy as np


class MultiObjectCompositor:
    def __init__(self, image_width=800, image_height=600):
        self.w = image_width
        self.h = image_height

    def compose_scene(self, object_layers):
        composite_rgb = np.zeros((self.h, self.w, 3), dtype=np.uint8)
        composite_depth = np.full((self.h, self.w), 65535, dtype=np.uint16)
        composite_mask = np.zeros((self.h, self.w), dtype=np.uint8)

        sorted_layers = sorted(object_layers, key=lambda x: np.mean(x['depth'][x['mask'] > 0]), reverse=True)

        original_pixel_counts = {}
        visible_pixel_counts = {}
        bop_gt = []

        for layer in sorted_layers:
            obj_id = layer['obj_id']
            rgb = layer['rgb']
            depth = layer['depth']
            mask = layer['mask']

            mask_bool = mask > 0
            original_pixel_counts[obj_id] = int(np.sum(mask_bool))

            closer = (depth < composite_depth) & mask_bool
            closer_fg = closer & (composite_mask > 0)
            closer_bg = closer & (composite_mask == 0)
            behind = mask_bool & (~closer)

            composite_rgb[closer_bg] = rgb[closer_bg]
            composite_depth[closer_bg] = depth[closer_bg]
            composite_mask[closer_bg] = obj_id

            composite_rgb[closer_fg] = rgb[closer_fg]
            composite_depth[closer_fg] = depth[closer_fg]
            composite_mask[closer_fg] = obj_id

            visible_pixel_counts[obj_id] = int(np.sum(closer))

            visibility = visible_pixel_counts[obj_id] / max(original_pixel_counts[obj_id], 1)

            bop_entry = {
                'cam_R_m2c': layer['cam_R_m2c'].flatten().tolist(),
                'cam_t_m2c': layer['cam_t_m2c'].flatten().tolist(),
                'obj_id': obj_id,
                'visibility': round(visibility, 4)
            }
            bop_gt.append(bop_entry)

        visibility_dict = {}
        for obj_id in original_pixel_counts:
            visibility_dict[obj_id] = round(
                visible_pixel_counts.get(obj_id, 0) / max(original_pixel_counts[obj_id], 1), 4
            )

        return {
            'rgb': composite_rgb,
            'depth': composite_depth,
            'mask': composite_mask,
            'visibility': visibility_dict,
            'bop_gt': bop_gt
        }


class IndustrialBackgroundProvider:
    def __init__(self, seed=None):
        self.rng = np.random.RandomState(seed)

    def generate(self, width, height, style='random'):
        styles = ['concrete', 'metal_floor', 'workshop', 'conveyor',
                  'gradient', 'noise', 'textured']
        if style == 'random':
            style = self.rng.choice(styles)
        generators = {
            'concrete': self._generate_concrete,
            'metal_floor': self._generate_metal_floor,
            'workshop': self._generate_workshop,
            'conveyor': self._generate_conveyor,
            'gradient': self._generate_gradient,
            'noise': self._generate_noise,
            'textured': self._generate_textured,
        }
        return generators[style](width, height)

    def _generate_concrete(self, w, h):
        base = self.rng.randint(120, 180)
        bg = np.full((h, w, 3), base, dtype=np.uint8)
        noise = self.rng.randint(0, 30, (h, w, 3), dtype=np.uint8)
        bg = cv2.add(bg, noise)
        for _ in range(self.rng.randint(2, 6)):
            x1 = self.rng.randint(0, w)
            y1 = self.rng.randint(0, h)
            x2 = self.rng.randint(0, w)
            y2 = self.rng.randint(0, h)
            thickness = self.rng.randint(1, 3)
            shade = self.rng.randint(80, 140)
            cv2.line(bg, (x1, y1), (x2, y2), (shade, shade, shade), thickness)
        for _ in range(self.rng.randint(3, 10)):
            cx = self.rng.randint(0, w)
            cy = self.rng.randint(0, h)
            radius = self.rng.randint(10, 60)
            shade = self.rng.randint(100, 160)
            cv2.circle(bg, (cx, cy), radius, (shade, shade, shade), -1)
        return bg

    def _generate_metal_floor(self, w, h):
        base = self.rng.randint(140, 200)
        bg = np.full((h, w, 3), base, dtype=np.uint8)
        noise = self.rng.randint(0, 15, (h, w, 3), dtype=np.uint8)
        bg = cv2.add(bg, noise)
        grid_size = self.rng.randint(30, 80)
        line_shade = self.rng.randint(90, 130)
        for x in range(0, w, grid_size):
            cv2.line(bg, (x, 0), (x, h), (line_shade, line_shade, line_shade), 1)
        for y in range(0, h, grid_size):
            cv2.line(bg, (0, y), (w, y), (line_shade, line_shade, line_shade), 1)
        for _ in range(self.rng.randint(0, 5)):
            cx = self.rng.randint(0, w)
            cy = self.rng.randint(0, h)
            radius = self.rng.randint(5, 30)
            shade = self.rng.randint(100, 150)
            cv2.circle(bg, (cx, cy), radius, (shade, shade, shade), 1)
        return bg

    def _generate_workshop(self, w, h):
        base = self.rng.randint(80, 130)
        bg = np.full((h, w, 3), base, dtype=np.uint8)
        noise = self.rng.randint(0, 25, (h, w, 3), dtype=np.uint8)
        bg = cv2.add(bg, noise)
        shelf_y = self.rng.randint(h // 3, 2 * h // 3)
        shelf_shade = self.rng.randint(60, 100)
        cv2.rectangle(bg, (0, shelf_y), (w, shelf_y + self.rng.randint(5, 15)),
                      (shelf_shade, shelf_shade, shelf_shade), -1)
        for _ in range(self.rng.randint(2, 5)):
            rx = self.rng.randint(0, w)
            ry = self.rng.randint(0, shelf_y)
            rw = self.rng.randint(20, 80)
            rh = self.rng.randint(20, 60)
            shade = self.rng.randint(50, 90)
            cv2.rectangle(bg, (rx, ry), (rx + rw, ry + rh), (shade, shade, shade), -1)
        pipe_shade = self.rng.randint(100, 160)
        for _ in range(self.rng.randint(1, 3)):
            y_pos = self.rng.randint(0, h)
            cv2.rectangle(bg, (0, y_pos), (w, y_pos + self.rng.randint(8, 20)),
                          (pipe_shade, pipe_shade, pipe_shade), -1)
        return bg

    def _generate_conveyor(self, w, h):
        base = self.rng.randint(60, 100)
        bg = np.full((h, w, 3), base, dtype=np.uint8)
        noise = self.rng.randint(0, 20, (h, w, 3), dtype=np.uint8)
        bg = cv2.add(bg, noise)
        belt_y1 = self.rng.randint(h // 4, h // 2)
        belt_y2 = self.rng.randint(3 * h // 4, h)
        belt_shade = self.rng.randint(40, 70)
        cv2.rectangle(bg, (0, belt_y1), (w, belt_y2), (belt_shade, belt_shade, belt_shade), -1)
        stripe_width = self.rng.randint(15, 40)
        stripe_shade = self.rng.randint(50, 80)
        for x in range(0, w, stripe_width * 2):
            cv2.rectangle(bg, (x, belt_y1), (x + stripe_width, belt_y2),
                          (stripe_shade, stripe_shade, stripe_shade), -1)
        rail_shade = self.rng.randint(120, 180)
        cv2.rectangle(bg, (0, belt_y1 - 5), (w, belt_y1), (rail_shade, rail_shade, rail_shade), -1)
        cv2.rectangle(bg, (0, belt_y2), (w, belt_y2 + 5), (rail_shade, rail_shade, rail_shade), -1)
        return bg

    def _generate_gradient(self, w, h):
        c1 = self.rng.randint(40, 220, size=3)
        c2 = self.rng.randint(40, 220, size=3)
        bg = np.zeros((h, w, 3), dtype=np.uint8)
        direction = self.rng.choice(['horizontal', 'vertical', 'diagonal'])
        if direction == 'horizontal':
            for x in range(w):
                t = x / max(w - 1, 1)
                color = (1 - t) * c1 + t * c2
                bg[:, x] = color.astype(np.uint8)
        elif direction == 'vertical':
            for y in range(h):
                t = y / max(h - 1, 1)
                color = (1 - t) * c1 + t * c2
                bg[y, :] = color.astype(np.uint8)
        else:
            for y in range(h):
                for x in range(w):
                    t = (x + y) / max(w + h - 2, 1)
                    color = (1 - t) * c1 + t * c2
                    bg[y, x] = color.astype(np.uint8)
        noise = self.rng.randint(0, 10, (h, w, 3), dtype=np.uint8)
        bg = cv2.add(bg, noise)
        return bg

    def _generate_noise(self, w, h):
        bg = self.rng.randint(0, 256, (h, w, 3), dtype=np.uint8)
        ksize = self.rng.choice([3, 5, 7])
        bg = cv2.GaussianBlur(bg, (ksize, ksize), 0)
        return bg

    def _generate_textured(self, w, h):
        base = self.rng.randint(80, 180)
        bg = np.full((h, w, 3), base, dtype=np.uint8)
        octaves = self.rng.randint(3, 7)
        for octave in range(octaves):
            freq = 2 ** (octave + 1)
            amp = self.rng.randint(5, 25) // (octave + 1)
            small_h = max(h // freq, 1)
            small_w = max(w // freq, 1)
            small_noise = self.rng.randint(-amp, amp + 1, (small_h, small_w, 3), dtype=np.int16)
            small_noise = small_noise.astype(np.float32)
            resized = cv2.resize(small_noise, (w, h), interpolation=cv2.INTER_LINEAR)
            bg = bg.astype(np.int16) + resized.astype(np.int16)
        bg = np.clip(bg, 0, 255).astype(np.uint8)
        return bg


class PhotometricRandomizer:
    def __init__(self, seed=None):
        self.rng = np.random.RandomState(seed)

    def randomize(self, rgb):
        result = rgb.copy().astype(np.float64)
        brightness = self.rng.uniform(0.5, 1.5)
        result = result * brightness

        contrast = self.rng.uniform(0.7, 1.3)
        mean = np.mean(result)
        result = (result - mean) * contrast + mean

        gamma = self.rng.uniform(0.6, 1.8)
        result = np.clip(result, 0, 255)
        result = 255.0 * np.power(result / 255.0, 1.0 / gamma)

        hue_shift = self.rng.randint(-20, 21, size=3)
        result = result + hue_shift

        result = np.clip(result, 0, 255).astype(np.uint8)

        if self.rng.random() < 0.5:
            result = self._add_shadow(result)

        if self.rng.random() < 0.4:
            result = self._add_highlight(result)

        if self.rng.random() < 0.5:
            result = self._apply_color_temperature(result)

        return result

    def _add_shadow(self, rgb):
        result = rgb.copy().astype(np.float64)
        h, w = rgb.shape[:2]
        cx = self.rng.randint(0, w)
        cy = self.rng.randint(0, h)
        radius = self.rng.randint(min(h, w) // 6, min(h, w) // 2)
        y_coords, x_coords = np.ogrid[:h, :w]
        dist = np.sqrt((x_coords - cx) ** 2 + (y_coords - cy) ** 2)
        shadow_mask = np.clip(1.0 - dist / radius, 0, 1)
        shadow_mask = shadow_mask * self.rng.uniform(0.2, 0.5)
        shadow_mask = shadow_mask[:, :, np.newaxis]
        result = result * (1.0 - shadow_mask)
        return np.clip(result, 0, 255).astype(np.uint8)

    def _add_highlight(self, rgb):
        result = rgb.copy().astype(np.float64)
        h, w = rgb.shape[:2]
        cx = self.rng.randint(0, w)
        cy = self.rng.randint(0, h)
        radius = self.rng.randint(min(h, w) // 8, min(h, w) // 3)
        y_coords, x_coords = np.ogrid[:h, :w]
        dist = np.sqrt((x_coords - cx) ** 2 + (y_coords - cy) ** 2)
        highlight_mask = np.clip(1.0 - dist / radius, 0, 1)
        highlight_mask = highlight_mask * self.rng.uniform(0.1, 0.3)
        highlight_mask = highlight_mask[:, :, np.newaxis]
        result = result + (255.0 - result) * highlight_mask
        return np.clip(result, 0, 255).astype(np.uint8)

    def _apply_color_temperature(self, rgb):
        result = rgb.copy().astype(np.float64)
        temp = self.rng.choice(['warm', 'cool'])
        if temp == 'warm':
            result[:, :, 0] += self.rng.uniform(5, 20)
            result[:, :, 1] += self.rng.uniform(2, 10)
            result[:, :, 2] -= self.rng.uniform(5, 15)
        else:
            result[:, :, 0] -= self.rng.uniform(5, 15)
            result[:, :, 1] += self.rng.uniform(0, 5)
            result[:, :, 2] += self.rng.uniform(5, 20)
        return np.clip(result, 0, 255).astype(np.uint8)


class DepthNoiseInjector:
    def __init__(self, seed=None):
        self.rng = np.random.RandomState(seed)

    def inject(self, depth, mask):
        result = depth.copy().astype(np.float64)
        h, w = depth.shape

        object_pixels = mask > 0
        bg_pixels = mask == 0

        std_mm = self.rng.uniform(1, 5)
        noise = self.rng.normal(0, std_mm, (h, w))
        result[object_pixels] += noise[object_pixels]

        quant_step = self.rng.choice([1, 2, 5])
        result[object_pixels] = np.round(result[object_pixels] / quant_step) * quant_step

        hole_prob = self.rng.uniform(0.005, 0.03)
        hole_mask = self.rng.random((h, w)) < hole_prob
        result[object_pixels & hole_mask] = 0

        flying_prob = self.rng.uniform(0.001, 0.005)
        flying_mask = self.rng.random((h, w)) < flying_prob
        edge_mask = self._get_edge_mask(mask)
        flying_pixels = flying_mask & edge_mask & object_pixels
        flying_shift = self.rng.uniform(50, 200, size=int(np.sum(flying_pixels)))
        result[flying_pixels] += flying_shift

        dilate_pixels = self.rng.randint(1, 4)
        kernel = np.ones((3, 3), dtype=np.uint8)
        dilated = cv2.dilate(mask, kernel, iterations=dilate_pixels)
        edge_band = (dilated > 0) & (mask == 0)
        result[edge_band] = 0

        multipath_prob = self.rng.uniform(0.01, 0.05)
        multipath_mask = self.rng.random((h, w)) < multipath_prob
        multipath_pixels = multipath_mask & edge_mask & object_pixels
        if np.any(multipath_pixels):
            neighbor_depth = self._get_neighbor_mean(result, multipath_pixels)
            alpha = self.rng.uniform(0.3, 0.7)
            result[multipath_pixels] = (1 - alpha) * result[multipath_pixels] + alpha * neighbor_depth[multipath_pixels]

        result = np.clip(result, 0, 65535).astype(np.uint16)
        return result

    def _get_edge_mask(self, mask):
        kernel = np.ones((3, 3), dtype=np.uint8)
        eroded = cv2.erode(mask, kernel, iterations=1)
        edge = (mask > 0) & (eroded == 0)
        return edge

    def _get_neighbor_mean(self, depth, pixel_mask):
        result = depth.copy()
        h, w = depth.shape
        padded = np.pad(depth, 1, mode='edge')
        neighbor_sum = np.zeros_like(depth)
        count = np.zeros_like(depth, dtype=np.float64)
        for dy in [-1, 0, 1]:
            for dx in [-1, 0, 1]:
                if dy == 0 and dx == 0:
                    continue
                neighbor_sum += padded[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
                count += 1
        result = neighbor_sum / count
        return result


class Sim2RealPipeline:
    def __init__(self, source_dir, output_dir,
                 num_scenes=500,
                 objects_per_scene=(2, 6),
                 image_width=800,
                 image_height=600,
                 seed=None):
        self.source_dir = Path(source_dir)
        self.output_dir = Path(output_dir)
        self.num_scenes = num_scenes
        self.min_objects = objects_per_scene[0]
        self.max_objects = objects_per_scene[1]
        self.image_width = image_width
        self.image_height = image_height
        self.seed = seed

        self.rng = np.random.RandomState(seed)
        self.compositor = MultiObjectCompositor(image_width, image_height)
        self.bg_provider = IndustrialBackgroundProvider(seed=seed)
        self.photo_randomizer = PhotometricRandomizer(seed=seed)
        self.depth_noise_injector = DepthNoiseInjector(seed=seed)

        self.obj_id_map, self.id_obj_map = self._build_object_id_map()
        self.object_frame_cache = {}

    def _build_object_id_map(self):
        object_names = sorted([
            d.name for d in self.source_dir.iterdir()
            if d.is_dir() and not d.name.startswith('_')
        ])
        obj_id_map = {name: i + 1 for i, name in enumerate(object_names)}
        id_obj_map = {v: k for k, v in obj_id_map.items()}
        return obj_id_map, id_obj_map

    def _load_object_data(self, obj_name, obj_id):
        obj_dir = self.source_dir / obj_name

        rgb_dir = obj_dir / 'rgb'
        mask_dir = obj_dir / 'mask'
        depth_dir = obj_dir / 'depth'

        if not rgb_dir.exists():
            return None

        rgb_files = sorted(rgb_dir.glob('*.png'))
        if not rgb_files:
            return None

        frame_idx = self.rng.randint(0, len(rgb_files))
        rgb_file = rgb_files[frame_idx]
        frame_stem = rgb_file.stem
        frame_num = frame_stem.split('_')[-1]

        rgb = cv2.imread(str(rgb_file), cv2.IMREAD_COLOR)
        if rgb is None:
            return None
        rgb = cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB)

        mask_file = mask_dir / f'mask_{frame_num}.png'
        if not mask_file.exists():
            return None
        mask = cv2.imread(str(mask_file), cv2.IMREAD_GRAYSCALE)
        if mask is None:
            return None

        depth = None
        depth_png = depth_dir / f'depth_{frame_num}.png'
        depth_npy = depth_dir / f'depth_{frame_num}.npy'
        if depth_png.exists():
            depth = cv2.imread(str(depth_png), cv2.IMREAD_UNCHANGED)
        elif depth_npy.exists():
            depth = np.load(str(depth_npy)).astype(np.uint16)

        if depth is None:
            depth = np.zeros((rgb.shape[0], rgb.shape[1]), dtype=np.uint16)

        scene_gt_path = obj_dir / 'scene_gt.json'
        cam_R_m2c = np.eye(3)
        cam_t_m2c = np.zeros(3)
        if scene_gt_path.exists():
            with open(scene_gt_path, 'r') as f:
                scene_gt = json.load(f)
            frame_key = str(int(frame_num))
            if frame_key in scene_gt:
                gt_list = scene_gt[frame_key]
                if len(gt_list) > 0:
                    gt_entry = gt_list[0]
                    cam_R_m2c = np.array(gt_entry['cam_R_m2c']).reshape(3, 3)
                    cam_t_m2c = np.array(gt_entry['cam_t_m2c'])

        scene_camera_path = obj_dir / 'scene_camera.json'
        cam_K = None
        if scene_camera_path.exists():
            with open(scene_camera_path, 'r') as f:
                scene_camera = json.load(f)
            frame_key = str(int(frame_num))
            if frame_key in scene_camera:
                cam_K = np.array(scene_camera[frame_key]['cam_K']).reshape(3, 3)

        if rgb.shape[0] != self.image_height or rgb.shape[1] != self.image_width:
            rgb = cv2.resize(rgb, (self.image_width, self.image_height), interpolation=cv2.INTER_LINEAR)
            mask = cv2.resize(mask, (self.image_width, self.image_height), interpolation=cv2.INTER_NEAREST)
            depth = cv2.resize(depth, (self.image_width, self.image_height), interpolation=cv2.INTER_NEAREST)

        return {
            'rgb': rgb,
            'depth': depth,
            'mask': mask,
            'obj_id': obj_id,
            'cam_R_m2c': cam_R_m2c,
            'cam_t_m2c': cam_t_m2c,
            'cam_K': cam_K,
            'obj_name': obj_name,
            'frame_num': frame_num
        }

    def _apply_background(self, composite_rgb, composite_mask):
        bg = self.bg_provider.generate(self.image_width, self.image_height)
        bg_mask = composite_mask == 0
        result = composite_rgb.copy()
        result[bg_mask] = bg[bg_mask]
        return result

    def _generate_coco_annotations(self, scene_id, composite_mask, visibility_dict):
        annotations = []
        unique_ids = np.unique(composite_mask)
        unique_ids = unique_ids[unique_ids > 0]

        for obj_id in unique_ids:
            obj_mask = (composite_mask == obj_id).astype(np.uint8)
            contours, _ = cv2.findContours(obj_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if len(contours) == 0:
                continue

            all_contours_points = []
            for contour in contours:
                for pt in contour:
                    all_contours_points.append((pt[0][0], pt[0][1]))

            if len(all_contours_points) == 0:
                continue

            segmentation = []
            for contour in contours:
                if len(contour) >= 3:
                    seg = contour.flatten().tolist()
                    segmentation.append(seg)

            xs = [p[0] for p in all_contours_points]
            ys = [p[1] for p in all_contours_points]
            x_min = int(min(xs))
            y_min = int(min(ys))
            x_max = int(max(xs))
            y_max = int(max(ys))
            bbox_w = x_max - x_min
            bbox_h = y_max - y_min
            area = int(np.sum(obj_mask))

            ann = {
                'id': scene_id * 100 + int(obj_id),
                'image_id': scene_id,
                'category_id': int(obj_id),
                'segmentation': segmentation,
                'area': area,
                'bbox': [x_min, y_min, bbox_w, bbox_h],
                'iscrowd': 0,
                'visibility': float(visibility_dict.get(int(obj_id), 0.0))
            }
            annotations.append(ann)

        return annotations

    def _generate_yolo_labels(self, composite_mask, visibility_dict):
        labels = []
        unique_ids = np.unique(composite_mask)
        unique_ids = unique_ids[unique_ids > 0]

        for obj_id in unique_ids:
            obj_mask = (composite_mask == obj_id).astype(np.uint8)
            contours, _ = cv2.findContours(obj_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if len(contours) == 0:
                continue

            xs = []
            ys = []
            for contour in contours:
                for pt in contour:
                    xs.append(pt[0][0])
                    ys.append(pt[0][1])

            if len(xs) == 0:
                continue

            x_min = min(xs)
            y_min = min(ys)
            x_max = max(xs)
            y_max = max(ys)

            cx = ((x_min + x_max) / 2.0) / self.image_width
            cy = ((y_min + y_max) / 2.0) / self.image_height
            bw = (x_max - x_min) / self.image_width
            bh = (y_max - y_min) / self.image_height

            seg_points = []
            for contour in contours:
                if len(contour) >= 3:
                    for pt in contour:
                        seg_points.extend([
                            pt[0][0] / self.image_width,
                            pt[0][1] / self.image_height
                        ])

            class_id = int(obj_id) - 1
            line_parts = [str(class_id), f'{cx:.6f}', f'{cy:.6f}', f'{bw:.6f}', f'{bh:.6f}']
            if seg_points:
                seg_str = ' '.join(f'{p:.6f}' for p in seg_points)
                line_parts.append(seg_str)
            labels.append(' '.join(line_parts))

        return labels

    def generate_dataset(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / 'rgb').mkdir(exist_ok=True)
        (self.output_dir / 'depth').mkdir(exist_ok=True)
        (self.output_dir / 'mask').mkdir(exist_ok=True)
        (self.output_dir / 'yolo_labels').mkdir(exist_ok=True)

        all_scene_gt = {}
        all_scene_camera = {}
        all_coco_annotations = []
        all_metadata = {}

        coco_categories = []
        for obj_name, obj_id in sorted(self.obj_id_map.items(), key=lambda x: x[1]):
            coco_categories.append({
                'id': obj_id,
                'name': obj_name,
                'supercategory': 'industrial_part'
            })

        available_objects = list(self.obj_id_map.keys())
        if len(available_objects) == 0:
            print(f"Error: no object directories found in {self.source_dir}")
            return

        for scene_idx in range(self.num_scenes):
            scene_id = scene_idx + 1
            scene_name = f'scene_{scene_id:06d}'

            num_objects = self.rng.randint(self.min_objects, self.max_objects + 1)
            num_objects = min(num_objects, len(available_objects))
            selected_objects = self.rng.choice(available_objects, size=num_objects, replace=False)

            object_layers = []
            reference_cam_K = None

            for obj_name in selected_objects:
                obj_id = self.obj_id_map[obj_name]
                data = self._load_object_data(obj_name, obj_id)
                if data is None:
                    continue

                if reference_cam_K is None:
                    reference_cam_K = data['cam_K']

                object_layers.append(data)

            if len(object_layers) == 0:
                continue

            composite = self.compositor.compose_scene(object_layers)

            composite_rgb = self._apply_background(composite['rgb'], composite['mask'])

            composite_rgb = self.photo_randomizer.randomize(composite_rgb)

            composite_depth = self.depth_noise_injector.inject(composite['depth'], composite['mask'])

            visibility_dict = composite['visibility']

            rgb_bgr = cv2.cvtColor(composite_rgb, cv2.COLOR_RGB2BGR)
            cv2.imwrite(str(self.output_dir / 'rgb' / f'{scene_name}.png'), rgb_bgr)
            cv2.imwrite(str(self.output_dir / 'depth' / f'{scene_name}.png'), composite_depth)
            cv2.imwrite(str(self.output_dir / 'mask' / f'{scene_name}.png'), composite['mask'])

            scene_gt_entries = []
            for gt_entry in composite['bop_gt']:
                if gt_entry['visibility'] >= 0.1:
                    scene_gt_entries.append(gt_entry)

            all_scene_gt[str(scene_id)] = scene_gt_entries

            if reference_cam_K is not None:
                cam_K_list = reference_cam_K.flatten().tolist()
            else:
                cam_K_list = [739.0, 0.0, 400.0, 0.0, 739.0, 300.0, 0.0, 0.0, 1.0]

            all_scene_camera[str(scene_id)] = {
                'cam_K': cam_K_list,
                'depth_scale': 1.0,
                'model_unit': 'mm'
            }

            coco_anns = self._generate_coco_annotations(scene_id, composite['mask'], visibility_dict)
            all_coco_annotations.extend(coco_anns)

            yolo_labels = self._generate_yolo_labels(composite['mask'], visibility_dict)
            yolo_path = self.output_dir / 'yolo_labels' / f'{scene_name}.txt'
            with open(str(yolo_path), 'w') as f:
                for line in yolo_labels:
                    f.write(line + '\n')

            scene_objects_info = []
            for layer in object_layers:
                scene_objects_info.append({
                    'obj_name': layer['obj_name'],
                    'obj_id': layer['obj_id'],
                    'frame_num': layer['frame_num'],
                    'visibility': visibility_dict.get(layer['obj_id'], 0.0)
                })

            all_metadata[str(scene_id)] = {
                'objects': scene_objects_info,
                'num_objects': len(object_layers),
                'visible_objects': sum(1 for v in visibility_dict.values() if v >= 0.1)
            }

            if (scene_idx + 1) % 50 == 0 or scene_idx == 0:
                print(f"Generated {scene_idx + 1}/{self.num_scenes} scenes")

        with open(str(self.output_dir / 'scene_gt.json'), 'w') as f:
            json.dump(all_scene_gt, f, indent=2)

        with open(str(self.output_dir / 'scene_camera.json'), 'w') as f:
            json.dump(all_scene_camera, f, indent=2)

        coco_output = {
            'images': [
                {
                    'id': i + 1,
                    'file_name': f'scene_{i + 1:06d}.png',
                    'width': self.image_width,
                    'height': self.image_height
                }
                for i in range(self.num_scenes)
            ],
            'annotations': all_coco_annotations,
            'categories': coco_categories
        }
        with open(str(self.output_dir / 'coco_annotations.json'), 'w') as f:
            json.dump(coco_output, f, indent=2)

        with open(str(self.output_dir / 'scene_metadata.json'), 'w') as f:
            json.dump(all_metadata, f, indent=2)

        total_visible = 0
        total_objects_in_scenes = 0
        visibility_histogram = {}
        for scene_data in all_metadata.values():
            for obj_info in scene_data['objects']:
                total_objects_in_scenes += 1
                vis = obj_info['visibility']
                if vis >= 0.1:
                    total_visible += 1
                bucket = int(vis * 10) / 10.0
                visibility_histogram[bucket] = visibility_histogram.get(bucket, 0) + 1

        dataset_info = {
            'dataset_name': 'Huhb3D-Sim2Real',
            'version': '1.0.0',
            'generator': 'Sim2RealPipeline',
            'source_dataset': str(self.source_dir),
            'num_scenes': self.num_scenes,
            'image_width': self.image_width,
            'image_height': self.image_height,
            'objects_per_scene_range': [self.min_objects, self.max_objects],
            'total_object_instances': total_objects_in_scenes,
            'total_visible_instances': total_visible,
            'visibility_threshold': 0.1,
            'object_id_map': self.obj_id_map,
            'visibility_histogram': {str(k): v for k, v in sorted(visibility_histogram.items())}
        }
        with open(str(self.output_dir / 'dataset_info.json'), 'w') as f:
            json.dump(dataset_info, f, indent=2)

        print(f"Dataset generation complete: {self.num_scenes} scenes saved to {self.output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Sim2Real Domain Randomization Pipeline')
    parser.add_argument("--source", default="sell_Huhb3D-Industrial-100",
                        help="Source dataset directory")
    parser.add_argument("--output", default="Huhb3D-Sim2Real-500",
                        help="Output dataset directory")
    parser.add_argument("--num-scenes", type=int, default=500,
                        help="Number of scenes to generate")
    parser.add_argument("--min-objects", type=int, default=2,
                        help="Minimum objects per scene")
    parser.add_argument("--max-objects", type=int, default=6,
                        help="Maximum objects per scene")
    parser.add_argument("--width", type=int, default=800,
                        help="Output image width")
    parser.add_argument("--height", type=int, default=600,
                        help="Output image height")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed for reproducibility")
    args = parser.parse_args()

    pipeline = Sim2RealPipeline(
        source_dir=args.source,
        output_dir=args.output,
        num_scenes=args.num_scenes,
        objects_per_scene=(args.min_objects, args.max_objects),
        image_width=args.width,
        image_height=args.height,
        seed=args.seed
    )
    pipeline.generate_dataset()
