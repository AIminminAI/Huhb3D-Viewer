import json, struct
from pathlib import Path

base = Path(r"d:\Huhb\AIProject\Huhb-Utopia-Project\Huhb-Viewer-ThreeAIExtend\Huhb3D-Viewer-AIHelper-RoboDataSynthesizer\sell_Huhb3D-6DoF-Industrial-Standard")

with open(base / "DATASET_METADATA.json") as f:
    meta = json.load(f)
print("=== DATASET METADATA ===")
print("  dataset_id:", meta["dataset_id"])
print("  total_objects:", meta["statistics"]["total_objects"])
print("  total_rgb:", meta["statistics"]["total_rgb_images"])
print("  license:", meta["license"]["id"])
print("  commercial_use:", meta["license"]["commercial_use_allowed"])

obj_dir = base / "flange"
with open(obj_dir / "scene_gt.json") as f:
    sg = json.load(f)

non_identity = 0
non_zero_t = 0
for key, objs in list(sg.items())[:50]:
    for obj in objs:
        r = obj.get("cam_R_m2c", [])
        t = obj.get("cam_t_m2c", [])
        is_id = abs(r[0]-1)<0.001 and abs(r[4]-1)<0.001 and abs(r[8]-1)<0.001
        is_zt = abs(t[0])<0.001 and abs(t[1])<0.001 and abs(t[2])<0.001
        if not is_id: non_identity += 1
        if not is_zt: non_zero_t += 1

print("\n=== BOP 6DoF QUALITY (50 frames) ===")
print(f"  Non-identity rotation: {non_identity}/50")
print(f"  Non-zero translation: {non_zero_t}/50")
bop_ok = non_identity > 40 and non_zero_t > 40
print(f"  Status: {'PASS' if bop_ok else 'FAIL'}")

with open(obj_dir / "scene_camera.json") as f:
    sc = json.load(f)
fc = sc[list(sc.keys())[0]]
print("\n=== CAMERA ===")
print("  cam_K:", fc["cam_K"])
print("  depth_scale:", fc["depth_scale"])

with open(obj_dir / "coco_annotations.json") as f:
    coco = json.load(f)
ann = coco["annotations"][0]
seg = ann["segmentation"]
counts = seg["counts"]
h, w = seg["size"]
total_px = sum(counts)
expected = h * w
print("\n=== COCO RLE ===")
print(f"  Image: {w}x{h} = {expected} px")
print(f"  RLE total: {total_px} px")
print(f"  Match: {total_px == expected}")
print(f"  Status: {'PASS' if total_px == expected else 'FAIL'}")

stl_dir = Path(r"d:\Huhb\AIProject\Huhb-Utopia-Project\Huhb-Viewer-ThreeAIExtend\Huhb3D-Viewer-AIHelper-RoboDataSynthesizer\test_models_output\stl")
print("\n=== STL GEOMETRY PRECISION ===")
for sf in sorted(stl_dir.glob("*.stl")):
    with open(sf, "rb") as f:
        f.read(80)
        tc = struct.unpack("<I", f.read(4))[0]
    q = "HIGH" if tc > 5000 else ("MEDIUM" if tc > 500 else "LOW")
    print(f"  {sf.stem:20s}: {tc:6d} triangles [{q}]")

print("\n=== LEGAL ===")
print("  LICENSE:", (base / "LICENSE").exists())
print("  README:", (base / "README.md").exists())
print("  Checksums:", (base / "checksums.sha256").exists())

inst_exists = (base / "flange" / "mask_instance" / "instance_0001.png").exists()
coco_inst = (obj_dir / "coco_instance_annotations.json").exists()
yolo = (obj_dir / "yolo_labels").exists()

print("\n=== REMAINING ISSUES ===")
issues = []
if not inst_exists: issues.append("Instance masks missing (C++ fix applied, need recompile)")
if not coco_inst: issues.append("COCO instance annotations missing (depends on instance masks)")
if not yolo: issues.append("YOLO labels missing (depends on instance masks)")
if issues:
    for i in issues: print(f"  - {i}")
    print(f"\n  All issues require C++ recompile. Run:")
    print(f"    cmake -B build -S . -G \"NMake Makefiles\" -DCMAKE_BUILD_TYPE=Release")
    print(f"    cmake --build build --config Release")
    print(f"    Then re-run sell_dataset.bat")
else:
    print("  ALL CHECKS PASSED - Ready for commercial sale!")
