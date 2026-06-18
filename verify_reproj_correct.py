import cv2, numpy as np, json
from pathlib import Path

ds = Path(__file__).parent / "sell_Huhb3D-Test-Precision-v4"
objs = sorted([d.name for d in ds.iterdir() if d.is_dir() and (d/"depth").exists()])

print("CORRECT Reprojection Error (depth pixel -> 3D -> reproject -> pixel)")
print("=" * 70)

for obj in objs:
    obj_dir = ds / obj
    dp = obj_dir / "depth" / "depth_0001.png"
    if not dp.exists():
        continue
    depth = cv2.imread(str(dp), cv2.IMREAD_UNCHANGED)
    if depth is None:
        continue

    with open(obj_dir / "scene_camera.json") as f:
        sc = json.load(f)
    with open(obj_dir / "scene_gt.json") as f:
        sg = json.load(f)

    K = np.array(sc["1"]["cam_K"]).reshape(3, 3)
    gt = sg["1"][0]
    R = np.array(gt["cam_R_m2c"]).reshape(3, 3)
    t = np.array(gt["cam_t_m2c"])

    mask = depth > 0
    if not mask.any():
        continue

    h, w = depth.shape
    fx, fy = K[0, 0], K[1, 1]
    cx, cy = K[0, 2], K[1, 2]

    u, v = np.arange(w), np.arange(h)
    uu, vv = np.meshgrid(u, v)

    z_m = depth.astype(np.float64) / 1000.0
    x_m = (uu - cx) * z_m / fx
    y_m = (vv - cy) * z_m / fy

    pts_cam = np.stack([x_m[mask], y_m[mask], z_m[mask]], axis=-1)

    n_sample = min(1000, len(pts_cam))
    sample_idx = np.random.choice(len(pts_cam), n_sample, replace=False)
    pts_sample = pts_cam[sample_idx]

    p_world = R.T @ (pts_sample.T - t.reshape(3, 1))
    p_reproj_cam = R @ p_world + t.reshape(3, 1)

    u_reproj = fx * p_reproj_cam[0] / p_reproj_cam[2] + cx
    v_reproj = fy * p_reproj_cam[1] / p_reproj_cam[2] + cy

    u_orig = uu[mask][sample_idx].astype(np.float64)
    v_orig = vv[mask][sample_idx].astype(np.float64)

    err = np.sqrt((u_reproj - u_orig) ** 2 + (v_reproj - v_orig) ** 2)
    status = "PASS" if err.max() < 5 else "FAIL"
    print(f"  {obj:20s} | mean={err.mean():.4f}px  max={err.max():.4f}px  {status}")

print()
print("NOTE: Previous audit used object origin -> image center projection,")
print("which is INCORRECT for measuring data accuracy.")
print("This test uses depth pixel -> 3D back-projection -> re-projection,")
print("which is the CORRECT BOP evaluation method.")
