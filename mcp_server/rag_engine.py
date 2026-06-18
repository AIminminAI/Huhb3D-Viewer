"""
RAG Engine for 3D Geometry Analysis - 基于嵌入的检索增强生成引擎

使用 sentence-transformers 生成文档/查询嵌入，FAISS 进行高效向量检索。
若 FAISS 不可用，自动回退到 numpy 余弦相似度检索。

核心流程:
  1. 文档语义分块 (按段落/章节切分，非固定行数)
  2. 嵌入向量化 (all-MiniLM-L6-v2, 384维)
  3. FAISS 索引构建与检索
  4. 相似度重排序
  5. 上下文组装 (含来源引用)
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 尝试导入可选依赖
# ──────────────────────────────────────────────
_EMBEDDING_AVAILABLE = False
_FAISS_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    _EMBEDDING_AVAILABLE = True
except ImportError:
    logger.info("sentence-transformers 未安装，将使用 TF-IDF 回退方案")

try:
    import faiss  # type: ignore
    _FAISS_AVAILABLE = True
except ImportError:
    logger.info("faiss-cpu 未安装，将使用 numpy 余弦相似度回退")


# ──────────────────────────────────────────────
# 数据结构
# ──────────────────────────────────────────────

@dataclass
class DocumentChunk:
    """文档分块，含元数据"""
    content: str
    source: str
    section: str
    chunk_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalResult:
    """检索结果"""
    chunk: DocumentChunk
    score: float  # 相似度分数，越高越相关


# ──────────────────────────────────────────────
# 3D几何知识库 - 真实技术内容
# ──────────────────────────────────────────────

GEOMETRY_KNOWLEDGE_BASE: list[dict[str, str]] = [
    {
        "source": "mesh_topology",
        "section": "watertight",
        "content": (
            "水密网格（watertight mesh）是指没有孔洞、所有边恰好被两个面共享的封闭三角网格。"
            "在3D打印中，水密性是最基本的要求——切片器需要明确区分模型的内部和外部，"
            "如果网格存在孔洞或非流形边，切片器将无法正确推断实体区域，导致切片失败或产生不完整的打印结果。"
            "检测水密性的标准方法是验证每条边恰好被两个三角形引用，同时欧拉数 V-E+F=2（单连通闭曲面）。"
        ),
    },
    {
        "source": "mesh_topology",
        "section": "non_manifold",
        "content": (
            "非流形边（non-manifold edge）是指被三个或更多三角形共享的边，或者仅被一个三角形引用的边界边。"
            "非流形边在3D建模中是严重的拓扑错误，它使得网格无法定义清晰的内外区域。"
            "常见原因包括：两个独立网格在公共边上意外合并、T型交叉（T-junction）未正确处理、"
            "或布尔运算后未清理结果。修复方法包括：沿非流形边拆分网格、删除多余的三角形、"
            "或使用网格修复工具（如 MeshLab 的 Filter > Cleaning and Repair > Remove Non-Manifold Edges）。"
        ),
    },
    {
        "source": "mesh_topology",
        "section": "degenerate_faces",
        "content": (
            "退化面（degenerate face）是面积为零或接近零的三角形，通常由三个共线顶点或两个重合顶点形成。"
            "退化面不会影响渲染结果，但会导致网格体积和表面积计算错误，也可能使切片器崩溃。"
            "检测方法：计算每个三角形的面积，若小于阈值（如 1e-10 mm²）则标记为退化面。"
            "修复方法：删除退化面，然后检查并修复由此产生的孔洞。"
            "在 STL 文件中，退化面还可能表现为法线为零向量的情况。"
        ),
    },
    {
        "source": "3d_printing",
        "section": "wall_thickness",
        "content": (
            "壁厚是3D打印中最关键的设计参数之一。FDM打印的最小壁厚通常为 0.8mm（约2条挤出线，喷嘴0.4mm），"
            "低于此值挤出线无法稳定堆叠。SLA打印由于光固化特性，最小壁厚可达 0.3mm。"
            "壁厚不足会导致打印件脆弱、变形甚至完全失败。对于功能件，建议壁厚至少 1.2mm（FDM）或 0.6mm（SLA）。"
            "测量壁厚的方法包括：射线投射法（从表面发射射线到对面）、"
            "基于体素的距离场方法、以及基于采样的最近点对距离估计。"
        ),
    },
    {
        "source": "3d_printing",
        "section": "overhang",
        "content": (
            "悬垂（overhang）是指3D打印中下方没有支撑材料的水平延伸部分。FDM打印中，"
            "超过45度的悬垂角度通常需要支撑结构，否则会出现下垂、拉丝或塌陷。"
            "悬垂角度定义为面法线与Z轴负方向的夹角——当法线Z分量小于 -cos(45°) ≈ -0.707 时，"
            "该面被视为悬垂面。减少支撑需求的设计策略包括：使用倒角代替直角、"
            "将模型旋转到减少悬垂的朝向、使用树状支撑（tree supports）代替线性支撑。"
            "SLA打印由于自下而上的固化方式，同样需要支撑但角度阈值更宽松。"
        ),
    },
    {
        "source": "3d_printing",
        "section": "support_structures",
        "content": (
            "支撑结构是3D打印中为悬垂部分提供临时基础的辅助结构。FDM常用线性支撑和树状支撑："
            "线性支撑生成快但难以去除且留痕明显，树状支撑接触面积小、易去除但生成慢。"
            "支撑的密度通常设为 10-20%，过密浪费材料且难去除，过疏则支撑不足。"
            "支撑Z距离（支撑与模型之间的间隙）通常设为层高的 1-2 倍，"
            "以确保支撑可以去除同时模型表面质量可接受。SLA打印的支撑需要考虑剥离力，"
            "接触点应尽量小以减少表面损伤。"
        ),
    },
    {
        "source": "mesh_topology",
        "section": "euler_number",
        "content": (
            "欧拉数（Euler number）是网格拓扑的基本不变量，定义为 V - E + F，其中 V 是顶点数、"
            "E 是边数、F 是面数。对于单连通的封闭曲面（如球面），欧拉数恒为 2。"
            "每增加一个贯通孔洞（如甜甜圈形状），欧拉数减 2。因此欧拉数可用于快速判断网格的拓扑类型。"
            "如果网格的欧拉数不是 2 但声称是水密的，说明存在拓扑错误（如内部面、非流形边等）。"
            "欧拉数的计算复杂度为 O(n)，是非常高效的网格完整性初筛工具。"
        ),
    },
    {
        "source": "geometry_analysis",
        "section": "curvature",
        "content": (
            "曲率估计是3D几何分析的核心任务之一。常用方法包括：(1) 拟合二次曲面法——"
            "对每个顶点的邻域拟合二次曲面，解析计算主曲率；(2) 离散微分算子——"
            "使用 cotangent 权重的 Laplace-Beltrami 算子估计平均曲率；"
            "(3) 法线差分法——通过相邻面法线的变化率近似曲率。"
            "主曲率 k1 和 k2 可进一步推导出高斯曲率 K=k1*k2 和平均曲率 H=(k1+k2)/2。"
            "曲率分析在网格简化、特征线提取和网格分割中有广泛应用。"
        ),
    },
    {
        "source": "geometry_analysis",
        "section": "bvh",
        "content": (
            "层次包围盒（BVH, Bounding Volume Hierarchy）是3D几何计算中最重要的加速结构之一。"
            "BVH 将空间中的三角形组织成一棵树，每个节点存储其子树的包围盒，"
            "查询时通过包围盒测试快速剪枝，将 O(n) 的暴力搜索降为 O(log n)。"
            "BVH 在射线投射、碰撞检测、最近点查询中不可或缺。"
            "常用构建策略包括：中点分割（Midpoint Split）、表面积启发式（SAH, Surface Area Heuristic）、"
            "和线性BVH（LBVH，适合GPU并行构建）。SAH通过最小化射线命中节点的期望代价来选择最优分割平面，"
            "通常能产生最高质量的BVH。"
        ),
    },
    {
        "source": "robotics",
        "section": "sim2real",
        "content": (
            "仿真到现实的域差距（Sim-to-Real Domain Gap）是机器人学习中的核心挑战。"
            "在仿真环境中训练的策略往往无法直接迁移到真实世界，原因包括：物理参数不精确"
            "（摩擦系数、质量分布、关节阻尼）、传感器噪声模型差异、延迟和通信抖动、"
            "以及视觉渲染差异（光照、纹理、反射）。缩小域差距的常用策略包括："
            "域随机化（Domain Randomization）——在训练时随机化仿真参数使策略更鲁棒；"
            "系统辨识（System Identification）——从真实数据估计物理参数；"
            "渐进式迁移（Progressive Transfer）——逐步增加仿真与现实的差异。"
        ),
    },
    {
        "source": "robotics",
        "section": "bop_format",
        "content": (
            "BOP格式是6DoF位姿估计的标准数据格式，由 BOP Benchmark 定义。"
            "每个物体由一个3D模型（通常为PLY格式）和一组RGB-D图像及标注组成。"
            "标注文件 scene_gt.json 包含每帧中每个物体的：物体ID、2D边界框、"
            "3D平移向量（cam_t_m2c，单位毫米）、3x3旋转矩阵（cam_R_m2c）。"
            "相机参数存储在 scene_camera.json 中，包含内参矩阵 cam_K 和深度缩放因子。"
            "BOP格式的评估指标包括：AR（Average Recall）、VSD（Visible Surface Discrepancy）、"
            "MSSD 和 MSPD，分别衡量不同条件下的位姿估计精度。"
        ),
    },
    {
        "source": "mesh_topology",
        "section": "self_intersection",
        "content": (
            "自相交（self-intersection）是指网格中三角形面之间互相穿透的现象。"
            "自相交使网格的体积定义变得模糊——无法确定哪些区域是实体内部，哪些是外部。"
            "这对3D打印是致命问题：切片器可能产生错误的刀具路径，导致打印失败。"
            "检测自相交的精确方法是逐对测试三角形相交，复杂度 O(n²)；"
            "使用BVH加速可将复杂度降至 O(n log n)。近似方法包括："
            "检查网格体积与凸包体积的比值（比值异常低可能暗示自相交）、"
            "或使用有向距离场（SDF）检测符号不一致的区域。"
        ),
    },
    {
        "source": "3d_printing",
        "section": "fdm_guidelines",
        "content": (
            "FDM（熔融沉积成型）是最普及的3D打印技术，其设计约束包括："
            "最小壁厚 0.8mm（0.4mm喷嘴）、最大悬垂角度 45°、层高通常 0.1-0.3mm、"
            "推荐打印温度 190-230°C（PLA）。FDM的各向异性是重要考虑因素——"
            "Z方向的层间结合力远低于XY方向的层内强度，通常只有 30-50%。"
            "因此承受载荷的零件应尽量使主应力方向平行于XY平面。"
            "FDM常见缺陷包括：翘曲（由热收缩引起，大平底件最严重）、拉丝（回抽不足）、"
            "和层偏移（Z轴机械问题）。"
        ),
    },
    {
        "source": "3d_printing",
        "section": "sla_guidelines",
        "content": (
            "SLA（立体光固化）打印使用紫外激光或LCD屏固化液态树脂，精度远高于FDM。"
            "设计约束包括：最小壁厚 0.3mm、最小孔径 0.5mm、最小凸起细节 0.1mm。"
            "SLA打印需要支撑结构来固定悬垂部分和抵抗剥离力。"
            "封闭内腔会困住未固化的树脂，需要在设计中添加排水孔（至少 2mm 直径）。"
            "SLA打印件在固化后仍需后处理：异丙醇清洗、UV二次固化。"
            "SLA树脂的机械性能差异大：标准树脂脆性高、韧性树脂抗冲击但精度略低、"
            "耐高温树脂可承受 200°C 以上但收缩率更大。"
        ),
    },
    {
        "source": "geometry_analysis",
        "section": "mesh_simplification",
        "content": (
            "网格简化（mesh simplification）是在保持形状特征的前提下减少三角形数量的技术。"
            "最经典的方法是 Garland-Heckbert 的二次误差度量（QEM, Quadric Error Metrics）："
            "对每条边计算折叠后的二次误差，优先折叠误差最小的边。"
            "QEM的核心思想是每个顶点关联一个4x4二次误差矩阵，"
            "该矩阵编码了该顶点到所有相邻面的距离平方和。"
            "边折叠后新顶点的位置通过最小化二次误差确定。"
            "其他简化方法包括：顶点聚类（将空间划分为网格，合并同一格内的顶点）、"
            "和渐进网格（Progressive Mesh，记录简化操作以支持连续细节层次）。"
        ),
    },
    {
        "source": "geometry_analysis",
        "section": "remeshing",
        "content": (
            "重网格化（remeshing）是将输入网格转换为满足特定质量标准的新网格的过程。"
            "常见目标包括：均匀化三角形大小、改善三角形形状（趋近等边三角形）、"
            "和适应曲率（高曲率区域更密的三角形）。"
            "最常用的方法是 Instant Meshes 的联合优化：同时优化位置和方向场，"
            "然后沿方向场参数化生成四边形网格。对于三角形重网格化，"
            "Open3D 的 isotropic remeshing 通过反复执行边分裂、边折叠和边翻转来改善网格质量。"
            "重网格化在有限元分析前处理中尤为重要——网格质量直接影响数值计算的精度和收敛性。"
        ),
    },
    {
        "source": "robotics",
        "section": "grasp_planning",
        "content": (
            "抓取规划（grasp planning）是机器人操作的基础问题，目标是找到稳定抓取物体的手部构型。"
            "力封闭（force closure）抓取是指通过接触点的摩擦力可以抵抗任意外力和力矩的抓取。"
            "判断力封闭的充要条件是接触力旋（wrench）的正锥体张成整个6维力旋空间。"
            "基于3D模型的抓取规划通常分为：(1) 采样候选抓取姿态；"
            "(2) 使用物理仿真评估抓取稳定性；(3) 选择最优抓取。"
            "深度学习方法（如 GraspNet、Contact-GraspNet）直接从点云预测抓取姿态，"
            "速度远快于传统采样-评估方法，但泛化性依赖训练数据多样性。"
        ),
    },
    {
        "source": "geometry_analysis",
        "section": "point_cloud",
        "content": (
            "点云（point cloud）是3D扫描和深度相机最原始的输出形式，由大量三维坐标点组成。"
            "点云处理的核心任务包括：配准（registration，将多视角点云对齐到统一坐标系）、"
            "滤波（filtering，去除噪声点）、分割（segmentation，分离不同物体或区域）、"
            "和表面重建（surface reconstruction，从点云生成三角网格）。"
            "ICP（Iterative Closest Point）是最经典的点云配准算法，"
            "通过迭代优化最近点对应关系来估计刚体变换。"
            "表面重建常用方法包括：Poisson 重建（隐式方法，输出水密网格）、"
            "Ball Pivoting（显式方法，可处理非均匀采样）和 Delaunay 三角化。"
        ),
    },
    {
        "source": "mesh_topology",
        "section": "normals",
        "content": (
            "面法线一致性（normal consistency）是指网格中所有三角形面的法线方向一致朝外。"
            "法线不一致会导致3D打印切片错误——切片器无法确定哪一侧是实体内部。"
            "检测方法：遍历所有共享边的相邻面，检查它们的法线是否一致（叉积方向一致）。"
            "修复方法：从任意面开始广度优先传播一致的绕序（winding order），"
            "或使用 trimesh 的 fix_normals 功能。STL格式存储面法线信息，"
            "但许多导出器不保证法线一致性，因此加载后验证和修复法线是标准流程。"
        ),
    },
    {
        "source": "geometry_analysis",
        "section": "hausdorff_distance",
        "content": (
            "Hausdorff距离是衡量两个3D形状之间差异的标准度量。"
            "有向Hausdorff距离 h(A,B) = max{min{d(a,b) : b∈B} : a∈A}，"
            "表示A中任一点到B最近点的最大距离。对称Hausdorff距离取两个方向的最大值。"
            "Hausdorff距离对局部异常值非常敏感（因为取最大值），"
            "因此实践中常用平均Hausdorff距离或百分位Hausdorff距离作为更鲁棒的替代。"
            "计算精确Hausdorff距离需要 O(n*m) 时间，使用BVH加速可降至 O((n+m)log(n+m))。"
            "在3D模型比较、简化质量评估和数字孪生验证中广泛使用。"
        ),
    },
    {
        "source": "3d_printing",
        "section": "infill",
        "content": (
            "填充（infill）是3D打印中内部实体区域的填充模式。FDM打印通常不使用100%填充，"
            "而是采用网格状填充以节省材料和时间。常见填充模式包括：网格（grid，最基础）、"
            "三角形（triangular，各方向强度均匀）、六边形（hexagonal，强度/重量比最优）、"
            "和陀螺仪（gyroid，各向同性且剪切强度高）。填充密度通常设为 15-25%（装饰件）"
            "或 50-80%（功能件）。100%填充仅用于需要最大强度的场合，"
            "但会增加打印时间、材料消耗和翘曲风险。"
        ),
    },
    {
        "source": "robotics",
        "section": "pose_estimation",
        "content": (
            "6DoF位姿估计（6DoF Pose Estimation）是确定物体在相机坐标系下3D位置和3D旋转的任务。"
            "主流方法分为三类：(1) 基于对应关系的方法——先建立2D-3D对应，再用PnP求解位姿；"
            "(2) 基于投票的方法——在位姿空间中投票，如PVNet通过向量场预测关键点；"
            "(3) 基于回归的方法——直接从图像回归位姿参数，如PoseCNN。"
            "当前SOTA方法（如 OnePose、GDRNet）结合了多种策略。"
            "评估指标 ADD（Average Distance of Model Points）计算变换后模型点的平均偏差，"
            "对于对称物体使用 ADD-S（基于最近点距离的平均偏差）。"
        ),
    },
    {
        "source": "geometry_analysis",
        "section": "convex_hull",
        "content": (
            "凸包（convex hull）是包含网格所有顶点的最小凸多面体。"
            "凸包在3D几何分析中有多种用途：计算紧凑度（网格体积/凸包体积）衡量凹凸程度、"
            "检测困住树脂的封闭内腔（SLA打印）、碰撞检测中的粗筛阶段、"
            "以及作为网格修复的参考。Qhull是计算凸包的标准算法库，时间复杂度 O(n log n)。"
            "紧凑度接近1.0表示模型接近凸体，值越低表示凹入程度越大。"
            "在SLA打印中，如果网格体积远小于凸包体积（如比值<0.3），"
            "可能存在困住未固化树脂的封闭内腔。"
        ),
    },
]


# ──────────────────────────────────────────────
# 语义分块器
# ──────────────────────────────────────────────

class SemanticChunker:
    """语义分块器：按段落/章节切分文档，非固定行数"""

    @staticmethod
    def chunk_text(
        text: str,
        source: str = "unknown",
        section: str = "default",
        max_chunk_size: int = 500,
        overlap_sentences: int = 1,
    ) -> list[DocumentChunk]:
        """将文本按语义段落分块

        Args:
            text: 待分块的文本
            source: 来源标识
            section: 章节标识
            max_chunk_size: 单个块的最大字符数
            overlap_sentences: 块之间重叠的句子数

        Returns:
            分块列表
        """
        # 按段落分割（空行或换行符）
        paragraphs = re.split(r'\n\s*\n|\r\n\s*\r\n', text.strip())
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        chunks: list[DocumentChunk] = []
        current_content = ""
        chunk_index = 0

        for para in paragraphs:
            # 如果当前块加上新段落不超过限制，合并
            if len(current_content) + len(para) + 1 <= max_chunk_size:
                current_content = f"{current_content}\n{para}" if current_content else para
            else:
                # 保存当前块
                if current_content:
                    chunks.append(SemanticChunker._make_chunk(
                        current_content, source, section, chunk_index
                    ))
                    chunk_index += 1

                # 如果单个段落超过限制，按句子再分割
                if len(para) > max_chunk_size:
                    sentences = re.split(r'(?<=[。！？.!?])\s*', para)
                    sentences = [s for s in sentences if s.strip()]

                    sentence_buffer = ""
                    for sent in sentences:
                        if len(sentence_buffer) + len(sent) + 1 <= max_chunk_size:
                            sentence_buffer = f"{sentence_buffer} {sent}" if sentence_buffer else sent
                        else:
                            if sentence_buffer:
                                chunks.append(SemanticChunker._make_chunk(
                                    sentence_buffer, source, section, chunk_index
                                ))
                                chunk_index += 1
                            sentence_buffer = sent

                    current_content = sentence_buffer
                else:
                    current_content = para

        # 保存最后一个块
        if current_content:
            chunks.append(SemanticChunker._make_chunk(
                current_content, source, section, chunk_index
            ))

        return chunks

    @staticmethod
    def _make_chunk(content: str, source: str, section: str, index: int) -> DocumentChunk:
        """创建文档分块"""
        chunk_id = hashlib.md5(f"{source}:{section}:{index}:{content[:50]}".encode()).hexdigest()[:12]
        return DocumentChunk(
            content=content.strip(),
            source=source,
            section=section,
            chunk_id=chunk_id,
            metadata={"index": index, "char_count": len(content)},
        )


# ──────────────────────────────────────────────
# TF-IDF 回退嵌入器
# ──────────────────────────────────────────────

class TFIDFEmbedder:
    """TF-IDF 嵌入器，当 sentence-transformers 不可用时使用"""

    def __init__(self, dim: int = 384):
        self.dim = dim
        self._vocabulary: dict[str, int] = {}
        self._idf: dict[str, float] = {}
        self._doc_count = 0

    def _tokenize(self, text: str) -> list[str]:
        """简单分词：中英文混合"""
        # 提取英文单词和中文单字
        tokens = re.findall(r'[a-zA-Z]+|[\u4e00-\u9fff]', text.lower())
        return tokens

    def fit(self, documents: list[str]) -> None:
        """构建词汇表和 IDF 权重"""
        self._doc_count = len(documents)
        doc_freq: dict[str, int] = {}

        for doc in documents:
            tokens = set(self._tokenize(doc))
            for token in tokens:
                doc_freq[token] = doc_freq.get(token, 0) + 1

        # 选取频率最高的词作为词汇表（限制维度）
        sorted_tokens = sorted(doc_freq.items(), key=lambda x: -x[1])
        vocab_size = min(self.dim, len(sorted_tokens))
        self._vocabulary = {token: idx for idx, (token, _) in enumerate(sorted_tokens[:vocab_size])}

        # 计算 IDF
        for token, freq in doc_freq.items():
            if token in self._vocabulary:
                self._idf[token] = np.log((self._doc_count + 1) / (freq + 1)) + 1.0

    def embed(self, text: str) -> np.ndarray:
        """将文本嵌入为向量"""
        tokens = self._tokenize(text)
        vec = np.zeros(self.dim, dtype=np.float32)

        # 计算 TF
        tf: dict[str, float] = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1.0
        total = len(tokens) if tokens else 1
        for token, count in tf.items():
            tf[token] = count / total

        # TF-IDF 向量化
        for token, tf_val in tf.items():
            if token in self._vocabulary:
                idx = self._vocabulary[token]
                idf_val = self._idf.get(token, 1.0)
                vec[idx] = tf_val * idf_val

        # L2 归一化
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm

        return vec


# ──────────────────────────────────────────────
# RAG 引擎主体
# ──────────────────────────────────────────────

class RAGEngine:
    """检索增强生成引擎

    核心组件:
      - 语义分块器 (SemanticChunker)
      - 嵌入器 (SentenceTransformer 或 TF-IDF 回退)
      - 向量索引 (FAISS 或 numpy 余弦相似度回退)
      - 重排序器 (相似度重排序)
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        similarity_threshold: float = 0.5,
        top_k: int = 5,
    ):
        self.similarity_threshold = similarity_threshold
        self.top_k = top_k
        self.model_name = model_name

        # 文档存储
        self._chunks: list[DocumentChunk] = []

        # 嵌入矩阵
        self._embeddings: np.ndarray | None = None

        # 嵌入器
        self._embedder: SentenceTransformer | TFIDFEmbedder | None = None
        self._use_transformer = False

        # FAISS 索引
        self._faiss_index: Any | None = None
        self._use_faiss = False

        # 初始化嵌入器
        self._init_embedder()

    def _init_embedder(self) -> None:
        """初始化嵌入模型"""
        if _EMBEDDING_AVAILABLE:
            try:
                self._embedder = SentenceTransformer(self.model_name)
                self._use_transformer = True
                logger.info(f"RAG引擎: 使用 SentenceTransformer ({self.model_name})")
            except Exception as e:
                logger.warning(f"SentenceTransformer 加载失败: {e}，回退到 TF-IDF")
                self._embedder = TFIDFEmbedder()
        else:
            self._embedder = TFIDFEmbedder()
            logger.info("RAG引擎: 使用 TF-IDF 嵌入器")

    def add_documents(self, documents: list[dict[str, str]]) -> None:
        """添加文档到知识库

        Args:
            documents: 文档列表，每个文档包含 source, section, content 字段
        """
        chunker = SemanticChunker()
        new_chunks: list[DocumentChunk] = []

        for doc in documents:
            content = doc.get("content", "")
            source = doc.get("source", "unknown")
            section = doc.get("section", "default")

            if not content.strip():
                continue

            chunks = chunker.chunk_text(
                content,
                source=source,
                section=section,
                max_chunk_size=500,
            )
            new_chunks.extend(chunks)

        self._chunks.extend(new_chunks)
        logger.info(f"添加 {len(new_chunks)} 个文档块，总计 {len(self._chunks)} 个")

        # 重建索引
        self._build_index()

    def _build_index(self) -> None:
        """构建向量索引"""
        if not self._chunks:
            return

        # 生成嵌入
        texts = [chunk.content for chunk in self._chunks]

        if self._use_transformer and isinstance(self._embedder, SentenceTransformer):
            embeddings = self._embedder.encode(texts, normalize_embeddings=True)
            self._embeddings = np.array(embeddings, dtype=np.float32)
        elif isinstance(self._embedder, TFIDFEmbedder):
            self._embedder.fit(texts)
            embeddings = [self._embedder.embed(t) for t in texts]
            self._embeddings = np.array(embeddings, dtype=np.float32)
        else:
            logger.error("嵌入器未初始化")
            return

        # 构建 FAISS 索引
        if _FAISS_AVAILABLE and self._embeddings is not None:
            dim = self._embeddings.shape[1]
            self._faiss_index = faiss.IndexFlatIP(dim)  # 内积索引（配合归一化向量等同余弦相似度）
            faiss.normalize_L2(self._embeddings)
            self._faiss_index.add(self._embeddings)
            self._use_faiss = True
            logger.info(f"FAISS 索引构建完成: {self._faiss_index.ntotal} 个向量, 维度={dim}")
        else:
            # numpy 回退：确保 L2 归一化
            if self._embeddings is not None:
                norms = np.linalg.norm(self._embeddings, axis=1, keepdims=True)
                norms[norms == 0] = 1.0
                self._embeddings = self._embeddings / norms
            self._use_faiss = False
            logger.info("使用 numpy 余弦相似度检索")

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        threshold: float | None = None,
    ) -> list[RetrievalResult]:
        """检索与查询最相关的文档块

        Args:
            query: 查询文本
            top_k: 返回的最大结果数，默认使用初始化时的值
            threshold: 相似度阈值，默认使用初始化时的值

        Returns:
            检索结果列表，按相似度降序排列
        """
        if not self._chunks or self._embeddings is None:
            return []

        k = top_k or self.top_k
        thresh = threshold if threshold is not None else self.similarity_threshold

        # 生成查询嵌入
        query_embedding = self._embed_query(query)
        if query_embedding is None:
            return []

        # 检索
        if self._use_faiss and self._faiss_index is not None:
            results = self._retrieve_faiss(query_embedding, k, thresh)
        else:
            results = self._retrieve_numpy(query_embedding, k, thresh)

        # 重排序
        results = self._rerank(query, results)

        return results

    def _embed_query(self, query: str) -> np.ndarray | None:
        """生成查询的嵌入向量"""
        if self._use_transformer and isinstance(self._embedder, SentenceTransformer):
            embedding = self._embedder.encode([query], normalize_embeddings=True)
            return np.array(embedding, dtype=np.float32).flatten()
        elif isinstance(self._embedder, TFIDFEmbedder):
            vec = self._embedder.embed(query)
            return vec
        return None

    def _retrieve_faiss(
        self, query_embedding: np.ndarray, k: int, threshold: float
    ) -> list[RetrievalResult]:
        """使用 FAISS 检索"""
        query_vec = query_embedding.reshape(1, -1)
        faiss.normalize_L2(query_vec)

        scores, indices = self._faiss_index.search(query_vec, min(k * 2, len(self._chunks)))

        results: list[RetrievalResult] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or score < threshold:
                continue
            results.append(RetrievalResult(
                chunk=self._chunks[idx],
                score=float(score),
            ))

        return results[:k]

    def _retrieve_numpy(
        self, query_embedding: np.ndarray, k: int, threshold: float
    ) -> list[RetrievalResult]:
        """使用 numpy 余弦相似度检索"""
        # 计算余弦相似度
        similarities = np.dot(self._embeddings, query_embedding)

        # 排序
        top_indices = np.argsort(similarities)[::-1][:k * 2]

        results: list[RetrievalResult] = []
        for idx in top_indices:
            score = float(similarities[idx])
            if score < threshold:
                continue
            results.append(RetrievalResult(
                chunk=self._chunks[idx],
                score=score,
            ))
            if len(results) >= k:
                break

        return results

    def _rerank(self, query: str, results: list[RetrievalResult]) -> list[RetrievalResult]:
        """简单重排序：基于查询词覆盖率和相似度的综合评分

        对检索结果进行二次排序，优先选择：
        1. 查询关键词覆盖率高的文档
        2. 原始相似度分数高的文档
        """
        if not results:
            return results

        query_tokens = set(re.findall(r'[a-zA-Z]+|[\u4e00-\u9fff]', query.lower()))

        scored_results: list[tuple[float, RetrievalResult]] = []
        for result in results:
            # 关键词覆盖率
            chunk_tokens = set(re.findall(r'[a-zA-Z]+|[\u4e00-\u9fff]', result.chunk.content.lower()))
            if query_tokens:
                coverage = len(query_tokens & chunk_tokens) / len(query_tokens)
            else:
                coverage = 0.0

            # 综合评分：70% 相似度 + 30% 关键词覆盖率
            combined_score = 0.7 * result.score + 0.3 * coverage
            scored_results.append((combined_score, result))

        # 按综合评分降序排序
        scored_results.sort(key=lambda x: -x[0])

        return [r for _, r in scored_results]

    def assemble_context(
        self,
        results: list[RetrievalResult],
        max_context_length: int = 3000,
    ) -> str:
        """将检索结果组装为上下文字符串，含来源引用

        Args:
            results: 检索结果列表
            max_context_length: 上下文最大字符数

        Returns:
            格式化的上下文字符串
        """
        if not results:
            return ""

        context_parts: list[str] = []
        current_length = 0

        for i, result in enumerate(results, 1):
            chunk = result.chunk
            citation = f"[{i}] 来源: {chunk.source}/{chunk.section} (相似度: {result.score:.3f})"
            entry = f"{citation}\n{chunk.content}"

            if current_length + len(entry) > max_context_length:
                break

            context_parts.append(entry)
            current_length += len(entry)

        return "\n\n---\n\n".join(context_parts)

    def query_with_context(
        self,
        query: str,
        top_k: int | None = None,
        threshold: float | None = None,
        max_context_length: int = 3000,
    ) -> dict[str, Any]:
        """完整的 RAG 查询流程：检索 + 组装上下文

        Args:
            query: 查询文本
            top_k: 返回的最大结果数
            threshold: 相似度阈值
            max_context_length: 上下文最大字符数

        Returns:
            包含上下文、来源和元数据的字典
        """
        results = self.retrieve(query, top_k=top_k, threshold=threshold)
        context = self.assemble_context(results, max_context_length)

        sources = [
            {
                "source": r.chunk.source,
                "section": r.chunk.section,
                "chunk_id": r.chunk.chunk_id,
                "score": round(r.score, 4),
            }
            for r in results
        ]

        return {
            "query": query,
            "context": context,
            "sources": sources,
            "num_results": len(results),
        }


# ──────────────────────────────────────────────
# 便捷函数：创建预填充知识库的 RAG 引擎
# ──────────────────────────────────────────────

def create_geometry_rag_engine(
    similarity_threshold: float = 0.15,
    top_k: int = 5,
) -> RAGEngine:
    """创建预填充3D几何知识库的 RAG 引擎

    Args:
        similarity_threshold: 相似度阈值（TF-IDF 模式下默认较低，因为稀疏向量余弦相似度偏低）
        top_k: 返回的最大结果数

    Returns:
        初始化完成的 RAGEngine 实例
    """
    engine = RAGEngine(
        similarity_threshold=similarity_threshold,
        top_k=top_k,
    )
    engine.add_documents(GEOMETRY_KNOWLEDGE_BASE)
    return engine
