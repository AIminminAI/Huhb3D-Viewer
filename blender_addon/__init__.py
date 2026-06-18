"""Huhb3D 6DoF Data Generator – Blender Add-on.

A one-click pipeline to generate 6DoF pose estimation training data
from STEP / CAD files.  Outputs BOP, COCO, and YOLO annotations with
optional Sim2Real augmentation.
"""

bl_info = {
    "name": "Huhb3D 6DoF Data Generator",
    "author": "Huhb3D",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Huhb3D",
    "description": "Generate 6DoF pose estimation training data from STEP files",
    "category": "Render",
}

import logging

logger = logging.getLogger(__name__)


def register():
    """Register all add-on components."""
    from . import ui
    ui.register()
    logger.info("Huhb3D 6DoF Data Generator registered")


def unregister():
    """Unregister all add-on components."""
    from . import ui
    ui.unregister()
    logger.info("Huhb3D 6DoF Data Generator unregistered")


if __name__ == "__main__":
    register()
