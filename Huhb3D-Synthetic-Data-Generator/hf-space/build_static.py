"""
build_static.py - Generate a self-contained index.html for HuggingFace Space
All images (base64) and JSON data are embedded directly into the HTML.
No external file requests needed - zero jitter, zero loading failures.
"""

import base64
import json
from pathlib import Path

DEMO_DIR = Path(__file__).parent / "demo_data"


def image_to_base64(path):
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except (FileNotFoundError, IOError):
        return ""


def main():
    rgb_dir = DEMO_DIR / "rgb"
    mask_dir = DEMO_DIR / "mask"

    rgb_files = sorted(rgb_dir.glob("*.png")) if rgb_dir.exists() else []
    mask_files = sorted(mask_dir.glob("*.png")) if mask_dir.exists() else []

    rgb_b64 = [image_to_base64(f) for f in rgb_files]
    mask_b64 = [image_to_base64(f) for f in mask_files]

    manifest = {}
    manifest_path = DEMO_DIR / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    gt_6dof = "null"
    gt_path = DEMO_DIR / "gt_6dof.json"
    if gt_path.exists():
        gt_6dof = gt_path.read_text(encoding="utf-8")

    scene_camera = "null"
    sc_path = DEMO_DIR / "scene_camera.json"
    if sc_path.exists():
        scene_camera = sc_path.read_text(encoding="utf-8")

    scene_gt = "null"
    sg_path = DEMO_DIR / "scene_gt.json"
    if sg_path.exists():
        scene_gt = sg_path.read_text(encoding="utf-8")

    camera_poses = "null"
    cp_path = DEMO_DIR / "camera_poses.json"
    if cp_path.exists():
        camera_poses = cp_path.read_text(encoding="utf-8")

    label_legend = ""
    ll_path = DEMO_DIR / "label_legend.txt"
    if ll_path.exists():
        label_legend = ll_path.read_text(encoding="utf-8")

    rgb_val = manifest.get("rgb_count", len(rgb_files))
    mask_val = manifest.get("mask_count", len(mask_files))
    depth_val = manifest.get("depth_count", 0)
    dof_val = "✅" if manifest.get("has_6dof_gt", False) else "❌"
    num_images = min(len(rgb_files), len(mask_files))

    js_rgb_array = "[" + ",".join(f'"{b}"' for b in rgb_b64) + "]"
    js_mask_array = "[" + ",".join(f'"{b}"' for b in mask_b64) + "]"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Huhb3D Synthetic Data Generator - Demo</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#0e1117;color:#e0e0e0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;line-height:1.6}}
.c{{max-width:1200px;margin:0 auto;padding:20px}}
h1{{font-size:1.8em;margin-bottom:4px}}
.sub{{color:#aaa;margin-bottom:16px}}
.warn{{background:#332b00;border:1px solid #665200;border-radius:8px;padding:12px 16px;margin-bottom:20px;color:#ffc107;font-size:0.9em}}
.warn a{{color:#4fc3f7}}
.st{{font-size:1.3em;font-weight:600;margin:24px 0 12px;padding-bottom:8px;border-bottom:1px solid #333}}
.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px}}
.m{{background:#1a1a2e;border-radius:8px;padding:16px;text-align:center}}
.m .v{{font-size:2em;font-weight:700}}
.m .l{{color:#aaa;font-size:0.9em}}
.sr{{display:flex;align-items:center;gap:12px;margin-bottom:16px}}
.sr label{{color:#ccc;font-weight:600;font-size:14px;white-space:nowrap}}
.sr input[type=range]{{flex:1;accent-color:#4fc3f7}}
.ig{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}}
.ic{{text-align:center}}
.ic .it{{color:#ccc;font-weight:600;margin-bottom:8px;font-size:14px}}
.iw{{background:#1a1a2e;border-radius:6px;overflow:hidden;aspect-ratio:4/3;display:flex;align-items:center;justify-content:center}}
.iw img{{max-width:100%;max-height:100%;object-fit:contain;display:block}}
.iw .ph{{color:#888;font-size:13px;padding:20px}}
.tabs{{display:flex;gap:4px;margin:16px 0 0;border-bottom:2px solid #333}}
.tab{{padding:8px 16px;cursor:pointer;border-radius:6px 6px 0 0;background:#1a1a2e;color:#aaa;font-size:0.85em;transition:all .2s;user-select:none}}
.tab:hover{{color:#fff}}
.tab.act{{background:#2d2d44;color:#fff;border-bottom:2px solid #4fc3f7;margin-bottom:-2px}}
.tc{{display:none;background:#1a1a2e;border-radius:0 0 8px 8px;padding:16px;overflow-x:auto}}
.tc.act{{display:block}}
.tc pre{{color:#ccc;font-size:0.8em;white-space:pre-wrap;word-break:break-all}}
.leg{{background:#1a1a2e;border-radius:8px;padding:16px;margin-top:16px}}
.leg pre{{color:#ccc;font-size:0.8em}}
.dep{{background:#1a1a2e;border-radius:8px;padding:20px;margin-top:16px}}
.dep h3{{margin-bottom:12px;color:#4fc3f7}}
.dep code{{background:#0e1117;padding:2px 6px;border-radius:4px;font-size:0.85em;color:#81c784}}
.dep pre{{background:#0e1117;padding:12px;border-radius:6px;overflow-x:auto;margin:8px 0;color:#ccc;font-size:0.8em}}
.ft{{text-align:center;color:#666;font-size:0.8em;margin-top:32px;padding-top:16px;border-top:1px solid #333}}
</style>
</head>
<body>
<div class="c">
<h1>🤖 Huhb3D Synthetic Data Generator</h1>
<p class="sub">面向机器人视觉训练的合成数据生成器 — Demo 展示</p>

<div class="warn">
⚠️ <strong>在线 Demo 模式</strong> — 当前展示预生成的样例数据。要使用自己的 CAD 模型生成数据，请在本地部署并编译 C++ 渲染引擎。<br>
📦 GitHub: <a href="https://github.com/AIminminAI/Huhb3D-Viewer" target="_blank">AIminminAI/Huhb3D-Viewer</a> |
📦 Gitee: <a href="https://gitee.com/aiminminai/Huhb3D-Viewer" target="_blank">aiminminai/Huhb3D-Viewer</a>
</div>

<div class="st">📊 Demo 数据概览</div>
<div class="metrics">
    <div class="m"><div class="v" style="color:#4fc3f7">{rgb_val}</div><div class="l">RGB 图像</div></div>
    <div class="m"><div class="v" style="color:#81c784">{mask_val}</div><div class="l">语义 Mask</div></div>
    <div class="m"><div class="v" style="color:#ffb74d">{depth_val}</div><div class="l">深度图</div></div>
    <div class="m"><div class="v" style="color:#e57373">{dof_val}</div><div class="l">6DoF 位姿</div></div>
</div>

<div class="st">🖼️ 渲染效果展示</div>
<div class="sr">
    <label>选择视角: <span id="idx">1</span> / {num_images}</label>
    <input type="range" id="slider" min="0" max="{num_images - 1}" value="0">
</div>
<div class="ig">
    <div class="ic">
        <div class="it">📷 RGB 渲染图</div>
        <div class="iw"><img id="rgbImg" src="" alt="RGB"></div>
    </div>
    <div class="ic">
        <div class="it">🏷️ 语义分割 Mask</div>
        <div class="iw"><img id="maskImg" src="" alt="Mask"></div>
    </div>
    <div class="ic">
        <div class="it">📏 深度图</div>
        <div class="iw"><div class="ph">深度图需在本地编译 C++ 引擎后生成</div></div>
    </div>
</div>

<div class="st">📐 6DoF &amp; BOP 格式数据</div>
<div class="tabs">
    <div class="tab act" data-t="t1">🎯 6DoF Ground Truth</div>
    <div class="tab" data-t="t2">📷 scene_camera.json</div>
    <div class="tab" data-t="t3">📋 scene_gt.json</div>
    <div class="tab" data-t="t4">🎥 camera_poses.json</div>
</div>
<div class="tc act" id="t1"><pre id="j1"></pre></div>
<div class="tc" id="t2"><pre id="j2"></pre></div>
<div class="tc" id="t3"><pre id="j3"></pre></div>
<div class="tc" id="t4"><pre id="j4"></pre></div>

<details class="leg" style="margin-top:16px">
<summary style="cursor:pointer;color:#4fc3f7;font-weight:600">🏷️ 语义标签分类</summary>
<pre>{label_legend}</pre>
</details>

<div class="st">🔧 本地部署（解锁完整功能）</div>
<div class="dep">
<h3>要使用自己的 CAD 模型生成数据，请按以下步骤本地部署：</h3>
<p>1. 克隆仓库：<code>git clone https://github.com/AIminminAI/Huhb3D-Viewer</code></p>
<p>2. 安装 Python 依赖：<code>pip install streamlit Pillow numpy opencv-python</code></p>
<p>3. 编译 C++ 渲染引擎：需要 Visual Studio 2019+ (Windows) 或 GCC (Linux)</p>
<p>4. 启动 Web UI：<code>streamlit run app.py --server.port 8501</code></p>
<h3 style="margin-top:12px">Docker 部署（最省心）：</h3>
<pre>docker build -t huhb3d-synthetic .
docker run -p 7860:7860 huhb3d-synthetic</pre>
<p>详见 <a href="https://github.com/AIminminAI/Huhb3D-Viewer" style="color:#4fc3f7">GitHub README</a> 获取完整部署指南。</p>
</div>

<div class="ft">Huhb3D Synthetic Data Generator v2.0 | AGPL-3.0 License</div>
</div>

<script>
var rgbData={js_rgb_array};
var maskData={js_mask_array};
var gt6dof={gt_6dof};
var sceneCam={scene_camera};
var sceneGt={scene_gt};
var camPoses={camera_poses};

var slider=document.getElementById('slider');
var idxEl=document.getElementById('idx');
var rgbImg=document.getElementById('rgbImg');
var maskImg=document.getElementById('maskImg');

function update(i){{
    idxEl.textContent=i+1;
    if(rgbData[i])rgbImg.src='data:image/png;base64,'+rgbData[i];
    if(maskData[i])maskImg.src='data:image/png;base64,'+maskData[i];
}}

slider.addEventListener('input',function(){{update(parseInt(this.value))}});
update(0);

document.getElementById('j1').textContent=JSON.stringify(gt6dof,null,2);
document.getElementById('j2').textContent=JSON.stringify(sceneCam,null,2);
document.getElementById('j3').textContent=JSON.stringify(sceneGt,null,2);
document.getElementById('j4').textContent=JSON.stringify(camPoses,null,2);

document.querySelectorAll('.tab').forEach(function(t){{
    t.addEventListener('click',function(){{
        document.querySelectorAll('.tab').forEach(function(x){{x.classList.remove('act')}});
        document.querySelectorAll('.tc').forEach(function(x){{x.classList.remove('act')}});
        this.classList.add('act');
        document.getElementById(this.dataset.t).classList.add('act');
    }});
}});
</script>
</body>
</html>"""

    output_path = Path(__file__).parent / "index.html"
    output_path.write_text(html, encoding="utf-8")
    size_kb = output_path.stat().st_size / 1024
    print(f"Generated index.html ({size_kb:.1f} KB) with {num_images} images embedded")


if __name__ == "__main__":
    main()
