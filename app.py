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

from license_guard import LicenseGuard

SUPPORTED_EXTENSIONS = ["step", "stp", "iges", "igs", "stl", "obj"]
SUPPORTED_UPLOAD_TYPES = [".step", ".stp", ".iges", ".igs", ".stl", ".obj"]

SCRIPT_DIR = Path(__file__).parent.resolve()
TEMP_DIR = SCRIPT_DIR / "temp_uploads"
OUTPUT_DIR = SCRIPT_DIR / "streamlit_output"
DEMO_DATA_DIR = SCRIPT_DIR / "demo_data"


def is_demo_mode():
    return find_cpp_executable() is None and DEMO_DATA_DIR.exists()


def show_demo_results():
    demo_rgb = DEMO_DATA_DIR / "rgb"
    demo_mask = DEMO_DATA_DIR / "mask"
    demo_legend = DEMO_DATA_DIR / "label_legend.txt"
    demo_poses = DEMO_DATA_DIR / "camera_poses.json"
    demo_manifest = DEMO_DATA_DIR / "manifest.json"
    demo_scene_camera = DEMO_DATA_DIR / "scene_camera.json"
    demo_scene_gt = DEMO_DATA_DIR / "scene_gt.json"
    demo_gt_6dof = DEMO_DATA_DIR / "gt_6dof.json"

    st.markdown("---")
    st.subheader("📊 Demo Results (Pre-generated Sample Data)")

    st.warning("⚠️ **Demo Mode** — You are viewing pre-generated sample data. "
               "To generate custom data from your own CAD models, the C++ rendering engine must be compiled. "
               "See `build_and_compile.bat` or Docker deployment.")

    rgb_files = sorted(demo_rgb.glob("*.png")) if demo_rgb.exists() else []
    mask_files = sorted(demo_mask.glob("*.png")) if demo_mask.exists() else []

    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    with col_s1:
        st.metric("RGB Images", len(rgb_files))
    with col_s2:
        st.metric("Mask Images", len(mask_files))
    with col_s3:
        st.metric("BOP Format", "✅" if demo_scene_camera.exists() else "❌")
    with col_s4:
        st.metric("6DoF GT", "✅" if demo_gt_6dof.exists() else "❌")

    if demo_legend.exists():
        categories = {}
        with open(demo_legend, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split()
                if len(parts) >= 4:
                    categories[parts[0]] = {"name": parts[1], "color": parts[2:5]}
        if categories:
            with st.expander("🏷️ Label Categories", expanded=False):
                cat_data = []
                for cat_id, cat_info in categories.items():
                    r, g, b = cat_info["color"]
                    cat_data.append({
                        "ID": cat_id,
                        "Category": cat_info["name"],
                        "Color (RGB)": f"({r}, {g}, {b})",
                    })
                st.table(cat_data)

    if rgb_files:
        with st.expander("🖼️ RGB Preview", expanded=True):
            preview_cols = st.columns(min(3, len(rgb_files[:3])))
            for idx, col in enumerate(preview_cols):
                if idx < len(rgb_files):
                    col.image(str(rgb_files[idx]), caption=rgb_files[idx].name,
                              use_container_width=True)
            if len(rgb_files) > 3:
                more_cols = st.columns(min(3, len(rgb_files[3:6])))
                for idx, col in enumerate(more_cols):
                    if 3 + idx < len(rgb_files):
                        col.image(str(rgb_files[3 + idx]), caption=rgb_files[3 + idx].name,
                                  use_container_width=True)

    if mask_files:
        with st.expander("🏷️ Mask Preview", expanded=True):
            mask_cols = st.columns(min(3, len(mask_files[:3])))
            for idx, col in enumerate(mask_cols):
                if idx < len(mask_files):
                    col.image(str(mask_files[idx]), caption=mask_files[idx].name,
                              use_container_width=True)
            if len(mask_files) > 3:
                more_cols = st.columns(min(3, len(mask_files[3:6])))
                for idx, col in enumerate(more_cols):
                    if 3 + idx < len(mask_files):
                        col.image(str(mask_files[3 + idx]), caption=mask_files[3 + idx].name,
                                  use_container_width=True)

    if demo_poses.exists():
        with st.expander("📐 Camera Poses (6DoF)", expanded=False):
            poses = json.loads(demo_poses.read_text(encoding='utf-8'))
            st.json(poses)

    if demo_gt_6dof.exists():
        with st.expander("🎯 6DoF Ground Truth (BOP + Quaternion)", expanded=False):
            gt_data = json.loads(demo_gt_6dof.read_text(encoding='utf-8'))
            st.json(gt_data)

    if demo_scene_camera.exists():
        with st.expander("📷 BOP scene_camera.json", expanded=False):
            sc_data = json.loads(demo_scene_camera.read_text(encoding='utf-8'))
            st.json(sc_data)

    if demo_scene_gt.exists():
        with st.expander("🎯 BOP scene_gt.json (Object Poses)", expanded=False):
            sg_data = json.loads(demo_scene_gt.read_text(encoding='utf-8'))
            st.json(sg_data)

    with st.expander("📦 Download Sample Data", expanded=False):
        zip_buffer = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        try:
            with zipfile.ZipFile(zip_buffer.name, 'w', zipfile.ZIP_DEFLATED) as zf:
                for f in rgb_files:
                    zf.write(f, f"rgb/{f.name}")
                for f in mask_files:
                    zf.write(f, f"mask/{f.name}")
                if demo_legend.exists():
                    zf.write(demo_legend, demo_legend.name)
                if demo_poses.exists():
                    zf.write(demo_poses, demo_poses.name)
                manifest = {
                    "version": "2.0",
                    "generator": "Huhb3D-SyntheticDataPipeline",
                    "mode": "demo",
                    "rgb_count": len(rgb_files),
                    "mask_count": len(mask_files),
                }
                zf.writestr("manifest.json", json.dumps(manifest, indent=2))
            zip_size = Path(zip_buffer.name).stat().st_size / (1024 * 1024)
            with open(zip_buffer.name, "rb") as f:
                st.download_button(
                    label=f"⬇️ Download Sample Dataset ({zip_size:.1f} MB)",
                    data=f.read(),
                    file_name="huhb3d_demo_data.zip",
                    mime="application/zip",
                    use_container_width=True,
                    type="primary",
                )
        finally:
            try:
                Path(zip_buffer.name).unlink()
            except Exception:
                pass


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
                   image_width, image_height, save_mask, save_depth=False,
                   progress_callback=None, extra_args=None):
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

    if save_depth:
        cmd.append("--depth")

    if extra_args:
        cmd.extend(extra_args)

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
    mask_instance_dir = output_path / "mask_instance"
    depth_dir = output_path / "depth"
    legend_file = output_path / "label_legend.txt"
    desc_file = output_path / "description.json"
    poses_file = output_path / "camera_poses.json"
    manifest_file = output_path / "manifest.json"

    rgb_count = len(list(rgb_dir.glob("*.png"))) if rgb_dir.exists() else 0
    mask_count = len(list(mask_dir.glob("*.png"))) if mask_dir.exists() else 0
    instance_count = len(list(mask_instance_dir.glob("*.png"))) if mask_instance_dir.exists() else 0
    depth_count = len(list(depth_dir.glob("*.png"))) if depth_dir.exists() else 0

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        if rgb_dir.exists():
            for f in sorted(rgb_dir.glob("*.png")):
                zf.write(f, f"rgb/{f.name}")
        if mask_dir.exists():
            for f in sorted(mask_dir.glob("*.png")):
                zf.write(f, f"mask/{f.name}")
        if mask_instance_dir.exists():
            for f in sorted(mask_instance_dir.glob("*.png")):
                zf.write(f, f"mask_instance/{f.name}")
        if depth_dir.exists():
            for f in sorted(depth_dir.glob("*.png")):
                zf.write(f, f"depth/{f.name}")
            for f in sorted(depth_dir.glob("*.raw")):
                zf.write(f, f"depth/{f.name}")
        if legend_file.exists():
            zf.write(legend_file, legend_file.name)
        if desc_file.exists():
            zf.write(desc_file, desc_file.name)
        if poses_file.exists():
            zf.write(poses_file, poses_file.name)
        if manifest_file.exists():
            zf.write(manifest_file, manifest_file.name)
        manifest = {
            "version": "3.0",
            "generator": "Huhb3D-SyntheticDataPipeline",
            "rgb_count": rgb_count,
            "mask_count": mask_count,
            "instance_mask_count": instance_count,
            "depth_count": depth_count,
            "has_legend": legend_file.exists(),
            "has_ai_description": desc_file.exists(),
            "has_camera_poses": poses_file.exists(),
            "has_manifest": manifest_file.exists(),
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

    if "license_guard" not in st.session_state:
        st.session_state.license_guard = LicenseGuard()

    guard = st.session_state.license_guard
    tier = guard.get_tier()
    tier_display = guard.get_tier_display_name()

    with st.sidebar:
        st.markdown("### 🔑 License")
        if tier == "free":
            st.warning(f"**{tier_display} Edition** — Limited features")
            license_key_input = st.text_input("Enter License Key", type="password", key="license_key")
            if st.button("Activate License"):
                if license_key_input:
                    validated_tier = None
                    from license_guard import _validate_license_key, _generate_machine_id
                    mid = _generate_machine_id()
                    validated_tier = _validate_license_key(license_key_input, mid)
                    if validated_tier:
                        st.session_state.license_guard.tier = validated_tier
                        st.success(f"✅ Activated: {validated_tier.title()} Edition")
                        st.rerun()
                    else:
                        st.error("❌ Invalid license key")
        else:
            st.success(f"**{tier_display} Edition**")
            info = guard.license_info
            if info.get("licensed_to"):
                st.caption(f"Licensed to: {info['licensed_to']}")
            if info.get("expires"):
                st.caption(f"Expires: {info['expires']}")

    demo_mode = is_demo_mode()
    if demo_mode:
        st.info("🎭 **Demo Mode** — You're viewing pre-generated sample data. To generate custom data, deploy locally with the C++ engine.")
    st.markdown("---")

    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.subheader("📁 Upload CAD Models")
        uploaded_files = st.file_uploader(
            "Supports STEP, STP, IGES, IGS, STL, OBJ (multiple files)",
            type=SUPPORTED_EXTENSIONS,
            accept_multiple_files=True,
            help="Upload one or more CAD model files. Multiple files enable multi-object scene synthesis.",
        )

        if uploaded_files:
            for uf in uploaded_files:
                file_ext = Path(uf.name).suffix.lower()
                file_size_mb = uf.size / (1024 * 1024)
                st.success(f"✅ {uf.name} ({file_size_mb:.1f} MB)")
            if len(uploaded_files) > 1:
                st.info(f"🎯 **Multi-object mode**: {len(uploaded_files)} models will be placed in a shared scene")
        else:
            st.info("👆 Please upload one or more CAD model files")

        st.markdown("---")
        st.subheader("⚙️ Generation Settings")

        max_images = guard.get_max_images()
        effective_max = max_images if max_images > 0 else 50000
        slider_max = min(1000, effective_max) if max_images > 0 else 50000
        slider_min = min(10, slider_max - 1)
        slider_default = min(500, slider_max) if slider_max > 500 else slider_max
        sample_count = st.slider(
            "📊 Sample Count",
            min_value=slider_min,
            max_value=slider_max,
            value=slider_default,
            step=50 if slider_max >= 100 else max(1, slider_max // 10),
            help="Number of 360° views to render",
        )
        if max_images > 0 and max_images < 50000:
            st.caption(f"💡 {tier_display} edition: max {max_images} images per session")

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

        save_depth = st.checkbox("📏 Generate Depth Maps", value=False,
                                 help="Generate depth maps for robot grasping planning")

        save_camera_poses = st.checkbox("📐 Export Camera Poses (6DoF)", value=True,
                                        help="Export camera position, rotation, view/projection matrices as JSON")

        model_unit = st.selectbox(
            "📏 Model Unit",
            ["mm", "m", "cm", "inch"],
            index=0,
            help="Unit of measurement in your CAD model. STEP files are typically in mm. Affects depth map values.",
        )

        st.markdown("---")
        with st.expander("🎯 Instance Segmentation & Multi-Object", expanded=True):
            instance_segmentation = st.checkbox(
                "🏷️ Instance-Level Segmentation",
                value=True,
                help="Encode InstanceID + FeatureTypeID + FeatureIndex in mask pixels. Each hole/bolt gets a unique ID.",
            )
            if instance_segmentation:
                st.caption("Mask pixel (R,G,B) = (InstanceID, FeatureTypeID, FeatureIndex)")

            multi_allowed = guard.is_feature_allowed("multi_object")
            multi_object_scene = st.checkbox(
                "📦 Multi-Object Scene Synthesis",
                value=len(uploaded_files) > 1 if uploaded_files else False,
                help="Place multiple objects in a shared scene with random positions/rotations",
                disabled=not multi_allowed,
            )
            if not multi_allowed:
                st.caption("🔒 Multi-Object requires Professional edition")
            if multi_object_scene:
                object_count_display = st.slider(
                    "Max objects per scene",
                    min_value=2, max_value=10, value=min(5, len(uploaded_files)) if uploaded_files else 5,
                    help="Number of objects to randomly place in each scene"
                )
                enable_collision = st.checkbox(
                    "🚧 Collision Avoidance",
                    value=True,
                    help="Prevent objects from overlapping in the scene",
                )

        st.markdown("---")
        with st.expander("🎲 Domain Randomization", expanded=False):
            enable_light_random = st.checkbox(
                "💡 Light Randomization",
                value=True,
                help="Randomize light angle, intensity, and color temperature per frame",
            )
            if enable_light_random:
                light_intensity_range = st.slider(
                    "Light Intensity Range",
                    min_value=0.1, max_value=3.0, value=(0.5, 2.0), step=0.1,
                    help="Min and max light intensity",
                )
                light_temp_range = st.slider(
                    "Color Temperature Range (K)",
                    min_value=2000, max_value=12000, value=(3000, 9000), step=500,
                    help="Color temperature range in Kelvin",
                )

            enable_camera_jitter = st.checkbox(
                "📷 Camera Jitter",
                value=True,
                help="Add slight random offset to camera position and focal length",
            )
            if enable_camera_jitter:
                camera_jitter_amount = st.slider(
                    "Jitter Amount",
                    min_value=0.0, max_value=0.2, value=0.05, step=0.01,
                    help="Camera position jitter range",
                )
                focal_jitter_amount = st.slider(
                    "Focal Jitter (°)",
                    min_value=0.0, max_value=5.0, value=2.0, step=0.5,
                    help="Focal length jitter in degrees",
                )

            enable_background_random = st.checkbox(
                "🖼️ Background Randomization",
                value=False,
                help="Randomize background with images or preset colors for domain randomization",
            )
            if enable_background_random:
                bg_images = st.file_uploader(
                    "Upload Background Images",
                    type=["png", "jpg", "jpeg", "bmp"],
                    accept_multiple_files=True,
                    help="Upload images to use as random backgrounds",
                )
                bg_dir = None
                if bg_images:
                    bg_dir = TEMP_DIR / "backgrounds"
                    bg_dir.mkdir(parents=True, exist_ok=True)
                    for bg_img in bg_images:
                        bg_path = bg_dir / bg_img.name
                        with open(bg_path, "wb") as f:
                            f.write(bg_img.getbuffer())

        st.markdown("---")
        with st.expander("🔬 STEP Topology Ground Truth", expanded=False):
            topo_allowed = guard.is_feature_allowed("step_topology")
            enable_step_topology = st.checkbox(
                "🔬 Use STEP Topology Labels",
                value=False,
                help="Parse STEP file topology to get EXACT face type labels (hole/bolt/plane) instead of curvature-based guessing",
                disabled=not topo_allowed,
            )
            if not topo_allowed:
                st.warning("🔒 STEP Topology requires Standard edition or above")
            if enable_step_topology:
                st.info("🎯 **Ground Truth Mode**: Labels come directly from CAD topology, not curvature estimation")
                st.caption("Requires: `pip install cadquery` (includes OpenCASCADE)")

                step_topology_files = st.file_uploader(
                    "Upload STEP/STP files for topology parsing",
                    type=["step", "stp"],
                    accept_multiple_files=True,
                    help="Upload STEP files corresponding to your models. The parser will extract exact face types.",
                )

                linear_deflection = st.slider(
                    "Tessellation Precision",
                    min_value=0.01, max_value=1.0, value=0.1, step=0.01,
                    help="Smaller = more triangles but more precise topology mapping",
                )

        st.markdown("---")
        with st.expander("🎨 Sim-to-Real Enhancement", expanded=False):
            enable_sim2real = st.checkbox(
                "🎨 Apply Sim-to-Real Augmentation",
                value=False,
                help="Post-process rendered images with realistic noise, blur, and color jitter",
            )
            if enable_sim2real:
                st.caption("Bridges the simulation-to-reality gap for robot vision training")

                aug_gaussian_noise = st.checkbox("📡 Gaussian Noise (sensor noise)", value=True)
                aug_motion_blur = st.checkbox("🏃 Motion Blur (camera movement)", value=True)
                aug_occlusion = st.checkbox("🚫 Random Occlusion", value=False)
                aug_color_jitter = st.checkbox("🌈 Color Jitter (brightness/contrast)", value=True)
                aug_depth_noise = st.checkbox("📏 Depth Sensor Noise", value=True)

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
        elif demo_mode:
            st.warning("🎭 **Demo Mode** — C++ engine not available on this server. Showing pre-generated results below.")
        else:
            st.error("❌ C++ Engine not found! Please compile the project first.")
            st.code("cd build && cmake --build . --config Release", language="bash")

        st.markdown("---")

        if demo_mode:
            show_demo_results()
        else:
            has_files = uploaded_files and len(uploaded_files) > 0
            start_button = st.button(
                "🚀 Start Generation",
                disabled=(not has_files or exe_path is None),
                use_container_width=True,
                type="primary",
            )

            if start_button and has_files:
                TEMP_DIR.mkdir(exist_ok=True)
                OUTPUT_DIR.mkdir(exist_ok=True)

                session_id = str(int(time.time()))
                session_output = OUTPUT_DIR / f"run_{session_id}"

                stl_paths = []
                for idx, uploaded_file in enumerate(uploaded_files):
                    file_ext = Path(uploaded_file.name).suffix.lower()
                    temp_input = TEMP_DIR / f"upload_{session_id}_{idx}{file_ext}"
                    temp_stl = TEMP_DIR / f"upload_{session_id}_{idx}.stl"

                    with open(temp_input, "wb") as f:
                        f.write(uploaded_file.getbuffer())

                    if file_ext not in (".stl",):
                        with st.spinner(f"Converting {uploaded_file.name} to STL..."):
                            conv_ok = convert_to_stl(temp_input, temp_stl)
                        if not conv_ok:
                            st.stop()
                        stl_paths.append((temp_stl, uploaded_file.name))
                        st.success(f"✅ {uploaded_file.name} converted to STL")
                    else:
                        stl_paths.append((temp_input, uploaded_file.name))

                st.info(f"📁 {len(stl_paths)} file(s) ready for generation")

                progress_bar = st.progress(0.0, text="Initializing...")
                status_text = st.empty()
                log_area = st.empty()

                def on_progress(pct, msg):
                    progress_bar.progress(pct, text=msg)

                start_time = time.time()

                primary_stl = stl_paths[0][0]

                extra_args = []
                extra_args.extend(["--model-unit", model_unit])
                if instance_segmentation:
                    extra_args.append("--instance-segmentation")
                if multi_object_scene and len(stl_paths) > 1:
                    extra_args.extend(["--multi-object"])
                    for stl_path, stl_name in stl_paths[1:]:
                        extra_args.extend(["--scene-object", str(stl_path)])
                if enable_light_random:
                    extra_args.append("--light-randomization")
                if enable_camera_jitter:
                    extra_args.append("--camera-jitter")
                if enable_background_random:
                    extra_args.append("--background-randomization")
                    if bg_dir and bg_dir.exists():
                        extra_args.extend(["--background-dir", str(bg_dir)])

                topology_labels_paths = []
                if enable_step_topology and step_topology_files:
                    from step_topology_parser import parse_step_topology
                    topology_output = TEMP_DIR / f"topology_{session_id}"
                    topology_output.mkdir(parents=True, exist_ok=True)

                    for tidx, step_file in enumerate(step_topology_files):
                        step_temp = TEMP_DIR / f"step_{session_id}_{tidx}{Path(step_file.name).suffix}"
                        with open(step_temp, "wb") as f:
                            f.write(step_file.getbuffer())

                        topo_out = topology_output / f"obj_{tidx}"
                        with st.spinner(f"Parsing STEP topology: {step_file.name}..."):
                            topo_ok = parse_step_topology(
                                str(step_temp), str(topo_out),
                                linear_deflection=linear_deflection,
                            )
                        if topo_ok:
                            labels_json = topo_out / "topology_labels.json"
                            tessellated_stl = topo_out / "tessellated.stl"
                            if labels_json.exists():
                                topology_labels_paths.append(str(labels_json))
                                st.success(f"✅ {step_file.name}: topology parsed (GROUND TRUTH)")
                                summary_json = topo_out / "topology_summary.json"
                                if summary_json.exists():
                                    with open(summary_json) as sf:
                                        summary = json.load(sf)
                                    cats = summary.get("categories", {})
                                    if cats:
                                        cat_str = ", ".join(
                                            f"{v['name']}({v['face_count']})"
                                            for v in cats.values()
                                        )
                                        st.caption(f"Faces: {cat_str}")
                            if tessellated_stl.exists() and tidx == 0:
                                primary_stl = str(tessellated_stl)
                                st.info(f"📐 Using STEP-tessellated mesh for primary object")
                        else:
                            st.warning(f"⚠️ {step_file.name}: topology parsing failed, using curvature fallback")

                    if topology_labels_paths:
                        extra_args.extend(["--topology-labels", topology_labels_paths[0]])
                        for tlp in topology_labels_paths[1:]:
                            extra_args.extend(["--scene-object-topology", tlp])

                success, log_msg = run_generation(
                    stl_path=primary_stl,
                    output_dir=session_output,
                    sample_count=sample_count,
                    camera_radius=camera_radius,
                    image_width=image_width,
                    image_height=image_height,
                    save_mask=save_mask,
                    save_depth=save_depth,
                    progress_callback=on_progress,
                    extra_args=extra_args,
                )

                elapsed = time.time() - start_time

                if success:
                    progress_bar.progress(1.0, text="✅ Generation Complete!")

                    stats = get_generation_stats(session_output)

                    st.markdown("---")
                    st.subheader("📊 Generation Results")

                    col_s1, col_s2, col_s3, col_s4, col_s5 = st.columns(5)
                    with col_s1:
                        st.metric("RGB Images", stats["rgb_count"])
                    with col_s2:
                        st.metric("Semantic Masks", stats["mask_count"])
                    with col_s3:
                        instance_count = len(list((session_output / "mask_instance").glob("*.png"))) if (session_output / "mask_instance").exists() else 0
                        st.metric("Instance Masks", instance_count)
                    with col_s4:
                        st.metric("Time", f"{elapsed:.1f}s")
                    with col_s5:
                        depth_count = len(list((session_output / "depth").glob("*.png"))) if (session_output / "depth").exists() else 0
                        st.metric("Depth Maps", depth_count)

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

                    with st.spinner("Generating quality report..."):
                        try:
                            from dataset_report import generate_report
                            report_path = str(session_output / "dataset_report.json")
                            report = generate_report(str(session_output), report_path, "json")
                            if report:
                                tr = report.get("training_readiness", {})
                                score = tr.get("score", 0)
                                grade = tr.get("grade", "?")
                                ready = tr.get("ready_for_training", False)
                                col_r1, col_r2, col_r3 = st.columns(3)
                                with col_r1:
                                    st.metric("Quality Score", f"{score}/100")
                                with col_r2:
                                    st.metric("Grade", grade)
                                with col_r3:
                                    st.metric("Training Ready", "✅ YES" if ready else "❌ NO")

                                html_report_path = str(session_output / "dataset_report.html")
                                generate_report(str(session_output), html_report_path, "html")
                        except ImportError:
                            st.info("📊 Install dataset_report.py for quality scoring")
                        except Exception as e:
                            st.warning(f"⚠️ Report generation failed: {e}")

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

                    if enable_sim2real:
                        with st.spinner("Applying Sim-to-Real augmentation..."):
                            from sim_to_real import process_directory
                            aug_output = session_output.parent / f"{session_output.name}_augmented"
                            aug_config = {
                                "gaussian_noise": aug_gaussian_noise,
                                "motion_blur": aug_motion_blur,
                                "occlusion": aug_occlusion,
                                "color_jitter": aug_color_jitter,
                                "depth_noise": aug_depth_noise,
                            }
                            aug_ok = process_directory(str(session_output), str(aug_output), aug_config)
                            if aug_ok:
                                st.success("✅ Sim-to-Real augmentation applied!")
                                session_output = aug_output
                            else:
                                st.warning("⚠️ Sim-to-Real augmentation failed, using original data")

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
                                    with st.expander("🏷️ Semantic Mask Preview", expanded=True):
                                        mask_cols = st.columns(min(4, len(mask_files[:4])))
                                        for idx, col in enumerate(mask_cols):
                                            if idx < len(mask_files):
                                                col.image(
                                                    str(mask_files[idx]),
                                                    caption=mask_files[idx].name,
                                                    use_container_width=True,
                                                )

                            preview_instance = session_output / "mask_instance"
                            if preview_instance.exists():
                                instance_files = sorted(preview_instance.glob("*.png"))
                                if instance_files:
                                    with st.expander("🎯 Instance Mask Preview", expanded=False):
                                        inst_cols = st.columns(min(4, len(instance_files[:4])))
                                        for idx, col in enumerate(inst_cols):
                                            if idx < len(instance_files):
                                                col.image(
                                                    str(instance_files[idx]),
                                                    caption=instance_files[idx].name,
                                                    use_container_width=True,
                                                )
                                        st.caption("Pixel (R,G,B) = (InstanceID, FeatureTypeID, FeatureIndex)")

                        manifest_path = session_output / "manifest.json"
                        if manifest_path.exists():
                            with st.expander("📋 Instance Manifest", expanded=False):
                                manifest_data = json.loads(manifest_path.read_text(encoding='utf-8'))
                                st.json(manifest_data)

                    st.session_state["last_output_dir"] = str(session_output)
                else:
                    progress_bar.progress(0.0, text="❌ Generation Failed")
                    st.error(f"Generation failed!\n\n{log_msg}")

            elif not has_files and start_button:
                st.warning("Please upload one or more CAD model files first.")

    st.markdown("---")
    with st.expander("ℹ️ About", expanded=False):
        st.markdown("""
        **Huhb3D Synthetic Data Generator** - Synthetic data generation engine for robot vision training.

        **Workflow:**
        1. Upload one or more CAD models (STEP/IGES/STL/OBJ)
        2. Configure generation parameters (instance segmentation, multi-object, domain randomization)
        3. Click "Start Generation" to run 360° sampling
        4. Download the ZIP package with RGB images + masks + annotations

        **Output Structure:**
        ```
        dataset.zip
        ├── rgb/frame_0001.png ~ frame_NNNN.png
        ├── mask/mask_0001.png ~ mask_NNNN.png (semantic segmentation)
        ├── mask_instance/instance_0001.png ~ instance_NNNN.png (instance segmentation)
        ├── depth/depth_0001.png ~ depth_NNNN.png (if enabled, 16-bit)
        ├── label_legend.txt
        ├── camera_poses.json (6DoF camera poses)
        ├── manifest.json (instance hierarchy: Scene -> Object -> Feature)
        ├── scene_camera.json (BOP format camera intrinsics/extrinsics)
        ├── scene_gt.json (BOP format object 6DoF poses)
        ├── gt_6dof.json (6DoF Ground Truth per frame with quaternion)
        ├── description.json (if AI description enabled)
        ├── topology_labels.json (if STEP topology enabled, per-triangle GROUND TRUTH)
        ├── topology_summary.json (face type statistics from STEP)
        └── coco_annotations.json / coco_instance_annotations.json
        ```

        **Instance Segmentation Encoding:**
        - Mask pixel (R, G, B) = (InstanceID, FeatureTypeID, FeatureIndex)
        - InstanceID: unique per object in scene (1-255)
        - FeatureTypeID: semantic category (0-11)
        - FeatureIndex: instance index within that feature type
        - Example: Pixel (2, 9, 3) = Object 2, Hole type, 4th hole instance

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
        | 8 | ConvexFeature_Bolt | Convex protrusion (bolt/boss) |
        | 9 | ConcaveFeature_Hole | Concave depression (hole) |
        | 10 | Flange | Flange feature |
        | 11 | Boss | Boss/stud feature |

        **Domain Randomization:**
        - 💡 Light randomization: angle, intensity, color temperature (CCT)
        - 📷 Camera jitter: position offset, focal length variation
        - 🎲 Scene randomization: object positions, rotations, scale per frame
        """)


if __name__ == "__main__":
    main()
