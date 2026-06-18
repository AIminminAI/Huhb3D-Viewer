"""
可视化10个样本的 RGB / Mask / Depth 并排对比
用法: python visualize_samples.py [--output vis_output]
"""
import argparse
import numpy as np
from PIL import Image
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = Path(__file__).parent / "sell_Huhb3D-Industrial-100"

CATEGORY_COLORS = {
    0: (128, 128, 128),   # FreeSurface - gray
    1: (0, 0, 255),       # HorizontalPlane - blue
    2: (0, 255, 0),       # LateralPlane_X - green
    3: (255, 0, 0),       # LateralPlane_Z - red
    4: (255, 255, 0),     # NearHorizontal - yellow
    5: (255, 0, 255),     # NearLateral_X - magenta
    6: (0, 255, 255),     # NearLateral_Z - cyan
    7: (255, 128, 0),     # Degenerate - orange
    8: (128, 0, 255),     # ConvexFeature_Bolt - purple
    9: (0, 128, 255),     # ConcaveFeature_Hole - sky blue
    10: (204, 204, 0),    # Flange - dark yellow
    11: (0, 204, 102),    # Boss - teal
    12: (153, 77, 0),     # Chamfer - brown
    13: (204, 102, 153),  # Fillet - pink
    14: (102, 179, 204),  # SphericalSurface - light steel blue
}

CATEGORY_NAMES = {
    0: "FreeSurface", 1: "HorizontalPlane", 2: "LateralPlane_X",
    3: "LateralPlane_Z", 4: "NearHorizontal", 5: "NearLateral_X",
    6: "NearLateral_Z", 7: "Degenerate", 8: "ConvexFeature_Bolt",
    9: "ConcaveFeature_Hole", 10: "Flange", 11: "Boss",
    12: "Chamfer", 13: "Fillet", 14: "SphericalSurface"
}

# Reverse lookup: RGB -> category_id
RGB_TO_CAT = {v: k for k, v in CATEGORY_COLORS.items()}


def rgb_to_category_id(mask_img: np.ndarray) -> np.ndarray:
    """Convert RGB mask to category ID map with tolerance for rounding."""
    h, w = mask_img.shape[:2]
    cat_map = np.zeros((h, w), dtype=np.int8)
    mask_int = mask_img.astype(np.int16)  # avoid uint8 overflow in subtraction
    for cat_id, rgb in CATEGORY_COLORS.items():
        # Allow +/-2 tolerance for OpenGL rounding (e.g. 127 vs 128)
        match = ((np.abs(mask_int[:, :, 0] - rgb[0]) <= 2) &
                 (np.abs(mask_int[:, :, 1] - rgb[1]) <= 2) &
                 (np.abs(mask_int[:, :, 2] - rgb[2]) <= 2))
        cat_map[match] = cat_id
    return cat_map


def load_depth_png(path: Path) -> np.ndarray:
    """Load 16-bit depth PNG (2-channel) and return mm values."""
    raw = np.array(Image.open(path))
    if raw.ndim == 3 and raw.shape[2] == 2:
        depth_mm = raw[:, :, 0].astype(np.uint16) | (raw[:, :, 1].astype(np.uint16) << 8)
    elif raw.ndim == 2:
        depth_mm = raw.astype(np.uint16)
    else:
        depth_mm = raw[:, :, 0].astype(np.uint16)
    return depth_mm


def collect_samples(n_samples: int = 10):
    """Collect diverse samples across objects."""
    samples = []
    obj_dirs = sorted([d for d in BASE.iterdir() if (d / "rgb").exists()])
    if not obj_dirs:
        return samples

    # Pick objects spread across the list
    indices = np.linspace(0, len(obj_dirs) - 1, min(n_samples, len(obj_dirs)), dtype=int)
    for idx in indices:
        obj_dir = obj_dirs[idx]
        # Use frame 1 for simplicity
        frame_id = 1
        rgb_path = obj_dir / "rgb" / f"frame_{frame_id:04d}.png"
        mask_path = obj_dir / "mask" / f"mask_{frame_id:04d}.png"
        depth_path = obj_dir / "depth" / f"depth_{frame_id:04d}.png"

        if rgb_path.exists() and mask_path.exists() and depth_path.exists():
            samples.append((obj_dir.name, frame_id, rgb_path, mask_path, depth_path))

    return samples


def visualize(samples, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)

    for i, (obj_name, frame_id, rgb_path, mask_path, depth_path) in enumerate(samples):
        rgb = np.array(Image.open(rgb_path))
        mask = np.array(Image.open(mask_path))
        depth = load_depth_png(depth_path)

        # Analyze mask categories
        cat_map = rgb_to_category_id(mask)
        # Use non-black mask pixels to find categories (background is black, FreeSurface=0 is gray)
        non_bg_mask = ~((mask[:, :, 0] == 0) & (mask[:, :, 1] == 0) & (mask[:, :, 2] == 0))
        present_cats = sorted(set(cat_map[non_bg_mask].tolist()))

        # Create figure
        fig, axes = plt.subplots(1, 4, figsize=(20, 5))
        fig.suptitle(f"{obj_name} - Frame {frame_id:04d}  |  Mask categories: {len(present_cats)} "
                     f"{[CATEGORY_NAMES.get(c, '?') for c in present_cats]}",
                     fontsize=12, fontweight="bold")

        # RGB
        axes[0].imshow(rgb)
        axes[0].set_title("RGB")
        axes[0].axis("off")

        # Mask (raw RGB)
        axes[1].imshow(mask)
        axes[1].set_title(f"Mask (RGB) - {len(present_cats)} cats")
        axes[1].axis("off")

        # Mask (category ID colormap)
        im = axes[2].imshow(cat_map, cmap="tab20", vmin=0, vmax=14)
        axes[2].set_title("Mask (Category ID)")
        axes[2].axis("off")
        plt.colorbar(im, ax=axes[2], shrink=0.8, ticks=range(15),
                     label="Category ID")

        # Depth
        valid_depth = depth[depth > 0]
        if len(valid_depth) > 0:
            vmin, vmax = valid_depth.min(), valid_depth.max()
        else:
            vmin, vmax = 0, 1
        im_d = axes[3].imshow(depth, cmap="plasma", vmin=vmin, vmax=vmax)
        axes[3].set_title(f"Depth ({vmin}-{vmax} mm)")
        axes[3].axis("off")
        plt.colorbar(im_d, ax=axes[3], shrink=0.8, label="Depth (mm)")

        plt.tight_layout()
        out_path = output_dir / f"sample_{i+1:02d}_{obj_name}.png"
        fig.savefig(str(out_path), dpi=120, bbox_inches="tight")
        plt.close(fig)
        print(f"  [{i+1}/{len(samples)}] {out_path.name} - cats={present_cats} depth=[{vmin},{vmax}]mm")

    # Legend page
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.set_title("Category Color Legend", fontsize=14, fontweight="bold")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 16)
    ax.axis("off")

    for cat_id in range(15):
        rgb = CATEGORY_COLORS[cat_id]
        y = 14.5 - cat_id
        rect = plt.Rectangle((0.5, y - 0.3), 1.2, 0.6,
                              facecolor=np.array(rgb) / 255.0, edgecolor="black")
        ax.add_patch(rect)
        ax.text(2.0, y, f"{cat_id}: {CATEGORY_NAMES[cat_id]}  RGB={rgb}",
                va="center", fontsize=10, family="monospace")

    fig.savefig(str(output_dir / "legend.png"), dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"  Legend saved to legend.png")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="vis_output", help="Output directory")
    parser.add_argument("--samples", type=int, default=10, help="Number of samples")
    args = parser.parse_args()

    print("=" * 60)
    print("  Huhb3D Sample Visualization")
    print("=" * 60)

    samples = collect_samples(args.samples)
    print(f"  Collected {len(samples)} samples")

    output_dir = Path(__file__).parent / args.output
    visualize(samples, output_dir)
    print(f"\n  Done! Output: {output_dir}")


if __name__ == "__main__":
    main()
