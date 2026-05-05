"""
generator_bridge.py - Synthetic Data Generator Bridge
=====================================================
Python wrapper for the Huhb3D C++ synthetic data pipeline.

Usage:
    python generator_bridge.py --input model.stl --output dataset --count 1000
    python generator_bridge.py -i model.stl -o dataset -n 500 --radius 8.0 --no-zip
"""

import argparse
import os
import subprocess
import sys
import shutil
import zipfile
import time
import json
from pathlib import Path


def find_cpp_executable():
    search_paths = [
        Path(__file__).parent / "build" / "Release" / "test_render.exe",
        Path(__file__).parent / "build_v2" / "Release" / "test_render.exe",
        Path(__file__).parent / "build" / "test_render.exe",
        Path(__file__).parent / "build_v2" / "test_render.exe",
    ]

    for path in search_paths:
        if path.exists():
            return str(path.resolve())

    return None


def validate_input_file(input_path):
    path = Path(input_path)
    if not path.exists():
        print(f"[ERROR] Input file not found: {input_path}")
        sys.exit(1)

    valid_extensions = {'.stl', '.STL', '.obj', '.OBJ'}
    if path.suffix not in valid_extensions:
        print(f"[WARNING] File extension '{path.suffix}' may not be supported.")
        print(f"          Supported formats: {', '.join(valid_extensions)}")

    return str(path.resolve())


def run_cpp_generator(exe_path, input_file, output_dir, count, radius, width, height, save_mask):
    cmd = [
        exe_path,
        "--batch",
        "--input", input_file,
        "--output", output_dir,
        "--count", str(count),
        "--radius", str(radius),
        "--width", str(width),
        "--img-height", str(height),
    ]

    if not save_mask:
        cmd.append("--no-mask")

    print(f"\n[CMD] {' '.join(cmd)}\n")
    print("=" * 60)

    start_time = time.time()

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding='utf-8',
            errors='replace',
        )

        for line in process.stdout:
            print(line, end='')

        process.wait()
        elapsed = time.time() - start_time

        print("=" * 60)
        print(f"[Bridge] C++ process exited with code: {process.returncode}")
        print(f"[Bridge] Elapsed time: {elapsed:.2f}s")

        return process.returncode == 0

    except FileNotFoundError:
        print(f"[ERROR] Executable not found: {exe_path}")
        return False
    except Exception as e:
        print(f"[ERROR] Failed to run C++ generator: {e}")
        return False


def package_dataset(output_dir, zip_name=None):
    output_path = Path(output_dir)
    if not output_path.exists():
        print(f"[ERROR] Output directory not found: {output_dir}")
        return None

    if zip_name is None:
        zip_name = output_path.name + ".zip"

    zip_path = output_path.parent / zip_name

    print(f"\n[Package] Creating ZIP: {zip_path}")

    rgb_dir = output_path / "rgb"
    mask_dir = output_path / "mask"
    legend_file = output_path / "label_legend.txt"

    rgb_count = len(list(rgb_dir.glob("*.png"))) if rgb_dir.exists() else 0
    mask_count = len(list(mask_dir.glob("*.png"))) if mask_dir.exists() else 0

    print(f"[Package] RGB images: {rgb_count}")
    print(f"[Package] Mask images: {mask_count}")

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        if rgb_dir.exists():
            for f in sorted(rgb_dir.glob("*.png")):
                zf.write(f, f"rgb/{f.name}")

        if mask_dir.exists():
            for f in sorted(mask_dir.glob("*.png")):
                zf.write(f, f"mask/{f.name}")

        if legend_file.exists():
            zf.write(legend_file, legend_file.name)

        manifest = {
            "version": "1.0",
            "generator": "Huhb3D-SyntheticDataPipeline",
            "rgb_count": rgb_count,
            "mask_count": mask_count,
            "has_legend": legend_file.exists(),
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    zip_size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"[Package] ZIP created: {zip_path} ({zip_size_mb:.1f} MB)")

    return str(zip_path)


def generate_preview_report(output_dir):
    output_path = Path(output_dir)
    report_path = output_path / "generation_report.json"

    rgb_dir = output_path / "rgb"
    mask_dir = output_path / "mask"
    legend_file = output_path / "label_legend.txt"

    report = {
        "output_directory": str(output_path.resolve()),
        "rgb_images": len(list(rgb_dir.glob("*.png"))) if rgb_dir.exists() else 0,
        "mask_images": len(list(mask_dir.glob("*.png"))) if mask_dir.exists() else 0,
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
                    cat_color = tuple(int(x) for x in parts[2:5])
                    categories[cat_id] = {
                        "name": cat_name,
                        "color_rgb": cat_color,
                    }
        report["categories"] = categories

    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"[Report] Generation report saved to: {report_path}")
    return report


def main():
    parser = argparse.ArgumentParser(
        description="Huhb3D Synthetic Data Generator Bridge",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generator_bridge.py --input model.stl --output dataset --count 1000
  python generator_bridge.py -i model.stl -o dataset -n 500 --radius 8.0
  python generator_bridge.py -i model.stl -o dataset -n 100 --no-mask --no-zip
  python generator_bridge.py -i model.stl -o dataset --exe path/to/test_render.exe
        """,
    )

    parser.add_argument("--input", "-i", required=True,
                        help="Path to CAD model file (STL/OBJ)")
    parser.add_argument("--output", "-o", default="synthetic_output",
                        help="Output directory (default: synthetic_output)")
    parser.add_argument("--count", "-n", type=int, default=1000,
                        help="Number of samples to generate (default: 1000)")
    parser.add_argument("--radius", "-r", type=float, default=5.0,
                        help="Camera orbit radius (default: 5.0)")
    parser.add_argument("--width", "-W", type=int, default=800,
                        help="Image width in pixels (default: 800)")
    parser.add_argument("--height", "-H", type=int, default=600,
                        help="Image height in pixels (default: 600)")
    parser.add_argument("--no-mask", action="store_true",
                        help="Skip semantic mask generation")
    parser.add_argument("--no-zip", action="store_true",
                        help="Skip ZIP packaging")
    parser.add_argument("--exe", type=str, default=None,
                        help="Path to C++ executable (auto-detected if not specified)")
    parser.add_argument("--keep-raw", action="store_true",
                        help="Keep raw output directory after ZIP packaging")

    args = parser.parse_args()

    print("=" * 60)
    print("  Huhb3D Synthetic Data Generator Bridge")
    print("=" * 60)

    input_file = validate_input_file(args.input)

    if args.exe:
        exe_path = args.exe
        if not Path(exe_path).exists():
            print(f"[ERROR] Specified executable not found: {exe_path}")
            sys.exit(1)
    else:
        exe_path = find_cpp_executable()
        if not exe_path:
            print("[ERROR] C++ executable not found!")
            print("        Searched in:")
            print("          - build/Release/test_render.exe")
            print("          - build_v2/Release/test_render.exe")
            print("        Please compile the project first or specify --exe")
            sys.exit(1)

    print(f"  Executable : {exe_path}")
    print(f"  Input file : {input_file}")
    print(f"  Output dir : {args.output}")
    print(f"  Sample count: {args.count}")
    print(f"  Camera radius: {args.radius}")
    print(f"  Image size  : {args.width}x{args.height}")
    print(f"  Save mask   : {'NO' if args.no_mask else 'YES'}")
    print(f"  Package ZIP : {'NO' if args.no_zip else 'YES'}")
    print("=" * 60)

    success = run_cpp_generator(
        exe_path=exe_path,
        input_file=input_file,
        output_dir=args.output,
        count=args.count,
        radius=args.radius,
        width=args.width,
        height=args.height,
        save_mask=not args.no_mask,
    )

    if not success:
        print("\n[ERROR] C++ generator failed!")
        sys.exit(1)

    report = generate_preview_report(args.output)

    if not args.no_zip:
        zip_path = package_dataset(args.output)

        if zip_path and not args.keep_raw:
            output_path = Path(args.output)
            if output_path.exists():
                shutil.rmtree(output_path)
                print(f"[Cleanup] Removed raw output directory: {args.output}")

    print("\n" + "=" * 60)
    print("  GENERATION COMPLETE")
    print(f"  RGB images  : {report['rgb_images']}")
    print(f"  Mask images : {report['mask_images']}")
    if not args.no_zip:
        print(f"  ZIP package : {zip_path}")
    else:
        print(f"  Output dir  : {args.output}")
    print("=" * 60)


if __name__ == "__main__":
    main()
