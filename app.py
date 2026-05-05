"""
app.py - Huhb3D Synthetic Data Generator Web UI
================================================
Streamlit-based web interface for the synthetic data pipeline.

Usage:
    streamlit run app.py
"""

import streamlit as st
import subprocess
import sys
import os
import shutil
import zipfile
import json
import time
import tempfile
import re
import random
import base64
from pathlib import Path

import requests


SUPPORTED_EXTENSIONS = ["step", "stp", "iges", "igs", "stl", "obj"]
SUPPORTED_UPLOAD_TYPES = [".step", ".stp", ".iges", ".igs", ".stl", ".obj"]

SCRIPT_DIR = Path(__file__).parent.resolve()
TEMP_DIR = SCRIPT_DIR / "temp_uploads"
OUTPUT_DIR = SCRIPT_DIR / "streamlit_output"


DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_PROMPT = (
    "你是一个工业质检专家，请描述这张3D零件图中的关键特征"
    "（如：法兰盘、沉头孔、中心轴等），用于训练机器人视觉模型。"
    "请按以下JSON格式输出：\n"
    '{"part_type": "零件类型", "key_features": ["特征1", "特征2", ...], '
    '"surfaces": ["面类型1", "面类型2", ...], '
    '"manufacturing_hints": ["加工提示1", ...], '
    '"description": "详细描述"}'
)


def call_deepseek_vision(image_path, api_key, model="deepseek-chat"):
    try:
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")

        ext = Path(image_path).suffix.lower()
        mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
        mime_type = mime_map.get(ext, "image/png")

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": DEEPSEEK_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{img_b64}"
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 1024,
            "temperature": 0.3,
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        resp = requests.post(
            DEEPSEEK_API_URL,
            headers=headers,
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()

        result = resp.json()
        content = result["choices"][0]["message"]["content"]

        description = {
            "source_image": Path(image_path).name,
            "model": model,
            "prompt": DEEPSEEK_PROMPT,
            "raw_response": content,
        }

        try:
            json_start = content.index("{")
            json_end = content.rindex("}") + 1
            parsed = json.loads(content[json_start:json_end])
            description["parsed"] = parsed
        except (ValueError, json.JSONDecodeError):
            description["parsed"] = None

        return True, description

    except requests.exceptions.Timeout:
        return False, "API request timed out (60s). Please try again."
    except requests.exceptions.ConnectionError:
        return False, "Cannot connect to DeepSeek API. Check your network."
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response else "unknown"
        detail = ""
        try:
            detail = e.response.json().get("error", {}).get("message", "")
        except Exception:
            pass
        return False, f"API HTTP error {code}: {detail}"
    except KeyError as e:
        return False, f"Unexpected API response format: missing {e}"
    except Exception as e:
        return False, f"Unexpected error: {type(e).__name__}: {str(e)}"


def find_cpp_executable():
    search_paths = [
        SCRIPT_DIR / "build" / "Release" / "test_render.exe",
        SCRIPT_DIR / "build_v2" / "Release" / "test_render.exe",
        SCRIPT_DIR / "build" / "test_render.exe",
        SCRIPT_DIR / "build_v2" / "test_render.exe",
    ]
    for path in search_paths:
        if path.exists():
            return str(path.resolve())
    return None


def convert_to_stl(input_path, output_stl_path):
    input_path = Path(input_path)
    suffix = input_path.suffix.lower()

    if suffix in (".stl",):
        if str(input_path.resolve()) != str(output_stl_path):
            shutil.copy2(input_path, output_stl_path)
        return True

    if suffix in (".step", ".stp", ".iges", ".igs"):
        try:
            import cadquery as cq
            if suffix in (".step", ".stp"):
                shape = cq.importers.importStep(str(input_path))
            else:
                shape = cq.importers.importStep(str(input_path))
            cq.exporters.export(shape, str(output_stl_path), exportType="STL")
            return True
        except ImportError:
            pass
        except Exception as e:
            st.warning(f"cadquery conversion failed: {e}")

        try:
            import FreeCAD
            FreeCAD.open(str(input_path))
            doc = FreeCAD.ActiveDocument
            if doc is None:
                st.error("FreeCAD failed to open the file")
                return False
            import Mesh
            mesh_objs = []
            for obj in doc.Objects:
                if hasattr(obj, "Shape"):
                    mesh_data = Mesh.Mesh(obj.Shape.tessellate(0.1))
                    mesh_objs.append(mesh_data)
            if mesh_objs:
                combined = mesh_objs[0]
                for m in mesh_objs[1:]:
                    combined = combined.unite(m)
                combined.write(str(output_stl_path))
            FreeCAD.closeDocument(doc.Name)
            return Path(output_stl_path).exists()
        except ImportError:
            pass
        except Exception as e:
            st.warning(f"FreeCAD conversion failed: {e}")

        st.error(
            "STEP/IGES format requires a conversion library.\n\n"
            "Please install one of:\n"
            "- `pip install cadquery` (recommended)\n"
            "- Or use FreeCAD with Python bindings\n\n"
            "Alternatively, convert your file to STL first using any CAD tool."
        )
        return False

    if suffix in (".obj",):
        try:
            import trimesh
            mesh = trimesh.load(str(input_path))
            mesh.export(str(output_stl_path))
            return True
        except ImportError:
            pass
        except Exception as e:
            st.warning(f"trimesh conversion failed: {e}")

        st.error(
            "OBJ format requires `trimesh` for conversion.\n"
            "Install with: `pip install trimesh`"
        )
        return False

    st.error(f"Unsupported format: {suffix}")
    return False


def parse_progress(line, total_count):
    m = re.search(r'Progress:\s+(\d+)/(\d+)\s+\((\d+\.?\d*)%', line)
    if m:
        current = int(m.group(1))
        total = int(m.group(2))
        percent = float(m.group(3))
        return current, total, percent / 100.0
    return None


def run_generation(stl_path, output_dir, sample_count, camera_radius,
                   image_width, image_height, save_mask, progress_callback):
    exe_path = find_cpp_executable()
    if not exe_path:
        return False, "C++ executable not found. Please compile the project first."

    cmd = [
        exe_path,
        "--batch",
        "--input", str(stl_path),
        "--output", str(output_dir),
        "--count", str(sample_count),
        "--radius", str(camera_radius),
        "--width", str(image_width),
        "--height", str(image_height),
    ]
    if not save_mask:
        cmd.append("--no-mask")

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding='utf-8',
            errors='replace',
            cwd=str(SCRIPT_DIR),
        )

        log_lines = []
        for line in process.stdout:
            line = line.rstrip()
            if line:
                log_lines.append(line)
                progress_info = parse_progress(line, sample_count)
                if progress_info:
                    current, total, pct = progress_info
                    progress_callback(pct, f"Rendering: {current}/{total}")

        process.wait()

        if process.returncode != 0:
            return False, "C++ generator failed.\n\nLog:\n" + "\n".join(log_lines[-20:])

        return True, "\n".join(log_lines[-10:])

    except FileNotFoundError:
        return False, f"Executable not found: {exe_path}"
    except Exception as e:
        return False, f"Error: {str(e)}"


def package_zip(output_dir):
    output_path = Path(output_dir)
    if not output_path.exists():
        return None

    zip_path = output_path.parent / (output_path.name + ".zip")

    rgb_dir = output_path / "rgb"
    mask_dir = output_path / "mask"
    legend_file = output_path / "label_legend.txt"
    desc_file = output_path / "description.json"

    rgb_count = len(list(rgb_dir.glob("*.png"))) if rgb_dir.exists() else 0
    mask_count = len(list(mask_dir.glob("*.png"))) if mask_dir.exists() else 0

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        if rgb_dir.exists():
            for f in sorted(rgb_dir.glob("*.png")):
                zf.write(f, f"rgb/{f.name}")
        if mask_dir.exists():
            for f in sorted(mask_dir.glob("*.png")):
                zf.write(f, f"mask/{f.name}")
        if legend_file.exists():
            zf.write(legend_file, legend_file.name)
        if desc_file.exists():
            zf.write(desc_file, desc_file.name)
        manifest = {
            "version": "1.0",
            "generator": "Huhb3D-SyntheticDataPipeline",
            "rgb_count": rgb_count,
            "mask_count": mask_count,
            "has_legend": legend_file.exists(),
            "has_ai_description": desc_file.exists(),
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    return str(zip_path)


def get_generation_stats(output_dir):
    output_path = Path(output_dir)
    rgb_dir = output_path / "rgb"
    mask_dir = output_path / "mask"
    legend_file = output_path / "label_legend.txt"

    stats = {
        "rgb_count": len(list(rgb_dir.glob("*.png"))) if rgb_dir.exists() else 0,
        "mask_count": len(list(mask_dir.glob("*.png"))) if mask_dir.exists() else 0,
        "has_legend": legend_file.exists(),
    }

    if legend_file.exists():
        categories = {}
        with open(legend_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split()
                if len(parts) >= 4:
                    cat_id = parts[0]
                    cat_name = parts[1]
                    cat_color = parts[2:5]
                    categories[cat_id] = {"name": cat_name, "color": cat_color}
        stats["categories"] = categories

    return stats


def main():
    st.set_page_config(
        page_title="Huhb3D Synthetic Data Generator",
        page_icon="🤖",
        layout="wide",
    )

    st.title("🤖 Huhb3D Synthetic Data Generator")
    st.markdown("---")

    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.subheader("📁 Upload CAD Model")
        uploaded_file = st.file_uploader(
            "Supports STEP, STP, IGES, IGS, STL, OBJ",
            type=SUPPORTED_EXTENSIONS,
            help="Upload your CAD model file. STEP/IGES files will be auto-converted to STL.",
        )

        if uploaded_file is not None:
            file_ext = Path(uploaded_file.name).suffix.lower()
            file_size_mb = uploaded_file.size / (1024 * 1024)
            st.success(f"✅ {uploaded_file.name} ({file_size_mb:.1f} MB)")

            if file_ext in (".step", ".stp", ".iges", ".igs"):
                st.info("🔄 STEP/IGES will be auto-converted to STL")
        else:
            st.info("👆 Please upload a CAD model file")

        st.markdown("---")
        st.subheader("⚙️ Generation Settings")

        sample_count = st.slider(
            "📊 Sample Count",
            min_value=100,
            max_value=1000,
            value=500,
            step=50,
            help="Number of 360° views to render",
        )

        camera_radius = st.slider(
            "🔭 Camera Radius",
            min_value=2.0,
            max_value=20.0,
            value=5.0,
            step=0.5,
            help="Distance of camera from model center",
        )

        col_w, col_h = st.columns(2)
        with col_w:
            image_width = st.selectbox("Width", [512, 640, 800, 1024, 1280], index=2)
        with col_h:
            image_height = st.selectbox("Height", [480, 600, 720, 768, 960], index=1)

        save_mask = st.checkbox("🏷️ Generate Semantic Masks", value=True,
                                help="Generate pixel-level semantic segmentation masks")

        st.markdown("---")
        st.subheader("🧠 AI Description")

        deepseek_api_key = st.text_input(
            "DeepSeek API Key",
            type="password",
            help="Enter your DeepSeek API key to generate AI-powered part descriptions",
        )

        enable_ai_desc = st.checkbox(
            "🧠 AI Feature Description",
            value=False,
            help="Use DeepSeek-V3 to describe key features of the generated part",
        )

        if enable_ai_desc and not deepseek_api_key:
            st.warning("⚠️ Please enter your DeepSeek API Key")

    with col_right:
        st.subheader("🚀 Generation Pipeline")

        exe_path = find_cpp_executable()
        if exe_path:
            st.success(f"✅ C++ Engine: `{Path(exe_path).name}`")
        else:
            st.error("❌ C++ Engine not found! Please compile the project first.")
            st.code("cd build && cmake --build . --config Release", language="bash")

        st.markdown("---")

        start_button = st.button(
            "🚀 Start Generation",
            disabled=(uploaded_file is None or exe_path is None),
            use_container_width=True,
            type="primary",
        )

        if start_button and uploaded_file is not None:
            TEMP_DIR.mkdir(exist_ok=True)
            OUTPUT_DIR.mkdir(exist_ok=True)

            session_id = str(int(time.time()))
            session_output = OUTPUT_DIR / f"run_{session_id}"

            file_ext = Path(uploaded_file.name).suffix.lower()
            temp_input = TEMP_DIR / f"upload_{session_id}{file_ext}"
            temp_stl = TEMP_DIR / f"upload_{session_id}.stl"

            with open(temp_input, "wb") as f:
                f.write(uploaded_file.getbuffer())

            st.info(f"📁 File saved: {uploaded_file.name}")

            if file_ext not in (".stl",):
                with st.spinner("Converting to STL..."):
                    conv_ok = convert_to_stl(temp_input, temp_stl)
                if not conv_ok:
                    st.stop()
                stl_path = temp_stl
                st.success("✅ Conversion to STL complete")
            else:
                stl_path = temp_input

            progress_bar = st.progress(0.0, text="Initializing...")
            status_text = st.empty()
            log_area = st.empty()

            def on_progress(pct, msg):
                progress_bar.progress(pct, text=msg)

            start_time = time.time()

            success, log_msg = run_generation(
                stl_path=stl_path,
                output_dir=session_output,
                sample_count=sample_count,
                camera_radius=camera_radius,
                image_width=image_width,
                image_height=image_height,
                save_mask=save_mask,
                progress_callback=on_progress,
            )

            elapsed = time.time() - start_time

            if success:
                progress_bar.progress(1.0, text="✅ Generation Complete!")

                stats = get_generation_stats(session_output)

                st.markdown("---")
                st.subheader("📊 Generation Results")

                col_s1, col_s2, col_s3 = st.columns(3)
                with col_s1:
                    st.metric("RGB Images", stats["rgb_count"])
                with col_s2:
                    st.metric("Mask Images", stats["mask_count"])
                with col_s3:
                    st.metric("Time", f"{elapsed:.1f}s")

                if stats.get("categories"):
                    with st.expander("🏷️ Label Categories", expanded=False):
                        cat_data = []
                        for cat_id, cat_info in stats["categories"].items():
                            r, g, b = cat_info["color"]
                            cat_data.append({
                                "ID": cat_id,
                                "Category": cat_info["name"],
                                "Color (RGB)": f"({r}, {g}, {b})",
                            })
                        st.table(cat_data)

                ai_description = None
                if enable_ai_desc and deepseek_api_key:
                    rgb_dir = session_output / "rgb"
                    if rgb_dir.exists():
                        png_files = sorted(rgb_dir.glob("*.png"))
                        if png_files:
                            sample_img = random.choice(png_files)
                            st.markdown("---")
                            st.subheader("🧠 AI Feature Description")

                            col_ai_img, col_ai_text = st.columns([1, 2])
                            with col_ai_img:
                                st.image(str(sample_img), caption=f"Sampled: {sample_img.name}",
                                         use_container_width=True)

                            with col_ai_text:
                                with st.spinner("Calling DeepSeek-V3 API..."):
                                    ai_ok, ai_result = call_deepseek_vision(
                                        str(sample_img), deepseek_api_key
                                    )

                            if ai_ok:
                                ai_description = ai_result
                                desc_path = session_output / "description.json"
                                with open(desc_path, "w", encoding="utf-8") as f:
                                    json.dump(ai_description, f, indent=2, ensure_ascii=False)

                                with col_ai_text:
                                    st.success("✅ AI description generated!")

                                    if ai_description.get("parsed"):
                                        parsed = ai_description["parsed"]
                                        st.markdown(f"**Part Type:** {parsed.get('part_type', 'N/A')}")

                                        features = parsed.get("key_features", [])
                                        if features:
                                            st.markdown("**Key Features:**")
                                            for feat in features:
                                                st.markdown(f"- {feat}")

                                        surfaces = parsed.get("surfaces", [])
                                        if surfaces:
                                            st.markdown("**Surfaces:** " + ", ".join(surfaces))

                                        hints = parsed.get("manufacturing_hints", [])
                                        if hints:
                                            st.markdown("**Manufacturing Hints:**")
                                            for h in hints:
                                                st.markdown(f"- {h}")

                                        desc_text = parsed.get("description", "")
                                        if desc_text:
                                            st.markdown(f"**Description:** {desc_text}")
                                    else:
                                        st.markdown(ai_description.get("raw_response", ""))

                                    with st.expander("📋 Raw JSON", expanded=False):
                                        st.json(ai_description)
                            else:
                                with col_ai_text:
                                    st.warning(f"⚠️ AI description failed: {ai_result}")
                                    st.info("The dataset will be packaged without AI description.")
                    else:
                        st.warning("⚠️ No RGB images found for AI description.")

                with st.spinner("Packaging ZIP..."):
                    zip_path = package_zip(session_output)

                if zip_path:
                    zip_size_mb = Path(zip_path).stat().st_size / (1024 * 1024)

                    st.markdown("---")
                    st.subheader("📦 Download Dataset")

                    with open(zip_path, "rb") as f:
                        st.download_button(
                            label=f"⬇️ Download Dataset ({zip_size_mb:.1f} MB)",
                            data=f.read(),
                            file_name=Path(zip_path).name,
                            mime="application/zip",
                            use_container_width=True,
                            type="primary",
                        )

                    if session_output.exists():
                        preview_rgb = session_output / "rgb"
                        if preview_rgb.exists():
                            png_files = sorted(preview_rgb.glob("*.png"))
                            if png_files:
                                with st.expander("🖼️ Preview", expanded=True):
                                    preview_cols = st.columns(min(4, len(png_files[:4])))
                                    for idx, col in enumerate(preview_cols):
                                        if idx < len(png_files):
                                            col.image(
                                                str(png_files[idx]),
                                                caption=png_files[idx].name,
                                                use_container_width=True,
                                            )
                                    if len(png_files) > 4:
                                        st.caption(f"... and {len(png_files) - 4} more images")

                    if save_mask:
                        preview_mask = session_output / "mask"
                        if preview_mask.exists():
                            mask_files = sorted(preview_mask.glob("*.png"))
                            if mask_files:
                                with st.expander("🏷️ Mask Preview", expanded=True):
                                    mask_cols = st.columns(min(4, len(mask_files[:4])))
                                    for idx, col in enumerate(mask_cols):
                                        if idx < len(mask_files):
                                            col.image(
                                                str(mask_files[idx]),
                                                caption=mask_files[idx].name,
                                                use_container_width=True,
                                            )

                st.session_state["last_output_dir"] = str(session_output)
            else:
                progress_bar.progress(0.0, text="❌ Generation Failed")
                st.error(f"Generation failed!\n\n{log_msg}")

        elif uploaded_file is None and start_button:
            st.warning("Please upload a CAD model file first.")

    st.markdown("---")
    with st.expander("ℹ️ About", expanded=False):
        st.markdown("""
        **Huhb3D Synthetic Data Generator** - Pipeline for generating synthetic training data from CAD models.

        **Workflow:**
        1. Upload a CAD model (STEP/IGES/STL/OBJ)
        2. Configure generation parameters
        3. Click "Start Generation" to run 360° sampling
        4. Download the ZIP package with RGB images + semantic masks

        **Output Structure:**
        ```
        dataset.zip
        ├── rgb/frame_0001.png ~ frame_NNNN.png
        ├── mask/mask_0001.png ~ mask_NNNN.png
        ├── label_legend.txt
        ├── description.json (if AI description enabled)
        └── manifest.json
        ```

        **Semantic Categories:**
        | ID | Category | Description |
        |----|----------|-------------|
        | 0 | FreeSurface | General curved surface |
        | 1 | HorizontalPlane | Top/bottom face (Y-axis) |
        | 2 | LateralPlane_X | Side face (X-axis) |
        | 3 | LateralPlane_Z | Front/back face (Z-axis) |
        | 4 | NearHorizontal | Near Y-axis surface |
        | 5 | NearLateral_X | Near X-axis surface |
        | 6 | NearLateral_Z | Near Z-axis surface |
        | 7 | Degenerate | Degenerate triangle |
        """)


if __name__ == "__main__":
    main()
