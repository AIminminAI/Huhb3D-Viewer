"""Sim2Real augmentation for synthetic 6DoF training data.

Provides industrial-style background generation, photometric randomisation,
depth noise injection, and multi-object composition using depth buffers.
Requires OpenCV (cv2) and numpy; falls back gracefully when unavailable.
"""

import os
import random
import math
import logging

logger = logging.getLogger(__name__)

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

# ---------------------------------------------------------------------------
# Industrial background generation – 7 styles
# ---------------------------------------------------------------------------

BG_STYLES = [
    "concrete_floor",
    "metal_shelf",
    "conveyor_belt",
    "factory_wall",
    "wood_workbench",
    "cable_tray",
    "painted_floor",
]

# Per-style base colour ranges (BGR, uint8)
_STYLE_COLOURS = {
    "concrete_floor":  ((140, 135, 130), (185, 180, 175)),
    "metal_shelf":     ((100, 100, 110), (160, 160, 170)),
    "conveyor_belt":   ((60, 55, 50),    (100, 95, 90)),
    "factory_wall":    ((150, 145, 135), (200, 195, 185)),
    "wood_workbench":  ((60, 80, 120),   (100, 120, 170)),
    "cable_tray":      ((70, 65, 60),    (110, 105, 100)),
    "painted_floor":   ((130, 140, 160), (180, 190, 210)),
}


def generate_background(width, height, style=None):
    """Generate a synthetic industrial background image.

    Parameters
    ----------
    width, height : int
        Image dimensions.
    style : str | None
        One of :data:`BG_STYLES`. Random if *None*.

    Returns
    -------
    numpy.ndarray
        BGR uint8 image of shape (height, width, 3).
    """
    if not HAS_CV2:
        logger.warning("OpenCV not available – returning grey placeholder background")
        return _grey_image(width, height)

    if style is None:
        style = random.choice(BG_STYLES)

    lo, hi = _STYLE_COLOURS[style]
    base = [random.randint(lo[c], hi[c]) for c in range(3)]
    img = np.full((height, width, 3), base, dtype=np.uint8)

    # Perlin-like noise via repeated Gaussian blur on random blocks
    noise = np.random.randint(0, 50, (height // 8, width // 8, 3), dtype=np.uint8)
    noise = cv2.resize(noise, (width, height), interpolation=cv2.INTER_CUBIC)
    img = cv2.addWeighted(img, 0.7, noise, 0.3, 0)

    # Occasional structural lines (shelves, conveyor rails)
    if style in ("metal_shelf", "conveyor_belt", "cable_tray"):
        for _ in range(random.randint(1, 4)):
            y = random.randint(0, height - 1)
            cv2.line(img, (0, y), (width, y), (base[0] - 20, base[1] - 20, base[2] - 20), 2)

    # Subtle vignette
    vignette = _vignette(width, height)
    img = cv2.multiply(img, vignette)

    return img


def _grey_image(w, h):
    """Fallback grey image when cv2 is missing."""
    try:
        import numpy as _np
        return _np.full((h, w, 3), 128, dtype=_np.uint8)
    except ImportError:
        return None


def _vignette(w, h, sigma=0.6):
    """Soft radial vignette mask (float32, 0-1)."""
    X = np.arange(w)[None, :].astype(np.float32)
    Y = np.arange(h)[:, None].astype(np.float32)
    cx, cy = w / 2.0, h / 2.0
    dist = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
    max_dist = math.sqrt(cx ** 2 + cy ** 2)
    vig = 1.0 - sigma * (dist / max_dist) ** 2
    vig = np.clip(vig, 0, 1)[..., None]
    return vig.astype(np.float32)


# ---------------------------------------------------------------------------
# Photometric randomisation
# ---------------------------------------------------------------------------

def photometric_randomize(image):
    """Apply random brightness, contrast, gamma, and shadow augmentation.

    Parameters
    ----------
    image : numpy.ndarray
        BGR uint8 image.

    Returns
    -------
    numpy.ndarray
        Augmented BGR uint8 image.
    """
    if not HAS_CV2:
        return image

    img = image.astype(np.float32) / 255.0

    # Brightness
    alpha_b = random.uniform(0.7, 1.3)
    img = img * alpha_b

    # Contrast
    alpha_c = random.uniform(0.8, 1.2)
    mean = img.mean()
    img = (img - mean) * alpha_c + mean

    # Gamma
    gamma = random.uniform(0.7, 1.5)
    img = np.power(np.clip(img, 0, 1), gamma)

    # Random shadow (dark band)
    if random.random() < 0.4:
        h, w = img.shape[:2]
        y0 = random.randint(0, h - 1)
        shadow_h = random.randint(h // 10, h // 3)
        shadow_alpha = random.uniform(0.3, 0.7)
        y1 = min(y0 + shadow_h, h)
        img[y0:y1, :] *= shadow_alpha

    img = np.clip(img * 255, 0, 255).astype(np.uint8)
    return img


# ---------------------------------------------------------------------------
# Depth noise injection
# ---------------------------------------------------------------------------

def depth_noise_inject(depth_mm, max_depth_mm=5000.0):
    """Add realistic depth-sensor noise to a depth map.

    Noise types: quantisation, holes (dropouts), flying pixels.

    Parameters
    ----------
    depth_mm : numpy.ndarray
        Depth in millimetres (float32 or uint16).
    max_depth_mm : float
        Maximum depth value for normalisation.

    Returns
    -------
    numpy.ndarray
        Noisy depth map (uint16, mm).
    """
    if not HAS_CV2:
        return depth_mm

    d = depth_mm.astype(np.float32).copy()
    h, w = d.shape[:2]

    # 1. Quantisation (1 mm resolution)
    d = np.round(d)

    # 2. Random holes (drop-out pixels)
    hole_mask = np.random.rand(h, w) < 0.005
    d[hole_mask] = 0.0

    # 3. Flying pixels at depth discontinuities
    if d.ndim == 2:
        dx = cv2.Sobel(d, cv2.CV_32F, 1, 0, ksize=3)
        dy = cv2.Sobel(d, cv2.CV_32F, 0, 1, ksize=3)
        grad_mag = np.sqrt(dx ** 2 + dy ** 2)
        edge_mask = grad_mag > 50.0  # mm threshold for discontinuity
        fly_mask = edge_mask & (np.random.rand(h, w) < 0.3)
        noise_fly = np.random.normal(0, 20.0, size=d.shape).astype(np.float32)
        d[fly_mask] += noise_fly[fly_mask]

    d = np.clip(d, 0, max_depth_mm)
    return d.astype(np.uint16)


# ---------------------------------------------------------------------------
# Multi-object composition using depth buffer
# ---------------------------------------------------------------------------

def compose_scene(objects, bg_image):
    """Compose multiple rendered objects onto a background using depth ordering.

    Parameters
    ----------
    objects : list[dict]
        Each dict must contain:
        - ``rgb``  : BGR uint8 image (H×W×3)
        - ``mask`` : binary mask (H×W), 1 where object exists
        - ``depth``: depth in mm (H×W), 0 where no object
    bg_image : numpy.ndarray
        Background BGR uint8 image (same H×W).

    Returns
    -------
    numpy.ndarray
        Composed BGR uint8 image.
    numpy.ndarray
        Composed depth map (uint16, mm).
    """
    if not HAS_CV2:
        return bg_image, None

    h, w = bg_image.shape[:2]
    composed = bg_image.copy().astype(np.float32)
    composed_depth = np.zeros((h, w), dtype=np.float32)

    # Sort objects far-to-near (painter's algorithm)
    def _mean_depth(obj):
        d = obj["depth"]
        m = obj["mask"]
        vals = d[m > 0]
        return vals.mean() if len(vals) > 0 else float("inf")

    objects_sorted = sorted(objects, key=_mean_depth, reverse=True)

    for obj in objects_sorted:
        rgb = obj["rgb"].astype(np.float32)
        mask = obj["mask"]
        depth = obj["depth"].astype(np.float32)

        alpha = mask.astype(np.float32)[..., None]
        composed = composed * (1 - alpha) + rgb * alpha
        composed_depth = composed_depth * (1 - mask) + depth * mask

    composed = np.clip(composed, 0, 255).astype(np.uint8)
    composed_depth = np.clip(composed_depth, 0, 65535).astype(np.uint16)
    return composed, composed_depth


# ---------------------------------------------------------------------------
# High-level augmentation pipeline
# ---------------------------------------------------------------------------

def augment_scene(rgb_path, depth_path, mask_path, output_dir, image_id):
    """Run the full Sim2Real augmentation pipeline on a single rendered view.

    1. Replace background with synthetic industrial texture.
    2. Apply photometric randomisation.
    3. Inject depth noise.

    Parameters
    ----------
    rgb_path : str
        Path to the rendered RGB image.
    depth_path : str
        Path to the rendered depth image (uint16 mm).
    mask_path : str
        Path to the binary mask image.
    output_dir : str
        Directory for augmented outputs.
    image_id : int
        Image identifier for naming.

    Returns
    -------
    dict | None
        Paths to augmented files, or *None* on failure.
    """
    if not HAS_CV2:
        logger.warning("Sim2Real augmentation skipped: OpenCV/numpy not available")
        return None

    rgb = cv2.imread(rgb_path, cv2.IMREAD_COLOR)
    depth = cv2.imread(depth_path, cv2.IMREAD_UNCHANGED)
    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)

    if rgb is None or depth is None or mask is None:
        logger.error("Failed to read input images for augmentation")
        return None

    h, w = rgb.shape[:2]

    # 1. Background replacement
    bg = generate_background(w, h)
    obj_dict = {"rgb": rgb, "mask": (mask > 127).astype(np.uint8), "depth": depth}
    composed_rgb, composed_depth = compose_scene([obj_dict], bg)

    # 2. Photometric randomisation
    composed_rgb = photometric_randomize(composed_rgb)

    # 3. Depth noise
    composed_depth = depth_noise_inject(composed_depth)

    # Save
    os.makedirs(output_dir, exist_ok=True)
    aug_rgb_path = os.path.join(output_dir, f"{image_id:06d}_aug.png")
    aug_depth_path = os.path.join(output_dir, f"{image_id:06d}_depth_aug.png")
    cv2.imwrite(aug_rgb_path, composed_rgb)
    cv2.imwrite(aug_depth_path, composed_depth)

    return {"rgb": aug_rgb_path, "depth": aug_depth_path}
