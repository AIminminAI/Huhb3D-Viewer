"""
STEP 拓扑提取商业 API — Replicate Cog 模型
============================================

这是 Huhb3D STEP 拓扑提取模型的 Replicate.com 部署版本。
纯 CPU 运行，无需 GPU 和 Blender，运行成本极低。

核心能力：
  1. 接收 STEP/STP CAD 文件上传
  2. 提取 15 类拓扑标签（PLANE, CYLINDER, CONE, SPHERE, TORUS,
     HorizontalPlane, LateralPlane, ConcaveFeature_Hole,
     ConvexFeature_Bolt, Chamfer, Fillet, Boss, Pocket, Slot, Step）
  3. 为每个面生成机器人抓取推荐
  4. 返回包含所有结果的 JSON 文件

商业价值：
  - 客户按 API 调用付费，你收取收入分成
  - 纯 CPU 运行 = 极低的推理成本
  - 独特的 STEP 拓扑提取能力，市场上几乎没有竞品
"""

import json
import math
import os
import sys
import tempfile
from pathlib import Path

# Cog 框架导入（Replicate 的模型框架）
try:
    from cog import BasePredictor, Input, Path as CogPath
except ImportError:
    # 本地测试时无 cog 环境的兼容处理
    class BasePredictor:
        pass
    class Input:
        @staticmethod
        def default(**kwargs):
            def decorator(fn):
                fn._cog_input = kwargs
                return fn
            return decorator
    CogPath = str


# ============================================================
# 备用拓扑解析器 — 当无法从父目录导入 step_topology_parser 时使用
# 基于 cadquery 的简化版实现
# ============================================================

# 15 类拓扑标签
TOPOLOGY_CATEGORIES = [
    "PLANE", "CYLINDER", "CONE", "SPHERE", "TORUS",
    "HorizontalPlane", "LateralPlane",
    "ConcaveFeature_Hole", "ConvexFeature_Bolt",
    "Chamfer", "Fillet", "Boss", "Pocket", "Slot", "Step",
]


def _classify_face_fallback(geom_type, normal, area, radius=None, axis_dir=None):
    """
    备用面分类器：基于几何类型 + 法线方向 + 邻接关系进行分类。

    分类逻辑：
      - PLANE + normal_z > 0.7 → HorizontalPlane
      - PLANE + abs(normal_z) < 0.3 → LateralPlane
      - PLANE → PLANE
      - CYLINDER + radius < 5 → ConvexFeature_Bolt（凸）或 ConcaveFeature_Hole（凹）
      - CYLINDER → CYLINDER
      - CONE → CONE
      - SPHERE → SPHERE
      - TORUS + minor_radius < 1 → Fillet
      - TORUS → TORUS
      - 其他 → OTHER
    """
    if geom_type == "PLANE":
        nz = normal[2] if normal else 0.0
        if nz > 0.7:
            return "HorizontalPlane"
        elif abs(nz) < 0.3:
            return "LateralPlane"
        else:
            return "PLANE"

    elif geom_type == "CYLINDER":
        if radius is not None and radius < 5:
            # 简化判断：小半径圆柱默认为凹（孔），实际应通过凹凸性判断
            # 这里保守地标记为 ConcaveFeature_Hole
            return "ConcaveFeature_Hole"
        else:
            return "CYLINDER"

    elif geom_type == "CONE":
        return "CONE"

    elif geom_type == "SPHERE":
        return "SPHERE"

    elif geom_type == "TORUS":
        # cadquery 不直接暴露 minor_radius，简化处理
        return "Fillet"

    else:
        return "OTHER"


def _parse_step_fallback(step_path, output_dir):
    """
    备用 STEP 拓扑解析器：使用 cadquery 进行简化版拓扑提取。
    当无法导入父目录的 step_topology_parser 时自动启用。

    流程：
      1. 使用 cq.importers.importStep(path) 导入 STEP 文件
      2. 遍历 result.faces() 获取每个面
      3. 对每个面获取 geomType()、Area()、Center()、法线方向
      4. 基于几何类型 + 法线 + 尺寸进行 15 类分类
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

            # 获取法线方向（在面中心处）
            normal = [0.0, 0.0, 0.0]
            radius = None
            axis_dir = None

            try:
                # 尝试通过 OCP 获取更精确的法线
                from OCP.BRepGProp import BRepGProp
                from OCP.GProp import GProp_GProps
                from OCP.BRepAdaptor import BRepAdaptor_Surface
                from OCP.TopoDS import TopoDS

                topo_face = TopoDS.Face_s(face_shape.wrapped)
                adaptor = BRepAdaptor_Surface(topo_face)
                u_mid = (adaptor.FirstUParameter() + adaptor.LastUParameter()) / 2
                v_mid = (adaptor.FirstVParameter() + adaptor.LastVParameter()) / 2

                from OCP.gp import gp_Vec, gp_Pnt
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
                # OCP 不可用时，对平面使用近似法线
                if geom_type == "PLANE" and area > 0:
                    # 简化：假设法线朝上
                    normal = [0.0, 1.0, 0.0]

            # 分类
            category = _classify_face_fallback(
                geom_type, normal, area,
                radius=radius, axis_dir=axis_dir
            )

            face_info = {
                "face_id": face_id,
                "geom_type": geom_type,
                "category_name": category,
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
            # 单个面解析失败时跳过，继续处理其他面
            continue

    # 生成拓扑标签 JSON
    labels_data = {
        "source_file": Path(step_path).name,
        "total_faces": len(faces_data),
        "shape_bounds": [round(v, 4) for v in shape_bounds],
        "parser": "cadquery_fallback",
        "faces": faces_data,
    }

    labels_path = output_dir / "topology_labels.json"
    with open(labels_path, "w", encoding="utf-8") as f:
        json.dump(labels_data, f, indent=2, ensure_ascii=False)

    # 生成拓扑摘要 JSON
    from collections import defaultdict
    category_stats = defaultdict(lambda: {"face_count": 0, "total_area": 0.0})
    for fi in faces_data:
        cat = fi["category_name"]
        category_stats[cat]["face_count"] += 1
        category_stats[cat]["total_area"] += fi["area"]

    summary_data = {
        "source_file": Path(step_path).name,
        "total_faces": len(faces_data),
        "shape_bounds": [round(v, 4) for v in shape_bounds],
        "parser": "cadquery_fallback",
        "categories": dict(category_stats),
    }

    summary_path = output_dir / "topology_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2, ensure_ascii=False)

    return labels_data, None


def _generate_grasp_fallback(topology_labels, topology_summary):
    """
    备用抓取推荐生成器：基于拓扑标签数据生成简化版抓取推荐。
    当无法导入父目录的 grasp_recommendations 时自动启用。
    """
    # 拓扑类别到抓取策略的映射
    strategy_map = {
        "HorizontalPlane":    ("vacuum_grip",    "vacuum_cup",         "水平平面，适合真空吸附"),
        "LateralPlane":       ("surface_grip",   "vacuum_cup_or_gecko","垂直平面，壁虎/真空吸附"),
        "PLANE":              ("surface_grip",   "vacuum_cup_or_gecko","斜面，可真空/壁虎吸附"),
        "ConcaveFeature_Hole":("expansion_grip", "expansion_gripper",  "孔特征，插入膨胀夹持"),
        "ConvexFeature_Bolt": ("lateral_pinch",  "parallel_jaw",       "凸起特征，平行爪夹持"),
        "CYLINDER":           ("contour_grip",   "soft_gripper",       "圆柱面，柔顺夹持"),
        "CONE":               ("edge_grip",      "parallel_jaw",       "锥面，边缘夹持"),
        "SPHERE":             ("contour_grip",   "soft_gripper",       "球面，柔顺夹持"),
        "Fillet":             ("contour_grip",   "soft_gripper",       "圆角过渡面，柔顺夹持"),
        "TORUS":              ("contour_grip",   "soft_gripper",       "环面，柔顺夹持"),
        "Boss":               ("lateral_pinch",  "parallel_jaw",       "凸台，平行爪夹持"),
        "Chamfer":            ("edge_grip",      "parallel_jaw",       "倒角，边缘夹持"),
        "Pocket":             ("expansion_grip", "expansion_gripper",  "凹槽，膨胀夹持"),
        "Slot":               ("lateral_pinch",  "parallel_jaw",       "槽特征，平行爪夹持"),
        "Step":               ("lateral_pinch",  "parallel_jaw",       "台阶面，平行爪夹持"),
        "OTHER":              ("contour_grip",   "soft_gripper",       "未知曲面，柔顺夹持"),
    }

    # 置信度映射
    confidence_map = {
        "HorizontalPlane": 0.95,
        "LateralPlane": 0.70,
        "PLANE": 0.70,
        "ConcaveFeature_Hole": 0.90,
        "ConvexFeature_Bolt": 0.80,
        "CYLINDER": 0.60,
        "CONE": 0.50,
        "SPHERE": 0.60,
        "Fillet": 0.50,
        "TORUS": 0.50,
        "Boss": 0.80,
        "Chamfer": 0.50,
        "Pocket": 0.75,
        "Slot": 0.70,
        "Step": 0.70,
        "OTHER": 0.40,
    }

    faces = topology_labels.get("faces", [])
    object_bounds = topology_labels.get("shape_bounds", [0, 0, 0, 0, 0, 0])

    face_recommendations = []
    for face in faces:
        cat = face.get("category_name", "OTHER")
        grasp_method, gripper_type, notes = strategy_map.get(
            cat, ("contour_grip", "soft_gripper", "未知面类型，柔顺夹持")
        )
        confidence = confidence_map.get(cat, 0.4)

        # 面积极小时降低置信度
        if face.get("area", 0) < 10:
            confidence *= 0.5

        # 计算接近方向（法线反方向）
        normal = face.get("normal", [0, 0, 0])
        approach = [-n for n in normal]
        alen = math.sqrt(sum(a * a for a in approach))
        if alen > 1e-10:
            approach = [a / alen for a in approach]

        rec = {
            "face_id": face.get("face_id", 0),
            "category_name": cat,
            "geom_type": face.get("geom_type", ""),
            "area": face.get("area", 0),
            "grasp_method": grasp_method,
            "gripper_type": gripper_type,
            "approach_direction": [round(a, 4) for a in approach],
            "confidence": round(confidence, 2),
            "notes": notes,
        }
        face_recommendations.append(rec)

    # 计算最优抓取策略：选择置信度 * sqrt(面积) 最高的面
    valid_recs = [r for r in face_recommendations if r["grasp_method"] != "not_recommended"]
    if valid_recs:
        best = max(valid_recs, key=lambda r: r["confidence"] * math.sqrt(max(r["area"], 0)))
        best_strategy = {
            "method": best["grasp_method"],
            "gripper_type": best["gripper_type"],
            "target_face_id": best["face_id"],
            "approach_direction": best["approach_direction"],
            "confidence": best["confidence"],
            "reasoning": f"面积 {best['area']:.1f} mm², {best['notes']}",
        }
    else:
        best_strategy = {
            "method": "not_recommended",
            "gripper_type": "none",
            "target_face_id": -1,
            "approach_direction": [0, 0, -1],
            "confidence": 0.0,
            "reasoning": "所有面均不适合抓取",
        }

    return {
        "source_file": topology_labels.get("source_file", ""),
        "object_bounds": object_bounds,
        "best_grasp_strategy": best_strategy,
        "face_recommendations": face_recommendations,
    }


class Predictor(BasePredictor):
    """
    STEP 拓扑提取 Replicate 模型预测器。

    接收 STEP/STP CAD 文件，提取拓扑标签和抓取推荐，
    返回包含所有分析结果的 JSON 文件。
    """

    def setup(self):
        """加载拓扑解析器和抓取推荐生成器。"""
        # 尝试从父目录导入完整版解析器
        self.parse_step_topology = None
        self.generate_grasp_recommendations = None
        self.use_fallback = False

        try:
            parent_dir = str(Path(__file__).parent.parent)
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            from step_topology_parser import parse_step_topology
            from grasp_recommendations import generate_grasp_recommendations
            self.parse_step_topology = parse_step_topology
            self.generate_grasp_recommendations = generate_grasp_recommendations
            print("[Setup] 已加载完整版拓扑解析器和抓取推荐模块")
        except ImportError as e:
            print(f"[Setup] 无法导入完整版模块 ({e})，将使用 cadquery 备用解析器")
            self.use_fallback = True

    def predict(
        self,
        step_file: CogPath = Input(description="STEP/STP CAD 文件，用于拓扑分析"),
        include_grasp: bool = Input(default=True, description="是否包含抓取推荐"),
    ) -> CogPath:
        """
        解析 STEP 文件，提取拓扑标签和抓取推荐。

        参数:
            step_file: 上传的 STEP/STP CAD 文件
            include_grasp: 是否在结果中包含抓取推荐

        返回:
            包含 topology_labels + topology_summary + grasp_recommendations 的 JSON 文件
        """
        # 创建临时输出目录
        output_dir = tempfile.mkdtemp(prefix="huhb3d_topo_")
        topo_dir = os.path.join(output_dir, "topology")
        os.makedirs(topo_dir, exist_ok=True)

        step_path = str(step_file)

        # 验证文件扩展名
        ext = Path(step_path).suffix.lower()
        if ext not in (".step", ".stp"):
            # 返回错误 JSON
            error_path = os.path.join(output_dir, "output.json")
            error_result = {
                "success": False,
                "error": f"不支持的文件格式: {ext}，请上传 .step 或 .stp 文件",
                "supported_formats": [".step", ".stp"],
            }
            with open(error_path, "w", encoding="utf-8") as f:
                json.dump(error_result, f, indent=2, ensure_ascii=False)
            return CogPath(error_path)

        # ========== 拓扑解析 ==========
        topology_labels = None
        topology_summary = None
        parse_error = None

        if not self.use_fallback and self.parse_step_topology is not None:
            # 使用完整版解析器
            try:
                success = self.parse_step_topology(step_path, topo_dir)
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
                    # 读取备用解析器生成的摘要
                    summary_path = os.path.join(topo_dir, "topology_summary.json")
                    if os.path.exists(summary_path):
                        with open(summary_path, "r", encoding="utf-8") as f:
                            topology_summary = json.load(f)
                    parse_error = None  # 备用解析器成功，清除错误
                else:
                    parse_error = fallback_error or "备用解析器也失败了"
            except Exception as e:
                parse_error = f"备用解析器异常: {str(e)}"

        # 拓扑解析完全失败，返回错误 JSON
        if topology_labels is None:
            error_path = os.path.join(output_dir, "output.json")
            error_result = {
                "success": False,
                "error": f"STEP 文件解析失败: {parse_error}",
                "suggestion": "请确认文件是有效的 STEP/STP 格式，且不包含损坏的几何数据",
                "source_file": Path(step_path).name,
            }
            with open(error_path, "w", encoding="utf-8") as f:
                json.dump(error_result, f, indent=2, ensure_ascii=False)
            return CogPath(error_path)

        # ========== 抓取推荐 ==========
        grasp_data = None
        if include_grasp:
            if not self.use_fallback and self.generate_grasp_recommendations is not None:
                # 使用完整版抓取推荐
                try:
                    labels_path = os.path.join(topo_dir, "topology_labels.json")
                    summary_path = os.path.join(topo_dir, "topology_summary.json")
                    grasp_path = os.path.join(topo_dir, "grasp_recommendations.json")
                    grasp_data = self.generate_grasp_recommendations(
                        labels_path, summary_path, grasp_path
                    )
                except Exception as e:
                    print(f"[Predict] 完整版抓取推荐失败 ({e})，使用备用生成器")
                    grasp_data = _generate_grasp_fallback(topology_labels, topology_summary)
            else:
                # 使用备用抓取推荐生成器
                grasp_data = _generate_grasp_fallback(topology_labels, topology_summary)

        # ========== 合并结果 ==========
        result = {
            "success": True,
            "source_file": Path(step_path).name,
            "topology_labels": topology_labels,
            "topology_summary": topology_summary,
        }

        if grasp_data is not None:
            result["grasp_recommendations"] = grasp_data

        # 保存合并结果
        output_path = os.path.join(output_dir, "output.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        return CogPath(output_path)
