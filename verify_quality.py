import json, struct, sys
from pathlib import Path

base = Path(r"d:\Huhb\AIProject\Huhb-Utopia-Project\Huhb-Viewer-ThreeAIExtend\Huhb3D-Viewer-AIHelper-RoboDataSynthesizer\sell_Huhb3D-6DoF-Industrial-Standard")

print("=" * 60)
print("  COMMERCIAL DATA QUALITY VERIFICATION REPORT")
print("=" * 60)

obj_dir = base / "flange"

print("\n[1] BOP 6DoF Ground Truth Check")
with open(obj_dir / "scene_gt.json") as f:
    sg = json.load(f)
first_key = list(sg.keys())[0]
first_obj = sg[first_key][0]
r = first_obj.get("cam_R_m2c", [])
t = first_obj.get("cam_t_m2c", [])
is_identity = (abs(r[0]-1)<0.001 and abs(r[4]-1)<0.001 and abs(r[8]-1)<0.001 and
               abs(r[1])<0.001 and abs(r[2])<0.001 and abs(r[3])<0.001 and
               abs(r[5])<0.001 and abs(r[6])<0.001 and abs(r[7])<0.001)
is_zero_t = abs(t[0])<0.001 and abs(t[1])<0.001 and abs(t[2])<0.001
print(f"  cam_R_m2c (first 3): {r[:3]}")
print(f"  cam_t_m2c: {t}")
if is_identity and is_zero_t:
    print("  STATUS: IDENTITY MATRIX - C++ engine NOT recompiled with fix!")
    print("  IMPACT: 6DoF training data is INVALID. Must recompile.")
else:
    print("  STATUS: OK - Non-trivial poses (fix applied)")

print("\n[2] Camera Intrinsics Check")
with open(obj_dir / "scene_camera.json") as f:
    sc = json.load(f)
first_cam = sc[first_key]
cam_K = first_cam.get("cam_K", [])
depth_scale = first_cam.get("depth_scale", "N/A")
print(f"  cam_K: {cam_K}")
print(f"  depth_scale: {depth_scale}")
print(f"  Total frames: {len(sc)}")
if len(cam_K) == 9:
    fx, fy = cam_K[0], cam_K[4]
    print(f"  fx={fx:.1f}, fy={fy:.1f}, cx={cam_K[2]:.1f}, cy={cam_K[5]:.1f}")
    if abs(fx - fy) < 1.0:
        print("  STATUS: OK - Square pixels")
    else:
        print("  STATUS: WARNING - Non-square pixels")

print("\n[3] Instance Segmentation Check")
inst_dir = obj_dir / "mask_instance"
print(f"  mask_instance dir exists: {inst_dir.exists()}")
if inst_dir.exists():
    inst_count = len(list(inst_dir.glob("*.png")))
    print(f"  Instance mask count: {inst_count}")
else:
    print("  STATUS: MISSING - No instance segmentation masks!")

print("\n[4] COCO Format Check")
coco_path = obj_dir / "coco_annotations.json"
coco_inst_path = obj_dir / "coco_instance_annotations.json"
print(f"  COCO semantic: {coco_path.exists()}")
print(f"  COCO instance: {coco_inst_path.exists()}")
if coco_path.exists():
    with open(coco_path) as f:
        coco = json.load(f)
    ann_count = len(coco.get("annotations", []))
    img_count = len(coco.get("images", []))
    print(f"  Semantic: {img_count} images, {ann_count} annotations")
    if ann_count > 0:
        sample = coco["annotations"][0]
        seg = sample.get("segmentation", {})
        if isinstance(seg, dict) and "counts" in seg:
            counts = seg["counts"]
            total_px = sum(counts)
            h, w = seg.get("size", [0, 0])
            expected = h * w
            match = total_px == expected
            print(f"  RLE pixel count: {total_px} (expected {expected}) match={match}")
            if not match:
                print("  STATUS: ERROR - RLE pixel count mismatch! COCO decode will fail!")
            else:
                print("  STATUS: OK - RLE encoding correct")

print("\n[5] YOLO Format Check")
yolo_dir = obj_dir / "yolo_labels"
print(f"  YOLO labels dir: {yolo_dir.exists()}")
if yolo_dir.exists():
    yolo_count = len(list(yolo_dir.glob("*.txt")))
    print(f"  YOLO label files: {yolo_count}")

print("\n[6] STL Geometry Precision")
stl_dir = base / "_source_models" / "stl"
if stl_dir.exists():
    for stl_file in sorted(stl_dir.glob("*.stl"))[:5]:
        with open(stl_file, "rb") as f:
            f.read(80)
            tri_count = struct.unpack("<I", f.read(4))[0]
        size_kb = stl_file.stat().st_size / 1024
        print(f"  {stl_file.name}: {tri_count} triangles, {size_kb:.1f} KB")
        if tri_count < 100:
            print(f"    WARNING: Very low triangle count - geometry may be too coarse!")
        elif tri_count > 100000:
            print(f"    NOTE: High triangle count - good precision but slower rendering")
        else:
            print(f"    OK: Reasonable triangle count for industrial parts")

print("\n[7] Dataset Metadata & Legal")
meta_path = base / "DATASET_METADATA.json"
if meta_path.exists():
    with open(meta_path) as f:
        meta = json.load(f)
    print(f"  dataset_id: {meta.get('dataset_id')}")
    print(f"  total_objects: {meta.get('statistics', {}).get('total_objects')}")
    print(f"  total_rgb_images: {meta.get('statistics', {}).get('total_rgb_images')}")
    print(f"  license: {meta.get('license', {}).get('id')}")
    print(f"  commercial_use: {meta.get('license', {}).get('commercial_use_allowed')}")
else:
    print("  DATASET_METADATA.json NOT FOUND")

print(f"  LICENSE file: {(base / 'LICENSE').exists()}")
print(f"  README.md: {(base / 'README.md').exists()}")
print(f"  checksums.sha256: {(base / 'checksums.sha256').exists()}")

print("\n[8] Per-Object Summary")
for obj_dir in sorted(base.iterdir()):
    if not obj_dir.is_dir() or obj_dir.name.startswith("_"):
        continue
    rgb = len(list((obj_dir / "rgb").glob("*.png"))) if (obj_dir / "rgb").exists() else 0
    mask = len(list((obj_dir / "mask").glob("*.png"))) if (obj_dir / "mask").exists() else 0
    depth = len(list((obj_dir / "depth").glob("*.png"))) if (obj_dir / "depth").exists() else 0
    has_bop = (obj_dir / "scene_camera.json").exists() and (obj_dir / "scene_gt.json").exists()
    has_coco = (obj_dir / "coco_annotations.json").exists()
    has_yolo = (obj_dir / "yolo_labels").exists()
    status = "OK" if rgb == 500 and mask == 500 and depth == 500 and has_bop else "INCOMPLETE"
    print(f"  {obj_dir.name:20s} | RGB:{rgb:4d} Mask:{mask:4d} Depth:{depth:4d} | BOP:{has_bop} COCO:{has_coco} YOLO:{has_yolo} | {status}")

print(f"\n{'='*60}")
print("  VERIFICATION COMPLETE")
print(f"{'='*60}")
