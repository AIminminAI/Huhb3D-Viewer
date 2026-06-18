import json
import numpy as np
import cv2
from pathlib import Path
from topology_segmentation_task import parse_stl_binary, load_topology_labels

base = Path("sell_Huhb3D-Industrial-100/flange")
stl_path = base / "topology/tessellated.stl"
labels_path = base / "topology/topology_labels.json"

triangles = parse_stl_binary(str(stl_path))
labels_data = load_topology_labels(str(labels_path))

with open(base / "scene_camera.json") as f:
    sc = json.load(f)
with open(base / "scene_gt.json") as f:
    sgt = json.load(f)

frame_id = "1"
cam_K = sc[frame_id]["cam_K"]
gt_obj = sgt[frame_id][0]
cam_R_m2c = np.array(gt_obj["cam_R_m2c"]).reshape(3, 3)
cam_t_m2c = np.array(gt_obj["cam_t_m2c"]).reshape(3, 1)
K = np.array(cam_K).reshape(3, 3)

print(f"cam_K:\n{K}")
print(f"cam_R_m2c:\n{cam_R_m2c}")
print(f"cam_t_m2c:\n{cam_t_m2c.flatten()}")
print(f"det(R) = {np.linalg.det(cam_R_m2c):.6f}")

tri = triangles[0]
v1 = np.array(tri["v1"])
center = (np.array(tri["v1"]) + np.array(tri["v2"]) + np.array(tri["v3"])) / 3.0
print(f"\nFirst triangle center (model coords): {center}")
print(f"STL bounds: v1 range x=[{min(t['v1'][0] for t in triangles):.1f}, {max(t['v1'][0] for t in triangles):.1f}]")

p_cam = cam_R_m2c @ center.reshape(3, 1) + cam_t_m2c
print(f"Center in camera coords: {p_cam.flatten()}")
print(f"Depth: {p_cam[2, 0]:.1f} mm")

if p_cam[2, 0] > 0:
    p_pix = K @ p_cam
    px = p_pix[0, 0] / p_pix[2, 0]
    py = p_pix[1, 0] / p_pix[2, 0]
    print(f"Projected pixel: ({px:.1f}, {py:.1f})")
else:
    print("BEHIND CAMERA!")

all_centers_cam = []
for tri in triangles:
    c = (np.array(tri["v1"]) + np.array(tri["v2"]) + np.array(tri["v3"])) / 3.0
    pc = cam_R_m2c @ c.reshape(3, 1) + cam_t_m2c
    all_centers_cam.append(pc.flatten())
all_centers_cam = np.array(all_centers_cam)
print(f"\nAll triangles depth range: [{all_centers_cam[:, 2].min():.1f}, {all_centers_cam[:, 2].max():.1f}] mm")
print(f"Triangles in front of camera: {(all_centers_cam[:, 2] > 0).sum()}/{len(triangles)}")

mask = cv2.imread(str(base / "mask/frame_0001.png"), cv2.IMREAD_GRAYSCALE)
print(f"\nMask shape: {mask.shape}, nonzero pixels: {(mask > 0).sum()}")
mask_ys, mask_xs = np.where(mask > 0)
print(f"Mask bounding box: x=[{mask_xs.min()}, {mask_xs.max()}], y=[{mask_ys.min()}, {mask_ys.max()}]")

rgb = cv2.imread(str(base / "rgb/frame_0001.png"))
h, w = rgb.shape[:2]
print(f"RGB shape: {rgb.shape}")
