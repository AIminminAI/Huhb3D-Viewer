# Huhb3D Viewer (Huhb 高性能三维 CAD 模型渲染与可视化系统)

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)]()
[![C++](https://img.shields.io/badge/Language-C++17-orange.svg)]()

> 🚀 **零拷贝架构 · 极致性能 · 工业级交互**

Huhb3D Viewer 是一款专为工业级三维模型（如 STL 格式）设计的极速解析与渲染软件。本项目采用底层 C++ 开发，结合 OpenGL Core Profile，自主研发了基于内存池的零拷贝解析架构以及 BVH（层次包围盒）空间加速结构。能够实现**百万级三角面片模型的秒级加载**、**170+ FPS 的流畅漫游**以及精确的微秒级射线拾取。

## ✨ 核心特性

- **极致的解析性能 (Zero-copy)**：抛弃传统的逐字节读取，通过内存映射（mmap/VirtualAlloc）与自定义内存池，实现 STL 文件的“零拷贝”级解析。
- **工业级渲染引擎**：基于 OpenGL 3.3+ Core Profile，实现 PBR (Physically Based Rendering) 基础材质，支持金属度 (Metallic) 与粗糙度 (Roughness) 实时调节。
- **BVH 空间加速结构**：底层构建了高效的层次包围盒（Bounding Volume Hierarchy），为视锥体裁剪、射线拾取（微秒级响应）提供强大的算力支撑。
- **CAD 标准交互体验**：完美复刻 SolidWorks/AutoCAD 的鼠标交互逻辑（中键平移、左键旋转、滚轮缩放）。
- **实时性能监控 (Dear ImGui)**：内嵌轻量级 GUI，实时反馈 FPS、顶点数、面片数、BVH 树深度及内存占用情况。

## 📸 运行效果

![运行效果截图](docs/images/screenshot.png)
*(注：加载大疆无人机 STL 模型，包含 46 万三角面片，渲染帧率稳定在 170+ FPS)*

## 🛠️ 编译与运行指南

本项目使用 CMake 构建，推荐在 Windows 10/11 配合 Visual Studio 2022 进行编译。

### 1. 环境准备
- **CMake** (>= 3.14)
- **Visual Studio 2022** (包含 "使用 C++ 的桌面开发" 工作负载)
- *(依赖库 GLFW, GLAD, ImGui 已内置或可通过脚本拉取)*

### 2. 编译步骤
在项目根目录下打开终端（如 PowerShell 或 Developer Command Prompt），依次执行：

```bash
# 1. 创建构建目录并生成项目文件
cmake -B build -DCMAKE_BUILD_TYPE=Release

# 2. 编译项目
cmake --build build --config Release
```

### 3. 运行测试
编译成功后，可执行文件位于 `build/src/render/Release/test_render.exe`（或 `build/src/render/test_render.exe`）。
双击运行，点击左侧面板的 **"Open STL File"**，选择你本地的 `.stl` 文件即可体验。

## 📂 测试数据

为了方便大家快速体验，项目中提供了一些基础测试模型，你也可以在 `test_models` 目录下放入自己的模型。
*(注：仓库发布后，可在此处放置一个云盘链接或指引用户去 Release 下载带有测试数据的压缩包)*

## 📄 协议与授权

本项目开源协议为 **AGPL-3.0**。
这意味着你可以自由地学习、修改和分发本代码。但如果你使用本项目的代码进行商业闭源软件的开发，你必须同样开源你的整个项目。如需商业闭源授权（Dual Licensing），请通过开发者联系方式进行沟通。

---
*Developed by Huhb - 致力于探索图形学与工业软件的极限性能。*
