"""
app.py - Huhb3D Synthetic Data Generator (HuggingFace Space Demo)
=================================================================
Demo-only version for HuggingFace Spaces.
Shows pre-generated sample data: RGB, Mask, Depth, 6DoF, BOP format.
Full data generation requires local deployment with C++ engine compiled.
"""

import streamlit as st
import streamlit.components.v1 as components
import json
import base64
from pathlib import Path

DEMO_DIR = Path(__file__).parent / "demo_data"

GITHUB_URL = "https://github.com/AIminminAI/Huhb3D-Viewer"
GITEE_URL = "https://gitee.com/aiminminai/Huhb3D-Viewer"
AFDIAN_URL = "https://afdian.com/a/aiminhu"


@st.cache_data(show_spinner=False)
def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


@st.cache_data(show_spinner=False)
def load_text(path: Path):
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


@st.cache_data(show_spinner=False)
def load_demo_images():
    rgb_dir = DEMO_DIR / "rgb"
    mask_dir = DEMO_DIR / "mask"
    depth_dir = DEMO_DIR / "depth"
    rgb_files = sorted(rgb_dir.glob("*.png")) if rgb_dir.exists() else []
    mask_files = sorted(mask_dir.glob("*.png")) if mask_dir.exists() else []
    depth_files = sorted(depth_dir.glob("*.png")) if depth_dir.exists() else []
    return rgb_files, mask_files, depth_files


@st.cache_data(show_spinner=False)
def image_to_base64(path_str: str):
    try:
        with open(path_str, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except (FileNotFoundError, IOError):
        return None


@st.cache_data(show_spinner=False)
def build_full_viewer_html(rgb_files, mask_files, depth_files, manifest, has_6dof):
    m = manifest or {}
    rgb_val = m.get("rgb_count", len(rgb_files))
    mask_val = m.get("mask_count", len(mask_files))
    depth_val = m.get("depth_count", len(depth_files))
    dof_val = "✅" if has_6dof else "❌"

    num_images = min(len(rgb_files), len(mask_files))
    if num_images == 0:
        return """
        <div style="background:#0e1117;padding:40px;text-align:center;color:#888;">
            暂无 Demo 数据。请在本地运行完整版。
        </div>
        """

    rgb_b64_list = []
    for f in rgb_files[:num_images]:
        b = image_to_base64(str(f))
        rgb_b64_list.append(b if b else "")

    mask_b64_list = []
    for f in mask_files[:num_images]:
        b = image_to_base64(str(f))
        mask_b64_list.append(b if b else "")

    depth_b64_list = []
    for f in depth_files[:num_images]:
        b = image_to_base64(str(f))
        depth_b64_list.append(b if b else "")

    has_depth = len(depth_files) > 0

    js_rgb_array = "[" + ",".join(f'"{b}"' for b in rgb_b64_list) + "]"
    js_mask_array = "[" + ",".join(f'"{b}"' for b in mask_b64_list) + "]"
    js_depth_array = "[" + ",".join(f'"{b}"' for b in depth_b64_list) + "]"

    return f"""
    <div style="background:#0e1117;padding:16px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px;">
            <div style="background:#1a1a2e;border-radius:8px;padding:16px;text-align:center;">
                <div style="font-size:2em;font-weight:700;color:#4fc3f7;">{rgb_val}</div>
                <div style="color:#aaa;font-size:0.9em;">RGB 图像</div>
            </div>
            <div style="background:#1a1a2e;border-radius:8px;padding:16px;text-align:center;">
                <div style="font-size:2em;font-weight:700;color:#81c784;">{mask_val}</div>
                <div style="color:#aaa;font-size:0.9em;">语义 Mask</div>
            </div>
            <div style="background:#1a1a2e;border-radius:8px;padding:16px;text-align:center;">
                <div style="font-size:2em;font-weight:700;color:#ffb74d;">{depth_val}</div>
                <div style="color:#aaa;font-size:0.9em;">深度图</div>
            </div>
            <div style="background:#1a1a2e;border-radius:8px;padding:16px;text-align:center;">
                <div style="font-size:2em;font-weight:700;color:#e57373;">{dof_val}</div>
                <div style="color:#aaa;font-size:0.9em;">6DoF 位姿</div>
            </div>
        </div>

        <div style="margin-bottom:16px;">
            <label style="color:#ccc;font-weight:600;font-size:14px;">
                选择视角: <span id="huhb_idx_label">1</span> / {num_images}
            </label>
            <input type="range" id="huhb_slider" min="0" max="{num_images - 1}" value="0"
                style="width:100%;margin-top:8px;accent-color:#4fc3f7;">
        </div>

        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;">
            <div style="text-align:center;">
                <div style="color:#ccc;font-weight:600;margin-bottom:8px;font-size:14px;">📷 RGB 渲染图</div>
                <div id="huhb_rgb_container" style="min-height:200px;display:flex;align-items:center;justify-content:center;background:#1a1a2e;border-radius:6px;overflow:hidden;">
                </div>
            </div>
            <div style="text-align:center;">
                <div style="color:#ccc;font-weight:600;margin-bottom:8px;font-size:14px;">🏷️ 语义分割 Mask</div>
                <div id="huhb_mask_container" style="min-height:200px;display:flex;align-items:center;justify-content:center;background:#1a1a2e;border-radius:6px;overflow:hidden;">
                </div>
            </div>
            <div style="text-align:center;">
                <div style="color:#ccc;font-weight:600;margin-bottom:8px;font-size:14px;">📏 深度图</div>
                <div id="huhb_depth_container" style="min-height:200px;display:flex;align-items:center;justify-content:center;background:#1a1a2e;border-radius:6px;overflow:hidden;">
                </div>
            </div>
        </div>
    </div>

    <script>
        (function() {{
            var rgbData = {js_rgb_array};
            var maskData = {js_mask_array};
            var depthData = {js_depth_array};
            var hasDepth = {"true" if has_depth else "false"};

            var slider = document.getElementById('huhb_slider');
            var label = document.getElementById('huhb_idx_label');
            var rgbC = document.getElementById('huhb_rgb_container');
            var maskC = document.getElementById('huhb_mask_container');
            var depthC = document.getElementById('huhb_depth_container');

            function update(idx) {{
                label.textContent = idx + 1;

                if (rgbData[idx]) {{
                    rgbC.innerHTML = '<img src="data:image/png;base64,' + rgbData[idx] + '" style="max-width:100%;border-radius:6px;display:block;">';
                }} else {{
                    rgbC.innerHTML = '<div style="color:#888;font-size:13px;">RGB 图像加载失败</div>';
                }}

                if (maskData[idx]) {{
                    maskC.innerHTML = '<img src="data:image/png;base64,' + maskData[idx] + '" style="max-width:100%;border-radius:6px;display:block;">';
                }} else {{
                    maskC.innerHTML = '<div style="color:#888;font-size:13px;">Mask 图像加载失败</div>';
                }}

                if (hasDepth && depthData[idx]) {{
                    depthC.innerHTML = '<img src="data:image/png;base64,' + depthData[idx] + '" style="max-width:100%;border-radius:6px;display:block;">';
                }} else {{
                    depthC.innerHTML = '<div style="color:#888;padding:40px 0;font-size:13px;">深度图需在本地编译 C++ 引擎后生成</div>';
                }}
            }}

            slider.addEventListener('input', function() {{
                update(parseInt(this.value));
            }});

            update(0);
        }})();
    </script>
    """


def main():
    st.set_page_config(
        page_title="Huhb3D Synthetic Data Generator - Demo",
        page_icon="🤖",
        layout="wide",
    )

    st.title("🤖 Huhb3D Synthetic Data Generator")
    st.markdown("**面向机器人视觉训练的合成数据生成器** — Demo 展示")

    st.warning(
        "⚠️ **在线 Demo 模式** — 当前展示预生成的样例数据。"
        "要使用自己的 CAD 模型生成数据，请在本地部署并编译 C++ 渲染引擎。\n\n"
        f"📦 GitHub: [{GITHUB_URL}]({GITHUB_URL}) | "
        f"📦 Gitee: [{GITEE_URL}]({GITEE_URL})"
    )

    rgb_files, mask_files, depth_files = load_demo_images()
    manifest = load_json(DEMO_DIR / "manifest.json")
    scene_camera = load_json(DEMO_DIR / "scene_camera.json")
    scene_gt = load_json(DEMO_DIR / "scene_gt.json")
    gt_6dof = load_json(DEMO_DIR / "gt_6dof.json")
    label_legend = load_text(DEMO_DIR / "label_legend.txt")
    camera_poses = load_json(DEMO_DIR / "camera_poses.json")

    st.markdown("---")

    viewer_html = build_full_viewer_html(
        rgb_files, mask_files, depth_files, manifest, gt_6dof is not None
    )
    components.html(viewer_html, height=560)

    if label_legend:
        with st.expander("🏷️ 语义标签分类", expanded=False):
            st.text(label_legend)

    st.markdown("---")
    st.subheader("📐 6DoF & BOP 格式数据")

    tab_6dof, tab_scene_cam, tab_scene_gt, tab_poses = st.tabs(
        ["🎯 6DoF Ground Truth", "📷 scene_camera.json", "📋 scene_gt.json", "🎥 camera_poses.json"]
    )

    with tab_6dof:
        if gt_6dof:
            st.json(gt_6dof)
        else:
            st.info("6DoF 数据需在本地编译 C++ 引擎后生成")

    with tab_scene_cam:
        if scene_camera:
            st.json(scene_camera)
        else:
            st.info("BOP scene_camera 数据需在本地生成")

    with tab_scene_gt:
        if scene_gt:
            st.json(scene_gt)
        else:
            st.info("BOP scene_gt 数据需在本地生成")

    with tab_poses:
        if camera_poses:
            st.json(camera_poses)
        else:
            st.info("camera_poses 数据需在本地生成")

    st.markdown("---")
    st.subheader("📋 完整数据格式说明")

    st.markdown("""
每次生成输出一个 ZIP 包，结构如下：

```
run_<timestamp>/
├── rgb/                    # RGB 渲染图 (PNG)
│   ├── view_000.png
│   ├── view_001.png
│   └── ...
├── mask/                   # 语义分割 Mask (PNG)
│   ├── view_000_mask.png
│   └── ...
├── depth/                  # 深度图 (PNG可视化 + RAW float)
│   ├── view_000_depth.png
│   └── view_000_depth.raw
├── camera_poses.json       # 6DoF 相机位姿
├── scene_camera.json       # BOP 格式相机内参
├── scene_gt.json           # BOP 格式 6DoF 位姿
├── gt_6dof.json            # 完整 6DoF + 四元数
├── label_legend.txt        # 语义标签对照表
└── manifest.json           # 数据集元信息
```
""")

    st.markdown("---")
    st.subheader("🔧 本地部署（解锁完整功能）")

    st.markdown(f"""
**要使用自己的 CAD 模型生成数据，请按以下步骤本地部署：**

1. 克隆仓库：`git clone {GITHUB_URL}`
2. 安装 Python 依赖：`pip install streamlit Pillow numpy opencv-python`
3. 编译 C++ 渲染引擎：需要 Visual Studio 2019+ (Windows) 或 GCC (Linux)
4. 启动 Web UI：`streamlit run app.py --server.port 8501`

**Docker 部署（最省心）：**
```bash
docker build -t huhb3d-synthetic .
docker run -p 7860:7860 huhb3d-synthetic
```

详见 [GitHub README]({GITHUB_URL}) 获取完整部署指南。
""")

    st.markdown("---")
    st.caption(f"Huhb3D Synthetic Data Generator v2.0 | AGPL-3.0 License | [☕ 爱发电]({AFDIAN_URL})")


if __name__ == "__main__":
    main()
