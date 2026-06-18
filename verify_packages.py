from pathlib import Path
import json

pkg = Path(__file__).parent / "Huhb3D-Precision-Benchmark"
print("=== Huhb3D-Precision-Benchmark Package Verification ===\n")

required_files = ["README.md", "CITATION.cff", "dataset_info.json",
                  "roboflow_config.json", "checksums.sha256", "dataset_metadata.json"]
for f in required_files:
    exists = (pkg / f).exists()
    status = "OK" if exists else "MISSING"
    print(f"  {f:30s} {status}")

print()
objects = sorted([d.name for d in pkg.iterdir() if d.is_dir() and (d / "depth").exists()])
print(f"  Objects with depth: {len(objects)}")

for obj in objects[:3]:
    obj_dir = pkg / obj
    rgb_count = len(list((obj_dir / "rgb").glob("*.png"))) if (obj_dir / "rgb").exists() else 0
    depth_count = len(list((obj_dir / "depth").glob("*.png"))) if (obj_dir / "depth").exists() else 0
    mask_count = len(list((obj_dir / "mask").glob("*.png"))) if (obj_dir / "mask").exists() else 0
    has_sc = (obj_dir / "scene_camera.json").exists()
    has_sg = (obj_dir / "scene_gt.json").exists()
    has_coco = (obj_dir / "coco_annotations.json").exists()
    print(f"  {obj}: rgb={rgb_count} depth={depth_count} mask={mask_count} sc={has_sc} sg={has_sg} coco={has_coco}")

reports_dir = pkg / "reports"
if reports_dir.exists():
    reports = list(reports_dir.glob("*.txt"))
    print(f"  Reports: {len(reports)} files")
    for r in reports:
        print(f"    - {r.name}")

code_dir = pkg / "code_templates"
if code_dir.exists():
    templates = list(code_dir.glob("*.py"))
    print(f"  Code templates: {len(templates)} files")
    for t in templates:
        print(f"    - {t.name}")

total_size = sum(f.stat().st_size for f in pkg.rglob("*") if f.is_file())
total_files = sum(1 for f in pkg.rglob("*") if f.is_file())
print(f"  Total: {total_files} files, {total_size/1024/1024:.1f} MB")

print("\n=== HF Format Check ===")
readme = pkg / "README.md"
if readme.exists():
    content = readme.read_text(encoding="utf-8")
    has_yaml = content.startswith("---")
    has_bibtex = "@dataset" in content
    has_quickstart = "Quick Start" in content
    has_citation = "Citation" in content
    print(f"  YAML frontmatter: {'OK' if has_yaml else 'MISSING'}")
    print(f"  BibTeX citation: {'OK' if has_bibtex else 'MISSING'}")
    print(f"  Quick Start section: {'OK' if has_quickstart else 'MISSING'}")
    print(f"  Citation section: {'OK' if has_citation else 'MISSING'}")

print("\n=== Roboflow Format Check ===")
rf_config = pkg / "roboflow_config.json"
if rf_config.exists():
    with open(rf_config) as f:
        cfg = json.load(f)
    print(f"  dataset_name: {cfg.get('dataset_name', 'MISSING')}")
    print(f"  classes: {len(cfg.get('classes', []))} objects")
    print(f"  annotation_format: {cfg.get('annotation_format', 'MISSING')}")
    print(f"  image size: {cfg.get('images', {})}")

print("\n=== Synthesizer Package Check ===")
synth = Path(__file__).parent / "huhb3d-synthesizer"
if synth.exists():
    pyproject = synth / "pyproject.toml"
    license_f = synth / "LICENSE"
    readme_f = synth / "README.md"
    init_f = synth / "huhb3d_synthesizer" / "__init__.py"
    cli_f = synth / "huhb3d_synthesizer" / "cli.py"
    gen_f = synth / "huhb3d_synthesizer" / "generator.py"
    aug_f = synth / "huhb3d_synthesizer" / "augmentor.py"
    ver_f = synth / "huhb3d_synthesizer" / "verifier.py"
    pkg_f = synth / "huhb3d_synthesizer" / "packager.py"

    for label, path in [
        ("pyproject.toml", pyproject), ("LICENSE", license_f),
        ("README.md", readme_f), ("__init__.py", init_f),
        ("cli.py", cli_f), ("generator.py", gen_f),
        ("augmentor.py", aug_f), ("verifier.py", ver_f),
        ("packager.py", pkg_f),
    ]:
        status = "OK" if path.exists() else "MISSING"
        print(f"  {label:20s} {status}")

print("\n=== ALL CHECKS COMPLETE ===")
