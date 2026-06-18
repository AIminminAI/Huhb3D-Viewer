# 可制造性审核报告

> 报告编号: `AUDIT-20260610-03818` | 源文件: `hex_bolt.step` | 生成时间: 2026-06-10T21:40:25

---

## 执行摘要

| 项目 | 结果 |
|------|------|
| 综合评分 | **89** / 100 |
| 等级 | 🟡 **B** |
| 严重问题 | 🔴 0 |
| 警告 | 🟡 0 |
| 提示 | 🔵 0 |

---

## 1. 零件概览

| 项目 | 数值 |
|------|------|
| 总面数 | 17 |
| 包围盒 (mm) | 18.0 × 15.59 × 47.0 |
| 总面积 (mm²) | 2000.46 |
| 估算重量 (kg) | 0.031 |
| 复杂度等级 | 低 |

---

## 2. 特征统计

| 特征类型 | 数量 |
|----------|------|
| 平面 | 15 |
| 孔 | 0 |
| 螺栓/凸起 | 0 |
| 倒角 | 1 |
| 圆角 | 0 |
| 其他 | 1 |

---

## 3. 可制造性评分

综合评分: **89** / 100 🟡 等级 **B**

---

## 4. 问题清单

**1.** ⚪ UNKNOWN — 壁厚不均匀，相邻面面积比达 18.9:1
   - 受影响面: 7, 2

**2.** ⚪ UNKNOWN — 锐边转角过多（约 13 处），建议添加倒角
   - 受影响面: 0, 1, 2, 3, 4, 5, 6, 7

---

## 5. 加工工艺方案

| 序号 | 工序 | 方法 | 预计时间 (h) | 备注 |
|------|------|------|-------------|------|
| 1 | 立铣小平面 (15个面，总面积 734.3mm²) | - | - | - |
| 2 | 倒角加工 (1条边) | - | - | - |
| 3 | 车削旋转特征 (1个) | - | - | - |

---

## 6. 抓取建议

### 最优抓取策略

| 项目 | 内容 |
|------|------|
| 抓取方法 | lateral_pinch |
| 夹爪类型 | parallel_jaw |
| 目标面 ID | 11 |
| 置信度 | 0.80 |
| 推理说明 | 凸台 (半径 5.0mm, 面积 1209.5 mm²) 适合平行爪夹持 |

### 各面抓取推荐

| 面 ID | 类别 | 抓取方法 | 夹爪类型 | 置信度 | 备注 |
|-------|------|----------|----------|--------|------|
| 0 | NearLateral_X | surface_grip | vacuum_cup_or_gecko | 0.65 | 近X向垂直面，壁虎/真空吸附 |
| 1 | NearLateral_X | surface_grip | vacuum_cup_or_gecko | 0.65 | 近X向垂直面，壁虎/真空吸附 |
| 2 | NearLateral_Z | surface_grip | vacuum_cup_or_gecko | 0.33 | 近Z向垂直面，壁虎/真空吸附 |
| 3 | LateralPlane_Z | surface_grip | vacuum_cup_or_gecko | 0.70 | Z向垂直平面，壁虎/真空吸附 |
| 4 | HorizontalPlane | vacuum_grip | vacuum_cup | 0.70 | 水平平面，适合真空吸附 |
| 5 | HorizontalPlane | vacuum_grip | vacuum_cup | 0.70 | 水平平面，适合真空吸附 |
| 6 | NearLateral_Z | surface_grip | vacuum_cup_or_gecko | 0.33 | 近Z向垂直面，壁虎/真空吸附 |
| 7 | LateralPlane_Z | surface_grip | vacuum_cup_or_gecko | 0.70 | Z向垂直平面，壁虎/真空吸附 |
| 8 | NearHorizontal | vacuum_grip | vacuum_cup | 0.35 | 近水平面，可真空吸附 |
| 9 | NearLateral_X | surface_grip | vacuum_cup_or_gecko | 0.65 | 近X向垂直面，壁虎/真空吸附 |
| 10 | NearLateral_X | surface_grip | vacuum_cup_or_gecko | 0.65 | 近X向垂直面，壁虎/真空吸附 |
| 11 | Boss | lateral_pinch | parallel_jaw | 0.80 | 凸台特征，建议平行爪夹持 |
| 12 | NearHorizontal | vacuum_grip | vacuum_cup | 0.35 | 近水平面，可真空吸附 |
| 13 | NearLateral_Z | surface_grip | vacuum_cup_or_gecko | 0.33 | 近Z向垂直面，壁虎/真空吸附 |
| 14 | NearLateral_Z | surface_grip | vacuum_cup_or_gecko | 0.33 | 近Z向垂直面，壁虎/真空吸附 |
| 15 | Chamfer | edge_grip | parallel_jaw | 0.50 | 倒角边缘，建议边缘夹持 |
| 16 | LateralPlane_Z | surface_grip | vacuum_cup_or_gecko | 0.70 | Z向垂直平面，壁虎/真空吸附 |

---

## 7. 成本估算

| 项目 | 数值 |
|------|------|
| 加工时间 (h) | 0.50 |
| 装夹时间 (h) | 0.50 |
| 难度系数 | ×1.00 |
| 预估成本 (CNY) | ¥200 ~ ¥400 |

---

## 8. 改进建议

**1.** 🔵 [低] 均匀化壁厚设计，避免大面积与小面积面相邻
   - 预期收益: 提高零件刚性，减少加工变形风险
   - 受影响面: 7, 2

**2.** 🔵 [低] 在平面转角处添加 C0.5 倒角或 R0.5 圆角，降低加工难度
   - 预期收益: 减少应力集中，降低加工难度
   - 受影响面: 0, 1, 2, 3, 4, 5, 6, 7

---

*报告由 Huhb3D 可制造性审核系统自动生成 | 2026-06-10T21:40:25*