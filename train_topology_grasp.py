"""
Huhb3D 拓扑感知抓取规划模型训练脚本
=====================================

本脚本是 Huhb3D 拓扑数据集的演示训练脚本，展示如何使用拓扑标注 + 抓取推荐数据
来训练一个拓扑感知的抓取规划模型。

这是"组合壁垒"策略的核心组件 —— 将数据 + 抓取推荐 + 训练脚本打包出售，
形成完整的商业价值闭环，而非单纯卖数据。

功能:
    1. 加载 topology_labels.json 和 grasp_recommendations.json 构建训练数据集
    2. 训练 TopologyGraspNet MLP 模型进行抓取方法分类
    3. 辅助输出夹爪类型预测
    4. 评估并输出混淆矩阵和各类别准确率
    5. 支持对新物体进行推理预测

用法:
    # 训练模式
    python train_topology_grasp.py --data-dir ./products/Huhb3D-Industrial-All --epochs 50 --batch-size 32

    # 推理模式
    python train_topology_grasp.py --predict --topology ./products/Huhb3D-Flange-Topology/objects/flange/topology_labels.json --model ./checkpoints/best_model.pt

商业说明:
    本脚本包含在 Huhb3D 商业数据包中，作为增值组件提供。
    客户购买数据包后可直接使用此脚本进行模型训练，
    无需从零开始编写训练代码，大幅降低使用门槛。
"""

import argparse
import json
import os
import random
import sys
from pathlib import Path

import numpy as np

# ===== 编码映射表 =====

# 抓取方法编码：8 个类别
GRASP_METHODS = {
    "vacuum_grip": 0,
    "expansion_grip": 1,
    "lateral_pinch": 2,
    "surface_grip": 3,
    "rim_grip": 4,
    "edge_grip": 5,
    "contour_grip": 6,
    "not_recommended": 7,
}

# 抓取方法反向映射（用于推理输出）
GRASP_METHOD_NAMES = {v: k for k, v in GRASP_METHODS.items()}

# 夹爪类型编码：5 个类别（含 none）
GRIPPER_TYPES = {
    "vacuum_cup": 0,
    "parallel_jaw": 1,
    "soft_gripper": 2,
    "expansion_gripper": 3,
    "vacuum_cup_or_gecko": 0,  # 映射为 vacuum_cup
    "none": 4,  # 用于 not_recommended
}

# 夹爪类型反向映射
GRIPPER_TYPE_NAMES = {0: "vacuum_cup", 1: "parallel_jaw", 2: "soft_gripper", 3: "expansion_gripper", 4: "none"}

# 几何类型编码
GEOM_TYPES = {
    "PLANE": 0,
    "CYLINDER": 1,
    "CONE": 2,
    "SPHERE": 3,
    "TORUS": 4,
    "OTHER": 5,
}

# 特征向量维度
FEATURE_DIM = 8  # [geom_type, category_id, area_norm, tri_count_norm, radius_or_0, normal_x, normal_y, normal_z]


def encode_gripper_type(gripper_type_str):
    """编码夹爪类型字符串为整数"""
    return GRIPPER_TYPES.get(gripper_type_str, 4)  # 未知类型映射为 none


def encode_geom_type(geom_type_str):
    """编码几何类型字符串为整数"""
    return GEOM_TYPES.get(geom_type_str, 5)  # 未知类型映射为 OTHER


def encode_grasp_method(method_str):
    """编码抓取方法字符串为整数"""
    return GRASP_METHODS.get(method_str, 7)  # 未知类型映射为 not_recommended


def get_normal_from_face(face):
    """
    从面的 extra 字段提取法线向量。
    平面使用 normal，圆柱/圆锥/环面使用 axis_direction，
    球面使用默认 [0,0,1]。
    """
    extra = face.get("extra", {})
    geom_type = face.get("geom_type", "")

    if geom_type == "PLANE" and "normal" in extra:
        n = extra["normal"]
        return [float(n[0]), float(n[1]), float(n[2])]
    elif geom_type in ("CYLINDER", "CONE", "TORUS") and "axis_direction" in extra:
        a = extra["axis_direction"]
        return [float(a[0]), float(a[1]), float(a[2])]
    elif geom_type == "SPHERE":
        return [0.0, 0.0, 1.0]
    else:
        # 默认法线
        return [0.0, 0.0, 1.0]


def get_radius_from_face(face):
    """从面的 extra 字段提取半径，无半径则返回 0.0"""
    extra = face.get("extra", {})
    return float(extra.get("radius", 0.0))


def build_face_feature(face, max_area, max_triangle_count):
    """
    构建单个面的特征向量。

    特征: [geom_type_encoded, category_id, area_normalized,
           triangle_count_normalized, radius_or_0, normal_x, normal_y, normal_z]

    参数:
        face: topology_labels.json 中的面对象
        max_area: 所有面中最大面积（用于归一化）
        max_triangle_count: 所有面中最大三角形数（用于归一化）

    返回:
        长度为 FEATURE_DIM 的 numpy 数组
    """
    geom_type = encode_geom_type(face.get("geom_type", "OTHER"))
    category_id = face.get("category_id", 0)
    area = face.get("area", 0.0)
    triangle_count = face.get("triangle_count", 0)
    radius = get_radius_from_face(face)
    normal = get_normal_from_face(face)

    # 归一化面积和三角形数，避免除零
    area_norm = area / max_area if max_area > 0 else 0.0
    tri_norm = triangle_count / max_triangle_count if max_triangle_count > 0 else 0.0

    feature = np.array([
        geom_type,
        category_id,
        area_norm,
        tri_norm,
        radius,
        normal[0],
        normal[1],
        normal[2],
    ], dtype=np.float32)

    return feature


def find_json_files(data_dir):
    """
    在数据目录中查找所有 topology_labels.json 和 grasp_recommendations.json 文件对。

    支持的目录结构:
        1. data_dir/objects/<obj_name>/topology_labels.json
        2. data_dir/<obj_name>/topology_labels.json
        3. data_dir/<obj_name>/topology/topology_labels.json
        4. data_dir/<obj_name>/topology_hd/topology_labels.json

    返回:
        列表，每个元素为 (topology_labels_path, grasp_recommendations_path, object_name)
    """
    data_path = Path(data_dir)
    pairs = []

    # 模式1: data_dir/objects/<obj_name>/
    objects_dir = data_path / "objects"
    if objects_dir.exists() and objects_dir.is_dir():
        for obj_dir in sorted(objects_dir.iterdir()):
            if not obj_dir.is_dir():
                continue
            pair = _find_pair_in_dir(obj_dir)
            if pair:
                pairs.append((pair[0], pair[1], obj_dir.name))

    # 模式2/3/4: data_dir/<obj_name>/
    if not pairs:
        for obj_dir in sorted(data_path.iterdir()):
            if not obj_dir.is_dir():
                continue
            pair = _find_pair_in_dir(obj_dir)
            if pair:
                pairs.append((pair[0], pair[1], obj_dir.name))

    # 模式5: data_dir 本身包含文件
    if not pairs:
        pair = _find_pair_in_dir(data_path)
        if pair:
            pairs.append((pair[0], pair[1], data_path.name))

    return pairs


def _find_pair_in_dir(obj_dir):
    """
    在单个目录中查找 topology_labels.json 和 grasp_recommendations.json 文件对。

    查找顺序:
        1. 目录直接包含
        2. topology/ 子目录
        3. topology_hd/ 子目录

    返回:
        (topology_labels_path, grasp_recommendations_path) 或 None
    """
    # 直接在目录下
    labels = obj_dir / "topology_labels.json"
    grasp = obj_dir / "grasp_recommendations.json"
    if labels.exists() and grasp.exists():
        return (str(labels), str(grasp))

    # topology/ 子目录
    labels = obj_dir / "topology" / "topology_labels.json"
    grasp = obj_dir / "grasp_recommendations.json"
    if labels.exists() and grasp.exists():
        return (str(labels), str(grasp))

    # topology_hd/ 子目录
    labels = obj_dir / "topology_hd" / "topology_labels.json"
    grasp = obj_dir / "grasp_recommendations.json"
    if labels.exists() and grasp.exists():
        return (str(labels), str(grasp))

    return None


def load_single_object(topology_labels_path, grasp_recommendations_path):
    """
    加载单个物体的拓扑标注和抓取推荐数据，构建特征-标签对。

    参数:
        topology_labels_path: topology_labels.json 文件路径
        grasp_recommendations_path: grasp_recommendations.json 文件路径

    返回:
        (features, grasp_labels, gripper_labels) 列表
        features: 面特征向量列表
        grasp_labels: 抓取方法标签列表
        gripper_labels: 夹爪类型标签列表
    """
    # 读取拓扑标注
    try:
        with open(topology_labels_path, "r", encoding="utf-8") as f:
            labels_data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"  [警告] 无法读取拓扑标注文件 {topology_labels_path}: {e}")
        return [], [], []

    # 读取抓取推荐
    try:
        with open(grasp_recommendations_path, "r", encoding="utf-8") as f:
            grasp_data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"  [警告] 无法读取抓取推荐文件 {grasp_recommendations_path}: {e}")
        return [], [], []

    faces = labels_data.get("faces", [])
    face_recs = grasp_data.get("face_recommendations", [])

    if not faces or not face_recs:
        print(f"  [警告] 数据为空: topology有{len(faces)}个面, grasp有{len(face_recs)}个推荐")
        return [], [], []

    # 构建 face_id -> grasp_recommendation 映射
    rec_map = {}
    for rec in face_recs:
        fid = rec.get("face_id", -1)
        rec_map[fid] = rec

    # 计算归一化参数
    max_area = max((face.get("area", 0.0) for face in faces), default=1.0)
    max_area = max(max_area, 1.0)  # 避免零除
    max_tri = max((face.get("triangle_count", 0) for face in faces), default=1)
    max_tri = max(max_tri, 1)

    features = []
    grasp_labels = []
    gripper_labels = []

    for face in faces:
        face_id = face.get("face_id", -1)
        rec = rec_map.get(face_id)

        if rec is None:
            # 没有对应的抓取推荐，跳过该面
            continue

        # 构建特征向量
        feature = build_face_feature(face, max_area, max_tri)

        # 构建标签
        grasp_method = rec.get("grasp_method", "not_recommended")
        gripper_type = rec.get("gripper_type", "none")

        grasp_label = encode_grasp_method(grasp_method)
        gripper_label = encode_gripper_type(gripper_type)

        features.append(feature)
        grasp_labels.append(grasp_label)
        gripper_labels.append(gripper_label)

    return features, grasp_labels, gripper_labels


class TopologyGraspDataset:
    """
    Huhb3D 拓扑抓取数据集。

    从数据目录中加载所有物体的 topology_labels.json 和 grasp_recommendations.json，
    构建面级特征向量和抓取方法标签。

    特征向量: [geom_type, category_id, area_norm, tri_count_norm, radius, normal_x, normal_y, normal_z]
    主标签: 抓取方法 (0-7)
    辅助标签: 夹爪类型 (0-4)
    """

    def __init__(self, features, grasp_labels, gripper_labels):
        """
        参数:
            features: numpy 数组 (N, 8)
            grasp_labels: numpy 数组 (N,)
            gripper_labels: numpy 数组 (N,)
        """
        self.features = features
        self.grasp_labels = grasp_labels
        self.gripper_labels = gripper_labels

    def __len__(self):
        return len(self.features)

    def __getitem__(self, idx):
        return (
            self.features[idx],
            self.grasp_labels[idx],
            self.gripper_labels[idx],
        )


def load_dataset(data_dir):
    """
    从数据目录加载所有物体数据，构建完整数据集。

    参数:
        data_dir: 数据根目录

    返回:
        (features, grasp_labels, gripper_labels) numpy 数组
    """
    pairs = find_json_files(data_dir)

    if not pairs:
        print(f"[错误] 未在 {data_dir} 中找到任何 topology_labels.json + grasp_recommendations.json 文件对")
        sys.exit(1)

    print(f"[信息] 找到 {len(pairs)} 个物体数据")

    all_features = []
    all_grasp_labels = []
    all_gripper_labels = []

    for topo_path, grasp_path, obj_name in pairs:
        features, grasp_labels, gripper_labels = load_single_object(topo_path, grasp_path)
        if features:
            all_features.extend(features)
            all_grasp_labels.extend(grasp_labels)
            all_gripper_labels.extend(gripper_labels)
            print(f"  [加载] {obj_name}: {len(features)} 个面样本")
        else:
            print(f"  [跳过] {obj_name}: 无有效数据")

    if not all_features:
        print("[错误] 没有加载到任何有效数据")
        sys.exit(1)

    features = np.array(all_features, dtype=np.float32)
    grasp_labels = np.array(all_grasp_labels, dtype=np.int64)
    gripper_labels = np.array(all_gripper_labels, dtype=np.int64)

    print(f"\n[统计] 总样本数: {len(features)}")
    print(f"[统计] 抓取方法分布:")
    for method_name, method_id in sorted(GRASP_METHODS.items(), key=lambda x: x[1]):
        count = int(np.sum(grasp_labels == method_id))
        if count > 0:
            print(f"  {method_name}: {count} ({count / len(grasp_labels) * 100:.1f}%)")
    print(f"[统计] 夹爪类型分布:")
    for type_name, type_id in sorted(GRIPPER_TYPE_NAMES.items(), key=lambda x: x[0]):
        count = int(np.sum(gripper_labels == type_id))
        if count > 0:
            print(f"  {type_name}: {count} ({count / len(gripper_labels) * 100:.1f}%)")

    return features, grasp_labels, gripper_labels


def split_dataset(features, grasp_labels, gripper_labels, train_ratio=0.8, seed=42):
    """
    将数据集按 train_ratio 比例划分为训练集和验证集。

    参数:
        features: 特征数组
        grasp_labels: 抓取方法标签数组
        gripper_labels: 夹爪类型标签数组
        train_ratio: 训练集比例（默认 0.8）
        seed: 随机种子

    返回:
        (train_dataset, val_dataset)
    """
    n = len(features)
    indices = list(range(n))
    random.seed(seed)
    random.shuffle(indices)

    split = int(n * train_ratio)
    train_idx = indices[:split]
    val_idx = indices[split:]

    train_dataset = TopologyGraspDataset(
        features[train_idx],
        grasp_labels[train_idx],
        gripper_labels[train_idx],
    )
    val_dataset = TopologyGraspDataset(
        features[val_idx],
        grasp_labels[val_idx],
        gripper_labels[val_idx],
    )

    print(f"\n[划分] 训练集: {len(train_dataset)} 样本, 验证集: {len(val_dataset)} 样本")

    return train_dataset, val_dataset


# ===== PyTorch 模型和训练 =====

def train_and_evaluate(train_dataset, val_dataset, epochs=50, batch_size=32, lr=0.001, checkpoint_dir="./checkpoints"):
    """
    训练 TopologyGraspNet 模型并评估。

    参数:
        train_dataset: 训练数据集
        val_dataset: 验证数据集
        epochs: 训练轮数
        batch_size: 批大小
        lr: 学习率
        checkpoint_dir: 模型保存目录
    """
    try:
        import torch
        import torch.nn as nn
        import torch.optim as optim
        from torch.utils.data import DataLoader, TensorDataset
    except ImportError:
        print("[错误] 需要安装 PyTorch: pip install torch")
        sys.exit(1)

    # 设置随机种子保证可复现
    torch.manual_seed(42)
    np.random.seed(42)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\n[训练] 使用设备: {device}")

    # ===== 模型定义 =====
    class TopologyGraspNet(nn.Module):
        """
        拓扑感知抓取规划网络。

        输入: 面特征向量 (dim=8)
        隐藏层: 128 -> 64 -> 32
        输出1: 抓取方法分类 (8 类)
        输出2: 夹爪类型辅助输出 (5 类)
        """

        def __init__(self, input_dim=FEATURE_DIM, num_grasp_classes=8, num_gripper_classes=5):
            super().__init__()
            # 共享特征提取层
            self.shared = nn.Sequential(
                nn.Linear(input_dim, 128),
                nn.ReLU(),
                nn.Dropout(0.2),
                nn.Linear(128, 64),
                nn.ReLU(),
                nn.Dropout(0.1),
                nn.Linear(64, 32),
                nn.ReLU(),
            )
            # 抓取方法分类头
            self.grasp_head = nn.Linear(32, num_grasp_classes)
            # 夹爪类型辅助分类头
            self.gripper_head = nn.Linear(32, num_gripper_classes)

        def forward(self, x):
            shared_feat = self.shared(x)
            grasp_out = self.grasp_head(shared_feat)
            gripper_out = self.gripper_head(shared_feat)
            return grasp_out, gripper_out

    # ===== 构建 DataLoader =====
    train_features = torch.tensor(train_dataset.features, dtype=torch.float32)
    train_grasp = torch.tensor(train_dataset.grasp_labels, dtype=torch.long)
    train_gripper = torch.tensor(train_dataset.gripper_labels, dtype=torch.long)

    val_features = torch.tensor(val_dataset.features, dtype=torch.float32)
    val_grasp = torch.tensor(val_dataset.grasp_labels, dtype=torch.long)
    val_gripper = torch.tensor(val_dataset.gripper_labels, dtype=torch.long)

    train_loader = DataLoader(
        TensorDataset(train_features, train_grasp, train_gripper),
        batch_size=batch_size,
        shuffle=True,
    )
    val_loader = DataLoader(
        TensorDataset(val_features, val_grasp, val_gripper),
        batch_size=batch_size,
        shuffle=False,
    )

    # ===== 初始化模型、损失函数、优化器 =====
    model = TopologyGraspNet().to(device)
    criterion_grasp = nn.CrossEntropyLoss()
    criterion_gripper = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=lr)

    # 辅助损失权重
    auxiliary_weight = 0.3

    # 创建保存目录
    os.makedirs(checkpoint_dir, exist_ok=True)
    best_model_path = os.path.join(checkpoint_dir, "best_model.pt")

    best_val_acc = 0.0

    # ===== 训练循环 =====
    print(f"\n{'='*70}")
    print(f"{'Epoch':>6} | {'训练损失':>10} | {'训练准确率':>10} | {'验证损失':>10} | {'验证准确率':>10}")
    print(f"{'='*70}")

    for epoch in range(1, epochs + 1):
        # 训练阶段
        model.train()
        train_loss_sum = 0.0
        train_correct = 0
        train_total = 0

        for batch_features, batch_grasp, batch_gripper in train_loader:
            batch_features = batch_features.to(device)
            batch_grasp = batch_grasp.to(device)
            batch_gripper = batch_gripper.to(device)

            optimizer.zero_grad()

            grasp_out, gripper_out = model(batch_features)

            loss_grasp = criterion_grasp(grasp_out, batch_grasp)
            loss_gripper = criterion_gripper(gripper_out, batch_gripper)
            loss = loss_grasp + auxiliary_weight * loss_gripper

            loss.backward()
            optimizer.step()

            train_loss_sum += loss.item() * batch_features.size(0)
            _, predicted = grasp_out.max(1)
            train_correct += predicted.eq(batch_grasp).sum().item()
            train_total += batch_features.size(0)

        train_loss = train_loss_sum / train_total
        train_acc = train_correct / train_total

        # 验证阶段
        model.eval()
        val_loss_sum = 0.0
        val_correct = 0
        val_total = 0

        with torch.no_grad():
            for batch_features, batch_grasp, batch_gripper in val_loader:
                batch_features = batch_features.to(device)
                batch_grasp = batch_grasp.to(device)
                batch_gripper = batch_gripper.to(device)

                grasp_out, gripper_out = model(batch_features)

                loss_grasp = criterion_grasp(grasp_out, batch_grasp)
                loss_gripper = criterion_gripper(gripper_out, batch_gripper)
                loss = loss_grasp + auxiliary_weight * loss_gripper

                val_loss_sum += loss.item() * batch_features.size(0)
                _, predicted = grasp_out.max(1)
                val_correct += predicted.eq(batch_grasp).sum().item()
                val_total += batch_features.size(0)

        val_loss = val_loss_sum / val_total
        val_acc = val_correct / val_total

        # 每 5 个 epoch 或最后一个 epoch 打印
        if epoch % 5 == 0 or epoch == 1 or epoch == epochs:
            print(f"{epoch:>6} | {train_loss:>10.4f} | {train_acc:>10.4f} | {val_loss:>10.4f} | {val_acc:>10.4f}")

        # 保存最佳模型
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "val_acc": val_acc,
                "train_acc": train_acc,
            }, best_model_path)

    print(f"{'='*70}")
    print(f"\n[完成] 训练结束，最佳验证准确率: {best_val_acc:.4f}")
    print(f"[保存] 最佳模型已保存至: {best_model_path}")

    # ===== 详细评估 =====
    print("\n" + "=" * 70)
    print("详细评估结果")
    print("=" * 70)

    # 加载最佳模型
    checkpoint = torch.load(best_model_path, map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    # 收集所有验证集预测
    all_preds = []
    all_labels = []

    with torch.no_grad():
        for batch_features, batch_grasp, batch_gripper in val_loader:
            batch_features = batch_features.to(device)
            grasp_out, _ = model(batch_features)
            _, predicted = grasp_out.max(1)
            all_preds.extend(predicted.cpu().numpy())
            all_labels.extend(batch_grasp.numpy())

    all_preds = np.array(all_preds)
    all_labels = np.array(all_labels)

    # 总体准确率
    overall_acc = np.mean(all_preds == all_labels)
    print(f"\n总体准确率: {overall_acc:.4f} ({np.sum(all_preds == all_labels)}/{len(all_labels)})")

    # 各类别准确率
    print(f"\n各类别抓取方法准确率:")
    print(f"{'类别':>20} | {'样本数':>6} | {'正确数':>6} | {'准确率':>8}")
    print("-" * 50)
    for method_name, method_id in sorted(GRASP_METHODS.items(), key=lambda x: x[1]):
        mask = all_labels == method_id
        count = int(np.sum(mask))
        if count > 0:
            correct = int(np.sum(all_preds[mask] == method_id))
            acc = correct / count
            print(f"{method_name:>20} | {count:>6} | {correct:>6} | {acc:>8.4f}")
        else:
            print(f"{method_name:>20} | {count:>6} | {'N/A':>6} | {'N/A':>8}")

    # 混淆矩阵
    num_classes = len(GRASP_METHODS)
    confusion = np.zeros((num_classes, num_classes), dtype=np.int64)
    for true_label, pred_label in zip(all_labels, all_preds):
        confusion[true_label][pred_label] += 1

    print(f"\n混淆矩阵 (行=真实标签, 列=预测标签):")
    # 表头
    header = f"{'真实\\预测':>18}"
    for method_name, _ in sorted(GRASP_METHODS.items(), key=lambda x: x[1]):
        header += f" {method_name[:6]:>6}"
    print(header)
    print("-" * len(header))

    for method_name, method_id in sorted(GRASP_METHODS.items(), key=lambda x: x[1]):
        row = f"{method_name:>18}"
        for _, col_id in sorted(GRASP_METHODS.items(), key=lambda x: x[1]):
            row += f" {confusion[method_id][col_id]:>6}"
        print(row)

    return model, best_model_path


def predict_grasp(topology_labels_path, model_path):
    """
    加载训练好的模型，对新物体的每个面预测抓取方法。

    参数:
        topology_labels_path: 新物体的 topology_labels.json 文件路径
        model_path: 训练好的模型文件路径

    返回:
        预测结果列表，每个元素为字典:
        {
            "face_id": int,
            "geom_type": str,
            "category_name": str,
            "predicted_grasp_method": str,
            "predicted_gripper_type": str,
            "confidence": float (softmax 概率)
        }
    """
    try:
        import torch
        import torch.nn as nn
    except ImportError:
        print("[错误] 需要安装 PyTorch: pip install torch")
        sys.exit(1)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # 读取拓扑标注
    try:
        with open(topology_labels_path, "r", encoding="utf-8") as f:
            labels_data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"[错误] 无法读取拓扑标注文件: {e}")
        return []

    faces = labels_data.get("faces", [])
    if not faces:
        print("[错误] 拓扑标注文件中没有面数据")
        return []

    # 计算归一化参数
    max_area = max((face.get("area", 0.0) for face in faces), default=1.0)
    max_area = max(max_area, 1.0)
    max_tri = max((face.get("triangle_count", 0) for face in faces), default=1)
    max_tri = max(max_tri, 1)

    # 构建特征
    features = []
    for face in faces:
        feature = build_face_feature(face, max_area, max_tri)
        features.append(feature)

    features_tensor = torch.tensor(np.array(features), dtype=torch.float32).to(device)

    # 定义模型结构（与训练时一致）
    class TopologyGraspNet(nn.Module):
        def __init__(self, input_dim=FEATURE_DIM, num_grasp_classes=8, num_gripper_classes=5):
            super().__init__()
            self.shared = nn.Sequential(
                nn.Linear(input_dim, 128),
                nn.ReLU(),
                nn.Dropout(0.2),
                nn.Linear(128, 64),
                nn.ReLU(),
                nn.Dropout(0.1),
                nn.Linear(64, 32),
                nn.ReLU(),
            )
            self.grasp_head = nn.Linear(32, num_grasp_classes)
            self.gripper_head = nn.Linear(32, num_gripper_classes)

        def forward(self, x):
            shared_feat = self.shared(x)
            grasp_out = self.grasp_head(shared_feat)
            gripper_out = self.gripper_head(shared_feat)
            return grasp_out, gripper_out

    # 加载模型权重
    model = TopologyGraspNet().to(device)
    checkpoint = torch.load(model_path, map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    # 推理
    results = []
    with torch.no_grad():
        grasp_out, gripper_out = model(features_tensor)

        # softmax 获取概率
        grasp_probs = torch.softmax(grasp_out, dim=1)
        gripper_probs = torch.softmax(gripper_out, dim=1)

        for i, face in enumerate(faces):
            grasp_pred = grasp_out[i].argmax().item()
            gripper_pred = gripper_out[i].argmax().item()
            grasp_conf = grasp_probs[i][grasp_pred].item()

            results.append({
                "face_id": face.get("face_id", i),
                "geom_type": face.get("geom_type", "UNKNOWN"),
                "category_name": face.get("category_name", "Unknown"),
                "predicted_grasp_method": GRASP_METHOD_NAMES.get(grasp_pred, "unknown"),
                "predicted_gripper_type": GRIPPER_TYPE_NAMES.get(gripper_pred, "unknown"),
                "confidence": round(grasp_conf, 4),
            })

    # 打印预测结果
    print(f"\n{'='*80}")
    print(f"推理结果: {topology_labels_path}")
    print(f"{'='*80}")
    print(f"{'面ID':>4} | {'几何类型':>10} | {'拓扑类别':>20} | {'抓取方法':>20} | {'夹爪类型':>16} | {'置信度':>6}")
    print("-" * 90)
    for r in results:
        print(f"{r['face_id']:>4} | {r['geom_type']:>10} | {r['category_name']:>20} | "
              f"{r['predicted_grasp_method']:>20} | {r['predicted_gripper_type']:>16} | {r['confidence']:>6.4f}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Huhb3D 拓扑感知抓取规划模型训练脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 训练模式
  python train_topology_grasp.py --data-dir ./products/Huhb3D-Industrial-All --epochs 50 --batch-size 32

  # 推理模式
  python train_topology_grasp.py --predict --topology ./products/Huhb3D-Flange-Topology/objects/flange/topology_labels.json --model ./checkpoints/best_model.pt
        """
    )

    # 训练模式参数
    parser.add_argument("--data-dir", type=str, default="./products/Huhb3D-Industrial-All",
                        help="数据集根目录（包含 objects/ 子目录或直接包含物体子目录）")
    parser.add_argument("--epochs", type=int, default=50, help="训练轮数（默认 50）")
    parser.add_argument("--batch-size", type=int, default=32, help="批大小（默认 32）")
    parser.add_argument("--lr", type=float, default=0.001, help="学习率（默认 0.001）")
    parser.add_argument("--checkpoint-dir", type=str, default="./checkpoints",
                        help="模型保存目录（默认 ./checkpoints）")

    # 推理模式参数
    parser.add_argument("--predict", action="store_true", help="推理模式：对新物体预测抓取方法")
    parser.add_argument("--topology", type=str, help="推理模式：topology_labels.json 文件路径")
    parser.add_argument("--model", type=str, default="./checkpoints/best_model.pt",
                        help="推理模式：训练好的模型文件路径")

    args = parser.parse_args()

    if args.predict:
        # ===== 推理模式 =====
        if not args.topology:
            parser.error("推理模式需要指定 --topology 参数")
        if not args.model:
            parser.error("推理模式需要指定 --model 参数")

        if not os.path.exists(args.topology):
            print(f"[错误] 拓扑标注文件不存在: {args.topology}")
            sys.exit(1)
        if not os.path.exists(args.model):
            print(f"[错误] 模型文件不存在: {args.model}")
            sys.exit(1)

        results = predict_grasp(args.topology, args.model)

        if results:
            # 找到最佳抓取面（最高置信度，排除 not_recommended）
            valid_results = [r for r in results if r["predicted_grasp_method"] != "not_recommended"]
            if valid_results:
                best = max(valid_results, key=lambda r: r["confidence"])
                print(f"\n[推荐] 最佳抓取面: face_id={best['face_id']}, "
                      f"方法={best['predicted_grasp_method']}, "
                      f"夹爪={best['predicted_gripper_type']}, "
                      f"置信度={best['confidence']:.4f}")
            else:
                print("\n[警告] 所有面均不推荐抓取")
    else:
        # ===== 训练模式 =====
        if not os.path.exists(args.data_dir):
            print(f"[错误] 数据目录不存在: {args.data_dir}")
            sys.exit(1)

        print("=" * 70)
        print("Huhb3D 拓扑感知抓取规划模型训练")
        print("=" * 70)
        print(f"数据目录: {args.data_dir}")
        print(f"训练轮数: {args.epochs}")
        print(f"批大小: {args.batch_size}")
        print(f"学习率: {args.lr}")
        print(f"模型保存: {args.checkpoint_dir}")

        # 加载数据
        features, grasp_labels, gripper_labels = load_dataset(args.data_dir)

        # 划分训练/验证集
        train_dataset, val_dataset = split_dataset(features, grasp_labels, gripper_labels, train_ratio=0.8)

        # 训练和评估
        model, model_path = train_and_evaluate(
            train_dataset, val_dataset,
            epochs=args.epochs,
            batch_size=args.batch_size,
            lr=args.lr,
            checkpoint_dir=args.checkpoint_dir,
        )

        print(f"\n[完成] 训练流程全部结束！")
        print(f"[提示] 使用以下命令进行推理:")
        print(f"  python train_topology_grasp.py --predict --topology <topology_labels.json路径> --model {model_path}")


if __name__ == "__main__":
    main()
