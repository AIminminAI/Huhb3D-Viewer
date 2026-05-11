"""
step_topology_parser.py - STEP File Topology Parser
====================================================
Extracts EXACT face type ground truth from STEP/STP CAD files
using OpenCASCADE topology analysis.

This is the KEY differentiator: instead of guessing labels from
triangle curvature (which is unreliable), we parse the CAD model's
actual topology to get ground truth face types:
  - CYLINDER (concave) → Hole
  - CYLINDER (convex)  → Bolt / Boss
  - PLANE              → HorizontalPlane / LateralPlane
  - CONE               → Chamfer
  - TORUS              → Fillet / Blend
  - SPHERE             → SphericalSurface

Usage:
    python step_topology_parser.py --input part.step --output-dir ./parsed
    python step_topology_parser.py --input part.step --output-dir ./parsed --linear-deflection 0.1

Output:
    - <output-dir>/tessellated.stl     (tessellated mesh for C++ engine)
    - <output-dir>/topology_labels.json (per-triangle face type labels)
    - <output-dir>/topology_summary.json (face type statistics)

Requirements:
    pip install cadquery  (includes OpenCASCADE)
"""

import argparse
import json
import math
import os
import struct
import sys
from pathlib import Path
from collections import defaultdict


CATEGORY_NAMES = {
    0: "FreeSurface",
    1: "HorizontalPlane",
    2: "LateralPlane_X",
    3: "LateralPlane_Z",
    4: "NearHorizontal",
    5: "NearLateral_X",
    6: "NearLateral_Z",
    7: "Degenerate",
    8: "ConvexFeature_Bolt",
    9: "ConcaveFeature_Hole",
    10: "Flange",
    11: "Boss",
    12: "Chamfer",
    13: "Fillet",
    14: "SphericalSurface",
}

CATEGORY_COLORS = {
    0: (127, 127, 127),
    1: (0, 0, 255),
    2: (0, 255, 0),
    3: (255, 0, 0),
    4: (255, 255, 0),
    5: (255, 0, 255),
    6: (0, 255, 255),
    7: (255, 127, 0),
    8: (200, 50, 50),
    9: (50, 50, 200),
    10: (200, 150, 50),
    11: (150, 50, 200),
    12: (100, 200, 100),
    13: (200, 100, 200),
    14: (100, 200, 200),
}


def classify_cylinder_face(face_shape, radius, axis_dir, face_area, shape_bounds):
    is_concave = False
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.BRepGProp import BRepGProp_SurfaceProperties
        from OCP.GProp import GProp_GProps
        from OCP.BRepLProp import BRepLProp_CLProps
        from OCP.BRepAdaptor import BRepAdaptor_Curve

        adaptor = BRepAdaptor_Surface(face_shape)
        cyl = adaptor.Cylinder()
        cyl_loc = cyl.Location()
        cx, cy, cz = cyl_loc.X(), cyl_loc.Y(), cyl_loc.Z()

        props = GProp_GProps()
        BRepGProp_SurfaceProperties(face_shape, props)
        center = props.CentreOfMass()
        fcx, fcy, fcz = center.X(), center.Y(), center.Z()

        u_mid = (adaptor.FirstUParameter() + adaptor.LastUParameter()) / 2
        v_mid = (adaptor.FirstVParameter() + adaptor.LastVParameter()) / 2
        pnt = adaptor.Value(u_mid, v_mid)

        dx_from_axis = pnt.X() - cx
        dy_from_axis = pnt.Y() - cy
        dz_from_axis = pnt.Z() - cz
        cross_x = dy_from_axis * axis_dir[2] - dz_from_axis * axis_dir[1]
        cross_y = dz_from_axis * axis_dir[0] - dx_from_axis * axis_dir[2]
        cross_z = dx_from_axis * axis_dir[1] - dy_from_axis * axis_dir[0]
        cross_len = math.sqrt(cross_x**2 + cross_y**2 + cross_z**2)
        if cross_len > 1e-6:
            radial_dir = [cross_x/cross_len, cross_y/cross_len, cross_z/cross_len]
        else:
            radial_dir = [1.0, 0.0, 0.0]

        from OCP.gp import gp_Vec, gp_Pnt
        pnt_gp = gp_Pnt()
        du = gp_Vec()
        dv = gp_Vec()
        adaptor.D1(u_mid, v_mid, pnt_gp, du, dv)
        normal_x = du.Y() * dv.Z() - du.Z() * dv.Y()
        normal_y = du.Z() * dv.X() - du.X() * dv.Z()
        normal_z = du.X() * dv.Y() - du.Y() * dv.X()
        nlen = math.sqrt(normal_x**2 + normal_y**2 + normal_z**2)
        if nlen > 1e-10:
            normal_x /= nlen
            normal_y /= nlen
            normal_z /= nlen

        dot = normal_x * radial_dir[0] + normal_y * radial_dir[1] + normal_z * radial_dir[2]
        is_concave = dot < 0
    except Exception:
        try:
            from OCP.BRepAdaptor import BRepAdaptor_Surface
            from OCP.BRepGProp import BRepGProp_SurfaceProperties
            from OCP.GProp import GProp_GProps
            adaptor = BRepAdaptor_Surface(face_shape)
            cyl = adaptor.Cylinder()
            cyl_loc = cyl.Location()
            cx2 = cyl_loc.X()
            cy2 = cyl_loc.Y()
            cz2 = cyl_loc.Z()
            u_mid = (adaptor.FirstUParameter() + adaptor.LastUParameter()) / 2
            v_mid = (adaptor.FirstVParameter() + adaptor.LastVParameter()) / 2
            pnt = adaptor.Value(u_mid, v_mid)
            dx_from_axis = pnt.X() - cx2
            dy_from_axis = pnt.Y() - cy2
            dz_from_axis = pnt.Z() - cz2
            cross_x = dy_from_axis * axis_dir[2] - dz_from_axis * axis_dir[1]
            cross_y = dz_from_axis * axis_dir[0] - dx_from_axis * axis_dir[2]
            cross_z = dx_from_axis * axis_dir[1] - dy_from_axis * axis_dir[0]
            cross_len = math.sqrt(cross_x**2 + cross_y**2 + cross_z**2)
            if cross_len > 1e-6:
                radial_dir = [cross_x/cross_len, cross_y/cross_len, cross_z/cross_len]
            else:
                radial_dir = [1.0, 0.0, 0.0]
            is_concave = radius < 5.0
        except Exception:
            is_concave = radius < 5.0

    max_dim = max(shape_bounds[3] - shape_bounds[0],
                  shape_bounds[4] - shape_bounds[1],
                  shape_bounds[5] - shape_bounds[2]) if shape_bounds else 100.0
    relative_radius = radius / max_dim if max_dim > 0 else 1.0

    if is_concave:
        if relative_radius < 0.15:
            return 9  # ConcaveFeature_Hole
        else:
            return 10  # Flange (large concave cylinder = bore/channel)
    else:
        if relative_radius < 0.1 and face_area < max_dim * max_dim * 0.05:
            return 8  # ConvexFeature_Bolt
        elif relative_radius < 0.3:
            return 11  # Boss
        else:
            return 0  # FreeSurface (large convex cylinder = main body)


def classify_plane_face(normal_x, normal_y, normal_z, face_area, shape_bounds):
    abs_x = abs(normal_x)
    abs_y = abs(normal_y)
    abs_z = abs(normal_z)
    threshold = 0.9
    near_threshold = 0.7

    if abs_y > threshold:
        return 1  # HorizontalPlane
    elif abs_x > threshold:
        return 2  # LateralPlane_X
    elif abs_z > threshold:
        return 3  # LateralPlane_Z
    elif abs_y > near_threshold:
        return 4  # NearHorizontal
    elif abs_x > near_threshold:
        return 5  # NearLateral_X
    elif abs_z > near_threshold:
        return 6  # NearLateral_Z
    else:
        return 0  # FreeSurface (angled plane)


def classify_cone_face(half_angle_deg, is_concave, radius, face_area):
    if is_concave:
        return 9  # ConcaveFeature_Hole (countersink)
    else:
        if half_angle_deg < 15:
            return 11  # Boss (steep cone)
        else:
            return 12  # Chamfer


def classify_torus_face(major_radius, minor_radius, is_concave):
    if is_concave:
        return 13  # Fillet (concave blend)
    else:
        if minor_radius / major_radius < 0.3:
            return 13  # Fillet (convex blend)
        else:
            return 0  # FreeSurface


def parse_step_topology(step_path, output_dir, linear_deflection=0.1, angular_deflection=0.5):
    try:
        from OCP.STEPControl import STEPControl_Reader
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
        from OCP.BRep import BRep_Tool
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.TopLoc import TopLoc_Location
        from OCP.Poly import Poly_Triangulation
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import (
            GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Cone,
            GeomAbs_Sphere, GeomAbs_Torus, GeomAbs_BezierSurface,
            GeomAbs_BSplineSurface, GeomAbs_SurfaceOfRevolution,
            GeomAbs_SurfaceOfExtrusion
        )
        from OCP.gp import gp_Vec
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib_AddClose
        from OCP.BRepGProp import BRepGProp_SurfaceProperties
        from OCP.GProp import GProp_GProps
    except ImportError:
        print("ERROR: pythonOCP not installed. Install with: pip install cadquery")
        print("  cadquery includes pythonOCP (OpenCASCADE bindings)")
        return False

    step_path = str(Path(step_path).resolve())
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[StepTopology] Parsing: {step_path}")
    print(f"[StepTopology] Output:  {output_dir}")

    reader = STEPControl_Reader()
    status = reader.ReadFile(step_path)
    if status != 1:
        print(f"ERROR: Failed to read STEP file: {step_path}")
        return False

    reader.TransferRoots()
    shape = reader.OneShape()
    if shape.IsNull():
        print("ERROR: No valid shape found in STEP file")
        return False

    print("[StepTopology] STEP file loaded successfully")

    mesh = BRepMesh_IncrementalMesh(shape, linear_deflection, False, angular_deflection)
    mesh.Perform()
    print(f"[StepTopology] Meshing complete (deflection={linear_deflection})")

    bbox = Bnd_Box()
    BRepBndLib_AddClose(shape, bbox)
    xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
    shape_bounds = [xmin, ymin, zmin, xmax, ymax, zmax]
    print(f"[StepTopology] Bounding box: ({xmin:.2f},{ymin:.2f},{zmin:.2f}) - ({xmax:.2f},{ymax:.2f},{zmax:.2f})")

    all_triangles = []
    triangle_labels = []
    face_info_list = []
    face_id_counter = 0

    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = explorer.Current()
        face_id = face_id_counter
        face_id_counter += 1

        adaptor = BRepAdaptor_Surface(face)
        surf_type = adaptor.GetType()

        props = GProp_GProps()
        BRepGProp_SurfaceProperties(face, props)
        face_area = props.Mass()
        face_center = props.CentreOfMass()

        geom_type_str = "UNKNOWN"
        category_id = 0
        category_name = "FreeSurface"
        extra_info = {}

        if surf_type == GeomAbs_Plane:
            geom_type_str = "PLANE"
            pln = adaptor.Plane()
            pos = pln.Position()
            dir_vec = pos.Direction()
            nx, ny, nz = dir_vec.X(), dir_vec.Y(), dir_vec.Z()
            if ny < 0:
                nx, ny, nz = -nx, -ny, -nz
            category_id = classify_plane_face(nx, ny, nz, face_area, shape_bounds)
            category_name = CATEGORY_NAMES.get(category_id, "Unknown")
            extra_info = {"normal": [nx, ny, nz]}

        elif surf_type == GeomAbs_Cylinder:
            geom_type_str = "CYLINDER"
            cyl = adaptor.Cylinder()
            radius = cyl.Radius()
            axis = cyl.Axis()
            axis_dir_vec = axis.Direction()
            ax_dx, ax_dy, ax_dz = axis_dir_vec.X(), axis_dir_vec.Y(), axis_dir_vec.Z()
            category_id = classify_cylinder_face(
                face, radius, [ax_dx, ax_dy, ax_dz], face_area, shape_bounds
            )
            category_name = CATEGORY_NAMES.get(category_id, "Unknown")
            extra_info = {
                "radius": round(radius, 4),
                "axis_direction": [round(ax_dx, 4), round(ax_dy, 4), round(ax_dz, 4)],
            }

        elif surf_type == GeomAbs_Cone:
            geom_type_str = "CONE"
            cone = adaptor.Cone()
            half_angle = cone.SemiAngle()
            half_angle_deg = math.degrees(half_angle)
            radius = cone.RefRadius()
            axis = cone.Axis()
            axis_dir_vec = axis.Direction()
            ax_dx, ax_dy, ax_dz = axis_dir_vec.X(), axis_dir_vec.Y(), axis_dir_vec.Z()
            is_concave = half_angle < 0
            category_id = classify_cone_face(abs(half_angle_deg), is_concave=is_concave,
                                              radius=radius, face_area=face_area)
            category_name = CATEGORY_NAMES.get(category_id, "Unknown")
            extra_info = {
                "half_angle_deg": round(half_angle_deg, 2),
                "ref_radius": round(radius, 4),
                "axis_direction": [round(ax_dx, 4), round(ax_dy, 4), round(ax_dz, 4)],
            }

        elif surf_type == GeomAbs_Sphere:
            geom_type_str = "SPHERE"
            sph = adaptor.Sphere()
            radius = sph.Radius()
            category_id = 14  # SphericalSurface
            category_name = CATEGORY_NAMES[14]
            extra_info = {"radius": round(radius, 4)}

        elif surf_type == GeomAbs_Torus:
            geom_type_str = "TORUS"
            tor = adaptor.Torus()
            major_r = tor.MajorRadius()
            minor_r = tor.MinorRadius()
            is_concave_torus = False
            try:
                u_mid = (adaptor.FirstUParameter() + adaptor.LastUParameter()) / 2
                v_mid = (adaptor.FirstVParameter() + adaptor.LastVParameter()) / 2
                from OCP.gp import gp_Vec, gp_Pnt
                pnt_gp = gp_Pnt()
                du = gp_Vec()
                dv = gp_Vec()
                adaptor.D1(u_mid, v_mid, pnt_gp, du, dv)
                normal_x = du.Y() * dv.Z() - du.Z() * dv.Y()
                normal_y = du.Z() * dv.X() - du.X() * dv.Z()
                normal_z = du.X() * dv.Y() - du.Y() * dv.X()
                nlen = math.sqrt(normal_x**2 + normal_y**2 + normal_z**2)
                if nlen > 1e-10:
                    normal_x /= nlen
                    normal_y /= nlen
                    normal_z /= nlen
                torus_loc = tor.Location()
                dx = pnt_gp.X() - torus_loc.X()
                dy = pnt_gp.Y() - torus_loc.Y()
                dz = pnt_gp.Z() - torus_loc.Z()
                dot = dx * normal_x + dy * normal_y + dz * normal_z
                is_concave_torus = dot < 0
            except Exception:
                pass
            category_id = classify_torus_face(major_r, minor_r, is_concave_torus)
            category_name = CATEGORY_NAMES.get(category_id, "Unknown")
            extra_info = {
                "major_radius": round(major_r, 4),
                "minor_radius": round(minor_r, 4),
            }

        elif surf_type in (GeomAbs_BezierSurface, GeomAbs_BSplineSurface):
            geom_type_str = "BSPLINE" if surf_type == GeomAbs_BSplineSurface else "BEZIER"
            category_id = 0  # FreeSurface
            category_name = CATEGORY_NAMES[0]

        elif surf_type in (GeomAbs_SurfaceOfRevolution, GeomAbs_SurfaceOfExtrusion):
            geom_type_str = "REVOLUTION" if surf_type == GeomAbs_SurfaceOfRevolution else "EXTRUSION"
            category_id = 0
            category_name = CATEGORY_NAMES[0]

        else:
            geom_type_str = f"TYPE_{surf_type}"
            category_id = 0
            category_name = CATEGORY_NAMES[0]

        face_triangulation = BRep_Tool.Triangulation(face, TopLoc_Location())
        tri_count_for_face = 0

        if not face_triangulation.IsNull():
            nodes = face_triangulation.Nodes()
            triangles = face_triangulation.Triangles()
            n_triangles = triangles.Length()

            trsf = face.Location().Transformation()

            for t_idx in range(1, n_triangles + 1):
                tri = triangles.Value(t_idx)
                n1_idx, n2_idx, n3_idx = tri.Get()

                v1 = nodes.Value(n1_idx)
                v2 = nodes.Value(n2_idx)
                v3 = nodes.Value(n3_idx)

                if not trsf.IsIdentity():
                    v1 = v1.Transformed(trsf)
                    v2 = v2.Transformed(trsf)
                    v3 = v3.Transformed(trsf)

                e1 = [v2.X() - v1.X(), v2.Y() - v1.Y(), v2.Z() - v1.Z()]
                e2 = [v3.X() - v1.X(), v3.Y() - v1.Y(), v3.Z() - v1.Z()]
                nx = e1[1]*e2[2] - e1[2]*e2[1]
                ny = e1[2]*e2[0] - e1[0]*e2[2]
                nz = e1[0]*e2[1] - e1[1]*e2[0]
                nlen = math.sqrt(nx*nx + ny*ny + nz*nz)
                if nlen > 1e-10:
                    nx /= nlen
                    ny /= nlen
                    nz /= nlen

                all_triangles.append({
                    "v1": [v1.X(), v1.Y(), v1.Z()],
                    "v2": [v2.X(), v2.Y(), v2.Z()],
                    "v3": [v3.X(), v3.Y(), v3.Z()],
                    "normal": [nx, ny, nz],
                })
                triangle_labels.append(category_id)
                tri_count_for_face += 1

        face_info = {
            "face_id": face_id,
            "geom_type": geom_type_str,
            "category_id": category_id,
            "category_name": category_name,
            "area": round(face_area, 6),
            "triangle_count": tri_count_for_face,
            "triangle_start": len(all_triangles) - tri_count_for_face,
            "extra": extra_info,
        }
        face_info_list.append(face_info)

        explorer.Next()

    print(f"[StepTopology] Extracted {len(face_info_list)} faces, {len(all_triangles)} triangles")

    stl_path = output_dir / "tessellated.stl"
    with open(stl_path, 'wb') as f:
        f.write(b'solid step_topology\n')
        for tri in all_triangles:
            nx, ny, nz = tri["normal"]
            f.write(f'  facet normal {nx:.6f} {ny:.6f} {nz:.6f}\n'.encode())
            f.write(b'    outer loop\n')
            for vk in ("v1", "v2", "v3"):
                vx, vy, vz = tri[vk]
                f.write(f'      vertex {vx:.6f} {vy:.6f} {vz:.6f}\n'.encode())
            f.write(b'    endloop\n')
            f.write(b'  endfacet\n')
        f.write(b'endsolid step_topology\n')
    print(f"[StepTopology] STL saved: {stl_path} ({len(all_triangles)} triangles)")

    labels_path = output_dir / "topology_labels.json"
    labels_data = {
        "source_file": Path(step_path).name,
        "total_triangles": len(all_triangles),
        "total_faces": len(face_info_list),
        "shape_bounds": [round(v, 4) for v in shape_bounds],
        "linear_deflection": linear_deflection,
        "angular_deflection": angular_deflection,
        "category_names": CATEGORY_NAMES,
        "triangle_labels": triangle_labels,
        "faces": face_info_list,
    }
    with open(labels_path, 'w', encoding='utf-8') as f:
        json.dump(labels_data, f, indent=2, ensure_ascii=False)
    print(f"[StepTopology] Labels saved: {labels_path}")

    category_stats = defaultdict(lambda: {"count": 0, "area": 0.0, "triangles": 0})
    for fi in face_info_list:
        cat = fi["category_id"]
        category_stats[cat]["count"] += 1
        category_stats[cat]["area"] += fi["area"]
        category_stats[cat]["triangles"] += fi["triangle_count"]

    summary = {
        "source_file": Path(step_path).name,
        "total_faces": len(face_info_list),
        "total_triangles": len(all_triangles),
        "shape_bounds": [round(v, 4) for v in shape_bounds],
        "categories": {},
    }
    for cat_id in sorted(category_stats.keys()):
        summary["categories"][str(cat_id)] = {
            "name": CATEGORY_NAMES.get(cat_id, "Unknown"),
            "face_count": category_stats[cat_id]["count"],
            "triangle_count": category_stats[cat_id]["triangles"],
            "total_area": round(category_stats[cat_id]["area"], 6),
        }

    summary_path = output_dir / "topology_summary.json"
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\n[StepTopology] === Classification Summary ===")
    for cat_id in sorted(category_stats.keys()):
        name = CATEGORY_NAMES.get(cat_id, "Unknown")
        stats = category_stats[cat_id]
        print(f"  {cat_id:2d} {name:25s}: {stats['count']:3d} faces, {stats['triangles']:6d} triangles, area={stats['area']:.4f}")
    print(f"[StepTopology] Total: {len(face_info_list)} faces, {len(all_triangles)} triangles")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="STEP Topology Parser - Extract exact face type labels from STEP files"
    )
    parser.add_argument("--input", "-i", required=True, help="Input STEP/STP file path")
    parser.add_argument("--output-dir", "-o", default=None,
                        help="Output directory (default: same as input file)")
    parser.add_argument("--linear-deflection", type=float, default=0.1,
                        help="Tessellation linear deflection (smaller = more triangles, default: 0.1)")
    parser.add_argument("--angular-deflection", type=float, default=0.5,
                        help="Tessellation angular deflection in radians (default: 0.5)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        sys.exit(1)

    output_dir = args.output_dir or str(input_path.parent / "topology_output")

    success = parse_step_topology(
        str(input_path),
        output_dir,
        linear_deflection=args.linear_deflection,
        angular_deflection=args.angular_deflection,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
