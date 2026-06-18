"""
Huhb3D CAD Feature Recognition API — FastAPI 主应用
=====================================================
基于 OpenCASCADE 拓扑分析的 STEP 文件特征识别 REST API 服务。
上传 STEP/STP 文件，获取 CAD 特征分析与机器人抓取推荐。

核心能力：
  1. 接收 STEP/STP CAD 文件上传
  2. 提取 15 类拓扑特征标签（水平面、侧面、孔、螺栓、倒角、圆角等）
  3. 为每个面生成机器人抓取推荐（8 种抓取方式 + 置信度 + 接近方向）
  4. 生成整体最优抓取策略
  5. 支持批量文件分析

端点：
  POST /analyze          — 上传 STEP 文件，获取特征分析
  POST /analyze/batch    — 上传多个 STEP 文件，批量分析
  GET  /features/types   — 列出所有 15 类特征类型
  GET  /grasp/methods    — 列出所有 8 种抓取方式
  GET  /health           — 健康检查
"""

import json
import math
import os
import shutil
import sys
import tempfile
import time
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ============================================================
# 日志配置
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("huhb3d-api")

# ============================================================
# 导入父目录的拓扑解析器和抓取推荐模块
# ============================================================
_parent_dir = str(Path(__file__).parent.parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

_parse_step_topology = None
_generate_grasp_recommendations = None
_USE_FALLBACK = False

try:
    from step_topology_parser import parse_step_topology, CATEGORY_NAMES
    _parse_step_topology = parse_step_topology
    logger.info("已加载完整版拓扑解析器")
except ImportError as e:
    logger.warning(f"无法导入完整版模块 ({e})，将使用 cadquery 备用解析器")
    _USE_FALLBACK = True
    # 15 类拓扑标签定义（备用）
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


# ============================================================
# 15 类特征类型定义（规范化的 15 类）
# ============================================================
FEATURE_CATEGORIES = {
    "FreeSurface":          "自由曲面 — 无法归入其他类别的曲面",
    "HorizontalPlane":      "水平平面 — 法线朝上的平面，适合真空吸附",
    "LateralPlane_X":       "X向侧面 — 法线沿X轴的垂直平面",
    "LateralPlane_Z":       "Z向侧面 — 法线沿Z轴的垂直平面",
    "NearHorizontal":       "近水平面 — 法线接近Y轴但未达阈值",
    "NearLateral_X":        "近X向侧面 — 法线接近X轴但未达阈值",
    "NearLateral_Z":        "近Z向侧面 — 法线接近Z轴但未达阈值",
    "Degenerate":           "退化面 — 面积极小，可能是建模残留",
    "ConvexFeature_Bolt":   "凸起螺栓 — 小半径凸圆柱特征",
    "ConcaveFeature_Hole":  "凹入孔 — 小半径凹圆柱特征（通孔/盲孔）",
    "Flange":               "法兰 — 大半径凹圆柱特征（环形槽/通道）",
    "Boss":                 "凸台 — 中等半径凸圆柱特征",
    "Chamfer":              "倒角 — 锥面过渡特征",
    "Fillet":               "圆角 — 环面过渡特征（圆角/倒圆）",
    "SphericalSurface":     "球面 — 球形曲面特征",
}

# 8 种抓取方式定义
GRASP_METHODS = {
    "vacuum_grip":      "真空吸附 — 利用负压吸附平面或近平面，适合水平面和大面积平面",
    "expansion_grip":   "膨胀夹持 — 插入孔内后膨胀夹紧，适合通孔和盲孔特征",
    "lateral_pinch":    "侧向夹持 — 平行爪从两侧夹紧，适合螺栓、凸台等凸起特征",
    "contour_grip":     "轮廓夹持 — 柔顺夹爪贴合曲面，适合自由曲面和球面",
    "wrap_grip":        "包裹夹持 — 柔性夹爪包裹整个工件，适合不规则形状",
    "parallel_clamp":   "平行夹紧 — 刚性平行爪夹持，适合法兰和边缘特征",
    "magnetic_grip":    "磁力吸附 — 电磁铁吸附铁磁材料，适合平面金属件",
    "none":             "不推荐 — 该面不适合抓取",
}

# 内部类别 ID 到规范化类别名称的映射
# 与 step_topology_parser.py 的 CATEGORY_NAMES 保持一致
_CATEGORY_ID_TO_API_NAME = {
    0: "FreeSurface",
    1: "HorizontalPlane",
    2: "LateralPlane_X",
    3: "LateralPlane_Z",
    4: "NearHorizontal",        # 近水平面 — 法线接近Y轴但未达阈值
    5: "NearLateral_X",         # 近X向侧面 — 法线接近X轴但未达阈值
    6: "NearLateral_Z",         # 近Z向侧面 — 法线接近Z轴但未达阈值
    7: "Degenerate",            # 退化面 — 面积极小，可能是建模残留
    8: "ConvexFeature_Bolt",
    9: "ConcaveFeature_Hole",
    10: "Flange",
    11: "Boss",
    12: "Chamfer",
    13: "Fillet",
    14: "SphericalSurface",
}

# 类别 ID 到抓取方式的映射
_CATEGORY_ID_TO_GRASP = {
    0: ("contour_grip", 0.60),
    1: ("vacuum_grip", 0.95),
    2: ("lateral_pinch", 0.70),
    3: ("lateral_pinch", 0.70),
    4: ("contour_grip", 0.65),
    5: ("contour_grip", 0.60),
    6: ("contour_grip", 0.60),
    7: ("none", 0.00),
    8: ("lateral_pinch", 0.80),
    9: ("expansion_grip", 0.90),
    10: ("parallel_clamp", 0.75),
    11: ("lateral_pinch", 0.80),
    12: ("parallel_clamp", 0.50),
    13: ("contour_grip", 0.50),
    14: ("contour_grip", 0.60),
}


# ============================================================
# 速率限制 — 基于 IP 地址的内存计数器（开源项目，无需 API Key）
# ============================================================
_rate_limit_by_ip: Dict[str, Dict[str, int]] = {}      # {ip: {date_str: count}}

DAILY_LIMIT = 100

# 文件大小限制：50MB
MAX_FILE_SIZE = 50 * 1024 * 1024


def _check_rate_limit(client_ip: str) -> Optional[str]:
    """
    检查 IP 地址的速率限制。
    返回 None 表示通过，返回错误信息字符串表示超限。
    """
    today = datetime.now().strftime("%Y-%m-%d")

    if client_ip not in _rate_limit_by_ip:
        _rate_limit_by_ip[client_ip] = {}

    # 清理过期数据
    for date_str in list(_rate_limit_by_ip[client_ip].keys()):
        if date_str < today:
            del _rate_limit_by_ip[client_ip][date_str]

    today_count = _rate_limit_by_ip[client_ip].get(today, 0)
    if today_count >= DAILY_LIMIT:
        return f"今日调用次数已达上限 ({DAILY_LIMIT}/天)"

    _rate_limit_by_ip[client_ip][today] = today_count + 1
    return None


# ============================================================
# 备用拓扑解析器 — 当无法从父目录导入 step_topology_parser 时使用
# ============================================================

def _classify_face_fallback(geom_type, normal, area, radius=None, axis_dir=None):
    """
    备用面分类器：基于几何类型 + 法线方向 + 尺寸进行分类。
    与 step_topology_parser.py 的分类逻辑保持一致。
    """
    if geom_type == "PLANE":
        nz = normal[2] if normal else 0.0
        ny = normal[1] if normal else 0.0
        nx = normal[0] if normal else 0.0
        abs_x, abs_y, abs_z = abs(nx), abs(ny), abs(nz)
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
            return 0  # FreeSurface

    elif geom_type == "CYLINDER":
        # 简化版：无法准确判断凹凸，用半径近似
        if radius is not None and radius < 5:
            return 9  # ConcaveFeature_Hole (小半径圆柱≈孔)
        elif radius is not None and radius < 20:
            return 8  # ConvexFeature_Bolt (中等半径圆柱≈螺栓/凸台)
        else:
            return 0  # FreeSurface (大圆柱≈主体)

    elif geom_type == "CONE":
        return 12  # Chamfer

    elif geom_type == "SPHERE":
        return 14  # SphericalSurface

    elif geom_type == "TORUS":
        return 13  # Fillet

    else:
        return 0  # FreeSurface


def _parse_step_fallback(step_path, output_dir):
    """
    备用 STEP 拓扑解析器：使用 cadquery 进行简化版拓扑提取。
    """
    try:
        import cadquery as cq
    except ImportError:
        return None, "cadquery 未安装，无法解析 STEP 文件"

    step_path = str(step_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 导入 STEP 文件
    try:
        result = cq.importers.importStep(step_path)
    except Exception as e:
        return None, f"STEP 文件导入失败: {str(e)}"

    # 获取包围盒
    try:
        bbox = result.val().BoundingBox()
        shape_bounds = [bbox.xmin, bbox.ymin, bbox.zmin, bbox.xmax, bbox.ymax, bbox.zmax]
    except Exception:
        shape_bounds = [0, 0, 0, 0, 0, 0]

    # 遍历所有面并提取拓扑信息
    faces_data = []
    face_id = 0

    try:
        faces = result.faces().vals()
    except Exception:
        return None, "无法获取面列表"

    for face_shape in faces:
        try:
            geom_type = face_shape.geomType()
            area = face_shape.Area()
            center = face_shape.Center()

            # 获取法线方向
            normal = [0.0, 0.0, 0.0]
            radius = None
            axis_dir = None

            try:
                from OCP.BRepAdaptor import BRepAdaptor_Surface
                from OCP.TopoDS import TopoDS
                from OCP.gp import gp_Vec, gp_Pnt

                topo_face = TopoDS.Face_s(face_shape.wrapped)
                adaptor = BRepAdaptor_Surface(topo_face)
                u_mid = (adaptor.FirstUParameter() + adaptor.LastUParameter()) / 2
                v_mid = (adaptor.FirstVParameter() + adaptor.LastVParameter()) / 2

                pnt = gp_Pnt()
                du = gp_Vec()
                dv = gp_Vec()
                adaptor.D1(u_mid, v_mid, pnt, du, dv)

                nx = du.Y() * dv.Z() - du.Z() * dv.Y()
                ny = du.Z() * dv.X() - du.X() * dv.Z()
                nz = du.X() * dv.Y() - du.Y() * dv.X()
                nlen = math.sqrt(nx * nx + ny * ny + nz * nz)
                if nlen > 1e-10:
                    normal = [nx / nlen, ny / nlen, nz / nlen]

                # 获取圆柱半径和轴向
                if geom_type == "CYLINDER":
                    try:
                        cyl = adaptor.Cylinder()
                        radius = cyl.Radius()
                        ax = cyl.Axis().Direction()
                        axis_dir = [ax.X(), ax.Y(), ax.Z()]
                    except Exception:
                        pass

            except Exception:
                if geom_type == "PLANE" and area > 0:
                    normal = [0.0, 1.0, 0.0]

            # 分类
            category_id = _classify_face_fallback(
                geom_type, normal, area,
                radius=radius, axis_dir=axis_dir
            )
            category_name = _CATEGORY_ID_TO_API_NAME.get(category_id, "FreeSurface")

            face_info = {
                "face_id": face_id,
                "geom_type": geom_type,
                "category_id": category_id,
                "category_name": category_name,
                "area": round(area, 6),
                "center": [round(center.x, 4), round(center.y, 4), round(center.z, 4)],
                "normal": [round(n, 4) for n in normal],
            }
            if radius is not None:
                face_info["radius"] = round(radius, 4)
            if axis_dir is not None:
                face_info["axis_direction"] = [round(a, 4) for a in axis_dir]

            faces_data.append(face_info)
            face_id += 1

        except Exception:
            continue

    # 生成拓扑标签 JSON
    labels_data = {
        "source_file": Path(step_path).name,
        "total_faces": len(faces_data),
        "total_triangles": 0,
        "shape_bounds": [round(v, 4) for v in shape_bounds],
        "parser": "cadquery_fallback",
        "faces": faces_data,
    }

    labels_path = output_dir / "topology_labels.json"
    with open(labels_path, "w", encoding="utf-8") as f:
        json.dump(labels_data, f, indent=2, ensure_ascii=False)

    # 生成拓扑摘要 JSON
    category_stats = defaultdict(lambda: {"face_count": 0, "total_area": 0.0})
    for fi in faces_data:
        cat = fi["category_id"]
        category_stats[cat]["face_count"] += 1
        category_stats[cat]["total_area"] += fi["area"]

    summary_data = {
        "source_file": Path(step_path).name,
        "total_faces": len(faces_data),
        "total_triangles": 0,
        "shape_bounds": [round(v, 4) for v in shape_bounds],
        "parser": "cadquery_fallback",
        "categories": {
            str(k): {
                "name": _CATEGORY_ID_TO_API_NAME.get(k, "Unknown"),
                "face_count": v["face_count"],
                "total_area": round(v["total_area"], 6),
            }
            for k, v in category_stats.items()
        },
    }

    summary_path = output_dir / "topology_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2, ensure_ascii=False)

    return labels_data, None


def _generate_grasp_fallback(topology_labels, topology_summary):
    """
    备用抓取推荐生成器：基于拓扑标签数据生成简化版抓取推荐。
    """
    faces = topology_labels.get("faces", [])
    object_bounds = topology_labels.get("shape_bounds", [0, 0, 0, 0, 0, 0])

    face_recommendations = []
    for face in faces:
        cat_id = face.get("category_id", 0)
        cat_name = face.get("category_name", "Unknown")
        area = face.get("area", 0)

        # 查找策略
        if cat_id in _CATEGORY_ID_TO_GRASP:
            grasp_method, confidence = _CATEGORY_ID_TO_GRASP[cat_id]
        else:
            grasp_method, confidence = "contour_grip", 0.4

        # 面积极小时降低置信度
        if area < 10:
            confidence *= 0.5

        # 计算接近方向（法线反方向）
        normal = face.get("normal", [0, 0, 0])
        if not normal or all(n == 0 for n in normal):
            # 从 extra 中获取法线
            normal = face.get("extra", {}).get("normal", [0, 0, 0])
        approach = [-n for n in normal]
        alen = math.sqrt(sum(a * a for a in approach))
        if alen > 1e-10:
            approach = [a / alen for a in approach]
        else:
            approach = [0.0, 0.0, -1.0]

        rec = {
            "face_id": face.get("face_id", 0),
            "category_name": cat_name,
            "geom_type": face.get("geom_type", ""),
            "area": round(area, 6),
            "grasp_method": grasp_method,
            "approach_direction": [round(a, 4) for a in approach],
            "confidence": round(confidence, 2),
        }
        face_recommendations.append(rec)

    # 计算最优抓取策略
    valid_recs = [r for r in face_recommendations if r["grasp_method"] != "none"]
    if valid_recs:
        best = max(valid_recs, key=lambda r: r["confidence"] * math.sqrt(max(r["area"], 0)))
        best_strategy = {
            "method": best["grasp_method"],
            "confidence": best["confidence"],
            "approach_direction": best["approach_direction"],
            "target_faces": [best["face_id"]],
        }
    else:
        best_strategy = {
            "method": "none",
            "confidence": 0.0,
            "approach_direction": [0.0, 0.0, -1.0],
            "target_faces": [],
        }

    return {
        "best_grasp_strategy": best_strategy,
        "face_recommendations": face_recommendations,
    }


# ============================================================
# 核心分析函数
# ============================================================

def _analyze_step_file(step_path: str, filename: str = "", file_size: int = 0) -> Dict:
    """
    分析单个 STEP 文件，返回完整的特征分析结果。
    包含：faces 列表、summary、recommended_grasp_strategy、model_info。
    """
    parse_start = time.time()
    step_path = str(Path(step_path).resolve())
    output_dir = tempfile.mkdtemp(prefix="huhb3d_api_")
    topo_dir = os.path.join(output_dir, "topology")
    os.makedirs(topo_dir, exist_ok=True)

    # ========== 拓扑解析 ==========
    topology_labels = None
    topology_summary = None
    parse_error = None

    if not _USE_FALLBACK and _parse_step_topology is not None:
        # 使用完整版解析器
        try:
            success = _parse_step_topology(step_path, topo_dir)
            if success:
                labels_path = os.path.join(topo_dir, "topology_labels.json")
                summary_path = os.path.join(topo_dir, "topology_summary.json")
                if os.path.exists(labels_path):
                    with open(labels_path, "r", encoding="utf-8") as f:
                        topology_labels = json.load(f)
                if os.path.exists(summary_path):
                    with open(summary_path, "r", encoding="utf-8") as f:
                        topology_summary = json.load(f)
            else:
                parse_error = "完整版解析器执行失败，尝试备用解析器"
        except Exception as e:
            parse_error = f"完整版解析器异常: {str(e)}"

    # 如果完整版失败，使用备用解析器
    if topology_labels is None:
        try:
            topology_labels, fallback_error = _parse_step_fallback(step_path, topo_dir)
            if topology_labels is not None:
                summary_path = os.path.join(topo_dir, "topology_summary.json")
                if os.path.exists(summary_path):
                    with open(summary_path, "r", encoding="utf-8") as f:
                        topology_summary = json.load(f)
                parse_error = None
            else:
                parse_error = fallback_error or "备用解析器也失败了"
        except Exception as e:
            parse_error = f"备用解析器异常: {str(e)}"

    # 拓扑解析完全失败
    if topology_labels is None:
        # 清理临时目录
        try:
            shutil.rmtree(output_dir, ignore_errors=True)
        except Exception:
            pass
        return {
            "success": False,
            "error": f"STEP 文件解析失败: {parse_error}",
            "suggestion": "请确认文件是有效的 STEP/STP 格式，且不包含损坏的几何数据",
        }

    # ========== 抓取推荐 ==========
    grasp_data = None
    if not _USE_FALLBACK and _generate_grasp_recommendations is not None:
        try:
            labels_path = os.path.join(topo_dir, "topology_labels.json")
            summary_path = os.path.join(topo_dir, "topology_summary.json")
            grasp_path = os.path.join(topo_dir, "grasp_recommendations.json")
            if os.path.exists(labels_path) and os.path.exists(summary_path):
                grasp_data = _generate_grasp_recommendations(
                    labels_path, summary_path, grasp_path
                )
        except Exception as e:
            logger.warning(f"完整版抓取推荐失败 ({e})，使用备用生成器")
            grasp_data = _generate_grasp_fallback(topology_labels, topology_summary)
    else:
        grasp_data = _generate_grasp_fallback(topology_labels, topology_summary)

    parse_time = time.time() - parse_start

    # ========== 构建 faces 列表（规范化的输出格式）==========
    raw_faces = topology_labels.get("faces", [])
    shape_bounds = topology_labels.get("shape_bounds", [0, 0, 0, 0, 0, 0])

    # 构建抓取推荐映射：face_id → recommendation
    grasp_map = {}
    if grasp_data:
        for rec in grasp_data.get("face_recommendations", []):
            grasp_map[rec.get("face_id", 0)] = rec

    faces = []
    for raw_face in raw_faces:
        cat_id = raw_face.get("category_id", 0)
        category = _CATEGORY_ID_TO_API_NAME.get(cat_id, raw_face.get("category_name", "FreeSurface"))
        geom_type = raw_face.get("geom_type", "UNKNOWN")

        # 法线方向
        normal = raw_face.get("normal", [0, 0, 0])
        if not normal or all(n == 0 for n in normal):
            normal = raw_face.get("extra", {}).get("normal", [0, 0, 0])
        normal = [round(n, 4) for n in normal]

        # 中心点
        center = raw_face.get("center", [0, 0, 0])
        if not center or all(c == 0 for c in center):
            # 从 extra 或包围盒估算
            cx = (shape_bounds[0] + shape_bounds[3]) / 2
            cy = (shape_bounds[1] + shape_bounds[4]) / 2
            cz = (shape_bounds[2] + shape_bounds[5]) / 2
            center = [round(cx, 4), round(cy, 4), round(cz, 4)]
        else:
            center = [round(c, 4) for c in center]

        # 半径（仅圆柱/球/环面有效）
        radius = None
        extra = raw_face.get("extra", {})
        if "radius" in extra:
            radius = round(extra["radius"], 4)
        elif "radius" in raw_face:
            radius = round(raw_face["radius"], 4)
        # 环面取 minor_radius
        if geom_type == "TORUS" and "minor_radius" in extra:
            radius = round(extra["minor_radius"], 4)

        # 抓取推荐
        face_id = raw_face.get("face_id", 0)
        rec = grasp_map.get(face_id, {})
        if rec:
            grasp_method = rec.get("grasp_method", "none")
            grasp_confidence = rec.get("confidence", 0.0)
            approach_dir = rec.get("approach_direction", [0, 0, -1])
        else:
            # 从映射表获取
            grasp_method, grasp_confidence = _CATEGORY_ID_TO_GRASP.get(cat_id, ("none", 0.0))
            # 计算接近方向
            approach = [-n for n in normal]
            alen = math.sqrt(sum(a * a for a in approach))
            if alen > 1e-10:
                approach_dir = [round(a / alen, 4) for a in approach]
            else:
                approach_dir = [0.0, 0.0, -1.0]

        face_obj = {
            "face_id": face_id,
            "geom_type": geom_type,
            "category": category,
            "area": round(raw_face.get("area", 0), 6),
            "normal": normal,
            "center": center,
            "radius": radius,
            "grasp_method": grasp_method,
            "grasp_confidence": round(grasp_confidence, 2),
            "grasp_approach_direction": approach_dir,
        }
        faces.append(face_obj)

    # ========== 构建 summary ==========
    category_counts = defaultdict(int)
    total_area = 0.0
    for face_obj in faces:
        category_counts[face_obj["category"]] += 1
        total_area += face_obj["area"]

    summary = {
        "total_faces": len(faces),
        "category_counts": dict(category_counts),
        "total_area": round(total_area, 6),
        "bounding_box": {
            "min": [round(v, 4) for v in shape_bounds[:3]],
            "max": [round(v, 4) for v in shape_bounds[3:]],
            "dimensions": [
                round(shape_bounds[3] - shape_bounds[0], 4),
                round(shape_bounds[4] - shape_bounds[1], 4),
                round(shape_bounds[5] - shape_bounds[2], 4),
            ],
        },
    }

    # ========== 构建 recommended_grasp_strategy ==========
    if grasp_data and "best_grasp_strategy" in grasp_data:
        best = grasp_data["best_grasp_strategy"]
        recommended_grasp_strategy = {
            "method": best.get("method", "none"),
            "confidence": best.get("confidence", 0.0),
            "approach_direction": best.get("approach_direction", [0, 0, -1]),
            "target_faces": [best.get("target_face_id", -1)] if best.get("target_face_id", -1) >= 0 else [],
        }
    else:
        # 从 faces 列表计算最优策略
        valid_faces = [f for f in faces if f["grasp_method"] != "none"]
        if valid_faces:
            best_face = max(valid_faces, key=lambda f: f["grasp_confidence"] * math.sqrt(max(f["area"], 0)))
            recommended_grasp_strategy = {
                "method": best_face["grasp_method"],
                "confidence": best_face["grasp_confidence"],
                "approach_direction": best_face["grasp_approach_direction"],
                "target_faces": [best_face["face_id"]],
            }
        else:
            recommended_grasp_strategy = {
                "method": "none",
                "confidence": 0.0,
                "approach_direction": [0.0, 0.0, -1.0],
                "target_faces": [],
            }

    # ========== 构建 model_info ==========
    model_info = {
        "filename": filename or Path(step_path).name,
        "file_size": file_size,
        "parse_time_seconds": round(parse_time, 3),
    }

    # 清理临时目录
    try:
        shutil.rmtree(output_dir, ignore_errors=True)
    except Exception:
        pass

    return {
        "success": True,
        "faces": faces,
        "summary": summary,
        "recommended_grasp_strategy": recommended_grasp_strategy,
        "model_info": model_info,
    }


# ============================================================
# FastAPI 应用
# ============================================================

app = FastAPI(
    title="Huhb3D CAD Feature Recognition API",
    description="上传 STEP 文件，获取 CAD 特征分析与机器人抓取推荐",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# 添加 CORS 中间件，允许 Web 前端跨域访问
_cors_origins_str = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://localhost:8000")
_cors_origins = [origin.strip() for origin in _cors_origins_str.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# 请求日志中间件
# ============================================================

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """记录每个请求的方法、路径、客户端 IP 和处理时间。"""
    start_time = time.time()
    client_ip = request.client.host if request.client else "unknown"

    # 跳过健康检查的详细日志
    if request.url.path == "/health":
        response = await call_next(request)
        return response

    logger.info(f"请求开始: {request.method} {request.url.path} | IP: {client_ip}")

    response = await call_next(request)

    process_time = time.time() - start_time
    logger.info(
        f"请求完成: {request.method} {request.url.path} | "
        f"状态: {response.status_code} | 耗时: {process_time:.3f}s | IP: {client_ip}"
    )

    return response


# ============================================================
# API 端点
# ============================================================

@app.get("/health")
async def health_check():
    """健康检查端点，返回 API 运行状态。"""
    return {
        "status": "healthy",
        "service": "Huhb3D CAD Feature Recognition API",
        "version": "1.0.0",
        "parser": "full" if not _USE_FALLBACK else "fallback",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/features/types")
async def list_feature_types():
    """
    列出所有 15 类特征类型。
    返回每个类别的名称和描述。
    """
    types = []
    for name, description in FEATURE_CATEGORIES.items():
        types.append({
            "name": name,
            "description": description,
        })

    return {
        "total": len(types),
        "feature_types": types,
    }


@app.get("/grasp/methods")
async def list_grasp_methods():
    """
    列出所有 8 种抓取方式。
    返回每种抓取方式的名称和描述。
    """
    methods = []
    for name, description in GRASP_METHODS.items():
        methods.append({
            "name": name,
            "description": description,
        })

    return {
        "total": len(methods),
        "grasp_methods": methods,
    }


@app.post("/analyze")
async def analyze_step_file(
    request: Request,
    file: UploadFile = File(..., description="STEP/STP CAD 文件"),
):
    """
    主分析端点：上传 STEP 文件，获取拓扑特征分析。
    按 IP 限速，100 次/天。
    """
    client_ip = request.client.host if request.client else "unknown"

    # 速率限制
    rate_error = _check_rate_limit(client_ip)
    if rate_error:
        raise HTTPException(status_code=429, detail=rate_error)
    logger.info(f"分析请求 | IP: {client_ip}")

    # 验证文件扩展名
    filename = file.filename or ""
    # 防止路径遍历：去除路径分隔符
    filename = filename.replace("/", "_").replace("\\", "_").replace("..", "_")
    ext = Path(filename).suffix.lower()
    if ext not in (".step", ".stp"):
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {ext}，请上传 .step 或 .stp 文件",
        )

    # 保存上传文件到临时目录（流式写入，避免大文件OOM）
    temp_dir = tempfile.mkdtemp(prefix="huhb3d_upload_")
    temp_path = os.path.join(temp_dir, filename)

    try:
        # 流式写入文件，同时检查大小
        file_size = 0
        with open(temp_path, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)  # 1MB chunks
                if not chunk:
                    break
                file_size += len(chunk)
                if file_size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail=f"文件过大 ({file_size / 1024 / 1024:.1f}MB)，最大支持 {MAX_FILE_SIZE / 1024 / 1024:.0f}MB",
                    )
                f.write(chunk)

        logger.info(f"文件上传: {filename} ({file_size} bytes) | IP: {client_ip}")

        # 执行分析
        result = _analyze_step_file(temp_path, filename=filename, file_size=file_size)

        if not result.get("success", False):
            raise HTTPException(
                status_code=422,
                detail=result.get("error", "STEP 文件解析失败"),
            )

        return result

    finally:
        # 清理临时文件
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass


@app.post("/analyze/batch")
async def analyze_batch(
    request: Request,
    files: List[UploadFile] = File(..., description="多个 STEP/STP CAD 文件"),
):
    """
    批量分析端点：上传多个 STEP 文件，获取每个文件的特征分析。
    按 IP 限速，每个文件计为一次。
    """
    client_ip = request.client.host if request.client else "unknown"

    # 检查剩余配额是否足够
    today = datetime.now().strftime("%Y-%m-%d")
    today_count = _rate_limit_by_ip.get(client_ip, {}).get(today, 0)
    remaining = DAILY_LIMIT - today_count
    if len(files) > remaining:
        raise HTTPException(
            status_code=429,
            detail=f"批量请求包含 {len(files)} 个文件，但今日剩余配额仅 {remaining} 次",
        )

    results = []
    for file in files:
        # 验证文件扩展名
        filename = file.filename or ""
        # 防止路径遍历：去除路径分隔符
        filename = filename.replace("/", "_").replace("\\", "_").replace("..", "_")
        ext = Path(filename).suffix.lower()
        if ext not in (".step", ".stp"):
            results.append({
                "filename": filename,
                "success": False,
                "error": f"不支持的文件格式: {ext}",
            })
            continue

        # 检查速率限制（每个文件计一次）
        rate_error = _check_rate_limit(client_ip)

        if rate_error:
            results.append({
                "filename": filename,
                "success": False,
                "error": rate_error,
            })
            continue

        # 保存上传文件到临时目录
        temp_dir = tempfile.mkdtemp(prefix="huhb3d_upload_")
        temp_path = os.path.join(temp_dir, filename)

        try:
            # 流式写入文件，同时检查大小
            file_size = 0
            with open(temp_path, "wb") as f:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    file_size += len(chunk)
                    if file_size > MAX_FILE_SIZE:
                        results.append({
                            "filename": filename,
                            "success": False,
                            "error": f"文件过大 ({file_size / 1024 / 1024:.1f}MB)",
                        })
                        break
                    f.write(chunk)
            else:
                # 执行分析
                result = _analyze_step_file(temp_path, filename=filename, file_size=file_size)
                result["filename"] = filename
                results.append(result)
                continue

        except Exception as e:
            results.append({
                "filename": filename,
                "success": False,
                "error": str(e),
            })

        finally:
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass

    return {
        "total_files": len(files),
        "results": results,
    }


# ============================================================
# 启动入口
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
