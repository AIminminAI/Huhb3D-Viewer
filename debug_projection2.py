import json
import numpy as np
import cv2
from pathlib import Path
from topology_segmentation_task import parse_stl_binary, load_topology_labels

base = Path("sell_Huhb3D-Industrial-100/flange")
stl_path = base / "topology_hd/tessellated.stl"
labels_path = base / "topology_hd/topology_labels.json"

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

all_px = []
all_py = []
for tri in triangles:
    for vk in ("v1", "v2", "v3"):
        p = np.array(tri[vk])
        p_cam = cam_R_m2c @ p.reshape(3, 1) + cam_t_m2c
        if p_cam[2, 0] > 0:
            p_pix = K @ p_cam
            px = p_pix[0, 0] / p_pix[2, 0]
            py = p_pix[1, 0] / p_pix[2, 0]
            all_px.append(px)
            all_py.append(py)

all_px = np.array(all_px)
all_py = np.array(all_py)
print(f"Projected X range: [{all_px.min():.1f}, {all_px.max():.1f}]")
print(f"Projected Y range: [{all_py.min():.1f}, {all_py.max():.1f}]")
print(f"Image size: 800x600")

seg = np.full((600, 800), 255, dtype=np.uint8)
for tri in triangles[:10]:
    pts_2d = []
    for vk in ("v1", "v2", "v3"):
        p = np.array(tri[vk])
        p_cam = cam_R_m2c @ p.reshape(3, 1) + cam_t_m2c
        p_pix = K @ p_cam
        px = int(round(p_pix[0, 0] / p_pix[2, 0]))
        py = int(round(p_pix[1, 0] / p_pix[2, 0]))
        pts_2d.append([px, py])
    print(f"Triangle {tri['v1'][:3]} -> pts_2d={pts_2d}")
    pts_arr = np.array(pts_2d, dtype=np.int32)
    cv2.fillPoly(seg, [pts_arr], 128)

cv2.imwrite("topology_segmentation/test/debug_projection.png", seg)
print("Debug projection saved")
