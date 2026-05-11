"""
batch_pipeline.py - Batch STEP File Processing Pipeline
========================================================
Commercial-grade batch processing for synthetic data generation.
Processes multiple STEP files through the complete pipeline:
  1. STEP Topology Parsing (ground truth labels)
  2. C++ Rendering (RGB + masks + depth)
  3. Sim-to-Real Augmentation
  4. COCO/YOLO/BOP Format Conversion
  5. Dataset Quality Report

Usage:
    python batch_pipeline.py --input-dir ./step_files --output-dir ./dataset
    python batch_pipeline.py --input-dir ./step_files --output-dir ./dataset \
        --samples 500 --topology --sim2real --report

Requirements:
    - Compiled C++ engine (test_render.exe)
    - cadquery (for STEP topology parsing)
    - opencv-python, numpy (for sim-to-real)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from collections import defaultdict


SCRIPT_DIR = Path(__file__).parent.resolve()


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


def find_step_files(input_dir):
    input_path = Path(input_dir)
    step_files = []
    for ext in ["*.step", "*.stp", "*.STEP", "*.STP"]:
        step_files.extend(input_path.glob(ext))
    return sorted(step_files)


def find_stl_files(input_dir):
    input_path = Path(input_dir)
    stl_files = []
    for ext in ["*.stl", "*.STL"]:
        stl_files.extend(input_path.glob(ext))
    return sorted(stl_files)


def parse_step_topology_file(step_path, output_dir, linear_deflection=0.1):
    try:
        from step_topology_parser import parse_step_topology
        topo_out = Path(output_dir) / "topology"
        topo_out.mkdir(parents=True, exist_ok=True)
        success = parse_step_topology(
            str(step_path), str(topo_out),
            linear_deflection=linear_deflection,
        )
        if success:
            labels_json = topo_out / "topology_labels.json"
            tessellated_stl = topo_out / "tessellated.stl"
            return {
                "success": True,
                "labels_path": str(labels_json) if labels_json.exists() else None,
                "stl_path": str(tessellated_stl) if tessellated_stl.exists() else None,
            }
        return {"success": False}
    except ImportError:
        print("[BatchPipeline] WARNING: cadquery not installed, skipping STEP topology")
        return {"success": False}
    except Exception as e:
        print(f"[BatchPipeline] STEP topology error: {e}")
        return {"success": False}


def run_rendering(stl_path, output_dir, config):
    exe_path = find_cpp_executable()
    if not exe_path:
        print("[BatchPipeline] ERROR: C++ executable not found")
        return False, "C++ executable not found"

    cmd = [
        exe_path,
        "--batch",
        "--input", str(stl_path),
        "--output", str(output_dir),
        "--count", str(config["samples"]),
        "--radius", str(config["camera_radius"]),
        "--width", str(config["width"]),
        "--height", str(config["height"]),
        "--model-unit", config.get("model_unit", "mm"),
    ]

    if config.get("save_mask", True):
        cmd.append("--instance-segmentation")
    else:
        cmd.append("--no-mask")

    if config.get("save_depth", False):
        cmd.append("--depth")

    if config.get("topology_labels_path"):
        cmd.extend(["--topology-labels", config["topology_labels_path"]])

    if config.get("light_randomization", False):
        cmd.append("--light-randomization")

    if config.get("camera_jitter", False):
        cmd.append("--camera-jitter")

    if config.get("no_bop", False):
        cmd.append("--no-bop-format")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(SCRIPT_DIR),
            timeout=3600,
        )
        if result.returncode != 0:
            return False, result.stderr[-500:] if result.stderr else "Unknown error"
        return True, result.stdout[-200:] if result.stdout else "OK"
    except subprocess.TimeoutExpired:
        return False, "Rendering timed out (1h limit)"
    except Exception as e:
        return False, str(e)


def run_sim2real(input_dir, output_dir, aug_config):
    try:
        from sim_to_real import process_directory
        return process_directory(input_dir, output_dir, aug_config)
    except ImportError:
        print("[BatchPipeline] WARNING: sim_to_real module not available")
        return False
    except Exception as e:
        print(f"[BatchPipeline] Sim-to-Real error: {e}")
        return False


def run_mask_to_coco(input_dir, instance_mode=False):
    try:
        cmd = [sys.executable, str(SCRIPT_DIR / "mask_to_coco.py"),
               "--input", str(input_dir)]
        if instance_mode:
            cmd.append("--instance")
        subprocess.run(cmd, capture_output=True, timeout=300)
        return True
    except Exception as e:
        print(f"[BatchPipeline] COCO conversion error: {e}")
        return False


def run_dataset_report(input_dir, output_format="json"):
    try:
        from dataset_report import generate_report
        report_path = str(Path(input_dir) / f"dataset_report.{output_format}")
        report = generate_report(input_dir, report_path, output_format)
        return report is not None
    except ImportError:
        print("[BatchPipeline] WARNING: dataset_report module not available")
        return False
    except Exception as e:
        print(f"[BatchPipeline] Report generation error: {e}")
        return False


def process_single_file(file_path, output_base, config, file_index, total_files):
    file_path = Path(file_path)
    file_name = file_path.stem
    file_output = Path(output_base) / file_name
    file_output.mkdir(parents=True, exist_ok=True)

    print(f"\n[BatchPipeline] [{file_index}/{total_files}] Processing: {file_name}")
    start_time = time.time()

    result = {
        "file": file_path.name,
        "status": "pending",
        "topology": None,
        "rendering": None,
        "augmentation": None,
        "report": None,
        "elapsed_seconds": 0,
    }

    stl_path = file_path
    topology_labels_path = None

    if config.get("topology", False) and file_path.suffix.lower() in (".step", ".stp"):
        print(f"  [1/5] Parsing STEP topology...")
        topo_result = parse_step_topology_file(
            file_path, str(file_output),
            linear_deflection=config.get("linear_deflection", 0.1),
        )
        result["topology"] = topo_result
        if topo_result["success"]:
            topology_labels_path = topo_result.get("labels_path")
            if topo_result.get("stl_path"):
                stl_path = topo_result["stl_path"]
            print(f"  ✅ Topology parsed (labels: {topology_labels_path is not None})")
        else:
            print(f"  ⚠️ Topology parsing failed, using curvature fallback")

    render_config = {
        "samples": config.get("samples", 500),
        "camera_radius": config.get("camera_radius", 5.0),
        "width": config.get("width", 800),
        "height": config.get("height", 600),
        "save_mask": config.get("save_mask", True),
        "save_depth": config.get("save_depth", False),
        "model_unit": config.get("model_unit", "mm"),
        "topology_labels_path": topology_labels_path,
        "light_randomization": config.get("light_randomization", True),
        "camera_jitter": config.get("camera_jitter", True),
        "no_bop": not config.get("bop_format", True),
    }

    print(f"  [2/5] Rendering {render_config['samples']} views...")
    render_ok, render_msg = run_rendering(stl_path, str(file_output), render_config)
    result["rendering"] = {"success": render_ok, "message": render_msg[:200]}
    if not render_ok:
        result["status"] = "rendering_failed"
        result["elapsed_seconds"] = time.time() - start_time
        print(f"  ❌ Rendering failed: {render_msg[:200]}")
        return result
    print(f"  ✅ Rendering complete")

    if config.get("sim2real", False):
        print(f"  [3/5] Applying Sim-to-Real augmentation...")
        aug_output = str(file_output.parent / f"{file_output.name}_augmented")
        aug_config = {
            "gaussian_noise": True,
            "motion_blur": True,
            "occlusion": config.get("aug_occlusion", False),
            "color_jitter": True,
            "depth_noise": config.get("save_depth", False),
        }
        aug_ok = run_sim2real(str(file_output), aug_output, aug_config)
        result["augmentation"] = {"success": aug_ok}
        if aug_ok:
            file_output = Path(aug_output)
            print(f"  ✅ Sim-to-Real applied")
        else:
            print(f"  ⚠️ Sim-to-Real failed, using original data")

    if config.get("coco_format", True):
        print(f"  [4/5] Generating COCO/YOLO annotations...")
        run_mask_to_coco(str(file_output), instance_mode=False)
        run_mask_to_coco(str(file_output), instance_mode=True)
        print(f"  ✅ COCO annotations generated")

    if config.get("report", True):
        print(f"  [5/5] Generating quality report...")
        report_ok = run_dataset_report(str(file_output), "json")
        result["report"] = {"success": report_ok}
        if report_ok:
            print(f"  ✅ Quality report generated")
        else:
            print(f"  ⚠️ Report generation failed")

    result["status"] = "success"
    result["elapsed_seconds"] = time.time() - start_time
    print(f"  ✅ [{file_index}/{total_files}] {file_name} complete ({result['elapsed_seconds']:.1f}s)")
    return result


def batch_process(input_dir, output_dir, config):
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    step_files = find_step_files(input_dir)
    stl_files = find_stl_files(input_dir)

    all_files = []
    seen_names = set()
    for f in step_files:
        if f.stem not in seen_names:
            all_files.append(f)
            seen_names.add(f.stem)
    for f in stl_files:
        if f.stem not in seen_names:
            all_files.append(f)
            seen_names.add(f.stem)

    if not all_files:
        print(f"[BatchPipeline] ERROR: No STEP/STL files found in {input_dir}")
        return None

    print(f"[BatchPipeline] Found {len(all_files)} files to process")
    print(f"[BatchPipeline] Output: {output_dir}")
    print(f"[BatchPipeline] Config: {json.dumps(config, indent=2)}")

    results = []
    total_start = time.time()

    for idx, file_path in enumerate(all_files, 1):
        result = process_single_file(file_path, str(output_path), config, idx, len(all_files))
        results.append(result)

    total_elapsed = time.time() - total_start

    success_count = sum(1 for r in results if r["status"] == "success")
    failed_count = sum(1 for r in results if r["status"] != "success")

    summary = {
        "generator": "Huhb3D-SyntheticDataPipeline",
        "pipeline_version": "1.0",
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "config": config,
        "total_files": len(all_files),
        "success_count": success_count,
        "failed_count": failed_count,
        "total_elapsed_seconds": round(total_elapsed, 2),
        "results": results,
    }

    summary_path = output_path / "batch_summary.json"
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\n[BatchPipeline] === Batch Processing Complete ===")
    print(f"  Total:    {len(all_files)}")
    print(f"  Success:  {success_count}")
    print(f"  Failed:   {failed_count}")
    print(f"  Time:     {total_elapsed:.1f}s")
    print(f"  Summary:  {summary_path}")

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Huhb3D Batch STEP File Processing Pipeline"
    )
    parser.add_argument("--input-dir", "-i", required=True,
                        help="Directory containing STEP/STL files")
    parser.add_argument("--output-dir", "-o", required=True,
                        help="Output directory for generated datasets")
    parser.add_argument("--samples", "-n", type=int, default=500,
                        help="Number of views per object (default: 500)")
    parser.add_argument("--camera-radius", "-r", type=float, default=5.0,
                        help="Camera radius (default: 5.0)")
    parser.add_argument("--width", type=int, default=800,
                        help="Image width (default: 800)")
    parser.add_argument("--height", type=int, default=600,
                        help="Image height (default: 600)")
    parser.add_argument("--model-unit", choices=["mm", "m", "cm", "inch"],
                        default="mm", help="Model unit (default: mm)")
    parser.add_argument("--topology", action="store_true",
                        help="Parse STEP topology for ground truth labels")
    parser.add_argument("--linear-deflection", type=float, default=0.1,
                        help="STEP tessellation precision (default: 0.1)")
    parser.add_argument("--sim2real", action="store_true",
                        help="Apply Sim-to-Real augmentation")
    parser.add_argument("--depth", action="store_true",
                        help="Generate depth maps")
    parser.add_argument("--no-mask", action="store_true",
                        help="Skip mask generation")
    parser.add_argument("--no-bop", action="store_true",
                        help="Skip BOP format output")
    parser.add_argument("--no-coco", action="store_true",
                        help="Skip COCO format conversion")
    parser.add_argument("--no-report", action="store_true",
                        help="Skip quality report generation")
    parser.add_argument("--light-randomization", action="store_true",
                        help="Enable light randomization")
    parser.add_argument("--camera-jitter", action="store_true",
                        help="Enable camera jitter")
    args = parser.parse_args()

    config = {
        "samples": args.samples,
        "camera_radius": args.camera_radius,
        "width": args.width,
        "height": args.height,
        "model_unit": args.model_unit,
        "topology": args.topology,
        "linear_deflection": args.linear_deflection,
        "sim2real": args.sim2real,
        "save_depth": args.depth,
        "save_mask": not args.no_mask,
        "bop_format": not args.no_bop,
        "coco_format": not args.no_coco,
        "report": not args.no_report,
        "light_randomization": args.light_randomization,
        "camera_jitter": args.camera_jitter,
    }

    summary = batch_process(args.input_dir, args.output_dir, config)
    sys.exit(0 if summary and summary["failed_count"] == 0 else 1)


if __name__ == "__main__":
    main()
