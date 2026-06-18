"""
Huhb3D MCP Server - 3D网格质量检测服务器

通过 MCP (Model Context Protocol) 为 AI 代理提供 3D 模型分析能力。
专注于机器人/3D打印领域的网格质量检测，而非 CAD 建模。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np
import trimesh
from mcp.server.fastmcp import FastMCP

# RAG 引擎和推理代理延迟导入，避免未安装依赖时崩溃
logger = logging.getLogger(__name__)

# 初始化 MCP 服务器
mcp = FastMCP("huhb3d-analyzer")

# 常用3D打印机尺寸 (mm)
PRINTER_BEDS: dict[str, dict[str, float]] = {
    "fdm": {"x": 220.0, "y": 220.0, "z": 250.0},  # Ender 3 等常见FDM
    "sla": {"x": 130.0, "y": 80.0, "z": 150.0},    # Photon 等常见SLA
}

# 最小壁厚阈值 (mm)
MIN_WALL_THICKNESS: dict[str, float] = {
    "fdm": 0.8,
    "sla": 0.3,
}

# FDM最大悬垂角度 (度)
MAX_OVERHANG_ANGLE_FDM = 45.0


ALLOWED_EXTENSIONS = {".stl", ".obj", ".glb", ".gltf", ".ply", ".off"}


def _load_mesh(file_path: str) -> trimesh.Trimesh:
    """加载3D网格文件，支持 STL/OBJ/GLB/PLY/OFF 格式"""
    # 路径安全验证：解析为绝对路径并拒绝路径遍历
    path = Path(file_path).resolve()
    if ".." in Path(file_path).parts:
        raise ValueError(f"路径包含非法的 '..' 遍历组件: {file_path}")

    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    suffix = path.suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"不支持的文件格式: {suffix}，支持: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    # trimesh.load 会根据后缀自动选择加载器
    loaded = trimesh.load(str(path), force="mesh")

    # GLB/GLTF 可能返回 Scene，提取其中最大的网格
    if isinstance(loaded, trimesh.Scene):
        geometries = list(loaded.geometry.values())
        if not geometries:
            raise ValueError("GLB/GLTF 文件中未找到网格数据")
        # 取顶点数最多的网格作为主网格
        loaded = max(geometries, key=lambda g: len(g.vertices))

    if not isinstance(loaded, trimesh.Trimesh):
        raise ValueError("加载的结果不是三角网格(Trimesh)")

    return loaded


def _safe_float(value: Any) -> float | None:
    """安全转换为 float，失败返回 None"""
    try:
        result = float(value)
        if np.isfinite(result):
            return result
        return None
    except (TypeError, ValueError):
        return None


def _safe_list(arr: Any) -> list | None:
    """安全将 numpy 数组转为列表"""
    try:
        if arr is None:
            return None
        return [float(x) for x in arr]
    except (TypeError, ValueError):
        return None


def _analyze_watertight(mesh: trimesh.Trimesh) -> dict[str, Any]:
    """分析网格是否封闭（水密）"""
    return {
        "is_watertight": bool(mesh.is_watertight),
        "euler_number": int(mesh.euler_number),
    }


def _analyze_volume(mesh: trimesh.Trimesh) -> dict[str, Any]:
    """分析体积相关属性"""
    volume = _safe_float(mesh.volume) if mesh.is_watertight else None
    return {
        "volume": volume,
        "centroid": _safe_list(mesh.centroid) if volume is not None else None,
    }


def _analyze_surface_area(mesh: trimesh.Trimesh) -> dict[str, Any]:
    """分析表面积"""
    return {
        "surface_area": _safe_float(mesh.area),
    }


def _analyze_bounding_box(mesh: trimesh.Trimesh) -> dict[str, Any]:
    """分析包围盒"""
    bounds = mesh.bounds
    extents = mesh.extents
    return {
        "min_corner": _safe_list(bounds[0]),
        "max_corner": _safe_list(bounds[1]),
        "dimensions": {
            "x": _safe_float(extents[0]),
            "y": _safe_float(extents[1]),
            "z": _safe_float(extents[2]),
        },
        "diagonal": _safe_float(np.linalg.norm(extents)),
    }


def _analyze_euler_number(mesh: trimesh.Trimesh) -> dict[str, Any]:
    """分析欧拉数"""
    return {
        "euler_number": int(mesh.euler_number),
        "vertices": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
        "edges": int(len(mesh.edges_unique)),
    }


def _analyze_thickness(mesh: trimesh.Trimesh) -> dict[str, Any]:
    """分析壁厚分布（基于采样点估计）"""
    try:
        # 使用 trimesh 的厚度估计功能
        thickness_map = trimesh.proximity.thickness(mesh, samples=500)
        if thickness_map is not None and len(thickness_map) > 0:
            valid = thickness_map[np.isfinite(thickness_map)]
            if len(valid) > 0:
                return {
                    "min_thickness": _safe_float(np.min(valid)),
                    "max_thickness": _safe_float(np.max(valid)),
                    "mean_thickness": _safe_float(np.mean(valid)),
                    "median_thickness": _safe_float(np.median(valid)),
                    "samples": int(len(valid)),
                }
    except Exception as e:
        # 壁厚采样失败，回退到包围盒估计
        pass

    # 备选方案：用包围盒最小维度的一半做粗略估计
    min_extent = _safe_float(np.min(mesh.extents))
    return {
        "min_thickness": None,
        "approx_min_surface_distance": min_extent / 2.0 if min_extent else None,
        "note": "精确壁厚分析需要封闭网格；approx_min_surface_distance 基于包围盒最小维度的一半，并非实际壁厚",
    }


def _analyze_defects(mesh: trimesh.Trimesh) -> dict[str, Any]:
    """分析网格缺陷"""
    defects: dict[str, Any] = {}

    # 退化面（面积为0或接近0的三角形）
    face_areas = mesh.area_faces
    degenerate_mask = face_areas < 1e-10
    degenerate_count = int(np.sum(degenerate_mask))
    defects["degenerate_faces"] = {
        "count": degenerate_count,
        "has_defect": degenerate_count > 0,
    }

    # 非流形边（连接超过2个面的边）
    try:
        is_watertight = bool(mesh.is_watertight)
        # 使用 trimesh.graph.faces_to_edges 计算每条边被多少面引用
        from trimesh.graph import faces_to_edges
        edges_of_faces = faces_to_edges(mesh.faces, return_index=True)
        unique_edges, counts = np.unique(edges_of_faces[0], axis=0, return_counts=True)
        non_manifold_edge_count = int(np.sum(counts > 2))
        nm_detail = None
    except Exception as e:
        is_watertight = bool(mesh.is_watertight)
        non_manifold_edge_count = 0
        nm_detail = f"非流形边检测失败: {type(e).__name__}: {e}"
    defects["non_manifold_edges"] = {
        "has_defect": not is_watertight or non_manifold_edge_count > 0,
        "estimated_count": non_manifold_edge_count,
    }
    if nm_detail:
        defects["non_manifold_edges"]["detail"] = nm_detail

    # 重复面
    dup_detail = None
    try:
        # 对面排序后去重检测
        sorted_faces = np.sort(mesh.faces, axis=1)
        unique_faces = np.unique(sorted_faces, axis=0)
        duplicate_count = int(len(sorted_faces) - len(unique_faces))
    except Exception as e:
        duplicate_count = 0
        dup_detail = f"重复面检测异常: {type(e).__name__}"
    defects["duplicate_faces"] = {
        "count": duplicate_count,
        "has_defect": duplicate_count > 0,
    }
    if dup_detail:
        defects["duplicate_faces"]["detail"] = dup_detail

    # 法线一致性
    defects["normals_consistent"] = {
        "is_consistent": bool(mesh.is_winding_consistent),
    }

    # 断开组件
    comp_detail = None
    try:
        components = mesh.split(only_watertight=False)
        component_count = len(components)
    except Exception as e:
        component_count = 1
        comp_detail = f"断开组件检测异常: {type(e).__name__}"
    defects["disconnected_components"] = {
        "count": component_count,
        "has_defect": component_count > 1,
    }
    if comp_detail:
        defects["disconnected_components"]["detail"] = comp_detail

    return defects


# ──────────────────────────────────────────────
# MCP 工具定义
# ──────────────────────────────────────────────


@mcp.tool()
def analyze_mesh(file_path: str, analysis_types: list[str]) -> dict[str, Any]:
    """分析3D网格文件，支持多种分析类型。

    Args:
        file_path: 3D模型文件路径 (STL/OBJ/GLB)
        analysis_types: 分析类型列表，可选值:
            watertight, volume, surface_area, bounding_box,
            euler_number, thickness, defects

    Returns:
        包含各项分析结果的字典
    """
    mesh = _load_mesh(file_path)

    # 支持的分析类型及其处理函数
    analyzers: dict[str, Any] = {
        "watertight": _analyze_watertight,
        "volume": _analyze_volume,
        "surface_area": _analyze_surface_area,
        "bounding_box": _analyze_bounding_box,
        "euler_number": _analyze_euler_number,
        "thickness": _analyze_thickness,
        "defects": _analyze_defects,
    }

    valid_types = set(analyzers.keys())
    requested = set(analysis_types)
    unknown = requested - valid_types
    if unknown:
        return {
            "error": f"未知的分析类型: {unknown}，支持: {valid_types}",
            "file": file_path,
        }

    results: dict[str, Any] = {
        "file": file_path,
        "file_size_bytes": os.path.getsize(file_path),
        "vertices": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
    }

    for atype in analysis_types:
        try:
            results[atype] = analyzers[atype](mesh)
        except Exception as e:
            results[atype] = {"error": str(e)}

    return results


@mcp.tool()
def check_3d_printability(
    file_path: str, printer_type: str = "fdm"
) -> dict[str, Any]:
    """检查3D模型是否适合3D打印。

    Args:
        file_path: 3D模型文件路径 (STL/OBJ/GLB)
        printer_type: 打印机类型，"fdm" 或 "sla"

    Returns:
        各项检查的通过/失败结果及详情
    """
    if printer_type not in ("fdm", "sla"):
        return {"error": f"不支持的打印机类型: {printer_type}，可选: fdm, sla"}

    mesh = _load_mesh(file_path)
    bed = PRINTER_BEDS[printer_type]
    min_wall = MIN_WALL_THICKNESS[printer_type]

    checks: dict[str, Any] = {}

    # ── 通用检查：水密性 ──
    is_watertight = bool(mesh.is_watertight)
    checks["watertight"] = {
        "passed": is_watertight,
        "detail": "模型封闭，适合打印" if is_watertight else "模型不封闭，打印时可能产生孔洞或切片错误",
        "severity": "critical" if not is_watertight else "info",
    }

    # ── 通用检查：包围盒是否适配打印机 ──
    extents = mesh.extents
    fits_bed = (
        extents[0] <= bed["x"]
        and extents[1] <= bed["y"]
        and extents[2] <= bed["z"]
    )
    checks["fits_printer_bed"] = {
        "passed": bool(fits_bed),
        "detail": {
            "model_dimensions_mm": {
                "x": _safe_float(extents[0]),
                "y": _safe_float(extents[1]),
                "z": _safe_float(extents[2]),
            },
            "printer_bed_mm": bed,
        },
        "severity": "critical" if not fits_bed else "info",
    }

    # ── 通用检查：薄壁检测 ──
    min_extent = float(np.min(extents))
    has_thin_walls = min_extent < min_wall * 2  # 最小维度小于2倍最小壁厚
    checks["thin_walls"] = {
        "passed": not has_thin_walls,
        "min_dimension_mm": _safe_float(min_extent),
        "threshold_mm": min_wall,
        "detail": (
            f"最小维度 {min_extent:.2f}mm 大于阈值 {min_wall}mm"
            if not has_thin_walls
            else f"最小维度 {min_extent:.2f}mm 可能存在薄壁问题（阈值 {min_wall}mm）"
        ),
        "severity": "warning" if has_thin_walls else "info",
    }

    # ── FDM 专用检查 ──
    if printer_type == "fdm":
        # 悬垂角度检测
        overhang_result = _check_overhangs(mesh)
        checks["overhangs"] = overhang_result

        # 法线方向一致性
        winding_ok = bool(mesh.is_winding_consistent)
        checks["normals_consistent"] = {
            "passed": winding_ok,
            "detail": "面法线方向一致" if winding_ok else "面法线方向不一致，可能导致切片异常",
            "severity": "warning" if not winding_ok else "info",
        }

    # ── SLA 专用检查 ──
    if printer_type == "sla":
        # 封闭体积检测（可能困住树脂）
        trapped = _check_trapped_volumes(mesh)
        checks["trapped_volumes"] = trapped

    # ── 汇总 ──
    all_passed = all(
        c.get("passed", True) for c in checks.values() if isinstance(c, dict)
    )
    critical_count = sum(
        1 for c in checks.values() if isinstance(c, dict) and c.get("severity") == "critical"
    )
    warning_count = sum(
        1 for c in checks.values() if isinstance(c, dict) and c.get("severity") == "warning"
    )

    return {
        "file": file_path,
        "printer_type": printer_type,
        "overall_result": "PASS" if all_passed else "FAIL",
        "critical_issues": critical_count,
        "warnings": warning_count,
        "checks": checks,
    }


def _check_overhangs(mesh: trimesh.Trimesh) -> dict[str, Any]:
    """检测FDM打印的悬垂角度"""
    try:
        face_normals = mesh.face_normals
        # Z轴负方向表示面朝下（悬垂面）
        # cos(45°) ≈ 0.707，法线Z分量小于 -cos(45°) 表示悬垂超过45度
        z_components = face_normals[:, 2]
        overhang_threshold = -np.cos(np.radians(MAX_OVERHANG_ANGLE_FDM))
        overhang_mask = z_components < overhang_threshold
        overhang_count = int(np.sum(overhang_mask))

        # 计算悬垂面的面积
        face_areas = mesh.area_faces
        overhang_area = float(np.sum(face_areas[overhang_mask]))

        return {
            "passed": overhang_count == 0,
            "overhang_face_count": overhang_count,
            "overhang_area_mm2": _safe_float(overhang_area),
            "max_angle_deg": MAX_OVERHANG_ANGLE_FDM,
            "detail": (
                "未检测到超过45度的悬垂面"
                if overhang_count == 0
                else f"检测到 {overhang_count} 个悬垂面（面积 {overhang_area:.1f}mm²），需要支撑结构"
            ),
            "severity": "warning" if overhang_count > 0 else "info",
        }
    except Exception as e:
        return {
            "passed": None,
            "detail": f"悬垂分析失败: {e}",
            "severity": "warning",
        }


def _check_trapped_volumes(mesh: trimesh.Trimesh) -> dict[str, Any]:
    """检测SLA打印中可能困住树脂的封闭体积"""
    try:
        if not mesh.is_watertight:
            return {
                "passed": None,
                "detail": "网格不封闭，无法检测封闭内腔",
                "severity": "warning",
            }

        # 检查是否存在内部封闭体积
        # 方法：用凸包体积与实际体积比较，如果实际体积远小于凸包体积，
        # 可能存在内部空腔
        convex_hull = mesh.convex_hull
        hull_volume = float(convex_hull.volume)
        mesh_volume = float(mesh.volume)

        if hull_volume > 0:
            volume_ratio = mesh_volume / hull_volume
            # 如果体积比很低，说明模型内部可能有大量空腔
            has_trapped = volume_ratio < 0.3
        else:
            has_trapped = False
            volume_ratio = 1.0

        return {
            "passed": not has_trapped,
            "volume_ratio": _safe_float(volume_ratio),
            "mesh_volume_mm3": _safe_float(mesh_volume),
            "convex_hull_volume_mm3": _safe_float(hull_volume),
            "detail": (
                "未检测到明显的封闭内腔"
                if not has_trapped
                else f"体积比 {volume_ratio:.2f} 较低，可能存在封闭内腔（会困住树脂）"
            ),
            "severity": "warning" if has_trapped else "info",
        }
    except Exception as e:
        return {
            "passed": None,
            "detail": f"封闭体积检测失败: {e}",
            "severity": "warning",
        }


@mcp.tool()
def compute_geometry(file_path: str, metrics: list[str]) -> dict[str, Any]:
    """计算3D网格的几何度量。

    Args:
        file_path: 3D模型文件路径 (STL/OBJ/GLB)
        metrics: 要计算的度量列表，可选值:
            volume, surface_area, centroid, moment_of_inertia,
            principal_axes, convex_hull_volume, compactness

    Returns:
        各项几何度量的计算结果
    """
    mesh = _load_mesh(file_path)

    valid_metrics = {
        "volume",
        "surface_area",
        "centroid",
        "moment_of_inertia",
        "principal_axes",
        "convex_hull_volume",
        "compactness",
    }
    requested = set(metrics)
    unknown = requested - valid_metrics
    if unknown:
        return {
            "error": f"未知的度量类型: {unknown}，支持: {valid_metrics}",
            "file": file_path,
        }

    results: dict[str, Any] = {"file": file_path}

    for metric in metrics:
        try:
            if metric == "volume":
                if mesh.is_watertight:
                    results["volume"] = {
                        "value_mm3": _safe_float(mesh.volume),
                        "value_cm3": _safe_float(mesh.volume / 1000.0),
                    }
                else:
                    results["volume"] = {
                        "value_mm3": None,
                        "note": "网格不封闭，无法计算体积",
                    }

            elif metric == "surface_area":
                results["surface_area"] = {
                    "value_mm2": _safe_float(mesh.area),
                    "value_cm2": _safe_float(mesh.area / 100.0),
                }

            elif metric == "centroid":
                results["centroid"] = {
                    "coordinates": _safe_list(mesh.centroid),
                    "note": "质心坐标 (x, y, z)，单位 mm",
                }

            elif metric == "moment_of_inertia":
                if mesh.is_watertight:
                    moi = mesh.moment_inertia
                    results["moment_of_inertia"] = {
                        "matrix": moi.tolist() if moi is not None else None,
                        "note": "3x3 惯性张量矩阵，单位 mm^5",
                    }
                else:
                    results["moment_of_inertia"] = {
                        "matrix": None,
                        "note": "网格不封闭，无法计算惯性张量",
                    }

            elif metric == "principal_axes":
                if mesh.is_watertight:
                    try:
                        moi = mesh.moment_inertia
                        if moi is not None:
                            eigenvalues, eigenvectors = np.linalg.eigh(moi)
                            results["principal_axes"] = {
                                "eigenvalues": _safe_list(eigenvalues),
                                "eigenvectors": [
                                    _safe_list(v) for v in eigenvectors.T
                                ],
                                "note": "主轴方向及对应惯性矩",
                            }
                        else:
                            results["principal_axes"] = None
                    except Exception as e:
                        results["principal_axes"] = {"error": f"主轴计算失败: {type(e).__name__}: {e}"}
                else:
                    results["principal_axes"] = {
                        "note": "网格不封闭，无法计算主轴",
                    }

            elif metric == "convex_hull_volume":
                try:
                    hull = mesh.convex_hull
                    hull_vol = float(hull.volume) if hull.is_watertight else None
                    results["convex_hull_volume"] = {
                        "value_mm3": _safe_float(hull_vol),
                    }
                except Exception as e:
                    results["convex_hull_volume"] = {"error": str(e)}

            elif metric == "compactness":
                # 紧凑度 = 体积 / 凸包体积，衡量模型与凸包的接近程度
                try:
                    if mesh.is_watertight:
                        mesh_vol = float(mesh.volume)
                        hull = mesh.convex_hull
                        if hull.is_watertight:
                            hull_vol = float(hull.volume)
                            ratio = min(1.0, mesh_vol / hull_vol) if hull_vol > 0 else 0.0
                        else:
                            ratio = None
                        results["compactness"] = {
                            "ratio": _safe_float(ratio),
                            "note": "1.0 表示完全凸，越小越凹",
                        }
                    else:
                        results["compactness"] = {
                            "ratio": None,
                            "note": "网格不封闭，无法计算紧凑度",
                        }
                except Exception as e:
                    results["compactness"] = {"error": str(e)}

        except Exception as e:
            results[metric] = {"error": str(e)}

    return results


@mcp.tool()
def detect_defects(file_path: str) -> dict[str, Any]:
    """检测3D网格中的缺陷，返回缺陷列表及严重程度。

    Args:
        file_path: 3D模型文件路径 (STL/OBJ/GLB)

    Returns:
        缺陷列表，每项包含类型、严重程度和位置信息
    """
    mesh = _load_mesh(file_path)

    defects: list[dict[str, Any]] = []

    # ── 非流形边检测 ──
    try:
        if not mesh.is_watertight:
            # 使用 trimesh.graph.faces_to_edges 计算每条边被多少面引用
            from trimesh.graph import faces_to_edges
            edges_of_faces = faces_to_edges(mesh.faces, return_index=True)
            unique_edges, counts = np.unique(edges_of_faces[0], axis=0, return_counts=True)
            non_manifold_mask = counts > 2
            nm_count = int(np.sum(non_manifold_mask))
            if nm_count > 0:
                nm_edges = unique_edges[non_manifold_mask]
                # 取前5个非流形边的顶点坐标作为位置参考
                sample_vertices = mesh.vertices[nm_edges[:5].flatten()]
                defects.append({
                    "type": "non_manifold_edges",
                    "severity": "critical",
                    "count": nm_count,
                    "description": f"检测到 {nm_count} 条非流形边（连接超过2个面）",
                    "sample_locations": [_safe_list(v) for v in sample_vertices[:5]],
                })
    except Exception as e:
        defects.append({
            "type": "non_manifold_edges",
            "severity": "warning",
            "description": f"非流形边检测失败: {type(e).__name__}: {e}",
        })

    # ── 退化面检测 ──
    try:
        face_areas = mesh.area_faces
        degenerate_mask = face_areas < 1e-10
        deg_count = int(np.sum(degenerate_mask))
        if deg_count > 0:
            deg_face_indices = np.where(degenerate_mask)[0][:5]
            sample_locations = []
            for idx in deg_face_indices:
                verts = mesh.vertices[mesh.faces[idx]]
                center = np.mean(verts, axis=0)
                sample_locations.append(_safe_list(center))
            defects.append({
                "type": "degenerate_faces",
                "severity": "critical",
                "count": deg_count,
                "description": f"检测到 {deg_count} 个退化面（面积接近零）",
                "sample_locations": sample_locations,
            })
    except Exception as e:
        defects.append({
            "type": "degenerate_faces",
            "severity": "warning",
            "description": f"退化面检测失败: {type(e).__name__}: {e}",
        })

    # ── 重复面检测 ──
    try:
        sorted_faces = np.sort(mesh.faces, axis=1)
        _, unique_idx, counts = np.unique(
            sorted_faces, axis=0, return_index=True, return_counts=True
        )
        dup_mask = counts > 1
        dup_count = int(np.sum(counts[dup_mask]) - np.sum(dup_mask))
        if dup_count > 0:
            defects.append({
                "type": "duplicate_faces",
                "severity": "warning",
                "count": dup_count,
                "description": f"检测到 {dup_count} 个重复面",
            })
    except Exception as e:
        defects.append({
            "type": "duplicate_faces",
            "severity": "warning",
            "description": f"重复面检测失败: {type(e).__name__}: {e}",
        })

    # ── 法线翻转检测 ──
    try:
        if not mesh.is_winding_consistent:
            defects.append({
                "type": "flipped_normals",
                "severity": "warning",
                "description": "面法线方向不一致，部分面可能朝内",
            })
    except Exception as e:
        defects.append({
            "type": "flipped_normals",
            "severity": "warning",
            "description": f"法线一致性检测失败: {type(e).__name__}: {e}",
        })

    # ── 断开组件检测 ──
    try:
        components = mesh.split(only_watertight=False)
        comp_count = len(components)
        if comp_count > 1:
            comp_sizes = [
                {"vertices": int(len(c.vertices)), "faces": int(len(c.faces))}
                for c in components
            ]
            defects.append({
                "type": "disconnected_components",
                "severity": "warning",
                "count": comp_count,
                "description": f"模型包含 {comp_count} 个断开的组件",
                "component_sizes": comp_sizes,
            })
    except Exception as e:
        defects.append({
            "type": "disconnected_components",
            "severity": "warning",
            "description": f"断开组件检测失败: {type(e).__name__}: {e}",
        })

    # ── 薄壁检测 ──
    try:
        min_extent = float(np.min(mesh.extents))
        if min_extent < 2.0:  # 2mm 以下视为薄壁
            defects.append({
                "type": "thin_walls",
                "severity": "warning",
                "min_dimension_mm": _safe_float(min_extent),
                "description": f"模型最小维度为 {min_extent:.2f}mm，可能存在薄壁问题",
            })
    except Exception as e:
        defects.append({
            "type": "thin_walls",
            "severity": "warning",
            "description": f"薄壁检测失败: {type(e).__name__}: {e}",
        })

    # ── 自相交检测 ──
    try:
        # 优先使用 trimesh 内置的 is_self_intersecting 属性
        if hasattr(mesh, "is_self_intersecting"):
            is_si = bool(mesh.is_self_intersecting)
        else:
            # 尝试使用 trimesh.self_intersections
            try:
                si_result = trimesh.self_intersections(mesh)
                is_si = len(si_result) > 0 if si_result is not None else False
            except (AttributeError, NotImplementedError):
                is_si = None  # 不可用时标记为 None 而非返回错误结果

        if is_si is True:
            defects.append({
                "type": "self_intersections",
                "severity": "critical",
                "description": "模型存在自相交（面之间互相穿透）",
            })
        elif is_si is None:
            defects.append({
                "type": "self_intersections",
                "severity": "info",
                "description": "自相交检测不可用（当前 trimesh 版本不支持）",
            })
    except Exception as e:
        defects.append({
            "type": "self_intersections",
            "severity": "warning",
            "description": f"自相交检测失败: {type(e).__name__}: {e}",
        })

    # ── 汇总 ──
    critical_count = sum(1 for d in defects if d.get("severity") == "critical")
    warning_count = sum(1 for d in defects if d.get("severity") == "warning")
    info_count = sum(1 for d in defects if d.get("severity") == "info")

    return {
        "file": file_path,
        "total_defects": len(defects),
        "critical": critical_count,
        "warning": warning_count,
        "info": info_count,
        "overall_status": (
            "CRITICAL" if critical_count > 0 else
            "WARNING" if warning_count > 0 else
            "OK"
        ),
        "defects": defects,
    }


@mcp.tool()
def compare_meshes(file_path_a: str, file_path_b: str) -> dict[str, Any]:
    """比较两个3D网格文件的差异。

    Args:
        file_path_a: 第一个3D模型文件路径
        file_path_b: 第二个3D模型文件路径

    Returns:
        两个网格之间的比较指标
    """
    mesh_a = _load_mesh(file_path_a)
    mesh_b = _load_mesh(file_path_b)

    results: dict[str, Any] = {
        "file_a": file_path_a,
        "file_b": file_path_b,
    }

    # ── 顶点/面数对比 ──
    results["topology"] = {
        "vertices_a": int(len(mesh_a.vertices)),
        "vertices_b": int(len(mesh_b.vertices)),
        "vertices_diff": int(len(mesh_a.vertices) - len(mesh_b.vertices)),
        "faces_a": int(len(mesh_a.faces)),
        "faces_b": int(len(mesh_b.faces)),
        "faces_diff": int(len(mesh_a.faces) - len(mesh_b.faces)),
    }

    # ── 体积对比 ──
    vol_a = float(mesh_a.volume) if mesh_a.is_watertight else None
    vol_b = float(mesh_b.volume) if mesh_b.is_watertight else None
    if vol_a is not None and vol_b is not None:
        vol_diff = vol_a - vol_b
        vol_pct = (vol_diff / vol_a * 100.0) if vol_a != 0 else 0.0
        results["volume"] = {
            "a_mm3": _safe_float(vol_a),
            "b_mm3": _safe_float(vol_b),
            "difference_mm3": _safe_float(vol_diff),
            "difference_percent": _safe_float(vol_pct),
        }
    else:
        results["volume"] = {
            "a_mm3": _safe_float(vol_a),
            "b_mm3": _safe_float(vol_b),
            "note": "至少一个网格不封闭，体积差值无法计算",
        }

    # ── 表面积对比 ──
    area_a = float(mesh_a.area)
    area_b = float(mesh_b.area)
    area_diff = area_a - area_b
    area_pct = (area_diff / area_a * 100.0) if area_a != 0 else 0.0
    results["surface_area"] = {
        "a_mm2": _safe_float(area_a),
        "b_mm2": _safe_float(area_b),
        "difference_mm2": _safe_float(area_diff),
        "difference_percent": _safe_float(area_pct),
    }

    # ── 包围盒对比 ──
    ext_a = mesh_a.extents
    ext_b = mesh_b.extents
    results["bounding_box"] = {
        "a_dimensions": {
            "x": _safe_float(ext_a[0]),
            "y": _safe_float(ext_a[1]),
            "z": _safe_float(ext_a[2]),
        },
        "b_dimensions": {
            "x": _safe_float(ext_b[0]),
            "y": _safe_float(ext_b[1]),
            "z": _safe_float(ext_b[2]),
        },
        "dimension_diff": {
            "x": _safe_float(ext_a[0] - ext_b[0]),
            "y": _safe_float(ext_a[1] - ext_b[1]),
            "z": _safe_float(ext_a[2] - ext_b[2]),
        },
    }

    # ── Hausdorff 距离 ──
    try:
        # 对两个网格采样点计算近似 Hausdorff 距离
        n_samples = min(5000, len(mesh_a.vertices), len(mesh_b.vertices))
        points_a = mesh_a.vertices[
            np.random.choice(len(mesh_a.vertices), n_samples, replace=False)
        ]
        points_b = mesh_b.vertices[
            np.random.choice(len(mesh_b.vertices), n_samples, replace=False)
        ]

        # A→B 方向最近距离
        from scipy.spatial import cKDTree  # type: ignore

        tree_b = cKDTree(points_b)
        dist_a_to_b, _ = tree_b.query(points_a)

        # B→A 方向最近距离
        tree_a = cKDTree(points_a)
        dist_b_to_a, _ = tree_a.query(points_b)

        hausdorff = max(float(np.max(dist_a_to_b)), float(np.max(dist_b_to_a)))
        mean_dist = float(np.mean(np.concatenate([dist_a_to_b, dist_b_to_a])))

        results["hausdorff_distance"] = {
            "max_mm": _safe_float(hausdorff),
            "mean_mm": _safe_float(mean_dist),
            "samples": n_samples,
            "note": "基于采样的近似Hausdorff距离",
        }
    except ImportError:
        # scipy 不可用时，用简化方法
        results["hausdorff_distance"] = {
            "note": "需要 scipy 来计算 Hausdorff 距离",
        }
    except Exception as e:
        results["hausdorff_distance"] = {"error": str(e)}

    # ── 重叠检测 ──
    try:
        # 简化重叠检测：检查包围盒是否重叠
        bounds_a = mesh_a.bounds
        bounds_b = mesh_b.bounds
        overlap_x = max(0, min(bounds_a[1][0], bounds_b[1][0]) - max(bounds_a[0][0], bounds_b[0][0]))
        overlap_y = max(0, min(bounds_a[1][1], bounds_b[1][1]) - max(bounds_a[0][1], bounds_b[0][1]))
        overlap_z = max(0, min(bounds_a[1][2], bounds_b[1][2]) - max(bounds_a[0][2], bounds_b[0][2]))
        has_overlap = overlap_x > 0 and overlap_y > 0 and overlap_z > 0

        results["overlap"] = {
            "bounding_boxes_overlap": bool(has_overlap),
            "overlap_dimensions_mm": {
                "x": _safe_float(overlap_x),
                "y": _safe_float(overlap_y),
                "z": _safe_float(overlap_z),
            },
            "note": "基于包围盒的简化重叠检测",
        }
    except Exception as e:
        results["overlap"] = {"error": str(e)}

    return results


@mcp.tool()
def generate_report(
    file_path: str, report_type: str = "summary"
) -> dict[str, Any]:
    """生成3D网格的综合分析报告。

    Args:
        file_path: 3D模型文件路径 (STL/OBJ/GLB)
        report_type: 报告类型，"summary" 或 "detailed"

    Returns:
        格式化的分析报告
    """
    if report_type not in ("summary", "detailed"):
        return {"error": f"不支持的报告类型: {report_type}，可选: summary, detailed"}

    mesh = _load_mesh(file_path)
    path = Path(file_path)

    # 收集所有分析数据
    watertight_info = _analyze_watertight(mesh)
    volume_info = _analyze_volume(mesh)
    area_info = _analyze_surface_area(mesh)
    bbox_info = _analyze_bounding_box(mesh)
    euler_info = _analyze_euler_number(mesh)
    defect_info = _analyze_defects(mesh)

    # 构建报告
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("  Huhb3D 网格质量检测报告")
    lines.append("=" * 60)
    lines.append("")

    # 基本信息
    lines.append("【基本信息】")
    lines.append(f"  文件: {path.name}")
    lines.append(f"  路径: {file_path}")
    lines.append(f"  文件大小: {os.path.getsize(file_path):,} 字节")
    lines.append(f"  顶点数: {euler_info['vertices']:,}")
    lines.append(f"  面数: {euler_info['faces']:,}")
    lines.append(f"  边数: {euler_info['edges']:,}")
    lines.append("")

    # 水密性
    lines.append("【水密性检测】")
    wt = watertight_info["is_watertight"]
    lines.append(f"  是否封闭: {'✓ 是' if wt else '✗ 否'}")
    lines.append(f"  欧拉数: {watertight_info['euler_number']}")
    lines.append("")

    # 体积与表面积
    lines.append("【几何属性】")
    vol = volume_info.get("volume")
    if vol is not None:
        lines.append(f"  体积: {vol:.4f} mm³ ({vol / 1000.0:.4f} cm³)")
    else:
        lines.append("  体积: 无法计算（网格不封闭）")

    sa = area_info["surface_area"]
    if sa is not None:
        lines.append(f"  表面积: {sa:.4f} mm² ({sa / 100.0:.4f} cm²)")

    centroid = volume_info.get("centroid")
    if centroid:
        lines.append(f"  质心: ({centroid[0]:.2f}, {centroid[1]:.2f}, {centroid[2]:.2f}) mm")
    lines.append("")

    # 包围盒
    lines.append("【包围盒】")
    dims = bbox_info["dimensions"]
    lines.append(f"  尺寸: {dims['x']:.2f} × {dims['y']:.2f} × {dims['z']:.2f} mm")
    lines.append(f"  对角线: {bbox_info['diagonal']:.2f} mm")
    if report_type == "detailed":
        lines.append(f"  最小角: ({bbox_info['min_corner'][0]:.2f}, {bbox_info['min_corner'][1]:.2f}, {bbox_info['min_corner'][2]:.2f})")
        lines.append(f"  最大角: ({bbox_info['max_corner'][0]:.2f}, {bbox_info['max_corner'][1]:.2f}, {bbox_info['max_corner'][2]:.2f})")
    lines.append("")

    # 缺陷
    lines.append("【缺陷检测】")
    deg = defect_info["degenerate_faces"]
    nm = defect_info["non_manifold_edges"]
    dup = defect_info["duplicate_faces"]
    normals = defect_info["normals_consistent"]
    comp = defect_info["disconnected_components"]

    lines.append(f"  退化面: {'✗ ' + str(deg['count']) + ' 个' if deg['has_defect'] else '✓ 无'}")
    lines.append(f"  非流形边: {'✗ 存在' if nm['has_defect'] else '✓ 无'}")
    lines.append(f"  重复面: {'✗ ' + str(dup['count']) + ' 个' if dup['has_defect'] else '✓ 无'}")
    lines.append(f"  法线一致性: {'✓ 一致' if normals['is_consistent'] else '✗ 不一致'}")
    lines.append(f"  断开组件: {'✗ ' + str(comp['count']) + ' 个' if comp['has_defect'] else '✓ 单一组件'}")
    lines.append("")

    # 3D打印适用性（简要）
    lines.append("【3D打印适用性】")
    fdm_ok = wt and not deg["has_defect"]
    sla_ok = wt and not deg["has_defect"]
    lines.append(f"  FDM打印: {'✓ 适合' if fdm_ok else '✗ 需修复后打印'}")
    lines.append(f"  SLA打印: {'✓ 适合' if sla_ok else '✗ 需修复后打印'}")
    lines.append("")

    # 详细报告额外内容
    if report_type == "detailed":
        lines.append("【详细几何分析】")
        lines.append(f"  欧拉数: {euler_info['euler_number']}")
        lines.append(f"  欧拉公式验证: V - E + F = {euler_info['vertices']} - {euler_info['edges']} + {euler_info['faces']} = {euler_info['vertices'] - euler_info['edges'] + euler_info['faces']}")

        # 紧凑度
        try:
            if mesh.is_watertight:
                mesh_vol = float(mesh.volume)
                hull = mesh.convex_hull
                if hull.is_watertight:
                    hull_vol = float(hull.volume)
                    compactness = mesh_vol / hull_vol if hull_vol > 0 else 0
                    lines.append(f"  紧凑度: {compactness:.4f} (1.0=完全凸)")
        except Exception as e:
            lines.append(f"  紧凑度: 计算失败 ({type(e).__name__})")

        # 壁厚
        try:
            thickness_info = _analyze_thickness(mesh)
            if thickness_info.get("min_thickness") is not None:
                lines.append(f"  最小壁厚: {thickness_info['min_thickness']:.4f} mm")
                lines.append(f"  平均壁厚: {thickness_info['mean_thickness']:.4f} mm")
            elif thickness_info.get("approx_min_surface_distance") is not None:
                lines.append(f"  近似最小表面距离: {thickness_info['approx_min_surface_distance']:.4f} mm (非实际壁厚)")
        except Exception as e:
            lines.append(f"  壁厚分析: 失败 ({type(e).__name__})")

        lines.append("")

    # 总结
    lines.append("【总结】")
    issues = []
    if not wt:
        issues.append("网格不封闭")
    if deg["has_defect"]:
        issues.append(f"存在 {deg['count']} 个退化面")
    if nm["has_defect"]:
        issues.append("存在非流形边")
    if dup["has_defect"]:
        issues.append(f"存在 {dup['count']} 个重复面")
    if not normals["is_consistent"]:
        issues.append("法线方向不一致")
    if comp["has_defect"]:
        issues.append(f"存在 {comp['count']} 个断开组件")

    if issues:
        lines.append("  发现以下问题:")
        for issue in issues:
            lines.append(f"    - {issue}")
        lines.append("  建议: 修复上述问题后再进行3D打印或进一步分析")
    else:
        lines.append("  网格质量良好，未检测到明显缺陷")
    lines.append("")
    lines.append("=" * 60)

    report_text = "\n".join(lines)

    return {
        "file": file_path,
        "report_type": report_type,
        "report": report_text,
        "summary": {
            "is_watertight": wt,
            "defect_count": len(issues),
            "print_ready": len(issues) == 0,
            "issues": issues,
        },
    }


@mcp.tool()
def smart_analyze(file_path: str, question: str) -> dict[str, Any]:
    """AI-powered intelligent 3D model analysis. Ask any question about your 3D model.

    Args:
        file_path: 3D model file path (STL/OBJ/GLB/PLY/OFF)
        question: Natural language question about the model

    Returns:
        AI-generated analysis with supporting data and knowledge sources
    """
    # ── 第一步：运行基础网格分析 ──
    mesh = _load_mesh(file_path)
    analysis_data: dict[str, Any] = {
        "file": file_path,
        "vertices": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
    }

    # 收集全面的分析数据
    analysis_data["watertight"] = _analyze_watertight(mesh)
    analysis_data["volume"] = _analyze_volume(mesh)
    analysis_data["surface_area"] = _analyze_surface_area(mesh)
    analysis_data["bounding_box"] = _analyze_bounding_box(mesh)
    analysis_data["defects"] = _analyze_defects(mesh)

    # 3D打印适用性
    try:
        fdm_result = check_3d_printability(file_path, "fdm")
        analysis_data["fdm_printability"] = fdm_result
    except Exception as e:
        analysis_data["fdm_printability"] = {"error": str(e)}

    # ── 第二步：使用 RAG 引擎检索相关知识 ──
    rag_context = ""
    knowledge_sources: list[dict[str, Any]] = []
    try:
        from mcp_server.rag_engine import create_geometry_rag_engine
        rag_engine = create_geometry_rag_engine(similarity_threshold=0.3, top_k=5)
        rag_result = rag_engine.query_with_context(question, top_k=5, max_context_length=2000)
        rag_context = rag_result.get("context", "")
        knowledge_sources = rag_result.get("sources", [])
    except Exception as e:
        logger.warning(f"RAG 检索失败: {e}")
        rag_context = ""

    # ── 第三步：尝试调用 LLM 生成智能分析 ──
    api_key = os.environ.get("HUHB3D_LLM_API_KEY", "")
    base_url = os.environ.get("HUHB3D_LLM_BASE_URL", "https://api.openai.com/v1")
    model_name = os.environ.get("HUHB3D_LLM_MODEL", "gpt-4o-mini")

    if api_key:
        answer = _call_llm_for_analysis(question, analysis_data, rag_context, api_key, base_url, model_name)
    else:
        # 无 API Key 时回退到规则分析
        answer = _rule_based_analysis(question, analysis_data)

    return {
        "answer": answer,
        "supporting_data": {
            "vertices": analysis_data["vertices"],
            "faces": analysis_data["faces"],
            "is_watertight": analysis_data["watertight"]["is_watertight"],
            "volume": analysis_data["volume"].get("volume"),
            "surface_area": analysis_data["surface_area"].get("surface_area"),
            "dimensions": analysis_data["bounding_box"]["dimensions"],
            "defects_summary": {
                "degenerate_faces": analysis_data["defects"]["degenerate_faces"]["has_defect"],
                "non_manifold_edges": analysis_data["defects"]["non_manifold_edges"]["has_defect"],
                "normals_consistent": analysis_data["defects"]["normals_consistent"]["is_consistent"],
            },
            "fdm_printability": analysis_data.get("fdm_printability", {}).get("overall_result"),
        },
        "knowledge_sources": knowledge_sources,
    }


def _call_llm_for_analysis(
    question: str,
    analysis_data: dict[str, Any],
    rag_context: str,
    api_key: str,
    base_url: str,
    model: str,
) -> str:
    """调用 LLM API 生成智能分析

    使用 OpenAI 兼容的 API 接口
    """
    try:
        import urllib.request
        import urllib.error

        # 构造提示词
        system_prompt = (
            "你是一个专业的3D几何分析专家，专注于网格质量检测和3D打印适用性评估。"
            "请根据提供的网格分析数据和知识库内容，回答用户的问题。"
            "回答要具体、有数据支撑，并在适当的地方引用具体数值。"
        )

        user_prompt = f"""## 用户问题
{question}

## 网格分析数据
```json
{json.dumps(analysis_data, ensure_ascii=False, indent=2, default=str)}
```

## 相关知识库内容
{rag_context if rag_context else "（未检索到相关知识）"}

请基于以上数据回答用户的问题。"""

        # 构造 API 请求
        request_body = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 1500,
        }, ensure_ascii=False).encode("utf-8")

        url = f"{base_url.rstrip('/')}/chat/completions"
        req = urllib.request.Request(
            url,
            data=request_body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"]

    except Exception as e:
        logger.warning(f"LLM 调用失败: {e}，回退到规则分析")
        return _rule_based_analysis(question, analysis_data)


def _rule_based_analysis(question: str, analysis_data: dict[str, Any]) -> str:
    """基于规则的分析回退方案（无 LLM API 时使用）"""
    q_lower = question.lower()

    # 提取关键信息
    is_watertight = analysis_data["watertight"]["is_watertight"]
    volume = analysis_data["volume"].get("volume")
    surface_area = analysis_data["surface_area"].get("surface_area")
    dims = analysis_data["bounding_box"]["dimensions"]
    defects = analysis_data["defects"]

    lines: list[str] = []

    # 判断问题类型并生成针对性回答
    if any(kw in q_lower for kw in ["print", "打印", "fdm", "sla", "制造", "fabricat"]):
        lines.append("## 3D打印适用性分析\n")
        if is_watertight:
            lines.append("✅ 模型封闭（水密），满足3D打印的基本要求。")
        else:
            lines.append("❌ 模型不封闭（非水密），切片器可能无法正确处理，建议修复后再打印。")

        if volume is not None:
            lines.append(f"\n体积: {volume:.2f} mm³ ({volume/1000:.4f} cm³)")

        # FDM 相关
        min_dim = min(dims["x"], dims["y"], dims["z"])
        if min_dim and min_dim < 0.8:
            lines.append(f"\n⚠️ 最小维度 {min_dim:.2f}mm 低于 FDM 最小壁厚 0.8mm，薄壁区域可能无法打印。")
        elif min_dim:
            lines.append(f"\n✅ 最小维度 {min_dim:.2f}mm，满足 FDM 最小壁厚要求。")

        # 悬垂检查
        fdm_data = analysis_data.get("fdm_printability", {})
        overhang = fdm_data.get("checks", {}).get("overhangs", {})
        if overhang.get("overhang_face_count", 0) > 0:
            lines.append(f"\n⚠️ 检测到 {overhang['overhang_face_count']} 个悬垂面，需要添加支撑结构。")

    elif any(kw in q_lower for kw in ["defect", "缺陷", "问题", "error", "quality", "质量"]):
        lines.append("## 网格缺陷分析\n")
        deg = defects["degenerate_faces"]
        nm = defects["non_manifold_edges"]
        normals = defects["normals_consistent"]
        dup = defects["duplicate_faces"]
        comp = defects["disconnected_components"]

        issues = []
        if not is_watertight:
            issues.append("❌ 网格不封闭（非水密）")
        if deg["has_defect"]:
            issues.append(f"❌ 存在 {deg['count']} 个退化面")
        if nm["has_defect"]:
            issues.append("❌ 存在非流形边")
        if not normals["is_consistent"]:
            issues.append("⚠️ 面法线方向不一致")
        if dup["has_defect"]:
            issues.append(f"⚠️ 存在 {dup['count']} 个重复面")
        if comp["has_defect"]:
            issues.append(f"⚠️ 存在 {comp['count']} 个断开组件")

        if issues:
            lines.append("发现以下问题:")
            for issue in issues:
                lines.append(f"  {issue}")
        else:
            lines.append("✅ 未检测到明显缺陷，网格质量良好。")

    elif any(kw in q_lower for kw in ["volume", "体积", "size", "尺寸", "dimension"]):
        lines.append("## 尺寸与体积分析\n")
        if volume is not None:
            lines.append(f"体积: {volume:.2f} mm³ ({volume/1000:.4f} cm³)")
        else:
            lines.append("体积: 无法计算（网格不封闭）")
        if surface_area is not None:
            lines.append(f"表面积: {surface_area:.2f} mm² ({surface_area/100:.4f} cm²)")
        lines.append(f"包围盒尺寸: {dims['x']:.2f} × {dims['y']:.2f} × {dims['z']:.2f} mm")

    elif any(kw in q_lower for kw in ["watertight", "水密", "封闭", "manifold", "流形"]):
        lines.append("## 水密性分析\n")
        if is_watertight:
            lines.append("✅ 模型是水密的（封闭网格）。")
            lines.append(f"欧拉数: {analysis_data['watertight']['euler_number']}")
        else:
            lines.append("❌ 模型不封闭。")
            if defects["non_manifold_edges"]["has_defect"]:
                lines.append("  原因: 存在非流形边")
            if defects["disconnected_components"]["has_defect"]:
                lines.append(f"  原因: 存在 {defects['disconnected_components']['count']} 个断开组件")

    else:
        # 通用分析
        lines.append("## 综合分析\n")
        lines.append(f"顶点数: {analysis_data['vertices']:,}")
        lines.append(f"面数: {analysis_data['faces']:,}")
        lines.append(f"水密性: {'是' if is_watertight else '否'}")
        if volume is not None:
            lines.append(f"体积: {volume:.2f} mm³")
        if surface_area is not None:
            lines.append(f"表面积: {surface_area:.2f} mm²")
        lines.append(f"尺寸: {dims['x']:.2f} × {dims['y']:.2f} × {dims['z']:.2f} mm")

        defect_count = sum(1 for v in defects.values() if isinstance(v, dict) and v.get("has_defect"))
        if defect_count > 0:
            lines.append(f"\n⚠️ 检测到 {defect_count} 类缺陷，建议进一步检查。")
        else:
            lines.append("\n✅ 网格质量良好。")

    return "\n".join(lines)


def main():
    """MCP 服务器入口点"""
    mcp.run()


if __name__ == "__main__":
    main()
