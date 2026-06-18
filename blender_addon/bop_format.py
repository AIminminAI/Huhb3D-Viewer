"""BOP format utilities for 6DoF pose estimation datasets.

Provides functions to save ground truth annotations in BOP, COCO, and YOLO formats,
and to convert Blender camera parameters to BOP-compatible representations.
"""

import json
import os
import math

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


# ---------------------------------------------------------------------------
# Blender camera  →  BOP conversion
# ---------------------------------------------------------------------------

def blender_camera_to_bop(camera_matrix_world, focal_length, sensor_width, image_width, image_height):
    """Convert a Blender camera to BOP-format intrinsics and extrinsics.

    Parameters
    ----------
    camera_matrix_world : list | numpy.ndarray
        4×4 world matrix of the Blender camera object.
    focal_length : float
        Camera focal length in millimetres.
    sensor_width : float
        Camera sensor width in millimetres.
    image_width : int
        Rendered image width in pixels.
    image_height : int
        Rendered image height in pixels.

    Returns
    -------
    dict
        ``cam_K`` – 3×3 intrinsic matrix (flattened, row-major).
    dict
        ``cam_R_m2c`` – 3×3 rotation (model-to-camera, row-major).
    dict
        ``cam_t_m2c`` – 3×1 translation in millimetres (model-to-camera).
    """
    if HAS_NUMPY:
        M = np.array(camera_matrix_world, dtype=np.float64).reshape(4, 4)
    else:
        M = [list(row) for row in _chunks(camera_matrix_world if hasattr(camera_matrix_world, '__len__') else camera_matrix_world, 4)]

    # --- Intrinsics ---
    fx = focal_length * image_width / sensor_width
    fy = fx  # square pixels
    cx = image_width / 2.0
    cy = image_height / 2.0
    cam_K = [[fx, 0.0, cx],
             [0.0, fy, cy],
             [0.0, 0.0, 1.0]]

    # --- Extrinsics (model-to-camera) ---
    # Blender's matrix_world is camera-to-world (c2w).
    # BOP expects model-to-camera (m2c), so we invert.
    if HAS_NUMPY:
        R_c2w = M[:3, :3]
        t_c2w = M[:3, 3]
        # Invert: R_m2c = R_c2w^T, t_m2c = -R_c2w^T @ t_c2w
        R_m2c = R_c2w.T
        t_m2c = -R_m2c @ t_c2w
    else:
        R_c2w = [[M[r][c] for c in range(3)] for r in range(3)]
        t_c2w = [M[r][3] for r in range(3)]
        R_m2c = _transpose3(R_c2w)
        t_m2c = _matvec3(R_m2c, [-t_c2w[0], -t_c2w[1], -t_c2w[2]])

    # BOP uses millimetres; Blender default unit is metres → ×1000
    # (If the scene unit is already mm this still works because the user
    #  controls the model scale; we multiply by 1000 as per BOP convention.)
    scale_to_mm = 1000.0
    if HAS_NUMPY:
        cam_t_m2c = (t_m2c * scale_to_mm).tolist()
    else:
        cam_t_m2c = [v * scale_to_mm for v in t_m2c]

    # Flatten row-major for BOP JSON
    if HAS_NUMPY:
        cam_R_m2c_flat = R_m2c.flatten().tolist()
    else:
        cam_R_m2c_flat = [R_m2c[r][c] for r in range(3) for c in range(3)]

    cam_K_flat = [cam_K[r][c] for r in range(3) for c in range(3)]

    return (
        {"cam_K": cam_K_flat},
        {"cam_R_m2c": cam_R_m2c_flat},
        {"cam_t_m2c": cam_t_m2c},
    )


# ---------------------------------------------------------------------------
# BOP scene_gt.json
# ---------------------------------------------------------------------------

def save_scene_gt(output_dir, scene_gt_dict):
    """Save BOP ``scene_gt.json``.

    Parameters
    ----------
    output_dir : str
        Directory that will contain the JSON file.
    scene_gt_dict : dict
        Mapping ``{im_id: [{"cam_R_m2c", "cam_t_m2c", "obj_id"}, ...]}``.
    """
    path = os.path.join(output_dir, "scene_gt.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(scene_gt_dict, f, indent=2)
    return path


# ---------------------------------------------------------------------------
# BOP scene_camera.json
# ---------------------------------------------------------------------------

def save_scene_camera(output_dir, scene_camera_dict):
    """Save BOP ``scene_camera.json``.

    Parameters
    ----------
    output_dir : str
        Directory that will contain the JSON file.
    scene_camera_dict : dict
        Mapping ``{im_id: {"cam_K", "depth_scale", ...}}``.
    """
    path = os.path.join(output_dir, "scene_camera.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(scene_camera_dict, f, indent=2)
    return path


# ---------------------------------------------------------------------------
# COCO annotations
# ---------------------------------------------------------------------------

def save_coco_annotations(output_dir, coco_dict):
    """Save COCO-format ``coco_annotations.json``.

    Parameters
    ----------
    output_dir : str
        Directory that will contain the JSON file.
    coco_dict : dict
        Full COCO annotation dictionary with ``images``, ``annotations``, ``categories``.
    """
    path = os.path.join(output_dir, "coco_annotations.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(coco_dict, f, indent=2)
    return path


# ---------------------------------------------------------------------------
# YOLO labels
# ---------------------------------------------------------------------------

def save_yolo_labels(output_dir, labels_dict):
    """Save YOLO-format label files.

    Parameters
    ----------
    output_dir : str
        Root directory; a ``labels/`` sub-folder will be created.
    labels_dict : dict
        Mapping ``{image_name: [{"class_id", "cx", "cy", "w", "h"}, ...]}``.
        All values are normalised to [0, 1].
    """
    labels_dir = os.path.join(output_dir, "labels")
    os.makedirs(labels_dir, exist_ok=True)

    for image_name, entries in labels_dict.items():
        txt_name = os.path.splitext(image_name)[0] + ".txt"
        path = os.path.join(labels_dir, txt_name)
        with open(path, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(f"{e['class_id']} {e['cx']:.6f} {e['cy']:.6f} {e['w']:.6f} {e['h']:.6f}\n")

    return labels_dir


# ---------------------------------------------------------------------------
# Helpers (pure-Python fallbacks when numpy is unavailable)
# ---------------------------------------------------------------------------

def _chunks(seq, n):
    """Yield successive n-sized chunks from *seq*."""
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def _transpose3(M):
    return [[M[r][c] for r in range(3)] for c in range(3)]


def _matvec3(M, v):
    return [sum(M[r][c] * v[c] for c in range(3)) for r in range(3)]
