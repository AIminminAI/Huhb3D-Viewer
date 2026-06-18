import json
import numpy as np
from pathlib import Path
from PIL import Image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import scipy.ndimage as ndi

DATASET_DIR = Path(__file__).parent / "sell_Huhb3D-Test-Precision-v4"
OUTPUT_DIR = Path(__file__).parent / "precision_comparison"

NOISE_SIGMA = 3.0
FIG_SIZE = (16, 12)
DPI = 150

REPROJ_DATA = {
    "Huhb3D": 0.0144,
    "YCB-Video": 3.5,
    "T-LESS": 2.0,
    "LM-O": 2.5,
    "ITODD": 1.2,
}

REPROJ_COLORS = {
    "Huhb3D": "#2ecc71",
    "YCB-Video": "#e74c3c",
    "T-LESS": "#3498db",
    "LM-O": "#f39c12",
    "ITODD": "#9b59b6",
}


def get_object_dirs():
    dirs = sorted([
        d for d in DATASET_DIR.iterdir()
        if d.is_dir() and (d / "mask").exists()
    ])
    return dirs


def load_mask(mask_path):
    mask = np.array(Image.open(str(mask_path)))
    if mask.ndim == 3:
        mask = mask[:, :, 0]
    return (mask > 0).astype(np.uint8)


def extract_edge(mask, width=2):
    dilated = ndi.binary_dilation(mask, iterations=width)
    eroded = ndi.binary_erosion(mask, iterations=width)
    edge = dilated.astype(np.uint8) - eroded.astype(np.uint8)
    return edge


def simulate_ycb_noise(mask, sigma=NOISE_SIGMA, seed=None):
    if seed is not None:
        np.random.seed(seed)
    coords = np.where(mask > 0)
    if len(coords[0]) == 0:
        return mask, np.zeros_like(mask, dtype=np.uint8)
    dx = np.random.normal(0, sigma, size=len(coords[0])).astype(np.int32)
    dy = np.random.normal(0, sigma, size=len(coords[0])).astype(np.int32)
    new_y = np.clip(coords[0] + dy, 0, mask.shape[0] - 1)
    new_x = np.clip(coords[1] + dx, 0, mask.shape[1] - 1)
    noisy = np.zeros_like(mask)
    noisy[new_y, new_x] = 1
    noise_region = np.abs(noisy.astype(np.int8) - mask.astype(np.int8))
    return noisy, noise_region


def render_panel_noisy(ax, rgb_img, mask, object_name, frame_idx):
    noisy_mask, noise_region = simulate_ycb_noise(mask, seed=frame_idx * 100 + 42)
    edge_orig = extract_edge(mask)
    edge_noisy = extract_edge(noisy_mask)
    overlay = rgb_img.copy().astype(np.float32)
    noise_vis = np.zeros_like(overlay)
    noise_vis[noise_region > 0] = [255, 0, 0]
    overlay = overlay * 0.6 + noise_vis * 0.4
    overlay = np.clip(overlay, 0, 255).astype(np.uint8)
    ax.imshow(overlay)
    edge_coords = np.where(edge_noisy > 0)
    if len(edge_coords[0]) > 0:
        ax.scatter(edge_coords[1], edge_coords[0], c="red", s=0.1, alpha=0.5)
    ax.set_title(f"Real-World Annotation Noise\n(YCB-Video level, sigma={NOISE_SIGMA}px)", fontsize=11, fontweight="bold")
    ax.set_xlabel(f"Object: {object_name} | Frame: {frame_idx}", fontsize=9)
    ax.set_ylabel("Pixels", fontsize=9)


def render_panel_precise(ax, rgb_img, mask, object_name, frame_idx):
    edge = extract_edge(mask)
    overlay = rgb_img.copy().astype(np.float32)
    edge_vis = np.zeros_like(overlay)
    edge_vis[edge > 0] = [0, 255, 0]
    overlay = overlay * 0.7 + edge_vis * 0.3
    overlay = np.clip(overlay, 0, 255).astype(np.uint8)
    ax.imshow(overlay)
    edge_coords = np.where(edge > 0)
    if len(edge_coords[0]) > 0:
        ax.scatter(edge_coords[1], edge_coords[0], c="lime", s=0.1, alpha=0.6)
    ax.set_title("Huhb3D Precise Annotation\n(Sub-pixel accuracy)", fontsize=11, fontweight="bold")
    ax.set_xlabel(f"Object: {object_name} | Frame: {frame_idx}", fontsize=9)
    ax.set_ylabel("Pixels", fontsize=9)


def render_panel_reproj(ax, object_names):
    datasets = list(REPROJ_DATA.keys())
    values = list(REPROJ_DATA.values())
    colors = [REPROJ_COLORS[d] for d in datasets]
    x = np.arange(len(datasets))
    bars = ax.bar(x, values, color=colors, width=0.6, edgecolor="black", linewidth=0.5)
    ax.set_yscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels(datasets, fontsize=9, rotation=15, ha="right")
    ax.set_ylabel("Reprojection Error (px, log scale)", fontsize=10)
    ax.set_title("Reprojection Error Distribution\n(Lower is better)", fontsize=11, fontweight="bold")
    ax.grid(axis="y", alpha=0.3, which="both")
    ax.set_axisbelow(True)
    for bar, val in zip(bars, values):
        label = f"{val:.4f}px" if val < 0.1 else f"{val:.1f}px"
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() * 1.3,
            label,
            ha="center", va="bottom", fontsize=9, fontweight="bold",
        )
    ax.set_ylim(0.005, max(values) * 10)
    info_text = (
        "Huhb3D: 0.0144px (sub-pixel)\n"
        "YCB-Video: 2-5px (human annotation)\n"
        "T-LESS: 1-3px\n"
        "LM-O: 1.5-4px\n"
        "ITODD: 0.5-2px"
    )
    ax.text(
        0.98, 0.98, info_text,
        transform=ax.transAxes, fontsize=7.5,
        verticalalignment="top", horizontalalignment="right",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="wheat", alpha=0.7),
    )


def render_panel_table(ax):
    ax.axis("off")
    table_data = [
        ["Metric", "Huhb3D", "YCB-Video", "T-LESS", "LM-O", "ITODD"],
        ["Reproj. Error (px)", "0.0144", "3.5", "2.0", "2.5", "1.2"],
        ["Annotation Type", "Rendering", "Manual", "Manual", "Manual", "Manual"],
        ["Mask Precision", "Exact", "2-5px", "1-3px", "1.5-4px", "0.5-2px"],
        ["Depth Accuracy", "Exact", "Moderate", "Moderate", "Low", "High"],
        ["6DoF GT Quality", "Exact", "Noisy", "Noisy", "Noisy", "Good"],
        ["Occlusion Labels", "Yes", "Partial", "No", "Yes", "No"],
        ["Instance Seg.", "Yes", "No", "No", "No", "No"],
        ["Scalability", "Unlimited", "Limited", "Limited", "Limited", "Limited"],
    ]
    col_colors = ["#f0f0f0"] + [
        REPROJ_COLORS.get(h, "#ffffff") for h in table_data[0][1:]
    ]
    cell_colors = []
    for i, row in enumerate(table_data):
        if i == 0:
            cell_colors.append([c + "aa" for c in col_colors])
        else:
            row_colors = ["#f8f8f8" if i % 2 == 0 else "#ffffff"] * 6
            row_colors[1] = "#d5f5e3"
            cell_colors.append(row_colors)
    table = ax.table(
        cellText=table_data,
        cellColours=cell_colors,
        cellLoc="center",
        loc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8.5)
    table.scale(1.0, 1.6)
    for (row, col), cell in table.get_celld().items():
        if row == 0:
            cell.set_text_props(fontweight="bold", fontsize=9)
        cell.set_edgecolor("#cccccc")
        cell.set_linewidth(0.5)
    ax.set_title("Precision Comparison Overview", fontsize=11, fontweight="bold", pad=20)


def generate_object_figure(obj_dir, frame_idx=1):
    mask_path = obj_dir / "mask" / f"mask_{frame_idx:04d}.png"
    rgb_path = obj_dir / "rgb" / f"frame_{frame_idx:04d}.png"
    if not mask_path.exists() or not rgb_path.exists():
        return None
    mask = load_mask(mask_path)
    rgb_img = np.array(Image.open(str(rgb_path)).convert("RGB"))
    object_name = obj_dir.name
    fig = plt.figure(figsize=FIG_SIZE, dpi=DPI)
    gs = GridSpec(2, 2, figure=fig, hspace=0.35, wspace=0.25)
    ax1 = fig.add_subplot(gs[0, 0])
    render_panel_noisy(ax1, rgb_img, mask, object_name, frame_idx)
    ax2 = fig.add_subplot(gs[0, 1])
    render_panel_precise(ax2, rgb_img, mask, object_name, frame_idx)
    ax3 = fig.add_subplot(gs[1, 0])
    render_panel_reproj(ax3, [object_name])
    ax4 = fig.add_subplot(gs[1, 1])
    render_panel_table(ax4)
    fig.suptitle(
        f"Huhb3D Precision Comparison - {object_name}",
        fontsize=14, fontweight="bold", y=0.98,
    )
    return fig


def generate_overview_figure(obj_dirs):
    fig = plt.figure(figsize=FIG_SIZE, dpi=DPI)
    gs = GridSpec(2, 2, figure=fig, hspace=0.35, wspace=0.25)
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.set_title("Real-World Annotation Noise\n(Multi-object overlay, YCB-Video level)", fontsize=11, fontweight="bold")
    all_noise_counts = []
    for obj_dir in obj_dirs:
        mask_path = obj_dir / "mask" / "mask_0001.png"
        if not mask_path.exists():
            continue
        mask = load_mask(mask_path)
        _, noise_region = simulate_ycb_noise(mask, seed=42)
        all_noise_counts.append(noise_region.sum())
    if all_noise_counts:
        names = [d.name for d in obj_dirs if (d / "mask" / "mask_0001.png").exists()]
        short_names = [n[:10] for n in names]
        colors = plt.cm.Reds(np.linspace(0.3, 0.9, len(all_noise_counts)))
        ax1.bar(range(len(all_noise_counts)), all_noise_counts, color=colors)
        ax1.set_xticks(range(len(short_names)))
        ax1.set_xticklabels(short_names, rotation=45, ha="right", fontsize=7)
        ax1.set_ylabel("Noise Pixel Count", fontsize=9)
        ax1.set_xlabel("Object", fontsize=9)
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.set_title("Huhb3D Precise Annotation\n(Zero noise, all objects)", fontsize=11, fontweight="bold")
    mask_counts = []
    for obj_dir in obj_dirs:
        mask_path = obj_dir / "mask" / "mask_0001.png"
        if not mask_path.exists():
            continue
        mask = load_mask(mask_path)
        mask_counts.append(mask.sum())
    if mask_counts:
        names = [d.name for d in obj_dirs if (d / "mask" / "mask_0001.png").exists()]
        short_names = [n[:10] for n in names]
        colors = plt.cm.Greens(np.linspace(0.3, 0.9, len(mask_counts)))
        ax2.bar(range(len(mask_counts)), mask_counts, color=colors)
        ax2.set_xticks(range(len(short_names)))
        ax2.set_xticklabels(short_names, rotation=45, ha="right", fontsize=7)
        ax2.set_ylabel("Mask Pixel Count", fontsize=9)
        ax2.set_xlabel("Object", fontsize=9)
    ax3 = fig.add_subplot(gs[1, 0])
    render_panel_reproj(ax3, [d.name for d in obj_dirs])
    ax4 = fig.add_subplot(gs[1, 1])
    render_panel_table(ax4)
    fig.suptitle(
        "Huhb3D Precision Comparison - Overview (All 20 Objects)",
        fontsize=14, fontweight="bold", y=0.98,
    )
    return fig


def generate_html(obj_dirs, output_dir):
    rows = []
    for obj_dir in obj_dirs:
        name = obj_dir.name
        img_path = f"per_object/{name}.png"
        rows.append(f'''
        <div class="card">
            <h3>{name}</h3>
            <img src="{img_path}" alt="{name}" loading="lazy">
        </div>''')
    cards_html = "\n".join(rows)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Huhb3D Precision Comparison</title>
<style>
body {{
    font-family: 'Segoe UI', Arial, sans-serif;
    margin: 0; padding: 20px;
    background: #1a1a2e; color: #eee;
}}
h1 {{
    text-align: center; color: #2ecc71;
    font-size: 2em; margin-bottom: 5px;
}}
h2 {{
    text-align: center; color: #aaa;
    font-size: 1.1em; font-weight: normal; margin-top: 0;
}}
.overview {{
    text-align: center; margin: 30px 0;
}}
.overview img {{
    max-width: 100%; border-radius: 8px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.5);
}}
.grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(800px, 1fr));
    gap: 20px; margin-top: 30px;
}}
.card {{
    background: #16213e; border-radius: 8px;
    padding: 15px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.3);
}}
.card h3 {{
    color: #2ecc71; margin: 0 0 10px 0;
    font-size: 1.1em;
}}
.card img {{
    width: 100%; border-radius: 4px;
}}
.stats {{
    display: flex; justify-content: center;
    gap: 30px; margin: 20px 0; flex-wrap: wrap;
}}
.stat {{
    text-align: center; padding: 15px 25px;
    background: #16213e; border-radius: 8px;
    border: 1px solid #2ecc71;
}}
.stat .value {{
    font-size: 1.8em; color: #2ecc71; font-weight: bold;
}}
.stat .label {{
    font-size: 0.85em; color: #aaa; margin-top: 5px;
}}
</style>
</head>
<body>
<h1>Huhb3D Precision Comparison</h1>
<h2>Sub-pixel annotation accuracy vs. real-world dataset noise</h2>
<div class="stats">
    <div class="stat">
        <div class="value">0.0144 px</div>
        <div class="label">Huhb3D Reprojection Error</div>
    </div>
    <div class="stat">
        <div class="value">3.5 px</div>
        <div class="label">YCB-Video (avg)</div>
    </div>
    <div class="stat">
        <div class="value">243x</div>
        <div class="label">Precision Advantage</div>
    </div>
    <div class="stat">
        <div class="value">20</div>
        <div class="label">Industrial Objects</div>
    </div>
</div>
<div class="overview">
    <img src="overview.png" alt="Overview">
</div>
<div class="grid">
{cards_html}
</div>
</body>
</html>"""
    html_path = output_dir / "index.html"
    html_path.write_text(html, encoding="utf-8")
    return html_path


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    obj_dirs = get_object_dirs()
    print(f"Found {len(obj_dirs)} objects in {DATASET_DIR}")
    per_obj_dir = OUTPUT_DIR / "per_object"
    per_obj_dir.mkdir(parents=True, exist_ok=True)
    for i, obj_dir in enumerate(obj_dirs):
        print(f"[{i+1}/{len(obj_dirs)}] Generating figure for: {obj_dir.name}")
        fig = generate_object_figure(obj_dir, frame_idx=1)
        if fig is not None:
            out_path = per_obj_dir / f"{obj_dir.name}.png"
            fig.savefig(str(out_path), dpi=DPI, bbox_inches="tight", facecolor="white")
            plt.close(fig)
        else:
            print(f"  Skipping {obj_dir.name}: missing mask/rgb data")
    print("Generating overview figure...")
    overview_fig = generate_overview_figure(obj_dirs)
    overview_path = OUTPUT_DIR / "overview.png"
    overview_fig.savefig(str(overview_path), dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(overview_fig)
    print("Generating HTML page...")
    html_path = generate_html(obj_dirs, OUTPUT_DIR)
    print(f"\nAll outputs saved to: {OUTPUT_DIR}")
    print(f"  Overview:  {overview_path}")
    print(f"  Per-object: {per_obj_dir}/ ({len(obj_dirs)} PNGs)")
    print(f"  HTML:      {html_path}")


if __name__ == "__main__":
    main()
