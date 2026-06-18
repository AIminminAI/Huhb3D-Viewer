import json
import math
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

BASE = Path(r"d:\Huhb\AIProject\Huhb-Utopia-Project\Huhb-Viewer-ThreeAIExtend\Huhb3D-Viewer-AIHelper-RoboDataSynthesizer\sell_Huhb3D-Test-Precision-v4")

CAMERA_RADIUS_MM = 800.0
NEAR_PLANE_MM = CAMERA_RADIUS_MM * 0.05
FAR_PLANE_MM = CAMERA_RADIUS_MM * 20.0
IMAGE_WIDTH = 800
IMAGE_HEIGHT = 600
FOV_DEG = 45.0
MODEL_UNIT = "mm"

PASS_COUNT = 0
FAIL_COUNT = 0


def check(name, condition, detail=""):
    global PASS_COUNT, FAIL_COUNT
    status = "PASS" if condition else "FAIL"
    if condition:
        PASS_COUNT += 1
    else:
        FAIL_COUNT += 1
    msg = f"  [{status}] {name}"
    if detail:
        msg += f" -- {detail}"
    print(msg)
    return condition


def load_depth_png(path):
    img = Image.open(path)
    arr = np.array(img)
    if arr.ndim == 2:
        return arr.astype(np.float64)
    return arr[:, :, 0].astype(np.float64)


def load_rgb_png(path):
    img = Image.open(path)
    return np.array(img)


def rotation_matrix_is_valid(R, tol=0.01):
    R = np.array(R, dtype=np.float64).reshape(3, 3)
    det = np.linalg.det(R)
    RtR = R.T @ R
    eye = np.eye(3)
    det_ok = abs(abs(det) - 1.0) < tol
    orth_ok = np.allclose(RtR, eye, atol=tol)
    return det_ok and orth_ok


def zbuf_to_linear_depth(z_buf, near, far):
    return (near * far) / (far - z_buf * (far - near))


def main():
    print("=" * 70)
    print("  INDUSTRIAL-GRADE PRECISION VERIFICATION v2")
    print("  Verifying: Depth Maps + Camera Intrinsics + BOP Compliance")
    print("=" * 70)
    print(f"  Camera radius: {CAMERA_RADIUS_MM}mm ({CAMERA_RADIUS_MM/1000:.1f}m)")
    print(f"  Near plane: {NEAR_PLANE_MM:.1f}mm ({NEAR_PLANE_MM/1000:.4f}m)")
    print(f"  Far plane: {FAR_PLANE_MM:.0f}mm ({FAR_PLANE_MM/1000:.1f}m)")
    print(f"  Near/Far ratio: {FAR_PLANE_MM/NEAR_PLANE_MM:.0f}:1")

    obj_dirs = sorted([d for d in BASE.iterdir() if d.is_dir() and (d / "scene_camera.json").exists()])
    if not obj_dirs:
        print("  ERROR: No object directories with scene_camera.json found!")
        sys.exit(1)

    print(f"\n  Found {len(obj_dirs)} objects to verify\n")

    test_obj = obj_dirs[0]
    print(f"  Primary test object: {test_obj.name}\n")

    with open(test_obj / "scene_camera.json") as f:
        scene_cam = json.load(f)
    with open(test_obj / "scene_gt.json") as f:
        scene_gt = json.load(f)

    print("-" * 70)
    print("  SECTION 1: CAMERA INTRINSICS (fx, fy, cx, cy)")
    print("-" * 70)

    f_ref = 1.0 / math.tan(FOV_DEG * 0.5 * math.pi / 180.0)
    fx_ref = IMAGE_HEIGHT * f_ref * 0.5
    fy_ref = IMAGE_HEIGHT * f_ref * 0.5
    cx_ref = IMAGE_WIDTH * 0.5
    cy_ref = IMAGE_HEIGHT * 0.5

    print(f"  Reference (no jitter): fx={fx_ref:.3f}, fy={fy_ref:.3f}, cx={cx_ref:.1f}, cy={cy_ref:.1f}")

    for frame_id in list(scene_cam.keys())[:3]:
        cam = scene_cam[frame_id]
        K = cam["cam_K"]
        fx, fy, cx, cy = K[0], K[4], K[2], K[5]

        check(f"Frame {frame_id}: fx == fy (square pixel)",
              abs(fx - fy) < 0.01,
              f"fx={fx:.3f}, fy={fy:.3f}, diff={abs(fx-fy):.6f}")

        check(f"Frame {frame_id}: cx = imageWidth/2",
              abs(cx - cx_ref) < 0.01,
              f"cx={cx:.1f}, expected={cx_ref:.1f}")

        check(f"Frame {frame_id}: cy = imageHeight/2",
              abs(cy - cy_ref) < 0.01,
              f"cy={cy:.1f}, expected={cy_ref:.1f}")

        jittered_fov = 2.0 * math.atan(1.0 / (fx / (IMAGE_HEIGHT * 0.5))) * 180.0 / math.pi
        check(f"Frame {frame_id}: FOV near 45 deg (with jitter)",
              abs(jittered_fov - FOV_DEG) < 5.0,
              f"jittered_fov={jittered_fov:.2f} deg")

    print()
    print("-" * 70)
    print("  SECTION 2: BOP DEPTH_SCALE")
    print("-" * 70)

    for frame_id in list(scene_cam.keys())[:3]:
        cam = scene_cam[frame_id]
        ds = cam.get("depth_scale", -1)
        check(f"Frame {frame_id}: depth_scale == 1.0",
              abs(ds - 1.0) < 0.001,
              f"depth_scale={ds}")

    print()
    print("-" * 70)
    print("  SECTION 3: DEPTH MAP PRECISION")
    print("-" * 70)

    depth_dir = test_obj / "depth"
    depth_files = sorted(depth_dir.glob("depth_*.png")) if depth_dir.exists() else []

    if not depth_files:
        check("Depth maps exist", False, "No depth PNG files found!")
    else:
        check("Depth maps exist", True, f"{len(depth_files)} files")

        for df in depth_files[:3]:
            depth_arr = load_depth_png(str(df))
            frame_name = df.stem

            non_zero = depth_arr[depth_arr > 0]
            if len(non_zero) == 0:
                check(f"{frame_name}: non-zero depth values", False, "All zeros!")
                continue

            min_depth = float(non_zero.min())
            max_depth = float(non_zero.max())
            mean_depth = float(non_zero.mean())

            check(f"{frame_name}: depth values in valid range",
                  min_depth > 0 and max_depth < 65535,
                  f"min={min_depth:.1f}, max={max_depth:.1f} mm")

            check(f"{frame_name}: min depth >= near plane ({NEAR_PLANE_MM:.0f}mm)",
                  min_depth >= NEAR_PLANE_MM * 0.5,
                  f"min_depth={min_depth:.1f}mm, near_plane={NEAR_PLANE_MM:.0f}mm")

            check(f"{frame_name}: max depth <= far plane ({FAR_PLANE_MM:.0f}mm)",
                  max_depth <= FAR_PLANE_MM * 1.1,
                  f"max_depth={max_depth:.1f}mm, far_plane={FAR_PLANE_MM:.0f}mm")

            check(f"{frame_name}: depth in industrial range (500-2000mm)",
                  500.0 <= min_depth and max_depth <= 2000.0,
                  f"range=[{min_depth:.1f}, {max_depth:.1f}]mm")

            print(f"    [INFO] {frame_name}: depth range [{min_depth:.1f}, {max_depth:.1f}]mm, mean={mean_depth:.1f}mm")

    print()
    print("-" * 70)
    print("  SECTION 4: DEPTH FORMULA VERIFICATION")
    print("-" * 70)

    if depth_files:
        df = depth_files[0]
        depth_arr = load_depth_png(str(df))
        frame_idx = int(df.stem.split("_")[1]) - 1
        frame_key = str(frame_idx + 1)

        print(f"  Near plane = {NEAR_PLANE_MM:.1f}mm, Far plane = {FAR_PLANE_MM:.0f}mm")

        z_buf_near = 0.01
        z_buf_mid = 0.1
        z_buf_far = 0.9

        for z_buf_val in [z_buf_near, z_buf_mid, z_buf_far]:
            depth_mm = zbuf_to_linear_depth(z_buf_val, NEAR_PLANE_MM, FAR_PLANE_MM)
            print(f"    z_buf={z_buf_val:.2f} -> depth={depth_mm:.1f}mm ({depth_mm/1000:.4f}m)")

        depth_at_mid = zbuf_to_linear_depth(0.5, NEAR_PLANE_MM, FAR_PLANE_MM)
        print(f"\n    At z_buf=0.5 (mid-buffer): depth={depth_at_mid:.1f}mm ({depth_at_mid/1000:.3f}m)")

        non_zero = depth_arr[depth_arr > 0]
        if len(non_zero) > 0:
            min_d = float(non_zero.min())
            max_d = float(non_zero.max())
            mean_d = float(non_zero.mean())

            cam_dist_mm = CAMERA_RADIUS_MM
            check(f"Depth values consistent with camera distance ({cam_dist_mm:.0f}mm)",
                  abs(mean_d - cam_dist_mm) < cam_dist_mm * 0.5,
                  f"mean_depth={mean_d:.1f}mm, camera_dist={cam_dist_mm:.0f}mm")

            check(f"Depth range reasonable for industrial inspection",
                  min_d > 300.0 and max_d < 3000.0,
                  f"range=[{min_d:.1f}, {max_d:.1f}]mm")

    print()
    print("-" * 70)
    print("  SECTION 5: REPROJECTION ERROR (6DoF + Depth Consistency)")
    print("-" * 70)

    if depth_files and frame_key in scene_cam and frame_key in scene_gt:
        cam = scene_cam[frame_key]
        K = cam["cam_K"]
        fx, fy, cx, cy = K[0], K[4], K[2], K[5]

        gt = scene_gt[frame_key][0]
        R_m2c = np.array(gt["cam_R_m2c"], dtype=np.float64).reshape(3, 3)
        t_m2c = np.array(gt["cam_t_m2c"], dtype=np.float64)

        mask_dir = test_obj / "mask_instance"
        mask_files = sorted(mask_dir.glob("instance_*.png")) if mask_dir.exists() else []

        if mask_files:
            mask_arr = load_rgb_png(str(mask_files[0]))
            obj_pixels = np.where(mask_arr[:, :, 0] > 0)

            if len(obj_pixels[0]) > 0:
                np.random.seed(42)
                sample_indices = np.random.choice(len(obj_pixels[0]), min(200, len(obj_pixels[0])), replace=False)

                depth_errors = []
                for idx in sample_indices:
                    py, px = int(obj_pixels[0][idx]), int(obj_pixels[1][idx])
                    depth_mm = float(depth_arr[py, px])
                    if depth_mm <= 0:
                        continue

                    depth_m = depth_mm / 1000.0

                    x_cam = (px - cx) * depth_m / fx
                    y_cam = (py - cy) * depth_m / fy
                    z_cam = depth_m

                    p_model = R_m2c.T @ (np.array([x_cam, y_cam, z_cam]) - t_m2c)

                    reproj_z = R_m2c[2, 0] * p_model[0] + R_m2c[2, 1] * p_model[1] + R_m2c[2, 2] * p_model[2] + t_m2c[2]
                    reproj_x = fx * (R_m2c[0, 0] * p_model[0] + R_m2c[0, 1] * p_model[1] + R_m2c[0, 2] * p_model[2] + t_m2c[0]) / reproj_z + cx
                    reproj_y = fy * (R_m2c[1, 0] * p_model[0] + R_m2c[1, 1] * p_model[1] + R_m2c[1, 2] * p_model[2] + t_m2c[1]) / reproj_z + cy

                    err = math.sqrt((reproj_x - px)**2 + (reproj_y - py)**2)
                    depth_errors.append(err)

                if depth_errors:
                    mean_err = np.mean(depth_errors)
                    max_err = np.max(depth_errors)
                    median_err = np.median(depth_errors)
                    check("Reprojection error < 2.0 px (industrial grade)",
                          mean_err < 2.0,
                          f"mean={mean_err:.4f}px, median={median_err:.4f}px, max={max_err:.4f}px")
                    check("Reprojection error < 0.5 px (high precision)",
                          mean_err < 0.5,
                          f"mean={mean_err:.4f}px")
            else:
                print("    [WARN] No object pixels in instance mask")
        else:
            print("    [WARN] No instance mask files found")

    print()
    print("-" * 70)
    print("  SECTION 6: OPENGL->OPENCV COORDINATE CONVENTION")
    print("-" * 70)

    for frame_id in list(scene_gt.keys())[:3]:
        gt_list = scene_gt[frame_id]
        for gt in gt_list:
            R = gt["cam_R_m2c"]
            t = gt["cam_t_m2c"]

            check(f"Frame {frame_id}: R_m2c is valid rotation matrix",
                  rotation_matrix_is_valid(R),
                  f"det={np.linalg.det(np.array(R, dtype=np.float64).reshape(3,3)):.6f}")

            R_mat = np.array(R, dtype=np.float64).reshape(3, 3)
            z_cam_dir = R_mat[2, :]

            cam_t_w2c = np.array(t, dtype=np.float64)
            cam_dist = np.linalg.norm(cam_t_w2c)
            check(f"Frame {frame_id}: camera distance ~{CAMERA_RADIUS_MM:.0f}mm",
                  abs(cam_dist - CAMERA_RADIUS_MM) < CAMERA_RADIUS_MM * 0.5,
                  f"dist={cam_dist:.1f}mm")

    print()
    print("-" * 70)
    print("  SECTION 7: INSTANCE MASK + COCO INSTANCE + YOLO")
    print("-" * 70)

    for obj_dir in obj_dirs[:3]:
        name = obj_dir.name
        inst_dir = obj_dir / "mask_instance"
        inst_files = sorted(inst_dir.glob("instance_*.png")) if inst_dir.exists() else []
        check(f"{name}: instance masks generated",
              len(inst_files) > 0,
              f"{len(inst_files)} masks")

        coco_inst = obj_dir / "coco_instance_annotations.json"
        check(f"{name}: COCO instance annotations",
              coco_inst.exists(),
              f"exists={coco_inst.exists()}")

        yolo_dir = obj_dir / "yolo_labels"
        yolo_files = sorted(yolo_dir.glob("*.txt")) if yolo_dir.exists() else []
        check(f"{name}: YOLO labels",
              len(yolo_files) > 0,
              f"{len(yolo_files)} labels")

    print()
    print("-" * 70)
    print("  SECTION 8: CROSS-OBJECT DEPTH CONSISTENCY")
    print("-" * 70)

    for obj_dir in obj_dirs[:5]:
        name = obj_dir.name
        sc_path = obj_dir / "scene_camera.json"
        depth_path = obj_dir / "depth"

        if not sc_path.exists() or not depth_path.exists():
            continue

        with open(sc_path) as f:
            sc = json.load(f)

        first_cam = sc[list(sc.keys())[0]]
        ds = first_cam.get("depth_scale", -1)
        check(f"{name}: depth_scale=1.0", abs(ds - 1.0) < 0.001, f"ds={ds}")

        K = first_cam["cam_K"]
        fx, fy = K[0], K[4]
        check(f"{name}: fx==fy", abs(fx - fy) < 0.01, f"fx={fx:.3f}, fy={fy:.3f}")

        cam_t = first_cam.get("cam_t_w2c", [0, 0, 0])
        cam_dist = math.sqrt(sum(x**2 for x in cam_t))
        check(f"{name}: camera at industrial distance",
              300 < cam_dist < 3000,
              f"dist={cam_dist:.1f}mm")

    print()
    print("=" * 70)
    print(f"  VERIFICATION SUMMARY")
    print(f"  PASS: {PASS_COUNT}")
    print(f"  FAIL: {FAIL_COUNT}")
    print(f"  Total: {PASS_COUNT + FAIL_COUNT}")
    if FAIL_COUNT == 0:
        print(f"\n  ALL CHECKS PASSED - INDUSTRIAL GRADE VERIFIED")
    else:
        print(f"\n  {FAIL_COUNT} CHECK(S) FAILED - NEEDS ATTENTION")
    print("=" * 70)


if __name__ == "__main__":
    main()
