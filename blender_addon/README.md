# Huhb3D 6DoF Data Generator

Blender 插件，一键从 STEP/CAD 文件生成 6DoF 位姿估计训练数据。

## 功能

- **多视角渲染**：基于 Fibonacci 球面采样，自动生成数百到数千个相机视角
- **多通道输出**：RGB + Depth (mm, uint16) + Instance Mask
- **6DoF 真值标注**：从 Blender 相机矩阵精确计算 cam_R_m2c、cam_t_m2c、cam_K
- **多格式导出**：
  - **BOP** — scene_gt.json / scene_camera.json
  - **COCO** — coco_annotations.json (含 bbox)
  - **YOLO** — labels/ 目录下的归一化标注文件
- **Sim2Real 增强**：
  - 7 种工业风格背景替换（混凝土地面、金属货架、传送带等）
  - 光度随机化（亮度、对比度、Gamma、阴影）
  - 深度噪声注入（量化、空洞、飞点像素）
  - 多物体合成场景（深度缓冲合成）

## 安装

1. 确保已安装 **Blender 3.x 或 4.x**
2. 将 `blender_addon` 文件夹打包为 zip，或直接复制到 Blender 插件目录
3. 打开 Blender → 编辑 (Edit) → 首选项 (Preferences) → 插件 (Add-ons)
4. 点击「安装…」(Install…) 选择 zip 文件，或搜索 "Huhb3D" 并启用

### 可选依赖

- **OpenCV (cv2)** + **NumPy**：Sim2Real 增强功能需要。安装方式：
  ```bash
  # 在 Blender 内置 Python 中安装
  <blender_path>/<version>/python/bin/python3.X -m pip install opencv-python-headless numpy
  ```
- **pythonOCP (OCCT)**：用于直接读取 STEP 文件（无此依赖时可回退到 STL/OBJ 导入）
- **Blender CAD Add-on**：Blender 4.x 内置的 CAD 导入功能

## 使用方法

1. 在 3D 视口中按 **N** 键打开侧边栏
2. 切换到 **Huhb3D** 标签页
3. 设置参数：
   - **STEP File**：选择要导入的 CAD 文件（.step / .stp / .stl / .obj / .fbx）
   - **Output Directory**：数据集输出目录
   - **Number of Views**：渲染视角数量（默认 100）
   - **Image Width/Height**：图像分辨率
   - **Camera Radius**：相机到物体原点的距离
   - 勾选需要的导出格式（BOP / COCO / YOLO）
   - 如需 Sim2Real 增强，勾选并设置增强场景数量
4. 点击 **Import STEP** 导入模型
5. 点击 **Generate Dataset** 开始生成
6. 完成后点击 **Open Output Folder** 查看结果

## 输出结构

```
<output_dir>/
├── rgb/                    # RGB 渲染图
│   ├── 000000.png
│   ├── 000001.png
│   └── ...
├── depth/                  # 深度图 (uint16, mm)
│   ├── 000000.png
│   └── ...
├── mask/                   # 实例掩码
│   ├── 000000_mask.png
│   └── ...
├── scene_gt.json           # BOP 位姿真值
├── scene_camera.json       # BOP 相机内参
├── coco_annotations.json   # COCO 格式标注
├── labels/                 # YOLO 格式标注
│   ├── 000000.txt
│   └── ...
└── augmented/              # Sim2Real 增强结果（如启用）
    ├── rgb/
    ├── depth/
    ├── multi_rgb/
    └── multi_depth/
```

## 支持的输入格式

| 格式 | 扩展名 | 说明 |
|------|--------|------|
| STEP | .step, .stp | 需 Blender CAD 插件或 pythonOCP |
| STL  | .stl | 直接支持 |
| OBJ  | .obj | 直接支持 |
| FBX  | .fbx | 直接支持 |

## 兼容性

- Blender 3.x / 4.x
- Windows / macOS / Linux

## 许可与购买

本插件为商业软件。请访问 [Huhb3D](https://huhb3d.com) 获取许可证和定价信息。
