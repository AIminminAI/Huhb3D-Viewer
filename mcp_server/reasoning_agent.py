"""
Multi-step Reasoning Agent for 3D Analysis

实现 ReAct (Reasoning + Acting) 循环的多步推理代理：
  - 任务分解：将复杂问题拆解为有序子任务
  - 顺序执行：按依赖关系执行子任务，传递中间结果
  - 结果验证：检查结果的一致性和合理性
  - 自我修正：结果异常时尝试替代方案
  - 证据组装：汇总所有子结果为有据可依的结论

示例流程:
  用户: "这个支架适合FDM打印吗？"

  代理分解:
    Step 1: 检查水密性 → 结果: 是
    Step 2: 检查壁厚 → 结果: 最小 0.42mm
    Step 3: 检查悬垂 → 结果: 发现15个悬垂面
    Step 4: 检查尺寸适配 → 结果: 适配 Ender 3

  代理验证:
    - 壁厚 0.42mm < FDM 最小 0.8mm → 发现问题
    - 15个悬垂面需要支撑 → 警告

  代理结论:
    "不适合FDM打印。发现2个问题:
     1. 严重: 壁厚0.42mm低于FDM最小0.8mm
     2. 警告: 15个悬垂面需要支撑材料"
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

import numpy as np

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 数据结构
# ──────────────────────────────────────────────

class StepStatus(str, Enum):
    """子任务执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class Severity(str, Enum):
    """问题严重程度"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class SubTask:
    """子任务定义"""
    task_id: str
    description: str
    tool_name: str
    tool_args: dict[str, Any]
    depends_on: list[str] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    error: str | None = None
    retry_count: int = 0
    max_retries: int = 1


@dataclass
class ValidationIssue:
    """验证发现的问题"""
    severity: Severity
    description: str
    evidence: str
    sub_task_id: str


@dataclass
class ReasoningStep:
    """推理步骤记录"""
    step_type: str  # "decompose" | "execute" | "validate" | "correct" | "conclude"
    description: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReasoningResult:
    """推理结果"""
    conclusion: str
    issues: list[ValidationIssue] = field(default_factory=list)
    steps: list[ReasoningStep] = field(default_factory=list)
    sub_task_results: dict[str, Any] = field(default_factory=dict)
    success: bool = True


# ──────────────────────────────────────────────
# 任务分解规则
# ──────────────────────────────────────────────

# 问题类型到子任务模板的映射
TASK_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "fdm_printability": [
        {
            "task_id": "check_watertight",
            "description": "检查网格水密性",
            "tool_name": "analyze_mesh",
            "tool_args": {"analysis_types": ["watertight"]},
        },
        {
            "task_id": "check_thickness",
            "description": "检查壁厚分布",
            "tool_name": "analyze_mesh",
            "tool_args": {"analysis_types": ["thickness"]},
        },
        {
            "task_id": "check_overhangs",
            "description": "检查FDM悬垂角度",
            "tool_name": "check_3d_printability",
            "tool_args": {"printer_type": "fdm"},
        },
        {
            "task_id": "check_bed_fit",
            "description": "检查模型是否适配打印床",
            "tool_name": "analyze_mesh",
            "tool_args": {"analysis_types": ["bounding_box"]},
        },
        {
            "task_id": "check_defects",
            "description": "检查网格缺陷",
            "tool_name": "analyze_mesh",
            "tool_args": {"analysis_types": ["defects"]},
        },
    ],
    "sla_printability": [
        {
            "task_id": "check_watertight",
            "description": "检查网格水密性",
            "tool_name": "analyze_mesh",
            "tool_args": {"analysis_types": ["watertight"]},
        },
        {
            "task_id": "check_thickness",
            "description": "检查壁厚分布",
            "tool_name": "analyze_mesh",
            "tool_args": {"analysis_types": ["thickness"]},
        },
        {
            "task_id": "check_sla",
            "description": "检查SLA打印适用性",
            "tool_name": "check_3d_printability",
            "tool_args": {"printer_type": "sla"},
        },
        {
            "task_id": "check_defects",
            "description": "检查网格缺陷",
            "tool_name": "analyze_mesh",
            "tool_args": {"analysis_types": ["defects"]},
        },
    ],
    "mesh_quality": [
        {
            "task_id": "check_watertight",
            "description": "检查水密性",
            "tool_name": "analyze_mesh",
            "tool_args": {"analysis_types": ["watertight"]},
        },
        {
            "task_id": "check_euler",
            "description": "检查欧拉数和拓扑",
            "tool_name": "analyze_mesh",
            "tool_args": {"analysis_types": ["euler_number"]},
        },
        {
            "task_id": "check_defects",
            "description": "检查网格缺陷",
            "tool_name": "detect_defects",
            "tool_args": {},
        },
        {
            "task_id": "check_normals",
            "description": "检查法线一致性",
            "tool_name": "analyze_mesh",
            "tool_args": {"analysis_types": ["defects"]},
        },
    ],
    "geometry_analysis": [
        {
            "task_id": "check_volume",
            "description": "计算体积和质心",
            "tool_name": "compute_geometry",
            "tool_args": {"metrics": ["volume", "centroid"]},
        },
        {
            "task_id": "check_surface",
            "description": "计算表面积",
            "tool_name": "compute_geometry",
            "tool_args": {"metrics": ["surface_area"]},
        },
        {
            "task_id": "check_inertia",
            "description": "计算惯性张量和主轴",
            "tool_name": "compute_geometry",
            "tool_args": {"metrics": ["moment_of_inertia", "principal_axes"]},
        },
        {
            "task_id": "check_compactness",
            "description": "计算紧凑度",
            "tool_name": "compute_geometry",
            "tool_args": {"metrics": ["compactness", "convex_hull_volume"]},
        },
    ],
    "robotics_readiness": [
        {
            "task_id": "check_watertight",
            "description": "检查水密性（碰撞检测需要）",
            "tool_name": "analyze_mesh",
            "tool_args": {"analysis_types": ["watertight"]},
        },
        {
            "task_id": "check_volume",
            "description": "计算体积（质量估计需要）",
            "tool_name": "compute_geometry",
            "tool_args": {"metrics": ["volume", "centroid"]},
        },
        {
            "task_id": "check_inertia",
            "description": "计算惯性张量（动力学仿真需要）",
            "tool_name": "compute_geometry",
            "tool_args": {"metrics": ["moment_of_inertia", "principal_axes"]},
        },
        {
            "task_id": "check_defects",
            "description": "检查网格缺陷",
            "tool_name": "detect_defects",
            "tool_args": {},
        },
    ],
}


def classify_question(question: str) -> str:
    """根据用户问题分类，确定使用哪组子任务模板

    Args:
        question: 用户的问题文本

    Returns:
        任务类型标识符
    """
    q_lower = question.lower()

    # FDM 打印相关
    if any(kw in q_lower for kw in ["fdm", "熔融", "挤出", "ender", "pla", "abs", "petg"]):
        return "fdm_printability"

    # SLA 打印相关
    if any(kw in q_lower for kw in ["sla", "树脂", "光固化", "lcd", "dlp", "photon"]):
        return "sla_printability"

    # 通用打印
    if any(kw in q_lower for kw in ["打印", "print", "制造", "fabricat", "适合"]):
        return "fdm_printability"

    # 网格质量
    if any(kw in q_lower for kw in ["质量", "缺陷", "defect", "修复", "repair", "问题", "error"]):
        return "mesh_quality"

    # 几何分析
    if any(kw in q_lower for kw in ["体积", "表面积", "惯性", "质心", "紧凑", "volume", "area", "inertia"]):
        return "geometry_analysis"

    # 机器人相关
    if any(kw in q_lower for kw in ["机器人", "robot", "抓取", "grasp", "碰撞", "仿真", "sim"]):
        return "robotics_readiness"

    # 默认：综合分析
    return "mesh_quality"


# ──────────────────────────────────────────────
# 验证规则
# ──────────────────────────────────────────────

class ValidationRule:
    """验证规则：检查子任务结果是否合理"""

    def __init__(
        self,
        sub_task_id: str,
        check_fn: Callable[[Any], ValidationIssue | None],
    ):
        self.sub_task_id = sub_task_id
        self.check_fn = check_fn

    def validate(self, result: Any) -> ValidationIssue | None:
        return self.check_fn(result)


def _build_validation_rules(task_type: str) -> list[ValidationRule]:
    """根据任务类型构建验证规则

    Args:
        task_type: 任务类型标识符

    Returns:
        验证规则列表
    """
    rules: list[ValidationRule] = []

    # ── 水密性验证 ──
    def check_watertight(result: Any) -> ValidationIssue | None:
        if isinstance(result, dict):
            wt = result.get("watertight", {})
            if not wt.get("is_watertight", True):
                return ValidationIssue(
                    severity=Severity.CRITICAL,
                    description="网格不封闭（非水密），切片器无法正确推断实体区域",
                    evidence=f"is_watertight={wt.get('is_watertight')}, euler_number={wt.get('euler_number')}",
                    sub_task_id="check_watertight",
                )
        return None

    rules.append(ValidationRule("check_watertight", check_watertight))

    # ── 壁厚验证 ──
    if task_type in ("fdm_printability", "sla_printability"):
        min_wall = 0.8 if task_type == "fdm_printability" else 0.3
        printer_type = "FDM" if task_type == "fdm_printability" else "SLA"

        def check_thickness(result: Any, _min=min_wall, _type=printer_type) -> ValidationIssue | None:
            if isinstance(result, dict):
                thick = result.get("thickness", {})
                min_t = thick.get("min_thickness")
                approx = thick.get("approx_min_surface_distance")
                val = min_t if min_t is not None else approx
                if val is not None and val < _min:
                    return ValidationIssue(
                        severity=Severity.CRITICAL,
                        description=f"壁厚 {val:.2f}mm 低于 {_type} 最小要求 {_min}mm",
                        evidence=f"min_thickness={min_t}, approx={approx}",
                        sub_task_id="check_thickness",
                    )
            return None

        rules.append(ValidationRule("check_thickness", check_thickness))

    # ── 缺陷验证 ──
    def check_defects(result: Any) -> ValidationIssue | None:
        if isinstance(result, dict):
            defects = result.get("defects", {})
            # 检查非流形边
            nm = defects.get("non_manifold_edges", {})
            if nm.get("has_defect"):
                return ValidationIssue(
                    severity=Severity.CRITICAL,
                    description=f"存在非流形边（约 {nm.get('estimated_count', '?')} 条），影响网格拓扑正确性",
                    evidence=f"non_manifold_edges.has_defect=True",
                    sub_task_id="check_defects",
                )
            # 检查退化面
            deg = defects.get("degenerate_faces", {})
            if deg.get("has_defect"):
                return ValidationIssue(
                    severity=Severity.WARNING,
                    description=f"存在 {deg.get('count', '?')} 个退化面（面积为零的三角形）",
                    evidence=f"degenerate_faces.count={deg.get('count')}",
                    sub_task_id="check_defects",
                )
            # 检查法线一致性
            normals = defects.get("normals_consistent", {})
            if not normals.get("is_consistent", True):
                return ValidationIssue(
                    severity=Severity.WARNING,
                    description="面法线方向不一致，部分面可能朝内",
                    evidence="normals_consistent.is_consistent=False",
                    sub_task_id="check_defects",
                )
        return None

    rules.append(ValidationRule("check_defects", check_defects))

    # ── 悬垂验证（仅FDM）──
    if task_type == "fdm_printability":
        def check_overhangs(result: Any) -> ValidationIssue | None:
            if isinstance(result, dict):
                checks = result.get("checks", {})
                overhang = checks.get("overhangs", {})
                count = overhang.get("overhang_face_count", 0)
                if count and count > 0:
                    area = overhang.get("overhang_area_mm2", 0)
                    return ValidationIssue(
                        severity=Severity.WARNING,
                        description=f"检测到 {count} 个悬垂面（面积 {area:.1f}mm²），需要支撑结构",
                        evidence=f"overhang_face_count={count}, overhang_area={area}",
                        sub_task_id="check_overhangs",
                    )
            return None

        rules.append(ValidationRule("check_overhangs", check_overhangs))

    # ── 打印床适配验证 ──
    if task_type in ("fdm_printability", "sla_printability"):
        def check_bed_fit(result: Any) -> ValidationIssue | None:
            if isinstance(result, dict):
                bbox = result.get("bounding_box", {})
                dims = bbox.get("dimensions", {})
                x = dims.get("x", 0) or 0
                y = dims.get("y", 0) or 0
                z = dims.get("z", 0) or 0

                # FDM Ender 3 尺寸
                bed_x, bed_y, bed_z = 220.0, 220.0, 250.0
                if x > bed_x or y > bed_y or z > bed_z:
                    return ValidationIssue(
                        severity=Severity.CRITICAL,
                        description=f"模型尺寸 ({x:.1f}×{y:.1f}×{z:.1f}mm) 超出打印床 ({bed_x}×{bed_y}×{bed_z}mm)",
                        evidence=f"dimensions: {x:.1f}×{y:.1f}×{z:.1f}mm",
                        sub_task_id="check_bed_fit",
                    )
            return None

        rules.append(ValidationRule("check_bed_fit", check_bed_fit))

    return rules


# ──────────────────────────────────────────────
# 推理代理主体
# ──────────────────────────────────────────────

class ReasoningAgent:
    """多步推理代理

    实现 ReAct 循环：
      1. 理解用户问题，分类并分解为子任务
      2. 顺序执行子任务，传递中间结果
      3. 验证每个子任务的结果
      4. 异常时尝试替代方案（自我修正）
      5. 汇总所有证据，形成有据可依的结论
    """

    def __init__(self, tool_registry: dict[str, Callable] | None = None):
        """初始化推理代理

        Args:
            tool_registry: 工具注册表，键为工具名，值为可调用函数
        """
        self._tools: dict[str, Callable] = tool_registry or {}
        self._trace: list[ReasoningStep] = []

    def register_tool(self, name: str, fn: Callable) -> None:
        """注册工具函数"""
        self._tools[name] = fn

    def reason(
        self,
        question: str,
        file_path: str,
        max_retries: int = 1,
    ) -> ReasoningResult:
        """执行多步推理

        Args:
            question: 用户的问题
            file_path: 3D模型文件路径
            max_retries: 每个子任务的最大重试次数

        Returns:
            推理结果，包含结论、问题列表和步骤记录
        """
        self._trace = []

        # ── 第一步：任务分解 ──
        task_type = classify_question(question)
        self._trace.append(ReasoningStep(
            step_type="decompose",
            description=f"问题分类: {task_type}，开始分解子任务",
            data={"question": question, "task_type": task_type},
        ))

        sub_tasks = self._decompose(task_type, file_path)
        self._trace.append(ReasoningStep(
            step_type="decompose",
            description=f"分解为 {len(sub_tasks)} 个子任务",
            data={"sub_task_ids": [t.task_id for t in sub_tasks]},
        ))

        # ── 第二步：顺序执行子任务 ──
        sub_results: dict[str, Any] = {}
        for task in sub_tasks:
            self._execute_sub_task(task, sub_results, max_retries)

        # ── 第三步：验证结果 ──
        issues = self._validate_results(task_type, sub_results)
        self._trace.append(ReasoningStep(
            step_type="validate",
            description=f"验证完成，发现 {len(issues)} 个问题",
            data={"issue_count": len(issues), "issues": [
                {"severity": i.severity.value, "description": i.description} for i in issues
            ]},
        ))

        # ── 第四步：自我修正（对失败的任务尝试替代方案）──
        failed_tasks = [t for t in sub_tasks if t.status == StepStatus.FAILED]
        if failed_tasks:
            self._self_correct(failed_tasks, sub_results, file_path)
            # 重新验证
            issues = self._validate_results(task_type, sub_results)

        # ── 第五步：组装结论 ──
        conclusion = self._assemble_conclusion(question, task_type, sub_results, issues)
        self._trace.append(ReasoningStep(
            step_type="conclude",
            description="推理完成",
            data={"conclusion_length": len(conclusion), "issue_count": len(issues)},
        ))

        return ReasoningResult(
            conclusion=conclusion,
            issues=issues,
            steps=self._trace,
            sub_task_results=sub_results,
            success=len([i for i in issues if i.severity == Severity.CRITICAL]) == 0,
        )

    def _decompose(self, task_type: str, file_path: str) -> list[SubTask]:
        """将任务类型分解为子任务列表"""
        template = TASK_TEMPLATES.get(task_type, TASK_TEMPLATES["mesh_quality"])

        sub_tasks: list[SubTask] = []
        for tmpl in template:
            # 将 file_path 注入工具参数
            args = dict(tmpl["tool_args"])
            if "file_path" not in args:
                args["file_path"] = file_path

            sub_tasks.append(SubTask(
                task_id=tmpl["task_id"],
                description=tmpl["description"],
                tool_name=tmpl["tool_name"],
                tool_args=args,
                depends_on=tmpl.get("depends_on", []),
                max_retries=1,
            ))

        return sub_tasks

    def _execute_sub_task(
        self,
        task: SubTask,
        sub_results: dict[str, Any],
        max_retries: int,
    ) -> None:
        """执行单个子任务"""
        task.status = StepStatus.RUNNING
        self._trace.append(ReasoningStep(
            step_type="execute",
            description=f"执行子任务: {task.description}",
            data={"task_id": task.task_id, "tool": task.tool_name},
        ))

        # 检查依赖是否完成
        for dep_id in task.depends_on:
            dep_result = sub_results.get(dep_id)
            if dep_result is None:
                self._trace.append(ReasoningStep(
                    step_type="execute",
                    description=f"子任务 {task.task_id} 的依赖 {dep_id} 未完成，跳过",
                ))
                task.status = StepStatus.FAILED
                task.error = f"依赖 {dep_id} 未完成"
                return

        # 执行工具
        tool_fn = self._tools.get(task.tool_name)
        if tool_fn is None:
            task.status = StepStatus.FAILED
            task.error = f"工具 {task.tool_name} 未注册"
            self._trace.append(ReasoningStep(
                step_type="execute",
                description=f"工具 {task.tool_name} 未注册",
                data={"task_id": task.task_id},
            ))
            return

        for attempt in range(max_retries + 1):
            try:
                result = tool_fn(**task.tool_args)
                task.result = result
                task.status = StepStatus.COMPLETED
                sub_results[task.task_id] = result

                self._trace.append(ReasoningStep(
                    step_type="execute",
                    description=f"子任务 {task.task_id} 完成",
                    data={"task_id": task.task_id, "attempt": attempt},
                ))
                return

            except Exception as e:
                task.retry_count = attempt
                if attempt < max_retries:
                    task.status = StepStatus.RETRYING
                    self._trace.append(ReasoningStep(
                        step_type="execute",
                        description=f"子任务 {task.task_id} 失败，重试中 ({attempt+1}/{max_retries})",
                        data={"error": str(e)},
                    ))
                else:
                    task.status = StepStatus.FAILED
                    task.error = str(e)
                    sub_results[task.task_id] = {"error": str(e)}
                    self._trace.append(ReasoningStep(
                        step_type="execute",
                        description=f"子任务 {task.task_id} 最终失败: {e}",
                        data={"error": str(e), "attempts": attempt + 1},
                    ))

    def _validate_results(
        self,
        task_type: str,
        sub_results: dict[str, Any],
    ) -> list[ValidationIssue]:
        """验证子任务结果"""
        rules = _build_validation_rules(task_type)
        issues: list[ValidationIssue] = []

        for rule in rules:
            result = sub_results.get(rule.sub_task_id)
            if result is not None:
                issue = rule.validate(result)
                if issue is not None:
                    issues.append(issue)

        return issues

    def _self_correct(
        self,
        failed_tasks: list[SubTask],
        sub_results: dict[str, Any],
        file_path: str,
    ) -> None:
        """对失败的子任务尝试替代方案

        替代策略：
          - analyze_mesh 失败 → 尝试 detect_defects
          - check_3d_printability 失败 → 尝试用 analyze_mesh 的部分结果推断
          - compute_geometry 失败 → 尝试用 analyze_mesh 的结果替代
        """
        self._trace.append(ReasoningStep(
            step_type="correct",
            description=f"尝试自我修正 {len(failed_tasks)} 个失败任务",
        ))

        for task in failed_tasks:
            # 替代方案映射
            alternatives: dict[str, list[dict[str, Any]]] = {
                "analyze_mesh": [
                    {"tool_name": "detect_defects", "tool_args": {"file_path": file_path}},
                ],
                "check_3d_printability": [
                    {"tool_name": "analyze_mesh", "tool_args": {
                        "file_path": file_path,
                        "analysis_types": ["watertight", "bounding_box", "defects"],
                    }},
                ],
                "compute_geometry": [
                    {"tool_name": "analyze_mesh", "tool_args": {
                        "file_path": file_path,
                        "analysis_types": ["volume", "surface_area", "bounding_box"],
                    }},
                ],
            }

            alts = alternatives.get(task.tool_name, [])
            for alt in alts:
                alt_tool = alt["tool_name"]
                alt_args = alt["tool_args"]
                alt_fn = self._tools.get(alt_tool)

                if alt_fn is None:
                    continue

                try:
                    result = alt_fn(**alt_args)
                    sub_results[task.task_id] = result
                    task.status = StepStatus.COMPLETED
                    task.result = result

                    self._trace.append(ReasoningStep(
                        step_type="correct",
                        description=f"子任务 {task.task_id} 通过替代方案 {alt_tool} 修正成功",
                        data={"original_tool": task.tool_name, "alternative_tool": alt_tool},
                    ))
                    break

                except Exception as e:
                    self._trace.append(ReasoningStep(
                        step_type="correct",
                        description=f"替代方案 {alt_tool} 也失败: {e}",
                        data={"error": str(e)},
                    ))

    def _assemble_conclusion(
        self,
        question: str,
        task_type: str,
        sub_results: dict[str, Any],
        issues: list[ValidationIssue],
    ) -> str:
        """汇总所有子结果，组装有据可依的结论"""
        lines: list[str] = []

        # 标题
        type_names = {
            "fdm_printability": "FDM 3D打印适用性",
            "sla_printability": "SLA 3D打印适用性",
            "mesh_quality": "网格质量",
            "geometry_analysis": "几何分析",
            "robotics_readiness": "机器人应用就绪度",
        }
        title = type_names.get(task_type, "综合分析")
        lines.append(f"## {title}评估报告\n")

        # 总体结论
        critical_count = len([i for i in issues if i.severity == Severity.CRITICAL])
        warning_count = len([i for i in issues if i.severity == Severity.WARNING])

        if critical_count > 0:
            lines.append(f"**结论: 不通过** — 发现 {critical_count} 个严重问题和 {warning_count} 个警告\n")
        elif warning_count > 0:
            lines.append(f"**结论: 有条件通过** — 发现 {warning_count} 个警告，无严重问题\n")
        else:
            lines.append("**结论: 通过** — 未发现严重问题或警告\n")

        # 详细结果
        lines.append("### 检查结果详情\n")

        for task_id, result in sub_results.items():
            if result is None:
                continue
            if isinstance(result, dict) and "error" in result:
                lines.append(f"- **{task_id}**: ❌ 执行失败 ({result['error']})")
                continue

            # 根据任务类型格式化结果
            formatted = self._format_sub_result(task_id, result)
            if formatted:
                lines.append(formatted)

        # 问题列表
        if issues:
            lines.append("\n### 发现的问题\n")
            for i, issue in enumerate(issues, 1):
                icon = "🔴" if issue.severity == Severity.CRITICAL else "🟡" if issue.severity == Severity.WARNING else "ℹ️"
                lines.append(f"{i}. {icon} **[{issue.severity.value.upper()}]** {issue.description}")
                lines.append(f"   - 证据: {issue.evidence}")
                lines.append(f"   - 关联步骤: {issue.sub_task_id}")

        # 建议
        if issues:
            lines.append("\n### 修复建议\n")
            for issue in issues:
                suggestion = self._get_fix_suggestion(issue)
                if suggestion:
                    lines.append(f"- {suggestion}")

        return "\n".join(lines)

    def _format_sub_result(self, task_id: str, result: Any) -> str:
        """格式化子任务结果为可读文本"""
        if not isinstance(result, dict):
            return f"- **{task_id}**: {result}"

        if task_id == "check_watertight":
            wt = result.get("watertight", {})
            is_wt = wt.get("is_watertight")
            icon = "✅" if is_wt else "❌"
            return f"- **水密性检查**: {icon} {'封闭' if is_wt else '不封闭'} (欧拉数: {wt.get('euler_number', '?')})"

        elif task_id == "check_thickness":
            thick = result.get("thickness", {})
            min_t = thick.get("min_thickness")
            approx = thick.get("approx_min_surface_distance")
            val = min_t if min_t is not None else approx
            if val is not None:
                return f"- **壁厚检查**: 最小壁厚 {val:.2f}mm"
            else:
                return f"- **壁厚检查**: 无法精确测量（{thick.get('note', '原因未知')}）"

        elif task_id in ("check_overhangs", "check_sla"):
            checks = result.get("checks", {})
            overall = result.get("overall_result", "?")
            icon = "✅" if overall == "PASS" else "❌"
            overhang = checks.get("overhangs", {})
            oh_count = overhang.get("overhang_face_count", 0)
            detail = f", 悬垂面: {oh_count}" if oh_count else ""
            return f"- **打印适用性**: {icon} {overall}{detail}"

        elif task_id == "check_bed_fit":
            bbox = result.get("bounding_box", {})
            dims = bbox.get("dimensions", {})
            return f"- **打印床适配**: 尺寸 {dims.get('x', 0):.1f}×{dims.get('y', 0):.1f}×{dims.get('z', 0):.1f}mm"

        elif task_id == "check_defects":
            defects = result.get("defects", {})
            if isinstance(result.get("total_defects"), int):
                # 来自 detect_defects
                status = result.get("overall_status", "?")
                total = result.get("total_defects", 0)
                icon = "✅" if status == "OK" else "⚠️" if status == "WARNING" else "❌"
                return f"- **缺陷检查**: {icon} {status} ({total} 个缺陷)"
            else:
                # 来自 analyze_mesh
                deg = defects.get("degenerate_faces", {})
                nm = defects.get("non_manifold_edges", {})
                normals = defects.get("normals_consistent", {})
                parts = []
                if deg.get("has_defect"):
                    parts.append(f"退化面: {deg.get('count', '?')}")
                if nm.get("has_defect"):
                    parts.append("非流形边")
                if not normals.get("is_consistent", True):
                    parts.append("法线不一致")
                if not parts:
                    parts.append("无缺陷")
                return f"- **缺陷检查**: {', '.join(parts)}"

        elif task_id == "check_euler":
            euler = result.get("euler_number", {})
            return f"- **拓扑检查**: 欧拉数={euler.get('euler_number', '?')}, V={euler.get('vertices', '?')}, E={euler.get('edges', '?')}, F={euler.get('faces', '?')}"

        elif task_id == "check_normals":
            defects = result.get("defects", {})
            normals = defects.get("normals_consistent", {})
            is_consistent = normals.get("is_consistent", True)
            icon = "✅" if is_consistent else "⚠️"
            return f"- **法线一致性**: {icon} {'一致' if is_consistent else '不一致'}"

        elif task_id == "check_volume":
            vol = result.get("volume", {})
            centroid = result.get("centroid", {})
            vol_val = vol.get("value_mm3")
            if vol_val is not None:
                return f"- **体积**: {vol_val:.2f} mm³ ({vol_val/1000:.4f} cm³)"
            return f"- **体积**: 无法计算"

        elif task_id == "check_surface":
            sa = result.get("surface_area", {})
            sa_val = sa.get("value_mm2")
            if sa_val is not None:
                return f"- **表面积**: {sa_val:.2f} mm²"
            return f"- **表面积**: 无法计算"

        elif task_id == "check_inertia":
            moi = result.get("moment_of_inertia", {})
            if moi.get("matrix") is not None:
                return f"- **惯性张量**: 已计算 (3×3 矩阵)"
            return f"- **惯性张量**: 无法计算（网格不封闭）"

        elif task_id == "check_compactness":
            compact = result.get("compactness", {})
            ratio = compact.get("ratio")
            if ratio is not None:
                return f"- **紧凑度**: {ratio:.4f} (1.0=完全凸)"
            return f"- **紧凑度**: 无法计算"

        # 通用格式
        return f"- **{task_id}**: 已完成"

    def _get_fix_suggestion(self, issue: ValidationIssue) -> str:
        """根据问题类型给出修复建议"""
        desc = issue.description.lower()

        if "不封闭" in desc or "非水密" in desc or "watertight" in desc.lower():
            return "使用网格修复工具（如 MeshLab/Netfabb）封闭孔洞，确保每条边恰好被两个面共享"

        if "壁厚" in desc or "thickness" in desc.lower():
            return "增加薄壁区域的厚度，FDM 建议至少 0.8mm，SLA 建议至少 0.3mm"

        if "非流形" in desc or "non-manifold" in desc.lower():
            return "沿非流形边拆分网格，删除多余的三角形，或使用 MeshLab 的 Remove Non-Manifold Edges 过滤器"

        if "悬垂" in desc or "overhang" in desc.lower():
            return "添加支撑结构，或重新设计模型使用倒角/圆角替代直角悬垂"

        if "法线" in desc or "normal" in desc.lower():
            return "使用法线一致化工具（如 MeshLab 的重新定向面法线功能）修复法线方向"

        if "退化" in desc or "degenerate" in desc.lower():
            return "删除退化面并修复由此产生的孔洞"

        if "打印床" in desc or "尺寸" in desc or "超出" in desc:
            return "缩小模型或分割为多个部分分别打印"

        return f"针对此问题进行针对性修复: {issue.description}"


# ──────────────────────────────────────────────
# 便捷函数：创建预配置的推理代理
# ──────────────────────────────────────────────

def create_reasoning_agent() -> ReasoningAgent:
    """创建预配置了 MCP Server 工具的推理代理

    Returns:
        配置完成的 ReasoningAgent 实例
    """
    from mcp_server.server import (
        analyze_mesh,
        check_3d_printability,
        compute_geometry,
        detect_defects,
    )

    agent = ReasoningAgent()
    agent.register_tool("analyze_mesh", analyze_mesh)
    agent.register_tool("check_3d_printability", check_3d_printability)
    agent.register_tool("compute_geometry", compute_geometry)
    agent.register_tool("detect_defects", detect_defects)

    return agent
