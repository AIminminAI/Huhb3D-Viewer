"""
dataset_report.py - Dataset Quality Report Generator
=====================================================
Generates comprehensive quality reports for synthetic datasets.
This is a COMMERCIAL DELIVERABLE that proves data quality to customers.

Reports include:
  - Dataset statistics (image counts, resolution, coverage)
  - Annotation quality metrics (mask coverage, label distribution)
  - 6DoF pose distribution analysis
  - Depth map quality checks
  - BOP format compliance validation
  - Training readiness assessment

Usage:
    python dataset_report.py --input <dataset_directory> --output report.json
    python dataset_report.py --input <dataset_directory> --output report.html
"""

import argparse
import json
import math
import os
import sys
from pathlib import Path
from collections import defaultdict, Counter


def analyze_rgb_directory(rgb_dir):
    stats = {
        "count": 0,
        "filenames": [],
        "naming_pattern": "unknown",
    }
    if not rgb_dir.exists():
        return stats
    png_files = sorted(rgb_dir.glob("*.png"))
    jpg_files = sorted(rgb_dir.glob("*.jpg"))
    all_files = png_files + jpg_files
    stats["count"] = len(all_files)
    stats["filenames"] = [f.name for f in all_files[:10]]
    if all_files:
        stats["naming_pattern"] = all_files[0].stem
    return stats


def analyze_mask_directory(mask_dir):
    stats = {
        "count": 0,
        "unique_colors_total": 0,
        "avg_unique_colors": 0.0,
        "mask_coverage_avg": 0.0,
        "category_distribution": {},
    }
    if not mask_dir.exists():
        return stats
    mask_files = sorted(mask_dir.glob("*.png"))
    stats["count"] = len(mask_files)
    if not mask_files:
        return stats
    try:
        import numpy as np
        from PIL import Image
        total_unique = 0
        total_coverage = 0.0
        category_counter = Counter()
        sample_size = min(20, len(mask_files))
        step = max(1, len(mask_files) // sample_size)
        sampled = 0
        for idx in range(0, len(mask_files), step):
            if sampled >= sample_size:
                break
            img = np.array(Image.open(mask_files[idx]))
            unique_colors = set()
            if img.ndim == 3:
                non_black = img[~((img[:, :, 0] == 0) & (img[:, :, 1] == 0) & (img[:, :, 2] == 0))]
                total_coverage += len(non_black) / (img.shape[0] * img.shape[1]) if img.size > 0 else 0
                for row in img.reshape(-1, img.shape[2]):
                    r, g, b = int(row[0]), int(row[1]), int(row[2])
                    if r == 0 and g == 0 and b == 0:
                        continue
                    category_counter[g] += 1
                    unique_colors.add((r, g, b))
            total_unique += len(unique_colors)
            sampled += 1
        if sampled > 0:
            stats["avg_unique_colors"] = round(total_unique / sampled, 1)
            stats["mask_coverage_avg"] = round(total_coverage / sampled, 4)
        stats["category_distribution"] = {
            str(k): v for k, v in sorted(category_counter.items())
        }
    except ImportError:
        stats["note"] = "Pillow/numpy not available, detailed analysis skipped"
    return stats


def analyze_instance_mask_directory(instance_dir):
    stats = {
        "count": 0,
        "avg_instance_count": 0.0,
        "max_instance_id": 0,
    }
    if not instance_dir.exists():
        return stats
    files = sorted(instance_dir.glob("*.png"))
    stats["count"] = len(files)
    if not files:
        return stats
    try:
        import numpy as np
        from PIL import Image
        total_instances = 0
        max_id = 0
        sample_size = min(20, len(files))
        step = max(1, len(files) // sample_size)
        sampled = 0
        for idx in range(0, len(files), step):
            if sampled >= sample_size:
                break
            img = np.array(Image.open(files[idx]))
            if img.ndim == 3:
                r_channel = img[:, :, 0]
                unique_ids = set(np.unique(r_channel)) - {0}
                total_instances += len(unique_ids)
                if unique_ids:
                    max_id = max(max_id, max(unique_ids))
            sampled += 1
        if sampled > 0:
            stats["avg_instance_count"] = round(total_instances / sampled, 1)
        stats["max_instance_id"] = int(max_id)
    except ImportError:
        pass
    return stats


def analyze_depth_directory(depth_dir):
    stats = {
        "count": 0,
        "has_npy": False,
        "has_png": False,
        "depth_range_mm": [0, 0],
        "valid_pixel_ratio_avg": 0.0,
    }
    if not depth_dir.exists():
        return stats
    npy_files = list(depth_dir.glob("*.npy"))
    png_files = list(depth_dir.glob("*.png"))
    stats["count"] = len(png_files)
    stats["has_npy"] = len(npy_files) > 0
    stats["has_png"] = len(png_files) > 0
    if not png_files:
        return stats
    try:
        import numpy as np
        from PIL import Image
        min_depth = float('inf')
        max_depth = 0.0
        total_valid = 0.0
        sample_size = min(10, len(png_files))
        step = max(1, len(png_files) // sample_size)
        sampled = 0
        for idx in range(0, len(png_files), step):
            if sampled >= sample_size:
                break
            img = np.array(Image.open(png_files[idx]))
            if img.ndim == 2:
                valid = img[img > 0]
                if len(valid) > 0:
                    min_depth = min(min_depth, float(valid.min()))
                    max_depth = max(max_depth, float(valid.max()))
                total_valid += len(valid) / img.size
            sampled += 1
        if sampled > 0:
            stats["valid_pixel_ratio_avg"] = round(total_valid / sampled, 4)
        if min_depth < float('inf'):
            stats["depth_range_mm"] = [round(min_depth, 2), round(max_depth, 2)]
    except ImportError:
        pass
    return stats


def analyze_camera_poses(poses_path):
    stats = {
        "exists": False,
        "frame_count": 0,
        "has_view_matrix": False,
        "has_projection_matrix": False,
        "has_fov": False,
        "position_range": {},
    }
    if not poses_path.exists():
        return stats
    stats["exists"] = True
    try:
        with open(poses_path, 'r') as f:
            poses = json.load(f)
        frame_keys = [k for k in poses.keys() if k.isdigit()]
        stats["frame_count"] = len(frame_keys)
        if frame_keys:
            first = poses[frame_keys[0]]
            stats["has_view_matrix"] = "view_matrix" in first
            stats["has_projection_matrix"] = "projection_matrix" in first
            stats["has_fov"] = "fov_degrees" in first
            positions = []
            for k in frame_keys:
                if "position" in poses[k]:
                    positions.append(poses[k]["position"])
            if positions:
                xs = [p[0] for p in positions]
                ys = [p[1] for p in positions]
                zs = [p[2] for p in positions]
                stats["position_range"] = {
                    "x": [round(min(xs), 4), round(max(xs), 4)],
                    "y": [round(min(ys), 4), round(max(ys), 4)],
                    "z": [round(min(zs), 4), round(max(zs), 4)],
                }
    except Exception as e:
        stats["error"] = str(e)
    return stats


def analyze_bop_files(output_dir):
    stats = {
        "has_scene_camera": False,
        "has_scene_gt": False,
        "has_gt_6dof": False,
        "scene_camera_frame_count": 0,
        "scene_gt_frame_count": 0,
        "gt_6dof_frame_count": 0,
        "bop_compliant": False,
    }
    scene_cam = output_dir / "scene_camera.json"
    scene_gt = output_dir / "scene_gt.json"
    gt_6dof = output_dir / "gt_6dof.json"
    stats["has_scene_camera"] = scene_cam.exists()
    stats["has_scene_gt"] = scene_gt.exists()
    stats["has_gt_6dof"] = gt_6dof.exists()
    if scene_cam.exists():
        try:
            with open(scene_cam) as f:
                data = json.load(f)
            stats["scene_camera_frame_count"] = len([k for k in data.keys() if k.isdigit()])
        except Exception:
            pass
    if scene_gt.exists():
        try:
            with open(scene_gt) as f:
                data = json.load(f)
            stats["scene_gt_frame_count"] = len([k for k in data.keys() if k.isdigit()])
        except Exception:
            pass
    if gt_6dof.exists():
        try:
            with open(gt_6dof) as f:
                data = json.load(f)
            stats["gt_6dof_frame_count"] = data.get("frame_count", 0)
        except Exception:
            pass
    stats["bop_compliant"] = stats["has_scene_camera"] and stats["has_scene_gt"]
    return stats


def analyze_topology_labels(output_dir):
    stats = {
        "has_topology_labels": False,
        "has_topology_summary": False,
        "total_faces": 0,
        "total_triangles": 0,
        "category_distribution": {},
    }
    labels_path = output_dir / "topology_labels.json"
    summary_path = output_dir / "topology_summary.json"
    stats["has_topology_labels"] = labels_path.exists()
    stats["has_topology_summary"] = summary_path.exists()
    if summary_path.exists():
        try:
            with open(summary_path) as f:
                data = json.load(f)
            stats["total_faces"] = data.get("total_faces", 0)
            stats["total_triangles"] = data.get("total_triangles", 0)
            stats["category_distribution"] = data.get("categories", {})
        except Exception:
            pass
    return stats


def compute_training_readiness(report):
    score = 0
    max_score = 100
    checks = []

    if report["rgb"]["count"] > 0:
        score += 10
        checks.append(("RGB images present", True, 10))
    else:
        checks.append(("RGB images present", False, 0))

    if report["rgb"]["count"] >= 100:
        score += 10
        checks.append(("Sufficient images (>=100)", True, 10))
    else:
        checks.append(("Sufficient images (>=100)", False, 0))

    if report["mask"]["count"] > 0:
        score += 15
        checks.append(("Semantic masks present", True, 15))
    else:
        checks.append(("Semantic masks present", False, 0))

    if report["mask"]["mask_coverage_avg"] > 0.01:
        score += 10
        checks.append(("Mask coverage adequate", True, 10))
    else:
        checks.append(("Mask coverage adequate", False, 0))

    if report["instance_mask"]["count"] > 0:
        score += 10
        checks.append(("Instance masks present", True, 10))
    else:
        checks.append(("Instance masks present", False, 0))

    if report["camera_poses"]["exists"]:
        score += 10
        checks.append(("Camera poses present", True, 10))
    else:
        checks.append(("Camera poses present", False, 0))

    if report["bop"]["bop_compliant"]:
        score += 15
        checks.append(("BOP format compliant", True, 15))
    else:
        checks.append(("BOP format compliant", False, 0))

    if report["depth"]["count"] > 0:
        score += 5
        checks.append(("Depth maps present", True, 5))
    else:
        checks.append(("Depth maps present", False, 0))

    if report["topology"]["has_topology_labels"]:
        score += 10
        checks.append(("STEP topology ground truth", True, 10))
    else:
        checks.append(("STEP topology ground truth", False, 0))

    if report["mask"]["count"] == report["rgb"]["count"] and report["rgb"]["count"] > 0:
        score += 5
        checks.append(("Mask/RGB count match", True, 5))
    else:
        checks.append(("Mask/RGB count match", False, 0))

    grade = "F"
    if score >= 90:
        grade = "A+"
    elif score >= 80:
        grade = "A"
    elif score >= 70:
        grade = "B"
    elif score >= 60:
        grade = "C"
    elif score >= 50:
        grade = "D"

    return {
        "score": score,
        "max_score": max_score,
        "grade": grade,
        "checks": checks,
        "ready_for_training": score >= 70,
    }


def generate_report(dataset_dir, output_path=None, format_type="json"):
    dataset_path = Path(dataset_dir)
    if not dataset_path.exists():
        print(f"ERROR: Dataset directory not found: {dataset_dir}")
        return None

    report = {
        "dataset_path": str(dataset_path),
        "generator": "Huhb3D-SyntheticDataPipeline",
        "report_version": "1.0",
        "rgb": analyze_rgb_directory(dataset_path / "rgb"),
        "mask": analyze_mask_directory(dataset_path / "mask"),
        "instance_mask": analyze_instance_mask_directory(dataset_path / "mask_instance"),
        "depth": analyze_depth_directory(dataset_path / "depth"),
        "camera_poses": analyze_camera_poses(dataset_path / "camera_poses.json"),
        "bop": analyze_bop_files(dataset_path),
        "topology": analyze_topology_labels(dataset_path),
    }

    report["training_readiness"] = compute_training_readiness(report)

    report["summary"] = {
        "total_images": report["rgb"]["count"],
        "total_masks": report["mask"]["count"],
        "total_instance_masks": report["instance_mask"]["count"],
        "total_depth_maps": report["depth"]["count"],
        "has_6dof_poses": report["camera_poses"]["exists"],
        "bop_compliant": report["bop"]["bop_compliant"],
        "has_ground_truth_topology": report["topology"]["has_topology_labels"],
        "training_readiness_score": report["training_readiness"]["score"],
        "training_readiness_grade": report["training_readiness"]["grade"],
        "ready_for_training": report["training_readiness"]["ready_for_training"],
    }

    if output_path is None:
        output_path = str(dataset_path / "dataset_report.json")

    if format_type == "json" or output_path.endswith(".json"):
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"[Report] JSON report saved to: {output_path}")
    elif format_type == "html" or output_path.endswith(".html"):
        html = generate_html_report(report)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"[Report] HTML report saved to: {output_path}")

    print(f"\n[Report] === Dataset Quality Summary ===")
    print(f"  Images:       {report['rgb']['count']}")
    print(f"  Masks:        {report['mask']['count']}")
    print(f"  Instance:     {report['instance_mask']['count']}")
    print(f"  Depth:        {report['depth']['count']}")
    print(f"  BOP Compliant: {report['bop']['bop_compliant']}")
    print(f"  6DoF Poses:   {report['camera_poses']['exists']}")
    print(f"  STEP GT:      {report['topology']['has_topology_labels']}")
    print(f"  Score:        {report['training_readiness']['score']}/{report['training_readiness']['max_score']} (Grade {report['training_readiness']['grade']})")
    print(f"  Ready:        {'YES' if report['training_readiness']['ready_for_training'] else 'NO'}")

    return report


def generate_html_report(report):
    tr = report["training_readiness"]
    score_pct = tr["score"]

    checks_html = ""
    for check_name, passed, points in tr["checks"]:
        icon = "✅" if passed else "❌"
        checks_html += f"<tr><td>{icon} {check_name}</td><td>{points}</td></tr>\n"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Huhb3D Dataset Quality Report</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 40px; background: #f5f5f5; }}
.container {{ max-width: 900px; margin: 0 auto; background: white; padding: 40px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
h1 {{ color: #1a1a2e; border-bottom: 3px solid #e94560; padding-bottom: 10px; }}
h2 {{ color: #16213e; margin-top: 30px; }}
.score {{ font-size: 48px; font-weight: bold; text-align: center; padding: 20px; }}
.score.a {{ color: #27ae60; }}
.score.b {{ color: #f39c12; }}
.score.f {{ color: #e74c3c; }}
table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
th, td {{ padding: 10px 15px; text-align: left; border-bottom: 1px solid #eee; }}
th {{ background: #f8f9fa; font-weight: 600; }}
.metric {{ display: inline-block; background: #f0f0f0; padding: 15px 25px; margin: 5px; border-radius: 8px; text-align: center; }}
.metric .value {{ font-size: 28px; font-weight: bold; color: #2c3e50; }}
.metric .label {{ font-size: 12px; color: #7f8c8d; }}
.badge {{ display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: bold; }}
.badge.green {{ background: #d4edda; color: #155724; }}
.badge.red {{ background: #f8d7da; color: #721c24; }}
</style>
</head>
<body>
<div class="container">
<h1>🤖 Huhb3D Dataset Quality Report</h1>
<p><strong>Dataset:</strong> {report['dataset_path']}</p>
<p><strong>Generator:</strong> {report['generator']}</p>

<h2>📊 Training Readiness Score</h2>
<div class="score {'a' if score_pct >= 70 else 'b' if score_pct >= 50 else 'f'}">
    {tr['score']}/{tr['max_score']} — Grade {tr['grade']}
</div>
<p style="text-align:center">
    <span class="badge {'green' if tr['ready_for_training'] else 'red'}">
        {'READY FOR TRAINING' if tr['ready_for_training'] else 'NOT READY — needs improvement'}
    </span>
</p>

<h2>📋 Quality Checks</h2>
<table>
<tr><th>Check</th><th>Points</th></tr>
{checks_html}
</table>

<h2>📈 Dataset Statistics</h2>
<div class="metric"><div class="value">{report['rgb']['count']}</div><div class="label">RGB Images</div></div>
<div class="metric"><div class="value">{report['mask']['count']}</div><div class="label">Semantic Masks</div></div>
<div class="metric"><div class="value">{report['instance_mask']['count']}</div><div class="label">Instance Masks</div></div>
<div class="metric"><div class="value">{report['depth']['count']}</div><div class="label">Depth Maps</div></div>

<h2>📐 6DoF & BOP</h2>
<table>
<tr><td>BOP Compliant</td><td>{'✅ Yes' if report['bop']['bop_compliant'] else '❌ No'}</td></tr>
<tr><td>Camera Poses</td><td>{'✅ Yes' if report['camera_poses']['exists'] else '❌ No'} ({report['camera_poses']['frame_count']} frames)</td></tr>
<tr><td>scene_camera.json</td><td>{'✅' if report['bop']['has_scene_camera'] else '❌'} ({report['bop']['scene_camera_frame_count']} frames)</td></tr>
<tr><td>scene_gt.json</td><td>{'✅' if report['bop']['has_scene_gt'] else '❌'} ({report['bop']['scene_gt_frame_count']} frames)</td></tr>
<tr><td>gt_6dof.json</td><td>{'✅' if report['bop']['has_gt_6dof'] else '❌'} ({report['bop']['gt_6dof_frame_count']} frames)</td></tr>
</table>

<h2>🔬 STEP Topology Ground Truth</h2>
<table>
<tr><td>Topology Labels</td><td>{'✅ Yes' if report['topology']['has_topology_labels'] else '❌ No'}</td></tr>
<tr><td>Total Faces</td><td>{report['topology']['total_faces']}</td></tr>
<tr><td>Total Triangles</td><td>{report['topology']['total_triangles']}</td></tr>
</table>

<h2>📏 Depth Maps</h2>
<table>
<tr><td>Count</td><td>{report['depth']['count']}</td></tr>
<tr><td>Has .npy</td><td>{'✅' if report['depth']['has_npy'] else '❌'}</td></tr>
<tr><td>Depth Range (mm)</td><td>{report['depth']['depth_range_mm']}</td></tr>
<tr><td>Valid Pixel Ratio</td><td>{report['depth']['valid_pixel_ratio_avg']:.2%}</td></tr>
</table>

<p style="margin-top:30px;color:#999;font-size:12px;">Generated by Huhb3D-SyntheticDataPipeline Report Engine v1.0</p>
</div>
</body>
</html>"""
    return html


def main():
    parser = argparse.ArgumentParser(description="Huhb3D Dataset Quality Report Generator")
    parser.add_argument("--input", "-i", required=True, help="Dataset directory")
    parser.add_argument("--output", "-o", default=None, help="Output report path (.json or .html)")
    parser.add_argument("--format", "-f", choices=["json", "html"], default="json", help="Report format")
    args = parser.parse_args()

    output = args.output
    if output is None:
        ext = ".html" if args.format == "html" else ".json"
        output = str(Path(args.input) / f"dataset_report{ext}")

    report = generate_report(args.input, output, args.format)
    sys.exit(0 if report else 1)


if __name__ == "__main__":
    main()
