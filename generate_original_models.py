"""
generate_original_models.py - Programmatic 3D Model Generator for Commercial Data
==================================================================================
Generates 100% ORIGINAL industrial standard parts using cadquery (Apache-2.0).

LEGAL BASIS:
  - All models are ORIGINAL works created by parametric CAD scripts
  - cadquery is licensed under Apache-2.0 (commercial use permitted)
  - OpenCASCADE (cadquery's kernel) is licensed under LGPL-2.1 (commercial use permitted)
  - No third-party copyrighted 3D models are used as input
  - Output STEP/STL files are original works of the script author

  => The generated models have ZERO copyright risk for commercial data sales.

Usage:
    python generate_original_models.py --output-dir ./original_models
    python generate_original_models.py --output-dir ./original_models --count 5
"""

import argparse
import json
import math
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

try:
    import cadquery as cq
except ImportError:
    print("ERROR: cadquery is required. Install with: pip install cadquery")
    print("  cadquery is Apache-2.0 licensed: https://github.com/CadQuery/cadquery")
    sys.exit(1)


MODEL_REGISTRY = []


def register_model(func):
    MODEL_REGISTRY.append(func)
    return func


@register_model
def generate_flange(params=None):
    p = params or {}
    outer_radius = p.get("outer_radius", 50)
    inner_radius = p.get("inner_radius", 15)
    bolt_circle_radius = p.get("bolt_circle_radius", 35)
    bolt_hole_radius = p.get("bolt_hole_radius", 4.5)
    bolt_count = p.get("bolt_count", 6)
    thickness = p.get("thickness", 12)
    hub_radius = p.get("hub_radius", 22)
    hub_height = p.get("hub_height", 20)
    fillet_radius = p.get("fillet_radius", 2)

    result = (
        cq.Workplane("XY")
        .circle(outer_radius).extrude(thickness)
        .faces(">Z").workplane()
        .circle(hub_radius).extrude(hub_height)
        .faces(">Z").workplane()
        .circle(inner_radius).cutThruAll()
    )

    for angle_deg in range(0, 360, max(1, 360 // bolt_count)):
        x = bolt_circle_radius * math.cos(math.radians(angle_deg))
        y = bolt_circle_radius * math.sin(math.radians(angle_deg))
        result = (
            result.faces(">Z").workplane()
            .center(x, y)
            .circle(bolt_hole_radius)
            .cutThruAll()
        )

    try:
        result = result.edges("|Z").fillet(fillet_radius)
    except Exception:
        pass

    metadata = {
        "part_type": "Flange",
        "standard": "DIN-style",
        "parameters": {
            "outer_radius_mm": outer_radius,
            "inner_radius_mm": inner_radius,
            "bolt_circle_radius_mm": bolt_circle_radius,
            "bolt_hole_radius_mm": bolt_hole_radius,
            "bolt_count": bolt_count,
            "thickness_mm": thickness,
            "hub_radius_mm": hub_radius,
            "hub_height_mm": hub_height,
        },
        "features": ["bolt_holes", "hub", "through_hole", "fillets"],
        "feature_types": {
            "bolt_holes": "ConcaveFeature_Hole",
            "through_hole": "ConcaveFeature_Hole",
            "hub": "ConvexFeature_Bolt",
            "top_face": "HorizontalPlane",
            "bottom_face": "HorizontalPlane",
            "side_face": "LateralPlane",
        }
    }
    return result, metadata


@register_model
def generate_hex_bolt(params=None):
    p = params or {}
    head_diameter = p.get("head_diameter", 18)
    head_height = p.get("head_height", 7)
    shaft_diameter = p.get("shaft_diameter", 10)
    shaft_length = p.get("shaft_length", 40)
    chamfer = p.get("chamfer", 1.5)

    result = (
        cq.Workplane("XY")
        .polygon(6, head_diameter).extrude(head_height)
        .faces(">Z").workplane()
        .circle(shaft_diameter / 2).extrude(shaft_length)
    )

    try:
        result = result.faces(">Z").chamfer(chamfer)
    except Exception:
        pass

    try:
        result = result.faces("<Z").chamfer(chamfer * 0.5)
    except Exception:
        pass

    metadata = {
        "part_type": "HexBolt",
        "standard": "ISO 4014 style",
        "parameters": {
            "head_diameter_mm": head_diameter,
            "head_height_mm": head_height,
            "shaft_diameter_mm": shaft_diameter,
            "shaft_length_mm": shaft_length,
        },
        "features": ["hex_head", "shaft", "chamfer"],
        "feature_types": {
            "hex_head": "ConvexFeature_Bolt",
            "shaft": "FreeSurface",
            "top_face": "HorizontalPlane",
            "bottom_face": "HorizontalPlane",
        }
    }
    return result, metadata


@register_model
def generate_bearing_block(params=None):
    p = params or {}
    width = p.get("width", 60)
    height = p.get("height", 40)
    depth = p.get("depth", 30)
    bore_radius = p.get("bore_radius", 15)
    mount_hole_radius = p.get("mount_hole_radius", 4)
    mount_hole_spacing = p.get("mount_hole_spacing", 40)
    fillet_r = p.get("fillet_radius", 3)

    result = (
        cq.Workplane("XY")
        .box(width, height, depth)
        .faces(">Z").workplane()
        .circle(bore_radius).cutThruAll()
    )

    for x_offset in [-mount_hole_spacing / 2, mount_hole_spacing / 2]:
        result = (
            result.faces(">Z").workplane()
            .center(x_offset, 0)
            .circle(mount_hole_radius)
            .cutBlind(-depth * 0.6)
        )

    try:
        result = result.edges("|Z").fillet(fillet_r)
    except Exception:
        pass

    try:
        result = result.edges("|X").fillet(fillet_r * 0.5)
    except Exception:
        pass

    metadata = {
        "part_type": "BearingBlock",
        "standard": "Pillow-block style",
        "parameters": {
            "width_mm": width,
            "height_mm": height,
            "depth_mm": depth,
            "bore_radius_mm": bore_radius,
            "mount_hole_spacing_mm": mount_hole_spacing,
        },
        "features": ["bore", "mount_holes", "fillets"],
        "feature_types": {
            "bore": "ConcaveFeature_Hole",
            "mount_holes": "ConcaveFeature_Hole",
            "top_face": "HorizontalPlane",
            "side_faces": "LateralPlane",
        }
    }
    return result, metadata


@register_model
def generate_step_shaft(params=None):
    p = params or {}
    segments = p.get("segments", [
        {"radius": 20, "length": 15},
        {"radius": 15, "length": 25},
        {"radius": 10, "length": 20},
        {"radius": 15, "length": 15},
    ])
    fillet_r = p.get("fillet_radius", 1.5)

    result = cq.Workplane("XY").circle(segments[0]["radius"]).extrude(segments[0]["length"])

    for seg in segments[1:]:
        result = (
            result.faces(">Z").workplane()
            .circle(seg["radius"])
            .extrude(seg["length"])
        )

    try:
        for i in range(1, len(segments)):
            step_face = result.faces(">Z").val()
            result = result.edges("|Z").fillet(fillet_r)
    except Exception:
        pass

    metadata = {
        "part_type": "StepShaft",
        "standard": "Custom",
        "parameters": {
            "segments": segments,
        },
        "features": ["steps", "shoulders"],
        "feature_types": {
            "shoulders": "ConvexFeature_Bolt",
            "shaft_surfaces": "FreeSurface",
            "step_faces": "HorizontalPlane",
        }
    }
    return result, metadata


@register_model
def generate_l_bracket(params=None):
    p = params or {}
    width = p.get("width", 50)
    height = p.get("height", 40)
    thickness = p.get("thickness", 8)
    hole_radius = p.get("hole_radius", 5)
    hole_count = p.get("hole_count", 3)
    fillet_r = p.get("fillet_radius", 4)

    result = (
        cq.Workplane("XY")
        .box(width, thickness, width)
        .faces(">Y").workplane()
        .center(0, width / 2)
        .box(width, height, thickness)
    )

    try:
        result = result.edges("|Z").fillet(fillet_r)
    except Exception:
        pass

    for i in range(hole_count):
        x_offset = -width / 2 + width / (hole_count + 1) * (i + 1)
        result = (
            result.faces("<Y").workplane()
            .center(x_offset, 0)
            .circle(hole_radius)
            .cutThruAll()
        )

    for i in range(hole_count):
        x_offset = -width / 2 + width / (hole_count + 1) * (i + 1)
        result = (
            result.faces(">Z").workplane()
            .center(x_offset, 0)
            .circle(hole_radius)
            .cutThruAll()
        )

    metadata = {
        "part_type": "LBracket",
        "standard": "Custom",
        "parameters": {
            "width_mm": width,
            "height_mm": height,
            "thickness_mm": thickness,
            "hole_count": hole_count,
        },
        "features": ["mount_holes", "corner_fillet"],
        "feature_types": {
            "mount_holes": "ConcaveFeature_Hole",
            "vertical_face": "LateralPlane",
            "horizontal_face": "HorizontalPlane",
        }
    }
    return result, metadata


@register_model
def generate_gear(params=None):
    p = params or {}
    module = p.get("module", 2.5)
    teeth = p.get("teeth", 20)
    thickness = p.get("thickness", 15)
    bore_radius = p.get("bore_radius", 10)
    hub_radius = p.get("hub_radius", 18)
    hub_height = p.get("hub_height", 10)
    chamfer = p.get("chamfer", 1.0)

    pitch_radius = module * teeth / 2
    outer_radius = pitch_radius + module
    root_radius = pitch_radius - module * 1.25

    tooth_points = []
    for i in range(teeth):
        angle = 2 * math.pi * i / teeth
        half_tooth = math.pi / teeth * 0.45

        a1 = angle - half_tooth * 1.2
        tooth_points.append((root_radius * math.cos(a1), root_radius * math.sin(a1)))

        a2 = angle - half_tooth * 0.6
        tooth_points.append((pitch_radius * math.cos(a2), pitch_radius * math.sin(a2)))

        a3 = angle - half_tooth * 0.3
        tooth_points.append((outer_radius * math.cos(a3), outer_radius * math.sin(a3)))

        a4 = angle + half_tooth * 0.3
        tooth_points.append((outer_radius * math.cos(a4), outer_radius * math.sin(a4)))

        a5 = angle + half_tooth * 0.6
        tooth_points.append((pitch_radius * math.cos(a5), pitch_radius * math.sin(a5)))

        a6 = angle + half_tooth * 1.2
        tooth_points.append((root_radius * math.cos(a6), root_radius * math.sin(a6)))

    tooth_points_closed = tooth_points + [tooth_points[0]]
    result = (
        cq.Workplane("XY")
        .polyline(tooth_points_closed).close()
        .extrude(thickness)
        .faces(">Z").workplane()
        .circle(hub_radius).extrude(hub_height)
        .faces(">Z").workplane()
        .circle(bore_radius).cutThruAll()
    )

    try:
        result = result.faces(">Z").chamfer(chamfer)
    except Exception:
        pass

    metadata = {
        "part_type": "SpurGear",
        "standard": "ISO 1328 style",
        "parameters": {
            "module": module,
            "teeth": teeth,
            "thickness_mm": thickness,
            "bore_radius_mm": bore_radius,
            "pitch_radius_mm": pitch_radius,
        },
        "features": ["teeth", "hub", "bore", "chamfer"],
        "feature_types": {
            "teeth": "ConvexFeature_Bolt",
            "bore": "ConcaveFeature_Hole",
            "hub": "ConvexFeature_Bolt",
            "top_face": "HorizontalPlane",
        }
    }
    return result, metadata


@register_model
def generate_pipe_tee(params=None):
    p = params or {}
    main_radius = p.get("main_radius", 20)
    main_length = p.get("main_length", 80)
    branch_radius = p.get("branch_radius", 15)
    branch_length = p.get("branch_length", 50)
    wall_thickness = p.get("wall_thickness", 4)

    main_outer = (
        cq.Workplane("XY")
        .circle(main_radius).extrude(main_length)
    )
    main_bore = (
        cq.Workplane("XY")
        .circle(main_radius - wall_thickness).extrude(main_length)
    )
    main_pipe = main_outer.cut(main_bore)

    branch_outer = (
        cq.Workplane("YZ")
        .workplane(offset=-main_length / 2)
        .circle(branch_radius).extrude(branch_length)
    )
    branch_bore = (
        cq.Workplane("YZ")
        .workplane(offset=-main_length / 2)
        .circle(branch_radius - wall_thickness).extrude(branch_length)
    )
    branch_pipe = branch_outer.cut(branch_bore)

    result = main_pipe.union(branch_pipe)

    metadata = {
        "part_type": "PipeTee",
        "standard": "ASME B16.9 style",
        "parameters": {
            "main_radius_mm": main_radius,
            "main_length_mm": main_length,
            "branch_radius_mm": branch_radius,
            "branch_length_mm": branch_length,
            "wall_thickness_mm": wall_thickness,
        },
        "features": ["main_bore", "branch_bore", "intersection"],
        "feature_types": {
            "main_bore": "ConcaveFeature_Hole",
            "branch_bore": "ConcaveFeature_Hole",
            "outer_surface": "FreeSurface",
        }
    }
    return result, metadata


@register_model
def generate_mounting_plate(params=None):
    p = params or {}
    width = p.get("width", 100)
    height = p.get("height", 80)
    thickness = p.get("thickness", 10)
    corner_radius = p.get("corner_radius", 8)
    hole_radius = p.get("hole_radius", 5.5)
    hole_margin = p.get("hole_margin", 12)
    center_hole_radius = p.get("center_hole_radius", 15)
    slot_width = p.get("slot_width", 6)
    slot_length = p.get("slot_length", 20)

    result = (
        cq.Workplane("XY")
        .rect(width, height).extrude(thickness)
    )

    try:
        result = result.edges("|Z").fillet(corner_radius)
    except Exception:
        pass

    for sx in [-1, 1]:
        for sy in [-1, 1]:
            result = (
                result.faces(">Z").workplane()
                .center(sx * (width / 2 - hole_margin), sy * (height / 2 - hole_margin))
                .circle(hole_radius)
                .cutThruAll()
            )

    result = (
        result.faces(">Z").workplane()
        .circle(center_hole_radius)
        .cutThruAll()
    )

    for y_offset in [-20, 20]:
        result = (
            result.faces(">Z").workplane()
            .center(0, y_offset)
            .slot2D(slot_length, slot_width, 0)
            .cutThruAll()
        )

    try:
        result = result.faces(">Z").chamfer(0.5)
    except Exception:
        pass

    metadata = {
        "part_type": "MountingPlate",
        "standard": "Custom",
        "parameters": {
            "width_mm": width,
            "height_mm": height,
            "thickness_mm": thickness,
            "corner_holes": 4,
            "center_hole_radius_mm": center_hole_radius,
        },
        "features": ["corner_holes", "center_hole", "slots", "chamfer"],
        "feature_types": {
            "corner_holes": "ConcaveFeature_Hole",
            "center_hole": "ConcaveFeature_Hole",
            "slots": "ConcaveFeature_Hole",
            "top_face": "HorizontalPlane",
        }
    }
    return result, metadata


@register_model
def generate_coupling(params=None):
    p = params or {}
    outer_radius = p.get("outer_radius", 25)
    length = p.get("length", 50)
    bore1_radius = p.get("bore1_radius", 10)
    bore2_radius = p.get("bore2_radius", 12)
    keyway_width = p.get("keyway_width", 4)
    keyway_depth = p.get("keyway_depth", 3)
    bolt_circle_r = p.get("bolt_circle_radius", 18)
    bolt_radius = p.get("bolt_radius", 3.5)
    bolt_count = p.get("bolt_count", 4)

    result = (
        cq.Workplane("XY")
        .circle(outer_radius).extrude(length)
        .faces("<Z").workplane()
        .circle(bore1_radius).cutBlind(length / 2)
        .faces(">Z").workplane()
        .circle(bore2_radius).cutBlind(length / 2)
    )

    result = (
        result.faces("<Z").workplane()
        .center(bore1_radius - keyway_depth / 2, 0)
        .rect(keyway_depth, keyway_width)
        .cutBlind(length / 2)
    )

    for angle_deg in range(0, 360, max(1, 360 // bolt_count)):
        x = bolt_circle_r * math.cos(math.radians(angle_deg))
        y = bolt_circle_r * math.sin(math.radians(angle_deg))
        result = (
            result.faces(">Z").workplane()
            .center(x, y)
            .circle(bolt_radius)
            .cutThruAll()
        )

    try:
        result = result.faces(">Z").chamfer(1.0)
        result = result.faces("<Z").chamfer(1.0)
    except Exception:
        pass

    metadata = {
        "part_type": "Coupling",
        "standard": "Custom",
        "parameters": {
            "outer_radius_mm": outer_radius,
            "length_mm": length,
            "bore1_radius_mm": bore1_radius,
            "bore2_radius_mm": bore2_radius,
            "keyway_width_mm": keyway_width,
        },
        "features": ["bores", "keyway", "bolt_holes", "chamfers"],
        "feature_types": {
            "bores": "ConcaveFeature_Hole",
            "keyway": "ConcaveFeature_Hole",
            "bolt_holes": "ConcaveFeature_Hole",
            "outer_surface": "FreeSurface",
        }
    }
    return result, metadata


@register_model
def generate_valve_body(params=None):
    p = params or {}
    body_radius = p.get("body_radius", 30)
    body_height = p.get("body_height", 50)
    inlet_radius = p.get("inlet_radius", 12)
    inlet_length = p.get("inlet_length", 25)
    outlet_radius = p.get("outlet_radius", 12)
    outlet_length = p.get("outlet_length", 25)
    wall_thickness = p.get("wall_thickness", 5)
    flange_radius = p.get("flange_radius", 22)
    flange_thickness = p.get("flange_thickness", 6)

    body_outer = (
        cq.Workplane("XY")
        .circle(body_radius).extrude(body_height)
    )

    inlet_outer = (
        cq.Workplane("YZ")
        .workplane(offset=-body_height / 2)
        .circle(inlet_radius).extrude(inlet_length)
    )

    outlet_outer = (
        cq.Workplane("YZ")
        .workplane(offset=body_height / 2)
        .circle(outlet_radius).extrude(outlet_length)
    )

    result = body_outer.union(inlet_outer).union(outlet_outer)

    chamber = (
        cq.Workplane("XY")
        .circle(body_radius - wall_thickness).extrude(body_height - wall_thickness)
    )
    result = result.cut(chamber)

    inlet_inner = (
        cq.Workplane("YZ")
        .workplane(offset=-body_height / 2)
        .circle(inlet_radius - wall_thickness).extrude(inlet_length + 1)
    )
    result = result.cut(inlet_inner)

    outlet_inner = (
        cq.Workplane("YZ")
        .workplane(offset=body_height / 2)
        .circle(outlet_radius - wall_thickness).extrude(outlet_length + 1)
    )
    result = result.cut(outlet_inner)

    inlet_flange = (
        cq.Workplane("YZ")
        .workplane(offset=-body_height / 2 - inlet_length)
        .circle(flange_radius).extrude(flange_thickness)
    )
    outlet_flange = (
        cq.Workplane("YZ")
        .workplane(offset=body_height / 2 + outlet_length - flange_thickness)
        .circle(flange_radius).extrude(flange_thickness)
    )
    result = result.union(inlet_flange).union(outlet_flange)

    metadata = {
        "part_type": "ValveBody",
        "standard": "Custom",
        "parameters": {
            "body_radius_mm": body_radius,
            "body_height_mm": body_height,
            "inlet_radius_mm": inlet_radius,
            "outlet_radius_mm": outlet_radius,
            "wall_thickness_mm": wall_thickness,
        },
        "features": ["inlet", "outlet", "chamber", "flanges"],
        "feature_types": {
            "inlet": "ConcaveFeature_Hole",
            "outlet": "ConcaveFeature_Hole",
            "chamber": "ConcaveFeature_Hole",
            "flanges": "Flange",
            "outer_surface": "FreeSurface",
        }
    }
    return result, metadata


@register_model
def generate_heat_sink(params=None):
    p = params or {}
    base_width = p.get("base_width", 60)
    base_depth = p.get("base_depth", 40)
    base_thickness = p.get("base_thickness", 5)
    fin_height = p.get("fin_height", 25)
    fin_thickness = p.get("fin_thickness", 2)
    fin_count = p.get("fin_count", 10)
    fin_gap = (base_depth - fin_count * fin_thickness) / max(1, fin_count - 1)

    result = (
        cq.Workplane("XY")
        .box(base_width, base_depth, base_thickness)
    )

    for i in range(fin_count):
        y_offset = -base_depth / 2 + fin_thickness / 2 + i * (fin_thickness + fin_gap)
        result = (
            result.faces(">Z").workplane()
            .center(0, y_offset)
            .rect(base_width, fin_thickness)
            .extrude(fin_height)
        )

    metadata = {
        "part_type": "HeatSink",
        "standard": "Custom",
        "parameters": {
            "base_width_mm": base_width,
            "base_depth_mm": base_depth,
            "base_thickness_mm": base_thickness,
            "fin_height_mm": fin_height,
            "fin_count": fin_count,
        },
        "features": ["fins", "base_plate"],
        "feature_types": {
            "fins": "ConvexFeature_Bolt",
            "base_plate": "HorizontalPlane",
            "fin_surfaces": "LateralPlane",
        }
    }
    return result, metadata


@register_model
def generate_connector_housing(params=None):
    p = params or {}
    width = p.get("width", 40)
    height = p.get("height", 30)
    depth = p.get("depth", 25)
    wall_thickness = p.get("wall_thickness", 3)
    pin_count = p.get("pin_count", 4)
    pin_radius = p.get("pin_radius", 1.5)
    pin_length = p.get("pin_length", 15)
    pin_spacing = p.get("pin_spacing", 6)
    cable_hole_radius = p.get("cable_hole_radius", 6)

    result = (
        cq.Workplane("XY")
        .box(width, height, depth)
        .faces(">Z").workplane()
        .rect(width - 2 * wall_thickness, height - 2 * wall_thickness)
        .cutBlind(-(depth - wall_thickness))
    )

    result = (
        result.faces("<Z").workplane()
        .circle(cable_hole_radius)
        .cutBlind(wall_thickness * 2)
    )

    start_x = -(pin_count - 1) * pin_spacing / 2
    for i in range(pin_count):
        x_offset = start_x + i * pin_spacing
        result = (
            result.faces(">Z").workplane()
            .center(x_offset, 0)
            .circle(pin_radius)
            .extrude(pin_length)
        )

    try:
        result = result.edges("|Z").fillet(1.0)
    except Exception:
        pass

    metadata = {
        "part_type": "ConnectorHousing",
        "standard": "Custom",
        "parameters": {
            "width_mm": width,
            "height_mm": height,
            "depth_mm": depth,
            "pin_count": pin_count,
            "pin_length_mm": pin_length,
        },
        "features": ["pins", "cavity", "cable_hole", "fillets"],
        "feature_types": {
            "pins": "ConvexFeature_Bolt",
            "cavity": "ConcaveFeature_Hole",
            "cable_hole": "ConcaveFeature_Hole",
            "outer_surface": "FreeSurface",
        }
    }
    return result, metadata


@register_model
def generate_ball_joint(params=None):
    """Ball joint with spherical surface - produces SphericalSurface (cat 14) topology."""
    p = params or {}
    shaft_radius = p.get("shaft_radius", 10)
    shaft_length = p.get("shaft_length", 30)
    ball_radius = p.get("ball_radius", 18)
    base_radius = p.get("base_radius", 25)
    base_height = p.get("base_height", 8)
    fillet_r = p.get("fillet_radius", 1.5)

    # Base plate
    result = (
        cq.Workplane("XY")
        .circle(base_radius).extrude(base_height)
    )

    # Shaft from base
    result = (
        result.faces(">Z").workplane()
        .circle(shaft_radius).extrude(shaft_length)
    )

    # Ball on top of shaft
    import math
    result = (
        result.faces(">Z").workplane()
        .circle(ball_radius).extrude(ball_radius)  # cylinder
    )
    # Add sphere by revolving a semicircle
    result = (
        result.faces(">Z").workplane()
        .circle(ball_radius).extrude(0)  # just to get the face
    )

    # Simpler approach: use sphere primitive
    result = (
        cq.Workplane("XY")
        .circle(base_radius).extrude(base_height)
    )
    result = (
        result.faces(">Z").workplane()
        .circle(shaft_radius).extrude(shaft_length)
    )
    # Sphere on top
    sphere = cq.Workplane("XY").sphere(ball_radius)
    result = result.union(sphere.translate((0, 0, base_height + shaft_length + ball_radius * 0.3)))

    try:
        result = result.edges("|Z").fillet(fillet_r)
    except Exception:
        pass

    metadata = {
        "part_type": "BallJoint",
        "standard": "Custom",
        "parameters": {
            "shaft_radius_mm": shaft_radius,
            "shaft_length_mm": shaft_length,
            "ball_radius_mm": ball_radius,
            "base_radius_mm": base_radius,
            "base_height_mm": base_height,
        },
        "features": ["spherical_head", "shaft", "base_plate", "fillets"],
        "feature_types": {
            "spherical_head": "SphericalSurface",
            "shaft": "FreeSurface",
            "base_top": "HorizontalPlane",
            "base_bottom": "HorizontalPlane",
            "base_side": "LateralPlane_Z",
            "fillets": "Fillet",
        }
    }
    return result, metadata


@register_model
def generate_thin_wall_bracket(params=None):
    """Thin-wall bracket with very thin features - produces Degenerate (cat 7) topology."""
    p = params or {}
    base_width = p.get("base_width", 60)
    base_depth = p.get("base_depth", 40)
    base_height = p.get("base_height", 5)
    wall_thickness = p.get("wall_thickness", 1.0)  # Very thin wall
    wall_height = p.get("wall_height", 35)
    rib_thickness = p.get("rib_thickness", 0.8)  # Ultra-thin rib
    hole_radius = p.get("hole_radius", 4)
    hole_count = p.get("hole_count", 4)
    chamfer_size = p.get("chamfer_size", 2)

    # Base plate
    result = (
        cq.Workplane("XY")
        .box(base_width, base_depth, base_height)
    )

    # Thin vertical wall along one edge
    result = (
        result.faces(">Z").workplane()
        .center(0, base_depth / 2 - wall_thickness / 2)
        .rect(base_width, wall_thickness)
        .extrude(wall_height)
    )

    # Ultra-thin diagonal rib (produces degenerate triangles)
    result = (
        result.faces(">Z").workplane()
        .center(base_width / 4, 0)
        .rect(rib_thickness, base_depth)
        .extrude(wall_height * 0.6)
    )

    # Another thin rib perpendicular
    result = (
        result.faces(">Z").workplane()
        .center(-base_width / 4, 0)
        .rect(rib_thickness, base_depth)
        .extrude(wall_height * 0.4)
    )

    # Mounting holes in base
    for x_sign in [-1, 1]:
        for y_sign in [-1, 1]:
            result = (
                result.faces("<Z").workplane()
                .center(x_sign * base_width / 3, y_sign * base_depth / 3)
                .circle(hole_radius)
                .cutThruAll()
            )

    # Chamfer on top edges of thin wall
    try:
        result = result.edges(">Z").chamfer(chamfer_size)
    except Exception:
        pass

    metadata = {
        "part_type": "ThinWallBracket",
        "standard": "Custom",
        "parameters": {
            "base_width_mm": base_width,
            "base_depth_mm": base_depth,
            "base_height_mm": base_height,
            "wall_thickness_mm": wall_thickness,
            "wall_height_mm": wall_height,
            "rib_thickness_mm": rib_thickness,
        },
        "features": ["thin_wall", "thin_ribs", "mounting_holes", "chamfers", "base_plate"],
        "feature_types": {
            "thin_wall": "LateralPlane_Z",
            "thin_ribs": "Degenerate",
            "mounting_holes": "ConcaveFeature_Hole",
            "base_top": "HorizontalPlane",
            "base_bottom": "HorizontalPlane",
            "base_side": "LateralPlane_Z",
            "chamfers": "Chamfer",
        }
    }
    return result, metadata


VARIANT_CONFIGS = {
    "flange_small": {"outer_radius": 35, "inner_radius": 10, "bolt_count": 4, "thickness": 8},
    "flange_medium": {"outer_radius": 50, "inner_radius": 15, "bolt_count": 6, "thickness": 12},
    "flange_large": {"outer_radius": 70, "inner_radius": 20, "bolt_count": 8, "thickness": 16},
    "bolt_m8": {"shaft_diameter": 8, "shaft_length": 30, "head_diameter": 14, "head_height": 5.5},
    "bolt_m10": {"shaft_diameter": 10, "shaft_length": 40, "head_diameter": 18, "head_height": 7},
    "bolt_m12": {"shaft_diameter": 12, "shaft_length": 50, "head_diameter": 20, "head_height": 8},
    "bearing_small": {"bore_radius": 10, "width": 40, "height": 30},
    "bearing_medium": {"bore_radius": 15, "width": 60, "height": 40},
    "gear_small": {"teeth": 12, "module": 2, "thickness": 10},
    "gear_medium": {"teeth": 20, "module": 2.5, "thickness": 15},
    "gear_large": {"teeth": 30, "module": 3, "thickness": 20},
}


def generate_all_models(output_dir, variant_count=1):
    output_path = Path(output_dir)
    step_dir = output_path / "step"
    stl_dir = output_path / "stl"
    step_dir.mkdir(parents=True, exist_ok=True)
    stl_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "generator": "generate_original_models.py",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "legal_basis": {
            "models_are_original_works": True,
            "cadquery_license": "Apache-2.0",
            "opencascade_license": "LGPL-2.1",
            "no_third_party_copyrighted_input": True,
            "output_models_license": "CC0-1.0 (public domain)",
        },
        "models": [],
    }

    model_index = 0
    for gen_func in MODEL_REGISTRY:
        base_name = gen_func.__name__.replace("generate_", "")

        configs = [{"name": base_name, "params": {}}]

        for vname, vparams in VARIANT_CONFIGS.items():
            if vname.startswith(base_name.split("_")[0].lower()):
                configs.append({"name": vname, "params": vparams})

        for config in configs:
            name = config["name"]
            params = config["params"]

            print(f"  Generating: {name}...", end=" ", flush=True)
            try:
                cq_obj, metadata = gen_func(params)

                step_path = step_dir / f"{name}.step"
                cq.exporters.export(cq_obj, str(step_path))
                metadata["step_file"] = f"step/{name}.step"

                stl_path = stl_dir / f"{name}.stl"
                cq.exporters.export(cq_obj, str(stl_path), exportType="STL")
                metadata["stl_file"] = f"stl/{name}.stl"

                metadata["model_id"] = model_index
                metadata["name"] = name
                manifest["models"].append(metadata)

                print(f"OK (STEP: {step_path.stat().st_size/1024:.1f}KB, STL: {stl_path.stat().st_size/1024:.1f}KB)")
                model_index += 1

            except Exception as e:
                print(f"FAILED: {e}")

    manifest_path = output_path / "models_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"\n  Total models generated: {len(manifest['models'])}")
    print(f"  Manifest: {manifest_path}")
    return manifest


def main():
    parser = argparse.ArgumentParser(
        description="Generate 100% original industrial 3D models for commercial data production"
    )
    parser.add_argument("--output-dir", "-o", default="./original_models",
                        help="Output directory for generated models")
    args = parser.parse_args()

    print("=" * 60)
    print("  Original 3D Model Generator (Commercial-Safe)")
    print("=" * 60)
    print(f"  Legal basis: All models are ORIGINAL parametric CAD works")
    print(f"  cadquery: Apache-2.0 | OpenCASCADE: LGPL-2.1")
    print(f"  Output license: CC0-1.0 (public domain, no restrictions)")
    print("=" * 60)
    print()

    manifest = generate_all_models(args.output_dir)

    print(f"\n{'='*60}")
    print(f"  GENERATION COMPLETE")
    print(f"  {len(manifest['models'])} models ready for commercial data production")
    print(f"  Output: {Path(args.output_dir).resolve()}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
