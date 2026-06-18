"""
Sim2Real 对比可视化报告生成器
生成原始数据集与 Sim2Real 增强数据集的对比 HTML 页面
"""

import json
import base64
from pathlib import Path
from collections import Counter

import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")  # Use non-interactive backend for headless environments
import matplotlib.pyplot as plt

SCRIPT_DIR = Path(__file__).parent
ORIGINAL_DIR = SCRIPT_DIR / "sell_Huhb3D-Industrial-100"
SIM2REAL_DIR = SCRIPT_DIR / "Huhb3D-Sim2Real-500"
OUTPUT_DIR = SCRIPT_DIR / "sim2real_comparison"

NUM_EXAMPLES = 8
DPI = 120


def get_object_dirs():
    """获取原始数据集中所有物体子目录"""
    if not ORIGINAL_DIR.exists():
        print(f"Warning: Original dataset not found at {ORIGINAL_DIR}")
        return []
    dirs = sorted([
        d for d in ORIGINAL_DIR.iterdir()
        if d.is_dir() and (d / "rgb").exists()
    ])
    return dirs


def load_json_safe(path):
    """安全加载 JSON 文件"""
    if not path.exists():
        return None
    try:
        with open(str(path), "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Warning: Failed to load {path}: {e}")
        return None


def count_original_images(obj_dirs):
    """统计原始数据集图像总数"""
    total = 0
    for obj_dir in obj_dirs:
        rgb_dir = obj_dir / "rgb"
        if rgb_dir.exists():
            total += len(list(rgb_dir.glob("*.png")))
    return total


def analyze_sim2real_scenes(scene_metadata):
    """分析 Sim2Real 场景的对象数量分布"""
    obj_counts = Counter()
    visibilities = []
    if scene_metadata is None:
        return obj_counts, visibilities
    for scene_id, scene_info in scene_metadata.items():
        num_obj = int(scene_info.get("num_objects", 0))
        obj_counts[num_obj] += 1
        for obj_info in scene_info.get("objects", []):
            vis = float(obj_info.get("visibility", 1.0))
            visibilities.append(vis)
    return obj_counts, visibilities


def generate_comparison_pairs(obj_dirs, scene_metadata, num_pairs=NUM_EXAMPLES):
    """生成对比图像对：原始单物体 vs Sim2Real 多物体场景"""
    pairs = []
    if scene_metadata is None or not obj_dirs:
        return pairs

    obj_name_to_dir = {d.name: d for d in obj_dirs}

    scene_ids = sorted(scene_metadata.keys(), key=lambda x: int(x))
    step = max(1, len(scene_ids) // num_pairs)
    selected_ids = scene_ids[::step][:num_pairs]

    for scene_id in selected_ids:
        scene_info = scene_metadata[scene_id]
        objects = scene_info.get("objects", [])
        if not objects:
            continue

        sim2real_rgb_path = SIM2REAL_DIR / "rgb" / f"scene_{int(scene_id):06d}.png"
        if not sim2real_rgb_path.exists():
            continue

        first_obj = objects[0]
        obj_name = first_obj["obj_name"]
        frame_num = first_obj["frame_num"]

        obj_dir = obj_name_to_dir.get(obj_name)
        if obj_dir is None:
            continue

        original_rgb_path = obj_dir / "rgb" / f"frame_{int(frame_num):04d}.png"
        if not original_rgb_path.exists():
            original_rgb_path = obj_dir / "rgb" / "frame_0001.png"
        if not original_rgb_path.exists():
            continue

        obj_names_list = [o["obj_name"] for o in objects]
        vis_list = [float(o.get("visibility", 1.0)) for o in objects]

        pairs.append({
            "scene_id": scene_id,
            "original_path": str(original_rgb_path),
            "sim2real_path": str(sim2real_rgb_path),
            "obj_name": obj_name,
            "frame_num": frame_num,
            "num_objects": len(objects),
            "obj_names": obj_names_list,
            "visibilities": vis_list,
        })

    return pairs


def save_comparison_image(pairs, output_dir):
    """保存每对对比图像为 PNG"""
    comparison_dir = output_dir / "comparisons"
    comparison_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = []
    for pair in pairs:
        orig_img = cv2.imread(pair["original_path"])
        s2r_img = cv2.imread(pair["sim2real_path"])
        if orig_img is None or s2r_img is None:
            print(f"  Skipping scene {pair['scene_id']}: cannot read images")
            continue

        orig_img = cv2.resize(orig_img, (400, 300))
        s2r_img = cv2.resize(s2r_img, (400, 300))

        gap = np.ones((300, 20, 3), dtype=np.uint8) * 240
        combined = np.hstack([orig_img, gap, s2r_img])

        label_orig = "Original (Single Object)"
        label_s2r = f"Sim2Real ({pair['num_objects']} Objects)"
        cv2.putText(combined, label_orig, (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 200), 1, cv2.LINE_AA)
        cv2.putText(combined, label_s2r, (430, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 150, 0), 1, cv2.LINE_AA)

        fname = f"comparison_scene_{int(pair['scene_id']):06d}.png"
        fpath = comparison_dir / fname
        cv2.imwrite(str(fpath), combined)
        saved_paths.append(f"comparisons/{fname}")

    return saved_paths


def generate_visibility_chart(dataset_info, output_dir):
    """生成可见度分布柱状图"""
    vis_hist = dataset_info.get("visibility_histogram", {})
    if not vis_hist:
        return None

    bins = sorted(vis_hist.keys())
    counts = [int(vis_hist[b]) for b in bins]

    fig, ax = plt.subplots(figsize=(10, 5))
    colors = []
    for b in bins:
        v = float(b)
        if v < 0.3:
            colors.append("#e74c3c")
        elif v < 0.6:
            colors.append("#f39c12")
        else:
            colors.append("#2ecc71")

    bars = ax.bar(bins, counts, color=colors, edgecolor="#333333", linewidth=0.5)
    ax.set_xlabel("Visibility Ratio", fontsize=11, fontweight="bold")
    ax.set_ylabel("Instance Count", fontsize=11, fontweight="bold")
    ax.set_title("Sim2Real Visibility Distribution", fontsize=13, fontweight="bold")
    ax.grid(axis="y", alpha=0.3)
    ax.set_axisbelow(True)

    for bar, count in zip(bars, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 5,
                str(count), ha="center", va="bottom", fontsize=8, fontweight="bold")

    legend_items = [
        plt.Rectangle((0, 0), 1, 1, fc="#e74c3c", label="Heavy Occlusion (<0.3)"),
        plt.Rectangle((0, 0), 1, 1, fc="#f39c12", label="Partial Occlusion (0.3-0.6)"),
        plt.Rectangle((0, 0), 1, 1, fc="#2ecc71", label="Light/No Occlusion (>0.6)"),
    ]
    ax.legend(handles=legend_items, fontsize=9, loc="upper left")

    plt.tight_layout()
    chart_path = output_dir / "visibility_distribution.png"
    fig.savefig(str(chart_path), dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return "visibility_distribution.png"


def generate_objects_per_scene_chart(obj_counts, output_dir):
    """生成每场景物体数量分布图"""
    if not obj_counts:
        return None

    fig, ax = plt.subplots(figsize=(8, 5))
    sorted_keys = sorted(obj_counts.keys())
    values = [obj_counts[k] for k in sorted_keys]
    colors = plt.cm.Blues(np.linspace(0.4, 0.8, len(sorted_keys)))

    bars = ax.bar([str(k) for k in sorted_keys], values, color=colors,
                  edgecolor="#333333", linewidth=0.5)
    ax.set_xlabel("Objects per Scene", fontsize=11, fontweight="bold")
    ax.set_ylabel("Scene Count", fontsize=11, fontweight="bold")
    ax.set_title("Sim2Real Objects-per-Scene Distribution", fontsize=13, fontweight="bold")
    ax.grid(axis="y", alpha=0.3)
    ax.set_axisbelow(True)

    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2,
                str(val), ha="center", va="bottom", fontsize=10, fontweight="bold")

    plt.tight_layout()
    chart_path = output_dir / "objects_per_scene.png"
    fig.savefig(str(chart_path), dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return "objects_per_scene.png"


def img_to_base64(img_path):
    """将图片转为 base64 内联数据"""
    with open(img_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    return f"data:image/png;base64,{data}"


def generate_html(pairs, comparison_paths, dataset_info, obj_counts,
                  vis_chart_path, obj_chart_path, obj_dirs, output_dir):
    """生成自包含 HTML 对比报告"""

    total_original = count_original_images(obj_dirs)
    num_objects = len(obj_dirs)

    sim2real_scenes = int(dataset_info.get("num_scenes", 0)) if dataset_info else 0
    total_instances = int(dataset_info.get("total_object_instances", 0)) if dataset_info else 0
    total_visible = int(dataset_info.get("total_visible_instances", 0)) if dataset_info else 0
    vis_threshold = float(dataset_info.get("visibility_threshold", 0.1)) if dataset_info else 0.1
    obj_range = dataset_info.get("objects_per_scene_range", [2, 6]) if dataset_info else [2, 6]

    vis_chart_b64 = img_to_base64(output_dir / vis_chart_path) if vis_chart_path else ""
    obj_chart_b64 = img_to_base64(output_dir / obj_chart_path) if obj_chart_path else ""

    comparison_cards = ""
    for i, pair in enumerate(pairs):
        comp_path = comparison_paths[i] if i < len(comparison_paths) else None
        if comp_path is None:
            continue
        comp_b64 = img_to_base64(output_dir / comp_path)

        obj_list_html = ""
        for name, vis in zip(pair["obj_names"], pair["visibilities"]):
            vis_pct = f"{vis * 100:.1f}%"
            if vis < 0.3:
                color = "#e74c3c"
            elif vis < 0.6:
                color = "#f39c12"
            else:
                color = "#2ecc71"
            obj_list_html += f'<span style="color:{color}; margin-right:8px;">{name} ({vis_pct})</span>'

        comparison_cards += f'''
        <div class="comparison-card">
            <h3>Scene {pair["scene_id"]} — {pair["num_objects"]} Objects</h3>
            <img src="{comp_b64}" alt="Scene {pair["scene_id"]}">
            <div class="obj-list">{obj_list_html}</div>
        </div>'''

    augmentation_types = {
        "Background Styles": [
            "Concrete (混凝土)", "Metal Floor (金属地板)", "Workshop (车间)",
            "Conveyor (传送带)", "Gradient (渐变)", "Noise (噪声)", "Textured (纹理)"
        ],
        "Photometric Changes": [
            "Brightness (亮度 0.5-1.5x)", "Contrast (对比度 0.7-1.3x)",
            "Gamma Correction (伽马 0.6-1.8)", "Hue Shift (色调偏移)",
            "Shadow (阴影)", "Highlight (高光)", "Color Temperature (色温)"
        ],
        "Depth Noise": [
            "Gaussian Noise (高斯噪声 1-5mm)", "Quantization (量化 1/2/5mm)",
            "Hole Simulation (空洞 0.5-3%)", "Flying Pixels (飞点)",
            "Edge Dilation (边缘膨胀 1-3px)", "Multipath Interference (多径干扰)"
        ]
    }

    aug_html = ""
    for category, items in augmentation_types.items():
        items_html = "".join([f'<li>{item}</li>' for item in items])
        aug_html += f'''
        <div class="aug-category">
            <h4>{category}</h4>
            <ul>{items_html}</ul>
        </div>'''

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Huhb3D Sim2Real 对比报告</title>
<style>
body {{
    font-family: 'Segoe UI', 'Microsoft YaHei', Arial, sans-serif;
    margin: 0; padding: 20px;
    background: #0f1923; color: #e0e0e0;
}}
h1 {{
    text-align: center; color: #00d4ff;
    font-size: 2.2em; margin-bottom: 5px;
}}
h2 {{
    text-align: center; color: #8899aa;
    font-size: 1.1em; font-weight: normal; margin-top: 0;
    margin-bottom: 30px;
}}
.stats-row {{
    display: flex; justify-content: center;
    gap: 20px; margin: 25px 0; flex-wrap: wrap;
}}
.stat-card {{
    text-align: center; padding: 18px 28px;
    background: #1a2a3a; border-radius: 10px;
    border: 1px solid #2a4a6a; min-width: 160px;
}}
.stat-card .value {{
    font-size: 2em; font-weight: bold;
}}
.stat-card .label {{
    font-size: 0.85em; color: #8899aa; margin-top: 5px;
}}
.stat-card.original .value {{ color: #ff6b6b; border-color: #ff6b6b; }}
.stat-card.sim2real .value {{ color: #51cf66; border-color: #51cf66; }}
.section-title {{
    color: #00d4ff; font-size: 1.5em;
    margin: 40px 0 20px 0; padding-bottom: 8px;
    border-bottom: 2px solid #1a3a5a;
}}
.comparison-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(860px, 1fr));
    gap: 20px; margin-top: 20px;
}}
.comparison-card {{
    background: #1a2a3a; border-radius: 10px;
    padding: 15px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.3);
}}
.comparison-card h3 {{
    color: #00d4ff; margin: 0 0 10px 0; font-size: 1.1em;
}}
.comparison-card img {{
    width: 100%; border-radius: 6px;
}}
.obj-list {{
    margin-top: 8px; font-size: 0.85em; line-height: 1.6;
}}
.table-container {{
    overflow-x: auto; margin: 20px 0;
}}
table {{
    width: 100%; border-collapse: collapse;
    background: #1a2a3a; border-radius: 8px;
    overflow: hidden;
}}
th {{
    background: #2a4a6a; color: #00d4ff;
    padding: 12px 16px; text-align: center;
    font-size: 0.95em;
}}
td {{
    padding: 10px 16px; text-align: center;
    border-bottom: 1px solid #1a3a5a;
    font-size: 0.9em;
}}
tr:hover {{ background: #223344; }}
td.highlight-orig {{ color: #ff6b6b; font-weight: bold; }}
td.highlight-s2r {{ color: #51cf66; font-weight: bold; }}
.chart-container {{
    text-align: center; margin: 20px 0;
    background: #1a2a3a; border-radius: 10px;
    padding: 20px;
}}
.chart-container img {{
    max-width: 100%; border-radius: 6px;
}}
.aug-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 20px; margin-top: 20px;
}}
.aug-category {{
    background: #1a2a3a; border-radius: 10px;
    padding: 15px 20px;
    border-left: 4px solid #00d4ff;
}}
.aug-category h4 {{
    color: #00d4ff; margin: 0 0 10px 0;
}}
.aug-category ul {{
    margin: 0; padding-left: 20px;
    color: #b0c4d8;
}}
.aug-category li {{
    margin: 4px 0; font-size: 0.9em;
}}
</style>
</head>
<body>

<h1>Huhb3D Sim2Real 对比报告</h1>
<h2>原始数据集 vs Sim2Real 增强数据集 — 全面对比分析</h2>

<div class="stats-row">
    <div class="stat-card original">
        <div class="value">{total_original:,}</div>
        <div class="label">原始图像总数</div>
    </div>
    <div class="stat-card original">
        <div class="value">{num_objects}</div>
        <div class="label">物体类别数</div>
    </div>
    <div class="stat-card sim2real">
        <div class="value">{sim2real_scenes}</div>
        <div class="label">Sim2Real 场景数</div>
    </div>
    <div class="stat-card sim2real">
        <div class="value">{total_instances:,}</div>
        <div class="label">物体实例总数</div>
    </div>
    <div class="stat-card sim2real">
        <div class="value">{total_visible:,}</div>
        <div class="label">可见实例数</div>
    </div>
</div>

<h3 class="section-title">📊 统计对比表</h3>
<div class="table-container">
<table>
<thead>
<tr>
    <th>指标</th>
    <th>原始数据集 (Original)</th>
    <th>Sim2Real 增强数据集</th>
</tr>
</thead>
<tbody>
<tr>
    <td>图像/场景数量</td>
    <td class="highlight-orig">{total_original:,} 张图像</td>
    <td class="highlight-s2r">{sim2real_scenes} 个场景</td>
</tr>
<tr>
    <td>每场景物体数</td>
    <td class="highlight-orig">1</td>
    <td class="highlight-s2r">{obj_range[0]}-{obj_range[1]}</td>
</tr>
<tr>
    <td>遮挡程度</td>
    <td class="highlight-orig">0% (无遮挡)</td>
    <td class="highlight-s2r">各种遮挡级别</td>
</tr>
<tr>
    <td>背景类型</td>
    <td class="highlight-orig">纯色/简单背景</td>
    <td class="highlight-s2r">7种工业背景</td>
</tr>
<tr>
    <td>深度噪声</td>
    <td class="highlight-orig">无</td>
    <td class="highlight-s2r">高斯/量化/空洞/飞点/多径</td>
</tr>
<tr>
    <td>光度变化</td>
    <td class="highlight-orig">无</td>
    <td class="highlight-s2r">亮度/对比度/伽马/色温/阴影</td>
</tr>
<tr>
    <td>可见度阈值</td>
    <td class="highlight-orig">N/A</td>
    <td class="highlight-s2r">{vis_threshold}</td>
</tr>
<tr>
    <td>物体实例总数</td>
    <td class="highlight-orig">{total_original:,}</td>
    <td class="highlight-s2r">{total_instances:,}</td>
</tr>
<tr>
    <td>标注格式</td>
    <td>scene_gt.json / coco_annotations.json</td>
    <td>scene_gt.json / coco_annotations.json / scene_metadata.json</td>
</tr>
</tbody>
</table>
</div>

<h3 class="section-title">🖼️ 逐场景对比</h3>
<div class="comparison-grid">
{comparison_cards}
</div>

<h3 class="section-title">📈 可见度分布</h3>
<div class="chart-container">
    <img src="{vis_chart_b64}" alt="Visibility Distribution">
</div>

<h3 class="section-title">📈 每场景物体数量分布</h3>
<div class="chart-container">
    <img src="{obj_chart_b64}" alt="Objects per Scene">
</div>

<h3 class="section-title">🔧 增强多样性总结</h3>
<div class="aug-grid">
{aug_html}
</div>

</body>
</html>"""

    html_path = output_dir / "sim2real_comparison.html"
    html_path.write_text(html, encoding="utf-8")
    return html_path


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Huhb3D Sim2Real 对比报告生成器")
    print("=" * 60)

    # 1. 加载原始数据集信息
    obj_dirs = get_object_dirs()
    print(f"\n[1/6] 原始数据集: 找到 {len(obj_dirs)} 个物体目录")
    total_original = count_original_images(obj_dirs)
    print(f"       原始图像总数: {total_original}")

    # 2. 加载 Sim2Real 数据集信息
    dataset_info = load_json_safe(SIM2REAL_DIR / "dataset_info.json")
    scene_metadata = load_json_safe(SIM2REAL_DIR / "scene_metadata.json")
    if dataset_info:
        print(f"[2/6] Sim2Real 数据集: {dataset_info.get('num_scenes', '?')} 场景, "
              f"{dataset_info.get('total_object_instances', '?')} 实例")
    else:
        print("[2/6] Sim2Real 数据集信息未找到")

    # 3. 分析 Sim2Real 场景
    obj_counts, visibilities = analyze_sim2real_scenes(scene_metadata)
    print(f"[3/6] 场景分析: 物体数量分布 {dict(obj_counts)}")

    # 4. 生成对比图像对
    pairs = generate_comparison_pairs(obj_dirs, scene_metadata, NUM_EXAMPLES)
    print(f"[4/6] 生成 {len(pairs)} 对对比图像")

    # 5. 保存对比 PNG
    comparison_paths = save_comparison_image(pairs, OUTPUT_DIR)
    print(f"[5/6] 保存 {len(comparison_paths)} 张对比 PNG")

    # 6. 生成图表
    vis_chart_path = None
    obj_chart_path = None
    if dataset_info:
        vis_chart_path = generate_visibility_chart(dataset_info, OUTPUT_DIR)
        print(f"       可见度分布图: {vis_chart_path}")
    if obj_counts:
        obj_chart_path = generate_objects_per_scene_chart(obj_counts, OUTPUT_DIR)
        print(f"       物体数量分布图: {obj_chart_path}")

    # 7. 生成 HTML
    html_path = generate_html(
        pairs, comparison_paths, dataset_info, obj_counts,
        vis_chart_path, obj_chart_path, obj_dirs, OUTPUT_DIR
    )
    print(f"\n[完成] HTML 报告: {html_path}")
    print(f"       输出目录: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
