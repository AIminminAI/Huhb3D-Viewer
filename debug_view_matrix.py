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
triangle_labels = labels_data["triangle_labels"]

with open(base / "camera_poses.json") as f:
    cam_poses = json.load(f)

pose = cam_poses["1"]
view_matrix = np.array(pose["view_matrix"]).reshape(4, 4).T
proj_matrix = np.array(pose["projection_matrix"]).reshape(4, 4).T
w, h = pose["image_width"], pose["image_height"]
near = pose["near_plane"]
far = pose["far_plane"]

print(f"View matrix:\n{view_matrix}")
print(f"Proj matrix:\n{proj_matrix}")
print(f"Near={near}, Far={far}, W={w}, H={h}")

all_px = []
all_py = []
for tri in triangles[:5]:
    for vk in ("v1", "v2", "v3"):
        p = np.array(tri[vk] + [1.0])
        p_view = view_matrix @ p
        p_clip = proj_matrix @ p_view
        if p_clip[3] > 0:
            ndc_x = p_clip[0] / p_clip[3]
            ndc_y = p_clip[1] / p_clip[3]
            screen_x = (ndc_x * 0.5 + 0.5) * w
            screen_y = (1.0 - (ndc_y * 0.5 + 0.5)) * h
            all_px.append(screen_x)
            all_py.append(screen_y)
            print(f"  {tri[vk]} -> view({p_view[0]:.1f},{p_view[1]:.1f},{p_view[2]:.1f}) -> clip({p_clip[0]:.2f},{p_clip[1]:.2f},{p_clip[2]:.2f},{p_clip[3]:.2f}) -> screen({screen_x:.1f},{screen_y:.1f})")

all_px = np.array(all_px)
all_py = np.array(all_py)
print(f"\nScreen X range: [{all_px.min():.1f}, {all_px.max():.1f}]")
print(f"Screen Y range: [{all_py.min():.1f}, {all_py.max():.1f}]")

seg = np.full((h, w), 255, dtype=np.uint8)
for tri, label in zip(triangles, triangle_labels):
    pts_2d = []
    valid = True
    for vk in ("v1", "v2", "v3"):
        p = np.array(tri[vk] + [1.0])
        p_view = view_matrix @ p
        p_clip = proj_matrix @ p_view
        if p_clip[3] <= 0:
            valid = False
            break
        ndc_x = p_clip[0] / p_clip[3]
        ndc_y = p_clip[1] / p_clip[3]
        screen_x = int(round((ndc_x * 0.5 + 0.5) * w))
        screen_y = int(round((1.0 - (ndc_y * 0.5 + 0.5)) * h))
        pts_2d.append([screen_x, screen_y])
    if valid:
        pts_arr = np.array(pts_2d, dtype=np.int32)
        cv2.fillPoly(seg, [pts_arr], label)

unique, counts = np.unique(seg, return_counts=True)
for u, c in zip(unique, counts):
    from topology_segmentation_task import CATEGORY_NAMES
    name = CATEGORY_NAMES.get(u, f"Unknown_{u}")
    print(f"  {u:3d} {name:25s}: {c:6d} pixels")

from topology_segmentation_task import visualize_segmentation
vis = visualize_segmentation(seg)
out_dir = Path("topology_segmentation/test")
out_dir.mkdir(parents=True, exist_ok=True)
cv2.imwrite(str(out_dir / "flange_frame1_view_matrix.png"), vis)
print(f"Saved to {out_dir / 'flange_frame1_view_matrix.png'}")
