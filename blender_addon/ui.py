"""UI panels and operators for the Huhb3D 6DoF Data Generator add-on.

Provides a sidebar panel in the 3D Viewport with all configuration properties
and action buttons.
"""

import os
import threading

import bpy


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

class Huhb3DProperties(bpy.types.PropertyGroup):
    """Shared properties for the 6DoF data generator."""

    # --- Input ---
    step_file: bpy.props.StringProperty(
        name="STEP File",
        description="Path to the STEP / STL / OBJ file to import",
        subtype="FILE_PATH",
        filter="*.step;*.stp;*.stl;*.obj;*.fbx",
    )  # type: ignore[assignment]

    # --- Output ---
    output_dir: bpy.props.StringProperty(
        name="Output Directory",
        description="Directory where the dataset will be saved",
        subtype="DIR_PATH",
    )  # type: ignore[assignment]

    # --- View sampling ---
    num_views: bpy.props.IntProperty(
        name="Number of Views",
        description="Number of camera viewpoints (Fibonacci sphere sampling)",
        default=100,
        min=10,
        max=2000,
    )  # type: ignore[assignment]

    image_width: bpy.props.IntProperty(
        name="Image Width",
        default=800,
        min=64,
        max=4096,
    )  # type: ignore[assignment]

    image_height: bpy.props.IntProperty(
        name="Image Height",
        default=600,
        min=64,
        max=4096,
    )  # type: ignore[assignment]

    camera_radius: bpy.props.FloatProperty(
        name="Camera Radius",
        description="Distance of the camera from the object origin",
        default=500.0,
        min=10.0,
        max=50000.0,
    )  # type: ignore[assignment]

    # --- Export formats ---
    export_bop: bpy.props.BoolProperty(
        name="Export BOP",
        description="Export scene_gt.json and scene_camera.json (BOP format)",
        default=True,
    )  # type: ignore[assignment]

    export_coco: bpy.props.BoolProperty(
        name="Export COCO",
        description="Export coco_annotations.json",
        default=True,
    )  # type: ignore[assignment]

    export_yolo: bpy.props.BoolProperty(
        name="Export YOLO",
        description="Export YOLO-format label files",
        default=True,
    )  # type: ignore[assignment]

    # --- Sim2Real ---
    sim2real_augment: bpy.props.BoolProperty(
        name="Sim2Real Augmentation",
        description="Apply background replacement and photometric randomisation",
        default=True,
    )  # type: ignore[assignment]

    num_augmented_scenes: bpy.props.IntProperty(
        name="Augmented Scenes",
        description="Number of multi-object augmented scenes to generate",
        default=100,
        min=0,
        max=5000,
    )  # type: ignore[assignment]

    min_objects_per_scene: bpy.props.IntProperty(
        name="Min Objects/Scene",
        default=2,
        min=1,
        max=20,
    )  # type: ignore[assignment]

    max_objects_per_scene: bpy.props.IntProperty(
        name="Max Objects/Scene",
        default=6,
        min=1,
        max=20,
    )  # type: ignore[assignment]

    # --- Progress ---
    progress: bpy.props.FloatProperty(
        name="Progress",
        default=0.0,
        min=0.0,
        max=1.0,
    )  # type: ignore[assignment]

    is_generating: bpy.props.BoolProperty(
        name="Generating",
        default=False,
    )  # type: ignore[assignment]

    status_message: bpy.props.StringProperty(
        name="Status",
        default="Ready",
    )  # type: ignore[assignment]

    def report_progress(self, fraction):
        """Callback for the generator to report progress."""
        self.progress = fraction


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class HUHB3D_OT_ImportStep(bpy.types.Operator):
    """Import a STEP / CAD file into the current scene."""

    bl_idname = "huhb3d.import_step"
    bl_label = "Import STEP"
    bl_description = "Import a STEP, STL, OBJ, or FBX file"
    bl_options = {"REGISTER", "UNDO"}

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")  # type: ignore[assignment]

    filter_glob: bpy.props.StringProperty(
        default="*.step;*.stp;*.stl;*.obj;*.fbx",
        options={"HIDDEN"},
    )  # type: ignore[assignment]

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        props = context.scene.huhb3d_props
        props.step_file = self.filepath

        from .generator import import_step_file
        try:
            imported = import_step_file(self.filepath)
            self.report({"INFO"}, f"Imported {len(imported)} object(s)")
        except RuntimeError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        return {"FINISHED"}


class HUHB3D_OT_GenerateDataset(bpy.types.Operator):
    """Generate the full 6DoF pose estimation dataset."""

    bl_idname = "huhb3d.generate_dataset"
    bl_label = "Generate Dataset"
    bl_description = "Render multi-view dataset with ground-truth annotations"
    bl_options = {"REGISTER"}

    def execute(self, context):
        props = context.scene.huhb3d_props

        if props.is_generating:
            self.report({"WARNING"}, "Generation already in progress")
            return {"CANCELLED"}

        props.is_generating = True
        props.progress = 0.0
        props.status_message = "Generating…"

        # Run generation in the main thread (Blender requires it for render ops)
        from .generator import generate_6dof_dataset
        success, message = generate_6dof_dataset(context, props)

        props.is_generating = False
        props.progress = 1.0

        if success:
            props.status_message = f"Done: {message}"
            self.report({"INFO"}, message)
        else:
            props.status_message = f"Failed: {message}"
            self.report({"ERROR"}, message)

        return {"FINISHED"}


class HUHB3D_OT_OpenOutputFolder(bpy.types.Operator):
    """Open the output directory in the system file browser."""

    bl_idname = "huhb3d.open_output"
    bl_label = "Open Output Folder"
    bl_description = "Open the output directory in the file explorer"

    def execute(self, context):
        props = context.scene.huhb3d_props
        path = bpy.path.abspath(props.output_dir)

        if not path or not os.path.isdir(path):
            self.report({"ERROR"}, "Output directory does not exist")
            return {"CANCELLED"}

        import platform
        system = platform.system()
        if system == "Windows":
            os.startfile(path)
        elif system == "Darwin":
            os.system(f'open "{path}"')
        else:
            os.system(f'xdg-open "{path}"')

        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------

class HUHB3D_PT_MainPanel(bpy.types.Panel):
    """Main sidebar panel for the Huhb3D 6DoF Data Generator."""

    bl_label = "Huhb3D 6DoF Generator"
    bl_idname = "HUHB3D_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Huhb3D"

    def draw(self, context):
        layout = self.layout
        props = context.scene.huhb3d_props

        # --- Input ---
        box = layout.box()
        box.label(text="Input File", icon="FILE_3D")
        box.prop(props, "step_file")
        box.operator("huhb3d.import_step", icon="IMPORT")

        # --- Output ---
        box = layout.box()
        box.label(text="Output", icon="OUTPUT")
        box.prop(props, "output_dir")

        # --- View Sampling ---
        box = layout.box()
        box.label(text="View Sampling", icon="CAMERA_DATA")
        box.prop(props, "num_views")
        row = box.row(align=True)
        row.prop(props, "image_width")
        row.prop(props, "image_height")
        box.prop(props, "camera_radius")

        # --- Export Formats ---
        box = layout.box()
        box.label(text="Export Formats", icon="EXPORT")
        box.prop(props, "export_bop")
        box.prop(props, "export_coco")
        box.prop(props, "export_yolo")

        # --- Sim2Real ---
        box = layout.box()
        box.label(text="Sim2Real Augmentation", icon="NODE_MATERIAL")
        box.prop(props, "sim2real_augment")

        aug_col = box.column()
        aug_col.enabled = props.sim2real_augment
        aug_col.prop(props, "num_augmented_scenes")
        row = aug_col.row(align=True)
        row.prop(props, "min_objects_per_scene")
        row.prop(props, "max_objects_per_scene")

        # --- Actions ---
        layout.separator()
        col = layout.column(align=True)
        col.scale_y = 1.5

        gen_op = col.operator("huhb3d.generate_dataset", icon="RENDER_ANIMATION")
        if props.is_generating:
            gen_op = None  # disable

        col.operator("huhb3d.open_output", icon="FILE_FOLDER")

        # --- Progress ---
        if props.is_generating or props.progress > 0:
            layout.separator()
            layout.prop(props, "progress", slider=True)
            layout.label(text=props.status_message)


# ---------------------------------------------------------------------------
# Registration helpers
# ---------------------------------------------------------------------------

classes = (
    Huhb3DProperties,
    HUHB3D_OT_ImportStep,
    HUHB3D_OT_GenerateDataset,
    HUHB3D_OT_OpenOutputFolder,
    HUHB3D_PT_MainPanel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.huhb3d_props = bpy.props.PointerProperty(type=Huhb3DProperties)


def unregister():
    del bpy.types.Scene.huhb3d_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
