import json
import numpy as np
import cv2
from pathlib import Path
from topology_segmentation_task import (
    generate_topology_gt_for_view_gl, CATEGORY_NAMES, visualize_segmentation
)

base = Path("sell_Huhb3D-Industrial-100/flange")
stl_path = base / "topology_hd/tessellated.stl"
labels_path = base / "topology_hd/topology_labels.json"

with open(base / "camera_poses.json") as f:
    cam_poses = json.load(f)

pose = cam_poses["1"]
view_matrix = pose["view_matrix"]
proj_matrix = pose["projection_matrix"]
w = pose["image_width"]
h = pose["image_height"]

seg = generate_topology_gt_for_view_gl(
    str(stl_path), str(labels_path), view_matrix, proj_matrix, w, h
)

unique, counts = np.unique(seg, return_counts=True)
print(f"Segmentation shape: {seg.shape}")
for u, c in zip(unique, counts):
    name = CATEGORY_NAMES.get(u, f"Unknown_{u}")
    print(f"  {u:3d} {name:25s}: {c:6d} pixels")

vis = visualize_segmentation(seg)
out_dir = Path("topology_segmentation/test")
out_dir.mkdir(parents=True, exist_ok=True)
cv2.imwrite(str(out_dir / "flange_frame1_topology_gl.png"), vis)
print(f"Topology GT saved to {out_dir / 'flange_frame1_topology_gl.png'}")

rgb = cv2.imread(str(base / "rgb/frame_0001.png"))
if rgb is not None:
    overlay = rgb.copy()
    mask_valid = seg != 255
    overlay[mask_valid] = vis[mask_valid]
    blend = cv2.addWeighted(rgb, 0.5, overlay, 0.5, 0)
    cv2.imwrite(str(out_dir / "flange_frame1_overlay_gl.png"), blend)
    print(f"Overlay saved to {out_dir / 'flange_frame1_overlay_gl.png'}")
