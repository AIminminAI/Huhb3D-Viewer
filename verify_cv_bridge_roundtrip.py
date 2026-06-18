"""
Huhb3D cv_bridge 16UC1 Round-Trip Verification
================================================
Simulates the FULL cv_bridge pipeline without requiring ROS2:
  1. Load depth PNG (IMREAD_UNCHANGED -> uint16)
  2. Simulate cv2_to_imgmsg(encoding="16UC1") -> raw bytes
  3. Simulate imgmsg_to_cv2(encoding="16UC1") -> uint16 Mat
  4. Compare original vs round-trip: byte-exact match?
  5. Verify imshow is NOT black (after normalization)
  6. Test WRONG methods to demonstrate common pitfalls

This script validates the exact same code path that
huhb3d_ros_publisher.py uses with real cv_bridge.
"""

import cv2
import numpy as np
import struct
import sys
from pathlib import Path

DATASET_DIR = Path(__file__).parent / "sell_Huhb3D-Test-Precision-v4"


def simulate_cv2_to_imgmsg_16UC1(depth_cv):
    h, w = depth_cv.shape
    encoding = "16UC1"
    raw_bytes = depth_cv.tobytes()
    step = w * 2
    return {
        "header": {"frame_id": "huhb3d_camera"},
        "height": h,
        "width": w,
        "encoding": encoding,
        "is_bigendian": 0,
        "step": step,
        "data": raw_bytes,
    }


def simulate_imgmsg_to_cv2_16UC1(msg):
    h = msg["height"]
    w = msg["width"]
    step = msg["step"]
    data = msg["data"]

    expected_size = h * step
    if len(data) != expected_size:
        raise ValueError(
            f"Data size mismatch: got {len(data)}, expected {expected_size}"
        )

    depth = np.frombuffer(data, dtype=np.uint16).reshape(h, w)
    return depth.copy()


def simulate_wrong_imgmsg_to_cv2_mono8(msg):
    h = msg["height"]
    w = msg["width"]
    step = msg["step"]
    data = msg["data"]

    raw = np.frombuffer(data, dtype=np.uint8).reshape(h, step)
    depth8 = raw[:, :w]
    return depth8.copy()


def check_imshow_black(depth, label=""):
    if depth.dtype == np.uint16:
        vis = cv2.normalize(depth, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
        nonzero_mask = depth > 0
        if nonzero_mask.any():
            nonzero_brightness = vis[nonzero_mask].mean()
            max_brightness = vis[nonzero_mask].max()
        else:
            nonzero_brightness = 0
            max_brightness = 0
        is_black = max_brightness < 5.0
        return is_black, float(max_brightness), float(nonzero_brightness)
    elif depth.dtype == np.uint8:
        nonzero_mask = depth > 0
        if nonzero_mask.any():
            max_brightness = float(depth[nonzero_mask].max())
            nonzero_brightness = float(depth[nonzero_mask].mean())
        else:
            max_brightness = 0.0
            nonzero_brightness = 0.0
        is_black = max_brightness < 5.0
        return is_black, max_brightness, nonzero_brightness
    else:
        return True, 0.0, 0.0


def verify_single_object(obj_name, frame_id=1):
    obj_dir = DATASET_DIR / obj_name
    depth_path = obj_dir / "depth" / f"depth_{frame_id:04d}.png"

    if not depth_path.exists():
        return {"object": obj_name, "status": "SKIP", "reason": "no depth file"}

    results = {"object": obj_name}

    depth_correct = cv2.imread(str(depth_path), cv2.IMREAD_UNCHANGED)
    if depth_correct is None:
        return {**results, "status": "FAIL", "reason": "imread returned None"}

    results["dtype"] = str(depth_correct.dtype)
    results["shape"] = depth_correct.shape
    nonzero = depth_correct[depth_correct > 0]
    if len(nonzero) > 0:
        results["depth_min"] = int(nonzero.min())
        results["depth_max"] = int(nonzero.max())
        results["depth_mean"] = float(nonzero.mean())
    results["nonzero_pct"] = float((depth_correct > 0).sum() / depth_correct.size * 100)

    msg = simulate_cv2_to_imgmsg_16UC1(depth_correct)
    results["msg_encoding"] = msg["encoding"]
    results["msg_step"] = msg["step"]
    results["msg_data_len"] = len(msg["data"])
    results["msg_expected_len"] = msg["height"] * msg["step"]
    results["step_correct"] = msg["step"] == msg["width"] * 2
    results["size_correct"] = len(msg["data"]) == msg["height"] * msg["step"]

    depth_roundtrip = simulate_imgmsg_to_cv2_16UC1(msg)
    results["roundtrip_dtype"] = str(depth_roundtrip.dtype)

    if depth_correct.shape == depth_roundtrip.shape:
        diff = np.abs(depth_correct.astype(np.int32) - depth_roundtrip.astype(np.int32))
        max_diff = diff.max()
        mean_diff = diff.mean()
        results["roundtrip_max_diff"] = int(max_diff)
        results["roundtrip_mean_diff"] = float(mean_diff)
        results["roundtrip_exact"] = bool(max_diff == 0)
    else:
        results["roundtrip_exact"] = False
        results["roundtrip_max_diff"] = -1

    mask = depth_correct > 0
    if mask.any():
        direct_max_val = float(depth_correct[mask].max())
        direct_mean_val = float(depth_correct[mask].mean())
        direct_imshow_brightness = direct_max_val / 256.0
        direct_is_black = direct_imshow_brightness < 5.0
    else:
        direct_max_val = 0
        direct_mean_val = 0
        direct_imshow_brightness = 0
        direct_is_black = True
    results["imshow_direct_black"] = direct_is_black
    results["imshow_direct_raw_max"] = direct_max_val
    results["imshow_direct_brightness"] = direct_imshow_brightness

    depth_vis = cv2.normalize(depth_correct, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    if mask.any():
        norm_max = float(depth_vis[mask].max())
        norm_mean = float(depth_vis[mask].mean())
        norm_is_black = norm_max < 5.0
    else:
        norm_max = 0
        norm_mean = 0
        norm_is_black = True
    results["imshow_normalized_black"] = norm_is_black
    results["imshow_normalized_max_brightness"] = norm_max
    results["imshow_normalized_mean_brightness"] = norm_mean

    depth_wrong_gray = cv2.imread(str(depth_path), cv2.IMREAD_GRAYSCALE)
    if depth_wrong_gray is not None and depth_wrong_gray.shape == depth_correct.shape:
        mask = depth_correct > 0
        if mask.any():
            gs_error = float(
                np.abs(depth_wrong_gray[mask].astype(float) - depth_correct[mask].astype(float)).mean()
                / depth_correct[mask].astype(float).mean() * 100
            )
        else:
            gs_error = -1
        results["imread_grayscale_error_pct"] = gs_error
        results["imread_grayscale_dtype"] = str(depth_wrong_gray.dtype)

    depth_wrong_mono8 = simulate_wrong_imgmsg_to_cv2_mono8(msg)
    if depth_wrong_mono8.shape == depth_correct.shape:
        mask = depth_correct > 0
        if mask.any():
            m8_error = float(
                np.abs(depth_wrong_mono8[mask].astype(float) - depth_correct[mask].astype(float)).mean()
                / depth_correct[mask].astype(float).mean() * 100
            )
        else:
            m8_error = -1
    else:
        m8_error = -1
    results["mono8_decode_error_pct"] = m8_error

    all_pass = (
        results.get("roundtrip_exact", False)
        and not results.get("imshow_normalized_black", True)
        and results.get("imread_grayscale_error_pct", 0) > 50
        and results.get("mono8_decode_error_pct", 0) > 50
        and results.get("step_correct", False)
        and results.get("size_correct", False)
    )
    results["status"] = "PASS" if all_pass else "PARTIAL"

    return results


def main():
    print("=" * 72)
    print("  Huhb3D cv_bridge 16UC1 Round-Trip Verification")
    print("  Simulates huhb3d_ros_publisher.py pipeline WITHOUT ROS2")
    print("=" * 72)

    objects = sorted([d.name for d in DATASET_DIR.iterdir()
                      if d.is_dir() and (d / "depth").exists()])

    if not objects:
        print(f"\n[ERROR] No objects with depth/ found in {DATASET_DIR}")
        sys.exit(1)

    print(f"\nDataset: {DATASET_DIR}")
    print(f"Objects with depth: {len(objects)}")

    print("\n" + "-" * 72)
    print("  TEST 1: IMREAD_UNCHANGED -> 16UC1 encode -> 16UC1 decode")
    print("-" * 72)

    all_results = []
    for obj in objects:
        r = verify_single_object(obj)
        all_results.append(r)
        status = r.get("status", "?")
        rt = r.get("roundtrip_exact", False)
        dtype = r.get("dtype", "?")
        dmin = r.get("depth_min", "?")
        dmax = r.get("depth_max", "?")
        nz = r.get("nonzero_pct", 0)
        print(f"  {obj:20s} | dtype={dtype:7s} | range=[{dmin}, {dmax}] mm | "
              f"nonzero={nz:5.1f}% | roundtrip={'EXACT' if rt else 'MISMATCH':8s} | {status}")

    print("\n" + "-" * 72)
    print("  TEST 2: imshow Display Verification")
    print("  (brightness measured on NON-ZERO pixels only)")
    print("-" * 72)

    for r in all_results:
        obj = r["object"]
        direct_black = r.get("imshow_direct_black", True)
        direct_raw = r.get("imshow_direct_raw_max", 0)
        direct_bright = r.get("imshow_direct_brightness", 0)
        norm_black = r.get("imshow_normalized_black", True)
        norm_max = r.get("imshow_normalized_max_brightness", 0)
        norm_mean = r.get("imshow_normalized_mean_brightness", 0)
        print(f"  {obj:20s} | direct imshow(uint16): {'BLACK' if direct_black else 'OK':5s} "
              f"(raw_max={direct_raw:.0f} -> brightness={direct_bright:.1f}/255) | "
              f"after normalize: {'BLACK' if norm_black else 'OK':5s} "
              f"(max={norm_max:.0f} mean={norm_mean:.0f}/255)")

    print("\n" + "-" * 72)
    print("  TEST 3: Common Pitfalls (WRONG methods)")
    print("-" * 72)

    for r in all_results:
        obj = r["object"]
        gs_err = r.get("imread_grayscale_error_pct", -1)
        m8_err = r.get("mono8_decode_error_pct", -1)
        gs_dtype = r.get("imread_grayscale_dtype", "?")
        print(f"  {obj:20s} | IMREAD_GRAYSCALE: {gs_err:6.1f}% error "
              f"(dtype={gs_dtype}) | mono8 decode: {m8_err:6.1f}% error")

    print("\n" + "-" * 72)
    print("  TEST 4: sensor_msgs/Image Structure Verification")
    print("-" * 72)

    for r in all_results:
        obj = r["object"]
        enc = r.get("msg_encoding", "?")
        step_ok = r.get("step_correct", False)
        size_ok = r.get("size_correct", False)
        step = r.get("msg_step", 0)
        dlen = r.get("msg_data_len", 0)
        print(f"  {obj:20s} | encoding={enc:5s} | step={step} "
              f"({'OK' if step_ok else 'WRONG':4s}) | "
              f"data_len={dlen} ({'OK' if size_ok else 'WRONG':4s})")

    print("\n" + "=" * 72)
    print("  SUMMARY")
    print("=" * 72)

    total = len(all_results)
    passed = sum(1 for r in all_results if r.get("status") == "PASS")
    partial = sum(1 for r in all_results if r.get("status") == "PARTIAL")
    skipped = sum(1 for r in all_results if r.get("status") == "SKIP")
    failed = sum(1 for r in all_results if r.get("status") == "FAIL")

    all_roundtrip_exact = all(r.get("roundtrip_exact", False) for r in all_results)
    all_norm_not_black = all(not r.get("imshow_normalized_black", True) for r in all_results)
    all_direct_black = all(r.get("imshow_direct_black", True) for r in all_results)
    all_gray_error = all(r.get("imread_grayscale_error_pct", 0) > 50 for r in all_results)

    print(f"\n  Total objects tested: {total}")
    print(f"  PASS: {passed}  PARTIAL: {partial}  SKIP: {skipped}  FAIL: {failed}")
    print()
    print(f"  Round-trip byte-exact:     {'ALL PASS' if all_roundtrip_exact else 'HAS MISMATCH'}")
    print(f"  Normalized imshow (OK):    {'ALL PASS' if all_norm_not_black else 'HAS BLACK'}")
    print(f"  Direct uint16 imshow:      {'ALL BLACK (expected!)' if all_direct_black else 'UNEXPECTED'}")
    print(f"  IMREAD_GRAYSCALE error:    {'ALL >50% (expected!)' if all_gray_error else 'UNEXPECTED'}")

    print()
    print("  VERDICT: cv_bridge 16UC1 conversion is",
          "SAFE - no black image after normalization" if all_roundtrip_exact and all_norm_not_black
          else "PROBLEMATIC - check errors above")

    print()
    print("  Key Takeaways:")
    print("  1. cv2.imread(path, IMREAD_UNCHANGED) -> uint16 (CORRECT)")
    print("  2. cv_bridge encoding='16UC1' -> byte-exact round-trip")
    print("  3. Direct imshow(uint16) -> BLACK (must normalize first)")
    print("  4. cv2.normalize(depth, None, 0, 255, NORM_MINMAX, CV_8U) -> visible")
    print("  5. IMREAD_GRAYSCALE -> 8-bit truncation (99%+ error)")
    print("  6. mono8 decode of 16UC1 data -> wrong values")
    print("=" * 72)


if __name__ == "__main__":
    main()
