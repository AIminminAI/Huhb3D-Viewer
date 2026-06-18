"""
STEP-AI-Analyzer — STEP文件AI智能分析工具包 (v3.0)
=====================================================
第一个开源的"STEP文件 + AI智能分析"工具。

核心流程：上传STEP文件 → 纯Python解析提取数据 → 喂给LLM → 智能分析报告

功能：
1. STEP文件拓扑解析（纯Python，无需OpenCASCADE）
2. AI驱动的特征识别（LLM替代规则引擎）
3. AI驱动的可制造性审核
4. AI驱动的加工建议
5. AI驱动的成本估算
6. AI驱动的自然语言问答

部署到 HuggingFace Spaces（免费 CPU 托管）。
支持 DeepSeek / OpenAI / 任何OpenAI兼容API。
"""

import json
import math
import os
import re
import sys
import tempfile
import time
import logging
from collections import defaultdict
from pathlib import Path

import gradio as gr

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("step-ai-analyzer")

# ============================================================
# LLM 配置
# ============================================================

LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")

# ============================================================
# STEP文件解析器（纯Python，无需OpenCASCADE）
# ============================================================

GEOM_TYPE_MAP = {
    "PLANE": "PLANE",
    "CYLINDRICAL_SURFACE": "CYLINDER",
    "CONICAL_SURFACE": "CONE",
    "SPHERICAL_SURFACE": "SPHERE",
    "TOROIDAL_SURFACE": "TORUS",
    "B_SPLINE_SURFACE_WITH_KNOTS": "BSPLINE",
    "B_SPLINE_SURFACE": "BSPLINE",
    "SURFACE_OF_REVOLUTION": "REVOLUTION",
    "SURFACE_OF_LINEAR_EXTRUSION": "EXTRUSION",
}


def _parse_step_text(step_path):
    """纯Python解析STEP文件，提取面和几何信息"""
    with open(step_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    entity_pattern = re.compile(r'#(\d+)\s*=\s*(\w+)\s*\(([^)]*(?:\([^)]*\))*[^)]*)\)', re.DOTALL)
    entities = {}
    for match in entity_pattern.finditer(content):
        eid = int(match.group(1))
        etype = match.group(2)
        eargs = match.group(3)
        entities[eid] = {"type": etype, "args": eargs}

    faces_data = []
    face_id = 0

    for eid, entity in entities.items():
        if entity["type"] != "ADVANCED_FACE":
            continue

        args = entity["args"]
        refs = re.findall(r'#(\d+)', args)
        surface_ref = None
        if len(refs) >= 3:
            surface_ref = int(refs[2])

        geom_type = "UNKNOWN"
        radius = None

        if surface_ref and surface_ref in entities:
            surface_entity = entities[surface_ref]
            if surface_entity["type"] in GEOM_TYPE_MAP:
                geom_type = GEOM_TYPE_MAP[surface_entity["type"]]
                if surface_entity["type"] == "CYLINDRICAL_SURFACE":
                    parts = surface_entity["args"].split(',')
                    if len(parts) > 0:
                        try:
                            radius = float(parts[0].strip())
                        except ValueError:
                            pass
            else:
                visited = set()
                queue = [surface_ref]
                while queue:
                    current = queue.pop(0)
                    if current in visited:
                        continue
                    visited.add(current)
                    if current in entities:
                        ce = entities[current]
                        if ce["type"] in GEOM_TYPE_MAP:
                            geom_type = GEOM_TYPE_MAP[ce["type"]]
                            if ce["type"] == "CYLINDRICAL_SURFACE":
                                parts = ce["args"].split(',')
                                if len(parts) > 0:
                                    try:
                                        radius = float(parts[0].strip())
                                    except ValueError:
                                        pass
                            break
                        for ref in re.findall(r'#(\d+)', ce["args"]):
                            queue.append(int(ref))

        face_info = {
            "face_id": face_id,
            "step_entity_id": eid,
            "geom_type": geom_type,
        }
        if radius is not None:
            face_info["radius_mm"] = round(radius, 4)

        faces_data.append(face_info)
        face_id += 1

    # 提取包围盒
    all_coords = re.findall(r'CARTESIAN_POINT\s*\([^)]*\(([^)]+)\)\)', content)
    xs, ys, zs = [], [], []
    for coord_str in all_coords:
        parts = coord_str.split(',')
        if len(parts) >= 3:
            try:
                xs.append(float(parts[0].strip()))
                ys.append(float(parts[1].strip()))
                zs.append(float(parts[2].strip()))
            except ValueError:
                pass

    shape_bounds = [0, 0, 0, 0, 0, 0]
    if xs:
        shape_bounds = [min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)]

    dx = shape_bounds[3] - shape_bounds[0] if len(shape_bounds) > 3 else 0
    dy = shape_bounds[4] - shape_bounds[1] if len(shape_bounds) > 4 else 0
    dz = shape_bounds[5] - shape_bounds[2] if len(shape_bounds) > 5 else 0
    bbox_volume = dx * dy * dz

    # 统计面类型
    face_type_counts = defaultdict(int)
    for face in faces_data:
        face_type_counts[face["geom_type"]] += 1

    # 提取零件名
    product_names = re.findall(r"PRODUCT\s*\(\s*'([^']+)'", content)
    part_names = [p for p in product_names if not (len(p) == 36 and p.count("-") == 4)]

    # 提取单位
    unit_match = re.search(r'LENGTH_UNIT\s*\([^)]*SI_UNIT\s*\([^)]*\)\s*\)\s*\)', content)

    complexity = min(len(faces_data) / 10, 3.0)

    return {
        "source_file": Path(step_path).name,
        "part_names": part_names[:5],
        "total_faces": len(faces_data),
        "total_entities": len(entities),
        "shape_bounds_mm": [round(v, 4) for v in shape_bounds],
        "bbox_dimensions_mm": [round(dx, 2), round(dy, 2), round(dz, 2)],
        "bbox_volume_mm3": round(bbox_volume, 2),
        "face_type_counts": dict(face_type_counts),
        "faces": faces_data,
        "complexity_score": round(complexity, 2),
    }


def _build_step_summary(topology):
    """构建STEP文件摘要，用于LLM上下文"""
    dims = topology.get("bbox_dimensions_mm", [0, 0, 0])
    face_counts = topology.get("face_type_counts", {})

    summary = f"""STEP文件分析数据：
- 文件名: {topology['source_file']}
- 零件名: {', '.join(topology.get('part_names', ['未知']))}
- 包围盒尺寸: {dims[0]} x {dims[1]} x {dims[2]} mm
- 包围盒体积: {topology['bbox_volume_mm3']} mm³
- 总面数: {topology['total_faces']}
- STEP实体数: {topology['total_entities']}
- 复杂度评分: {topology['complexity_score']}x
- 面类型统计:"""

    for ftype, count in sorted(face_counts.items(), key=lambda x: -x[1]):
        summary += f"\n  - {ftype}: {count}"

    # 添加孔特征详情
    holes = [f for f in topology["faces"] if f["geom_type"] == "CYLINDER" and f.get("radius_mm")]
    if holes:
        summary += "\n- 孔/圆柱特征详情:"
        for h in holes:
            r = h.get("radius_mm", 0)
            d = r * 2
            summary += f"\n  - 孔径 Φ{d:.2f}mm (半径 {r:.2f}mm)"

    return summary


# ============================================================
# LLM 调用
# ============================================================

def _call_llm(system_prompt, user_prompt, temperature=0.3):
    """调用LLM API（兼容DeepSeek/OpenAI/任何OpenAI兼容API）"""
    if not LLM_API_KEY:
        return "⚠️ 未配置LLM API Key。请在环境变量中设置 LLM_API_KEY。\n\n可使用 DeepSeek API（https://platform.deepseek.com），1元=100万tokens。"

    try:
        import openai
        client = openai.OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=2000,
        )
        return response.choices[0].message.content
    except ImportError:
        return "⚠️ 请安装 openai 库：pip install openai"
    except Exception as e:
        logger.error(f"LLM调用失败: {e}")
        return f"⚠️ LLM调用失败: {str(e)}"


# ============================================================
# AI驱动的分析功能
# ============================================================

SYSTEM_PROMPT_ENGINEER = """你是一位资深的CNC加工工艺工程师，拥有20年的机械设计和制造经验。
你精通STEP文件格式、CNC加工工艺、可制造性设计(DFM)、材料选择和成本估算。

你的分析应该：
1. 基于提供的STEP文件数据，给出专业、准确的分析
2. 使用Markdown格式输出，清晰易读
3. 给出具体的数值和建议，不要泛泛而谈
4. 如果数据不足以做出准确判断，请明确说明
5. 用中文回答"""


def ai_feature_recognition(topology):
    """AI驱动的特征识别"""
    step_summary = _build_step_summary(topology)
    prompt = f"""请分析以下STEP文件数据，识别零件的制造特征。

{step_summary}

请识别以下类型的特征：
1. 加工特征：孔（通孔/盲孔/螺纹孔）、槽（通槽/盲槽/键槽）、台阶、倒角、圆角
2. 钣金特征：折弯、翻边、冲孔
3. 铸造/注塑特征：拔模斜度、壁厚均匀性
4. 装配特征：螺纹、卡扣、定位销孔

请用表格列出每个特征的类型、尺寸、位置和加工建议。"""

    return _call_llm(SYSTEM_PROMPT_ENGINEER, prompt)


def ai_manufacturability_audit(topology):
    """AI驱动的可制造性审核"""
    step_summary = _build_step_summary(topology)
    prompt = f"""请对以下STEP文件数据进行可制造性(DFM)审核。

{step_summary}

请检查以下项目：
1. 深孔径比（孔深/孔径 > 5:1 为困难，> 8:1 为极难）
2. 最小壁厚（< 0.5mm 极难加工）
3. 最小圆角半径（< R0.5 需特殊刀具）
4. 锐角/锐边（无倒角/圆角过渡的平面转角）
5. 内部特征（是否需要5轴或电火花加工）
6. 大平面支撑（薄壁大平面易变形）
7. 刀具可达性（所有面是否都能被刀具到达）
8. 装夹方案（需要几次装夹）

请给出：
- 总体可制造性评分（0-100分）
- 每个问题的严重程度（ERROR/WARNING/INFO）
- 具体的修改建议"""

    return _call_llm(SYSTEM_PROMPT_ENGINEER, prompt)


def ai_process_recommendation(topology):
    """AI驱动的加工工艺推荐"""
    step_summary = _build_step_summary(topology)
    prompt = f"""请为以下STEP文件推荐加工工艺方案。

{step_summary}

请给出：
1. 推荐的加工工艺（CNC铣削/CNC车削/钣金/3D打印等）
2. 推荐的机床类型（3轴/4轴/5轴CNC加工中心、CNC车床等）
3. 工序清单（按加工顺序）
4. 每道工序的刀具选择
5. 预估加工时间
6. 装夹方案和次数
7. 需要的特殊工艺（热处理、表面处理等）"""

    return _call_llm(SYSTEM_PROMPT_ENGINEER, prompt)


def ai_cost_estimation(topology, material, quantity, finishing, tolerance):
    """AI驱动的成本估算"""
    step_summary = _build_step_summary(topology)
    prompt = f"""请为以下STEP文件估算CNC加工成本。

{step_summary}

用户指定条件：
- 材料: {material}
- 数量: {quantity}
- 表面处理: {finishing}
- 公差等级: {tolerance}

请给出：
1. 材料成本估算（毛坯尺寸、重量、单价）
2. 加工成本估算（机床费率、加工时间、难度系数）
3. 装夹成本（按数量分摊）
4. 表面处理成本
5. 单件总成本和报价
6. 批量折扣
7. 价格区间（低-高）

注意：给出人民币(CNY)价格，利润率按30%计算。"""

    return _call_llm(SYSTEM_PROMPT_ENGINEER, prompt)


def ai_qa(topology, question):
    """AI驱动的自然语言问答"""
    step_summary = _build_step_summary(topology)
    prompt = f"""基于以下STEP文件数据，回答用户的问题。

{step_summary}

用户问题：{question}

请给出专业、准确的回答。如果数据不足以回答，请说明需要什么额外信息。"""

    return _call_llm(SYSTEM_PROMPT_ENGINEER, prompt, temperature=0.5)


# ============================================================
# 离线分析（无LLM时的降级方案）
# 注意：以下材料价格为2024年市场参考价，实际价格请以供应商报价为准
# ============================================================

# 材料参考价格（来源：公开市场报价，仅供参考，非精确数据）
MATERIAL_PRICES = {
    "铝合金6061": {"price_per_kg": 28, "density": 2.70, "machinability": 1.0},
    "铝合金7075": {"price_per_kg": 55, "density": 2.81, "machinability": 0.9},
    "不锈钢304": {"price_per_kg": 22, "density": 7.93, "machinability": 0.6},
    "不锈钢316": {"price_per_kg": 35, "density": 7.99, "machinability": 0.55},
    "碳钢45#": {"price_per_kg": 8, "density": 7.85, "machinability": 0.85},
    "黄铜H62": {"price_per_kg": 45, "density": 8.50, "machinability": 1.1},
    "钛合金Ti6Al4V": {"price_per_kg": 380, "density": 4.43, "machinability": 0.3},
}


def _offline_analysis(topology, material, quantity, finishing, tolerance):
    """离线分析（无LLM时的降级方案）"""
    dims = topology.get("bbox_dimensions_mm", [0, 0, 0])
    face_counts = topology.get("face_type_counts", {})
    mat = MATERIAL_PRICES.get(material, MATERIAL_PRICES["铝合金6061"])

    # 粗略成本估算（以下系数均为行业经验估算值，非精确计算）
    bbox_vol = topology.get("bbox_volume_mm3", 1000)
    complexity = topology.get("complexity_score", 1.0)
    fill_factor = 0.15 + (complexity * 0.05)  # 经验估算：填充率15%-40%
    part_volume_cm3 = bbox_vol * min(fill_factor, 0.4) / 1000
    blank_volume_cm3 = part_volume_cm3 * 2.5  # 经验估算：毛坯体积为零件2.5倍
    material_weight_kg = (blank_volume_cm3 * mat["density"]) / 1000
    material_cost = material_weight_kg * mat["price_per_kg"]

    machining_time_min = 5 + len(topology["faces"]) * 2  # 经验估算：每面2分钟
    machine_rate = 120  # 经验估算：机床费率120元/小时
    machining_cost = (machining_time_min / 60) * machine_rate / mat["machinability"]

    per_part = material_cost + machining_cost
    total = per_part * quantity * 1.3  # 30%利润

    summary = f"""## 离线分析结果（未连接AI）

| 项目 | 结果 |
|------|------|
| 零件名 | {', '.join(topology.get('part_names', ['未知']))} |
| 尺寸 | {dims[0]} x {dims[1]} x {dims[2]} mm |
| 总面数 | {topology['total_faces']} |
| 复杂度 | {complexity:.1f}x |
| 材料 | {material} ({material_weight_kg:.4f}kg) |
| 单件成本 | ¥{per_part:.2f} |
| 单件报价 | ¥{per_part * 1.3:.2f} |
| {quantity}件总价 | ¥{total:.2f} |

> ⚠️ 这是离线估算，精度有限。配置LLM API后可获得AI智能分析。
"""

    # 面类型统计
    face_stats = "\n### 面类型统计\n"
    for ftype, count in sorted(face_counts.items(), key=lambda x: -x[1]):
        face_stats += f"- {ftype}: {count}\n"

    return summary + face_stats


# ============================================================
# 主分析函数
# ============================================================

def analyze_step_file(step_file, material, quantity, finishing, tolerance):
    """分析 STEP 文件"""
    if step_file is None:
        return "请上传 STEP/STP 文件", "", "", ""

    if isinstance(step_file, str):
        step_path = step_file
    elif hasattr(step_file, 'name'):
        step_path = step_file.name
    else:
        step_path = str(step_file)

    ext = Path(step_path).suffix.lower()
    if ext not in (".step", ".stp"):
        return f"不支持的文件格式: {ext}", "", "", ""

    try:
        qty = int(quantity) if quantity else 1
    except (ValueError, TypeError):
        qty = 1

    start_time = time.time()

    try:
        topology = _parse_step_text(step_path)
        elapsed = time.time() - start_time

        # 如果有LLM API Key，使用AI分析
        if LLM_API_KEY:
            feature_result = ai_feature_recognition(topology)
            audit_result = ai_manufacturability_audit(topology)
            process_result = ai_process_recommendation(topology)
            cost_result = ai_cost_estimation(topology, material, qty, finishing, tolerance)

            summary = f"""## AI分析完成 ({elapsed:.1f}秒解析 + AI分析)

| 项目 | 结果 |
|------|------|
| 文件 | {topology['source_file']} |
| 尺寸 | {topology['bbox_dimensions_mm'][0]} x {topology['bbox_dimensions_mm'][1]} x {topology['bbox_dimensions_mm'][2]} mm |
| 总面数 | {topology['total_faces']} |
| 复杂度 | {topology['complexity_score']}x |
| AI模型 | {LLM_MODEL} |

请查看下方各标签页的详细分析结果。"""

            return summary, feature_result, audit_result, process_result, cost_result
        else:
            # 离线分析
            offline_result = _offline_analysis(topology, material, qty, finishing, tolerance)
            return offline_result, "⚠️ 需要配置LLM API Key", "⚠️ 需要配置LLM API Key", "⚠️ 需要配置LLM API Key", "⚠️ 需要配置LLM API Key"

    except Exception as e:
        logger.error(f"分析出错: {e}", exc_info=True)
        return f"分析出错: {str(e)}", "", "", "", ""


def qa_step_file(step_file, question, history_state):
    """STEP文件自然语言问答"""
    if step_file is None:
        return "请先上传STEP文件", history_state

    if not question.strip():
        return "请输入问题", history_state

    if isinstance(step_file, str):
        step_path = step_file
    elif hasattr(step_file, 'name'):
        step_path = step_file.name
    else:
        step_path = str(step_file)

    try:
        topology = _parse_step_text(step_path)
        answer = ai_qa(topology, question)

        # 更新历史
        if history_state is None:
            history_state = []
        history_state.append((question, answer))

        # 格式化历史
        formatted = ""
        for q, a in history_state:
            formatted += f"**Q: {q}**\n\n{a}\n\n---\n\n"

        return formatted, history_state
    except Exception as e:
        return f"出错: {str(e)}", history_state


# ============================================================
# Gradio UI
# ============================================================

MATERIAL_CHOICES = list(MATERIAL_PRICES.keys())
FINISHING_CHOICES = ["无", "喷砂", "阳极氧化(本色)", "阳极氧化(着色)", "硬质阳极氧化", "电镀镍", "电镀铬", "发黑处理", "抛光", "拉丝"]
TOLERANCE_CHOICES = ["粗加工", "普通精度", "精密", "高精度"]

with gr.Blocks(title="STEP-AI-Analyzer — STEP文件AI智能分析", theme=gr.themes.Soft()) as demo:
    gr.Markdown("""
    # STEP-AI-Analyzer
    **第一个开源的 STEP文件 + AI智能分析 工具**

    上传 STEP 文件 → AI自动识别特征、审核可制造性、推荐工艺、估算成本

    支持任何 OpenAI 兼容 API（DeepSeek / OpenAI / 本地模型）
    """)

    with gr.Row():
        with gr.Column(scale=1):
            file_input = gr.File(
                label="上传 STEP 文件",
                file_types=[".step", ".stp"],
                type="filepath",
            )

            with gr.Row():
                material_input = gr.Dropdown(
                    choices=MATERIAL_CHOICES,
                    value="铝合金6061",
                    label="材料",
                )
                quantity_input = gr.Number(
                    value=10,
                    label="数量",
                    minimum=1,
                    maximum=10000,
                    step=1,
                )

            with gr.Row():
                finishing_input = gr.Dropdown(
                    choices=FINISHING_CHOICES,
                    value="无",
                    label="表面处理",
                )
                tolerance_input = gr.Dropdown(
                    choices=TOLERANCE_CHOICES,
                    value="普通精度",
                    label="公差等级",
                )

            analyze_btn = gr.Button("AI 智能分析", variant="primary", size="lg")

            gr.Markdown("""
            ### 关于
            - **开源项目**: [GitHub](https://github.com/AIminminAI/Huhb3D-Viewer)
            - **技术**: 纯Python STEP解析 + LLM智能分析
            - **无需OpenCASCADE**: 轻量部署，HF Space免费运行
            - **AI引擎**: DeepSeek / OpenAI / 任何兼容API

            ### 配置LLM
            设置环境变量：
            - `LLM_API_KEY`: API密钥
            - `LLM_BASE_URL`: API地址（默认DeepSeek）
            - `LLM_MODEL`: 模型名（默认deepseek-chat）

            DeepSeek: 1元=100万tokens
            """)

        with gr.Column(scale=2):
            summary_output = gr.Markdown(label="分析摘要")

    with gr.Row():
        with gr.Tabs():
            with gr.Tab("特征识别"):
                feature_output = gr.Markdown(label="AI特征识别")
            with gr.Tab("可制造性审核"):
                audit_output = gr.Markdown(label="AI可制造性审核")
            with gr.Tab("工艺推荐"):
                process_output = gr.Markdown(label="AI工艺推荐")
            with gr.Tab("成本估算"):
                cost_output = gr.Markdown(label="AI成本估算")

    # AI问答区
    gr.Markdown("---")
    gr.Markdown("### AI 问答（关于这个STEP文件的任何问题）")

    with gr.Row():
        qa_input = gr.Textbox(
            label="提问",
            placeholder="例如：这个零件能用3轴CNC加工吗？需要几次装夹？",
            lines=2,
        )
        qa_btn = gr.Button("提问", variant="secondary")

    qa_output = gr.Markdown(label="AI回答")
    qa_history = gr.State(None)

    analyze_btn.click(
        fn=analyze_step_file,
        inputs=[file_input, material_input, quantity_input, finishing_input, tolerance_input],
        outputs=[summary_output, feature_output, audit_output, process_output, cost_output],
    )

    qa_btn.click(
        fn=qa_step_file,
        inputs=[file_input, qa_input, qa_history],
        outputs=[qa_output, qa_history],
    )

    qa_input.submit(
        fn=qa_step_file,
        inputs=[file_input, qa_input, qa_history],
        outputs=[qa_output, qa_history],
    )

    gr.Markdown("""
    ---
    **STEP-AI-Analyzer** | Open Source STEP File AI Analysis | [GitHub](https://github.com/AIminminAI/Huhb3D-Viewer)
    """)


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
