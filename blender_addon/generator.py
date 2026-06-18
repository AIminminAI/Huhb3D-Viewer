"""Core 6DoF dataset generation logic.

Orchestrates STEP import, camera placement, rendering, ground-truth computation,
and export to BOP / COCO / YOLO formats with optional Sim2Real augmentation.
"""

import os
import json
import math
import logging
import tempfile

import bpy

from . import bop_format
from .sim2real import augment_scene, HAS_CV2

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fibonacci sphere sampling
# ---------------------------------------------------------------------------

def fibonacci_sphere(n_points, radius=1.0):
    """Return *n_points* roughly uniform points on a sphere of given *radius*.

    Uses the golden-angle spiral method.

    Yields
    ------
    tuple[float, float, float]
        (x, y, z) coordinates.
    """
    golden_angle = math.pi * (3.0 - math.sqrt(5.0))
    for i in range(n_points):
        y = 1.0 - (i / float(n_points - 1)) * 2.0  # 1 → -1
        r = math.sqrt(1.0 - y * y)
        theta = golden_angle * i
        x = math.cos(theta) * r
        z = math.sin(theta) * r
        yield (x * radius, y * radius, z * radius)


# ---------------------------------------------------------------------------
# STEP / CAD import
# ---------------------------------------------------------------------------

def import_step_file(filepath):
    """Import a STEP/STP file into the current Blender scene.

    Tries Blender 4.x CAD add-on first, then falls back to STL/OBJ.

    Parameters
    ----------
    filepath : str
        Path to the STEP file.

    Returns
    -------
    list[bpy.types.Object]
        Imported mesh objects.

    Raises
    ------
    RuntimeError
        If the file cannot be imported by any available method.
    """
    ext = os.path.splitext(filepath)[1].lower()
    imported = []

    # --- Try native STEP import (Blender 4.x with CAD add-on) ---
    if ext in (".step", ".stp"):
        try:
            bpy.ops.import_scene.step(filepath=filepath)
            imported = [o for o in bpy.context.selected_objects if o.type == "MESH"]
            if imported:
                logger.info("Imported STEP via native importer: %d objects", len(imported))
                return imported
        except AttributeError:
            logger.debug("Native STEP importer not available")
        except Exception as exc:
            logger.debug("Native STEP import failed: %s", exc)

        # --- Try pythonOCP (OCCT) bridge ---
        try:
            from OCP.STEPControl import STEPControl_Reader  # noqa: F401
            imported = _import_via_pythonocp(filepath)
            if imported:
                return imported
        except ImportError:
            logger.debug("pythonOCP not available")
        except Exception as exc:
            logger.debug("pythonOCP import failed: %s", exc)

        raise RuntimeError(
            "Cannot import STEP file. Enable the Blender CAD add-on or install pythonOCP, "
            "or provide an STL/OBJ file instead."
        )

    # --- STL ---
    if ext == ".stl":
        bpy.ops.import_mesh.stl(filepath=filepath)
        imported = [o for o in bpy.context.selected_objects if o.type == "MESH"]
        if imported:
            return imported

    # --- OBJ ---
    if ext in (".obj", ".obj"):
        bpy.ops.import_scene.obj(filepath=filepath)
        imported = [o for o in bpy.context.selected_objects if o.type == "MESH"]
        if imported:
            return imported

    # --- FBX ---
    if ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=filepath)
        imported = [o for o in bpy.context.selected_objects if o.type == "MESH"]
        if imported:
            return imported

    raise RuntimeError(f"Unsupported file format: {ext}")


def _import_via_pythonocp(filepath):
    """Import STEP via pythonOCP, write a temporary STL, and load it."""
    from OCP.STEPControl import STEPControl_Reader
    from OCP.StlAPI import StlAPI_Writer
    from OCP.TopAbs import TopAbs_SOLID

    reader = STEPControl_Reader()
    status = reader.ReadFile(filepath)
    if status != 1:
        raise RuntimeError("pythonOCP could not read STEP file")
    reader.TransferRoots()
    shape = reader.OneShape()

    tmp_stl = os.path.join(tempfile.gettempdir(), "_huhb3d_tmp.stl")
    writer = StlAPI_Writer()
    writer.Write(shape, tmp_stl)

    bpy.ops.import_mesh.stl(filepath=tmp_stl)
    imported = [o for o in bpy.context.selected_objects if o.type == "MESH"]
    try:
        os.remove(tmp_stl)
    except OSError:
        pass
    return imported


# ---------------------------------------------------------------------------
# Scene setup helpers
# ---------------------------------------------------------------------------

def _clear_scene():
    """Remove all mesh objects, cameras, and lights from the scene."""
    bpy.ops.object.select_all(action="SELECT")
    for obj in bpy.context.selected_objects:
        if obj.type in {"MESH", "CAMERA", "LIGHT"}:
            bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.object.select_all(action="DESELECT")


def _setup_render_settings(scene, width, height):
    """Configure render settings for dataset generation."""
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"

    # Use Cycles for better quality (fall back to EEVEE if unavailable)
    try:
        scene.render.engine = "CYCLES"
        scene.cycles.samples = 64
        scene.cycles.use_denoising = True
    except Exception:
        scene.render.engine = "BLENDER_EEVEE"

    # Enable depth and object index passes
    view_layer = scene.view_layers["View Layer"]
    view_layer.use_pass_z = True
    view_layer.use_pass_object_index = True


def _setup_compositing(scene):
    """Set up compositor nodes to output depth and object-index passes."""
    scene.use_nodes = True
    tree = scene.node_tree
    nodes = tree.nodes
    links = tree.links

    # Clear existing
    for n in nodes:
        nodes.remove(n)

    render_layers = nodes.new("CompositorNodeRLayers")
    composite = nodes.new("CompositorNodeComposite")
    composite.location = (600, 0)

    # Depth output
    depth_file = nodes.new("CompositorNodeOutputFile")
    depth_file.location = (600, -200)
    depth_file.format.file_format = "OPEN_EXR"
    depth_file.format.color_mode = "RGB"
    depth_file.base_path = ""  # set per render

    # Index output
    index_file = nodes.new("CompositorNodeOutputFile")
    index_file.location = (600, -400)
    index_file.format.file_format = "OPEN_EXR"
    index_file.format.color_mode = "RGB"
    index_file.base_path = ""

    links.new(render_layers.outputs["Image"], composite.inputs["Image"])
    links.new(render_layers.outputs["Depth"], depth_file.inputs[0])
    links.new(render_layers.outputs["IndexOB"], index_file.inputs[0])

    return render_layers, composite, depth_file, index_file


def _create_camera(scene, location, target=(0, 0, 0)):
    """Create a camera at *location* pointing at *target*."""
    cam_data = bpy.data.cameras.new("Huhb3D_Cam")
    cam_obj = bpy.data.objects.new("Huhb3D_Cam", cam_data)
    scene.collection.objects.link(cam_obj)

    cam_obj.location = location

    # Look-at constraint
    import mathutils
    direction = mathutils.Vector(target) - mathutils.Vector(location)
    rot_quat = direction.to_track_quat("-Z", "Y")
    cam_obj.rotation_euler = rot_quat.to_euler()

    scene.camera = cam_obj
    return cam_obj


def _create_light(scene):
    """Add a sun light for even illumination."""
    light_data = bpy.data.lights.new("Huhb3D_Sun", type="SUN")
    light_data.energy = 3.0
    light_obj = bpy.data.objects.new("Huhb3D_Sun", light_data)
    light_obj.location = (0, 0, 1000)
    scene.collection.objects.link(light_obj)
    return light_obj


def _normalise_object(obj):
    """Centre the object at origin and set pass_index = 1."""
    import mathutils

    # Centre
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    obj.location = (0, 0, 0)

    # Object index for mask pass
    obj.pass_index = 1

    # Ensure smooth shading
    for poly in obj.data.polygons:
        poly.use_smooth = True


# ---------------------------------------------------------------------------
# Mask extraction
# ---------------------------------------------------------------------------

def _extract_mask_from_index(index_img_path, width, height, obj_index=1):
    """Read object-index EXR and produce a binary mask PNG.

    Returns the path to the saved mask PNG.
    """
    try:
        import numpy as np
        import cv2
        img = cv2.imread(index_img_path, cv2.IMREAD_UNCHANGED)
        if img is None:
            return None
        if img.ndim == 3:
            img = img[:, :, 0]
        mask = ((img - obj_index) < 0.5).astype(np.uint8) * 255
        mask_path = index_img_path.replace(".exr", "_mask.png")
        cv2.imwrite(mask_path, mask)
        return mask_path
    except Exception as exc:
        logger.warning("Mask extraction failed: %s", exc)
        return None


def _depth_exr_to_mm(depth_exr_path, output_path):
    """Convert depth EXR (Blender Z-buffer in metres) to uint16 mm PNG."""
    try:
        import numpy as np
        import cv2
        img = cv2.imread(depth_exr_path, cv2.IMREAD_UNCHANGED)
        if img is None:
            return None
        if img.ndim == 3:
            img = img[:, :, 0]
        # Blender depth is in scene units (default metres); convert to mm
        depth_mm = np.clip(img * 1000.0, 0, 65535).astype(np.uint16)
        cv2.imwrite(output_path, depth_mm)
        return output_path
    except Exception as exc:
        logger.warning("Depth conversion failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Mask → contour → COCO / YOLO
# ---------------------------------------------------------------------------

def _mask_to_bbox(mask_path, width, height):
    """Read a binary mask and return (x, y, w, h) and normalised YOLO box."""
    try:
        import numpy as np
        import cv2
        mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
        if mask is None:
            return None, None
        ys, xs = np.where(mask > 127)
        if len(xs) == 0:
            return None, None
        x_min, x_max = int(xs.min()), int(xs.max())
        y_min, y_max = int(ys.min()), int(ys.max())
        bbox = (x_min, y_min, x_max - x_min, y_max - y_min)
        yolo = {
            "cx": (x_min + x_max) / 2.0 / width,
            "cy": (y_min + y_max) / 2.0 / height,
            "w":  (x_max - x_min) / float(width),
            "h":  (y_max - y_min) / float(height),
        }
        return bbox, yolo
    except Exception:
        return None, None


def _mask_to_contour_area(mask_path):
    """Return the segmentation area from a mask image."""
    try:
        import cv2
        mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
        if mask is None:
            return 0
        return int((mask > 127).sum())
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Main generation function
# ---------------------------------------------------------------------------

def generate_6dof_dataset(context, props):
    """Generate a 6DoF pose estimation dataset.

    Parameters
    ----------
    context : bpy.types.Context
    props : bpy.types.PropertyGroup
        Add-on properties (see ui.py).

    Returns
    -------
    tuple[bool, str]
        (success, message)
    """
    step_file = props.step_file
    output_dir = props.output_dir
    num_views = props.num_views
    img_w = props.image_width
    img_h = props.image_height
    cam_radius = props.camera_radius
    export_bop = props.export_bop
    export_coco = props.export_coco
    export_yolo = props.export_yolo
    do_sim2real = props.sim2real_augment
    num_aug_scenes = props.num_augmented_scenes
    min_objs = props.min_objects_per_scene
    max_objs = props.max_objects_per_scene

    # --- Validate inputs ---
    if not step_file or not os.path.isfile(step_file):
        return False, f"STEP file not found: {step_file}"
    if not output_dir:
        return False, "Output directory is not set"

    os.makedirs(output_dir, exist_ok=True)
    rgb_dir = os.path.join(output_dir, "rgb")
    depth_dir = os.path.join(output_dir, "depth")
    mask_dir = os.path.join(output_dir, "mask")
    for d in (rgb_dir, depth_dir, mask_dir):
        os.makedirs(d, exist_ok=True)

    scene = context.scene

    # --- Import STEP ---
    try:
        imported = import_step_file(step_file)
    except RuntimeError as exc:
        return False, str(exc)

    if not imported:
        return False, "No mesh objects were imported"

    # Normalise first object as the target
    target_obj = imported[0]
    _normalise_object(target_obj)

    # --- Render setup ---
    _setup_render_settings(scene, img_w, img_h)
    render_layers_node, composite_node, depth_file_node, index_file_node = _setup_compositing(scene)

    # Light
    _create_light(scene)

    # --- Camera intrinsics info ---
    # We'll create a temporary camera just to read focal_length / sensor_width
    tmp_cam_data = bpy.data.cameras.new("Huhb3D_tmp")
    focal_length = tmp_cam_data.lens  # mm
    sensor_width = tmp_cam_data.sensor_width  # mm
    bpy.data.cameras.remove(tmp_cam_data)

    # --- BOP / COCO / YOLO accumulators ---
    scene_gt = {}
    scene_camera = {}
    coco_images = []
    coco_annotations = []
    yolo_labels = {}

    obj_id = 1
    category_id = 1
    annotation_id = 1

    # --- Render loop ---
    points = list(fibonacci_sphere(num_views, cam_radius))

    for i, (px, py, pz) in enumerate(points):
        # Skip views that are too close to the poles (mostly top/bottom)
        # (optional – keep all for completeness)

        # Remove old camera
        old_cam = scene.camera
        if old_cam and old_cam.name.startswith("Huhb3D_Cam"):
            bpy.data.objects.remove(old_cam, do_unlink=True)

        cam_obj = _create_camera(scene, (px, py, pz))
        cam_data = cam_obj.data
        focal_length = cam_data.lens
        sensor_width = cam_data.sensor_width

        # Update compositing output paths
        base_name = f"{i:06d}"
        rgb_path = os.path.join(rgb_dir, f"{base_name}.png")
        depth_exr = os.path.join(depth_dir, f"{base_name}_depth.exr")
        index_exr = os.path.join(mask_dir, f"{base_name}_index.exr")

        scene.render.filepath = rgb_path
        depth_file_node.base_path = depth_dir
        depth_file_node.file_slots[0].path = f"{base_name}_depth"
        index_file_node.base_path = mask_dir
        index_file_node.file_slots[0].path = f"{base_name}_index"

        # Render
        bpy.ops.render.render(write_still=True)

        # --- Post-process depth & mask ---
        actual_depth_exr = os.path.join(depth_dir, f"{base_name}_depth0001.exr")
        if not os.path.isfile(actual_depth_exr):
            # Try without frame suffix
            actual_depth_exr = os.path.join(depth_dir, f"{base_name}_depth.exr")

        depth_png_path = os.path.join(depth_dir, f"{base_name}.png")
        _depth_exr_to_mm(actual_depth_exr, depth_png_path)

        actual_index_exr = os.path.join(mask_dir, f"{base_name}_index0001.exr")
        if not os.path.isfile(actual_index_exr):
            actual_index_exr = os.path.join(mask_dir, f"{base_name}_index.exr")

        mask_png_path = _extract_mask_from_index(actual_index_exr, img_w, img_h, obj_index=1)
        if mask_png_path is None:
            # Fallback: create empty mask
            mask_png_path = os.path.join(mask_dir, f"{base_name}_mask.png")

        # --- Ground truth ---
        cam_K_dict, cam_R_dict, cam_t_dict = bop_format.blender_camera_to_bop(
            [v for row in cam_obj.matrix_world for v in row],
            focal_length, sensor_width, img_w, img_h,
        )

        # BOP scene_gt
        scene_gt[str(i)] = [{
            "cam_R_m2c": cam_R_dict["cam_R_m2c"],
            "cam_t_m2c": cam_t_dict["cam_t_m2c"],
            "obj_id": obj_id,
        }]

        # BOP scene_camera
        scene_camera[str(i)] = {
            "cam_K": cam_K_dict["cam_K"],
            "depth_scale": 1.0,
        }

        # COCO
        bbox, yolo_box = _mask_to_bbox(mask_png_path, img_w, img_h)
        area = _mask_to_contour_area(mask_png_path)

        coco_images.append({
            "id": i,
            "file_name": f"{base_name}.png",
            "width": img_w,
            "height": img_h,
        })
        if bbox is not None:
            coco_annotations.append({
                "id": annotation_id,
                "image_id": i,
                "category_id": category_id,
                "bbox": list(bbox),
                "area": area,
                "iscrowd": 0,
            })
            annotation_id += 1

        # YOLO
        if yolo_box is not None:
            yolo_labels[f"{base_name}.png"] = [{
                "class_id": category_id - 1,  # YOLO uses 0-indexed
                "cx": yolo_box["cx"],
                "cy": yolo_box["cy"],
                "w": yolo_box["w"],
                "h": yolo_box["h"],
            }]

        # Progress report
        if hasattr(props, "report_progress"):
            props.report_progress(i / num_views)

    # --- Export formats ---
    if export_bop:
        bop_format.save_scene_gt(output_dir, scene_gt)
        bop_format.save_scene_camera(output_dir, scene_camera)

    if export_coco:
        coco_dict = {
            "images": coco_images,
            "annotations": coco_annotations,
            "categories": [{"id": category_id, "name": target_obj.name, "supercategory": "object"}],
        }
        bop_format.save_coco_annotations(output_dir, coco_dict)

    if export_yolo:
        bop_format.save_yolo_labels(output_dir, yolo_labels)

    # --- Sim2Real augmentation ---
    if do_sim2real and HAS_CV2:
        aug_dir = os.path.join(output_dir, "augmented")
        os.makedirs(aug_dir, exist_ok=True)
        aug_rgb_dir = os.path.join(aug_dir, "rgb")
        aug_depth_dir = os.path.join(aug_dir, "depth")
        os.makedirs(aug_rgb_dir, exist_ok=True)
        os.makedirs(aug_depth_dir, exist_ok=True)

        for i in range(num_views):
            base_name = f"{i:06d}"
            rgb_path = os.path.join(rgb_dir, f"{base_name}.png")
            depth_path = os.path.join(depth_dir, f"{base_name}.png")
            mask_path = os.path.join(mask_dir, f"{base_name}_mask.png")

            if not os.path.isfile(mask_path):
                continue

            result = augment_scene(rgb_path, depth_path, mask_path, aug_rgb_dir, i)
            if result:
                # Move depth to proper dir
                import shutil
                aug_depth_src = result["depth"]
                aug_depth_dst = os.path.join(aug_depth_dir, os.path.basename(aug_depth_src))
                if aug_depth_src != aug_depth_dst:
                    shutil.move(aug_depth_src, aug_depth_dst)

        # Multi-object composition scenes
        _generate_multi_object_scenes(
            output_dir, aug_dir, num_aug_scenes, min_objs, max_objs, img_w, img_h,
        )

    # --- Cleanup ---
    # Remove temporary camera and light
    for obj_name in ("Huhb3D_Cam", "Huhb3D_Sun"):
        obj = bpy.data.objects.get(obj_name)
        if obj:
            bpy.data.objects.remove(obj, do_unlink=True)

    return True, f"Dataset generated: {num_views} views → {output_dir}"


# ---------------------------------------------------------------------------
# Multi-object composition scenes
# ---------------------------------------------------------------------------

def _generate_multi_object_scenes(base_dir, aug_dir, num_scenes, min_objs, max_objs, img_w, img_h):
    """Create multi-object augmented scenes by compositing single-object renders."""
    try:
        import cv2
        import numpy as np
        from .sim2real import compose_scene, photometric_randomize, generate_background
    except ImportError:
        logger.warning("Cannot generate multi-object scenes: missing cv2/numpy")
        return

    rgb_dir = os.path.join(base_dir, "rgb")
    depth_dir = os.path.join(base_dir, "depth")
    mask_dir = os.path.join(base_dir, "mask")

    if not os.path.isdir(rgb_dir):
        return

    rgb_files = sorted([f for f in os.listdir(rgb_dir) if f.endswith(".png")])
    if not rgb_files:
        return

    multi_rgb_dir = os.path.join(aug_dir, "multi_rgb")
    multi_depth_dir = os.path.join(aug_dir, "multi_depth")
    os.makedirs(multi_rgb_dir, exist_ok=True)
    os.makedirs(multi_depth_dir, exist_ok=True)

    for s in range(num_scenes):
        n_objs = random.randint(min_objs, max_objs)
        chosen = random.sample(rgb_files, min(n_objs, len(rgb_files)))

        bg = generate_background(img_w, img_h)
        objects = []

        for fname in chosen:
            base = os.path.splitext(fname)[0]
            rgb_path = os.path.join(rgb_dir, fname)
            depth_path = os.path.join(depth_dir, f"{base}.png")
            mask_path = os.path.join(mask_dir, f"{base}_mask.png")

            rgb = cv2.imread(rgb_path)
            depth = cv2.imread(depth_path, cv2.IMREAD_UNCHANGED)
            mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)

            if rgb is None or depth is None or mask is None:
                continue

            # Random spatial offset for variety
            dx = random.randint(-img_w // 4, img_w // 4)
            dy = random.randint(-img_h // 4, img_h // 4)

            M = np.float32([[1, 0, dx], [0, 1, dy]])
            rgb_shifted = cv2.warpAffine(rgb, M, (img_w, img_h))
            depth_shifted = cv2.warpAffine(depth, M, (img_w, img_h))
            mask_shifted = cv2.warpAffine(mask, M, (img_w, img_h))

            objects.append({
                "rgb": rgb_shifted,
                "mask": (mask_shifted > 127).astype(np.uint8),
                "depth": depth_shifted,
            })

        if not objects:
            continue

        composed_rgb, composed_depth = compose_scene(objects, bg)
        composed_rgb = photometric_randomize(composed_rgb)

        cv2.imwrite(os.path.join(multi_rgb_dir, f"scene_{s:06d}.png"), composed_rgb)
        if composed_depth is not None:
            cv2.imwrite(os.path.join(multi_depth_dir, f"scene_{s:06d}.png"), composed_depth)


# We need random for multi-object scenes
import random
