import json
import sys
import math
from pathlib import Path
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from step_topology_parser import CATEGORY_NAMES, CATEGORY_COLORS, parse_step_topology

DATASET_DIR = Path(__file__).parent / "sell_Huhb3D-Test-Precision-v4"
STEP_DIR = Path(__file__).parent / "original_models" / "step"
OUTPUT_DIR = Path(__file__).parent / "topology_visualization"

VIS_COLORS = {
    0: (127/255, 127/255, 127/255),
    1: (0, 0, 1),
    2: (0, 1, 0),
    3: (1, 0, 0),
    8: (200/255, 50/255, 50/255),
    9: (50/255, 50/255, 200/255),
    10: (200/255, 150/255, 50/255),
    11: (150/255, 50/255, 200/255),
    12: (100/255, 200/255, 100/255),
    13: (200/255, 100/255, 200/255),
    14: (100/255, 200/255, 200/255),
}

LEGEND_COLORS = {
    0: (127, 127, 127),
    1: (0, 0, 255),
    2: (0, 255, 0),
    3: (255, 0, 0),
    8: (200, 50, 50),
    9: (50, 50, 200),
    10: (200, 150, 50),
    11: (150, 50, 200),
    12: (100, 200, 100),
    13: (200, 100, 200),
    14: (100, 200, 200),
}


def find_step_files():
    step_files = []
    if STEP_DIR.exists():
        for f in STEP_DIR.rglob("*.step"):
            step_files.append(f)
        for f in STEP_DIR.rglob("*.stp"):
            step_files.append(f)
    if not step_files and DATASET_DIR.exists():
        for f in DATASET_DIR.rglob("*.step"):
            step_files.append(f)
        for f in DATASET_DIR.rglob("*.stp"):
            step_files.append(f)
    return step_files


def read_stl_triangles(stl_path):
    triangles = []
    try:
        with open(stl_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        verts = []
        for line in lines:
            line = line.strip()
            if line.startswith("vertex"):
                parts = line.split()
                verts.append([float(parts[1]), float(parts[2]), float(parts[3])])
                if len(verts) == 3:
                    triangles.append(verts[:])
                    verts = []
    except Exception as e:
        print(f"[Visualize] Error reading STL: {e}")
    return triangles


def load_topology_data(topo_dir):
    labels_path = topo_dir / "topology_labels.json"
    summary_path = topo_dir / "topology_summary.json"
    stl_path = topo_dir / "tessellated.stl"
    if not labels_path.exists():
        return None, None, None
    with open(labels_path, "r", encoding="utf-8") as f:
        labels_data = json.load(f)
    summary_data = None
    if summary_path.exists():
        with open(summary_path, "r", encoding="utf-8") as f:
            summary_data = json.load(f)
    tri_verts = read_stl_triangles(stl_path) if stl_path.exists() else []
    return labels_data, summary_data, tri_verts


def render_3d_topology(labels_data, tri_verts, object_name, output_path):
    labels = labels_data["triangle_labels"]
    if not tri_verts or not labels:
        print(f"[Visualize] No triangle data for 3D render: {object_name}")
        return

    fig = plt.figure(figsize=(10, 8), dpi=150)
    ax = fig.add_subplot(111, projection="3d")

    all_x, all_y, all_z = [], [], []

    label_to_tris = defaultdict(list)
    for i, label in enumerate(labels):
        if i < len(tri_verts):
            label_to_tris[label].append(i)

    for cat_id in sorted(label_to_tris.keys()):
        color = VIS_COLORS.get(cat_id, (0.5, 0.5, 0.5))
        polys = []
        for ti in label_to_tris[cat_id]:
            v = tri_verts[ti]
            polys.append(v)
            all_x.extend([v[0][0], v[1][0], v[2][0]])
            all_y.extend([v[0][1], v[1][1], v[2][1]])
            all_z.extend([v[0][2], v[1][2], v[2][2]])
        if polys:
            poly3d = Poly3DCollection(
                polys, alpha=0.8, facecolor=color,
                edgecolor=(0.2, 0.2, 0.2, 0.1), linewidth=0.1
            )
            ax.add_collection3d(poly3d)

    if all_x:
        max_range = max(
            max(all_x) - min(all_x),
            max(all_y) - min(all_y),
            max(all_z) - min(all_z)
        ) / 2
        if max_range < 1e-6:
            max_range = 1.0
        mid_x = (max(all_x) + min(all_x)) / 2
        mid_y = (max(all_y) + min(all_y)) / 2
        mid_z = (max(all_z) + min(all_z)) / 2
        ax.set_xlim(mid_x - max_range * 1.05, mid_x + max_range * 1.05)
        ax.set_ylim(mid_y - max_range * 1.05, mid_y + max_range * 1.05)
        ax.set_zlim(mid_z - max_range * 1.05, mid_z + max_range * 1.05)

    ax.view_init(elev=25, azim=45)
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.set_zlabel("Z")

    cat_counts = defaultdict(int)
    for label in labels:
        cat_counts[label] += 1

    stats_parts = []
    for cat_id in sorted(cat_counts.keys()):
        name = CATEGORY_NAMES.get(cat_id, f"Cat{cat_id}")
        stats_parts.append(f"{name}:{cat_counts[cat_id]}")
    stats_str = " ".join(stats_parts)

    ax.set_title(f"{object_name}\n{stats_str}", fontsize=10)

    legend_handles = []
    for cat_id in sorted(cat_counts.keys()):
        name = CATEGORY_NAMES.get(cat_id, f"Cat{cat_id}")
        rgb = LEGEND_COLORS.get(cat_id, (127, 127, 127))
        color = (rgb[0]/255, rgb[1]/255, rgb[2]/255)
        legend_handles.append(
            plt.Line2D([0], [0], marker="s", color="w",
                       markerfacecolor=color, markersize=8,
                       label=f"{cat_id}: {name}")
        )
    ax.legend(handles=legend_handles, loc="upper left", fontsize=7, framealpha=0.8)

    plt.tight_layout()
    fig.savefig(str(output_path), bbox_inches="tight")
    plt.close(fig)
    print(f"[Visualize] 3D topology saved: {output_path}")


def render_pie_chart(summary_data, object_name, output_path):
    if not summary_data or "categories" not in summary_data:
        print(f"[Visualize] No summary data for pie chart: {object_name}")
        return

    categories = summary_data["categories"]
    cat_ids = sorted(categories.keys(), key=lambda x: int(x))
    labels = []
    sizes = []
    colors = []
    for cid_str in cat_ids:
        cat_info = categories[cid_str]
        cat_id = int(cid_str)
        name = CATEGORY_NAMES.get(cat_id, f"Cat{cid_str}")
        labels.append(f"{name} ({cat_info['triangle_count']})")
        sizes.append(cat_info["triangle_count"])
        rgb = LEGEND_COLORS.get(cat_id, (127, 127, 127))
        colors.append((rgb[0]/255, rgb[1]/255, rgb[2]/255))

    if not sizes:
        return

    fig, ax = plt.subplots(figsize=(8, 6), dpi=150)
    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, colors=colors, autopct="%1.1f%%",
        startangle=90, pctdistance=0.85, textprops={"fontsize": 7}
    )
    for t in autotexts:
        t.set_fontsize(6)
    ax.set_title(f"{object_name} - Topology Distribution", fontsize=10)
    plt.tight_layout()
    fig.savefig(str(output_path), bbox_inches="tight")
    plt.close(fig)
    print(f"[Visualize] Pie chart saved: {output_path}")


def generate_html_index(object_entries, output_path):
    html_parts = []
    html_parts.append("<!DOCTYPE html>")
    html_parts.append("<html lang='en'>")
    html_parts.append("<head>")
    html_parts.append("<meta charset='UTF-8'>")
    html_parts.append("<meta name='viewport' content='width=device-width, initial-scale=1.0'>")
    html_parts.append("<title>Topology Visualization - Huhb3D</title>")
    html_parts.append("<style>")
    html_parts.append("body { font-family: 'Segoe UI', Arial, sans-serif; background: #1a1a2e; color: #e0e0e0; margin: 0; padding: 20px; }")
    html_parts.append("h1 { text-align: center; color: #00d4ff; margin-bottom: 30px; }")
    html_parts.append(".legend { display: flex; flex-wrap: wrap; justify-content: center; gap: 15px; margin-bottom: 30px; padding: 15px; background: #16213e; border-radius: 8px; }")
    html_parts.append(".legend-item { display: flex; align-items: center; gap: 6px; }")
    html_parts.append(".legend-color { width: 20px; height: 20px; border-radius: 3px; border: 1px solid #555; }")
    html_parts.append(".grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(900px, 1fr)); gap: 25px; }")
    html_parts.append(".object-card { background: #16213e; border-radius: 10px; padding: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }")
    html_parts.append(".object-card h2 { color: #00d4ff; margin-top: 0; border-bottom: 1px solid #333; padding-bottom: 10px; }")
    html_parts.append(".viz-row { display: flex; gap: 20px; align-items: flex-start; flex-wrap: wrap; }")
    html_parts.append(".viz-row img { max-width: 100%; border-radius: 6px; }")
    html_parts.append(".viz-3d { flex: 2; min-width: 400px; }")
    html_parts.append(".viz-pie { flex: 1; min-width: 300px; }")
    html_parts.append("</style>")
    html_parts.append("</head>")
    html_parts.append("<body>")
    html_parts.append("<h1>Huhb3D Topology Visualization</h1>")

    html_parts.append("<div class='legend'>")
    for cat_id in sorted(LEGEND_COLORS.keys()):
        name = CATEGORY_NAMES.get(cat_id, f"Cat{cat_id}")
        rgb = LEGEND_COLORS[cat_id]
        html_parts.append(
            f"<div class='legend-item'>"
            f"<div class='legend-color' style='background:rgb({rgb[0]},{rgb[1]},{rgb[2]})'></div>"
            f"<span>{cat_id}: {name}</span>"
            f"</div>"
        )
    html_parts.append("</div>")

    html_parts.append("<div class='grid'>")
    for entry in object_entries:
        name = entry["name"]
        img_3d = entry.get("img_3d", "")
        img_pie = entry.get("img_pie", "")
        html_parts.append("<div class='object-card'>")
        html_parts.append(f"<h2>{name}</h2>")
        html_parts.append("<div class='viz-row'>")
        if img_3d:
            html_parts.append(f"<div class='viz-3d'><img src='{img_3d}' alt='{name} 3D Topology'></div>")
        if img_pie:
            html_parts.append(f"<div class='viz-pie'><img src='{img_pie}' alt='{name} Pie Chart'></div>")
        html_parts.append("</div>")
        html_parts.append("</div>")
    html_parts.append("</div>")

    html_parts.append("</body>")
    html_parts.append("</html>")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(html_parts))
    print(f"[Visualize] HTML index saved: {output_path}")


def process_step_file(step_path):
    object_name = step_path.stem
    obj_output_dir = OUTPUT_DIR / object_name
    obj_output_dir.mkdir(parents=True, exist_ok=True)

    topo_output_dir = obj_output_dir / "topology_output"
    topo_output_dir.mkdir(parents=True, exist_ok=True)

    success = parse_step_topology(str(step_path), str(topo_output_dir))
    if not success:
        print(f"[Visualize] Failed to parse: {step_path}")
        return None

    labels_data, summary_data, tri_verts = load_topology_data(topo_output_dir)
    if labels_data is None:
        print(f"[Visualize] No topology labels found for: {object_name}")
        return None

    img_3d_path = obj_output_dir / f"{object_name}_3d_topology.png"
    render_3d_topology(labels_data, tri_verts, object_name, img_3d_path)

    img_pie_path = obj_output_dir / f"{object_name}_pie_chart.png"
    render_pie_chart(summary_data, object_name, img_pie_path)

    return {
        "name": object_name,
        "img_3d": f"{object_name}/{object_name}_3d_topology.png",
        "img_pie": f"{object_name}/{object_name}_pie_chart.png",
    }


def process_existing_topologies():
    entries = []
    for topo_dir in OUTPUT_DIR.rglob("topology_output"):
        labels_path = topo_dir / "topology_labels.json"
        summary_path = topo_dir / "topology_summary.json"
        if not labels_path.exists():
            continue
        object_name = topo_dir.parent.name

        labels_data, summary_data, tri_verts = load_topology_data(topo_dir)
        if labels_data is None:
            continue

        img_3d_path = topo_dir.parent / f"{object_name}_3d_topology.png"
        render_3d_topology(labels_data, tri_verts, object_name, img_3d_path)

        img_pie_path = topo_dir.parent / f"{object_name}_pie_chart.png"
        render_pie_chart(summary_data, object_name, img_pie_path)

        entries.append({
            "name": object_name,
            "img_3d": f"{object_name}/{object_name}_3d_topology.png",
            "img_pie": f"{object_name}/{object_name}_pie_chart.png",
        })
    return entries


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    step_files = find_step_files()
    print(f"[Visualize] Found {len(step_files)} STEP files")

    all_entries = []

    if step_files:
        for step_path in step_files:
            entry = process_step_file(step_path)
            if entry:
                all_entries.append(entry)
    else:
        print("[Visualize] No STEP files found, checking existing topology outputs...")
        all_entries = process_existing_topologies()

    if all_entries:
        html_path = OUTPUT_DIR / "index.html"
        generate_html_index(all_entries, html_path)
        print(f"\n[Visualize] Done! {len(all_entries)} objects visualized.")
        print(f"[Visualize] Open {html_path} to view results.")
    else:
        print("[Visualize] No objects to visualize.")
        print("[Visualize] Please run generate_original_models.py first to create STEP files,")
        print("[Visualize] or place STEP files in the 'step/' directory.")


if __name__ == "__main__":
    main()
