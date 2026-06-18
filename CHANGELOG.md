# 更新日志

所有重要变更都会记录在此文件中。

## [1.0.0] - 2026-05-06

### 新增
- 360° Fibonacci 球面采样，支持 100-1000 张多角度 RGB 渲染
- 像素级语义分割 Mask（12 类标签）
- 基于高斯曲率/平均曲率的几何特征识别（螺栓/孔/法兰/凸台）
- 深度图生成（PNG 可视化 + RAW float32 原始数据）
- 6DoF 相机位姿导出（camera_poses.json）
- COCO JSON / YOLO 标注格式转换（mask_to_coco.py）
- PBR 渲染引擎（金属度/粗糙度可调）
- 零拷贝 STL 解析（内存映射 + 自定义内存池）
- BVH 空间加速结构
- Streamlit Web UI
- AI 特征描述（DeepSeek-V3 可选接入）
- ZIP 打包输出
- 一键启动脚本（start_all.bat / stop_all.bat）
- Docker 部署支持
