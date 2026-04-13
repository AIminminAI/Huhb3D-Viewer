# Huhb3D Viewer & AI Agent (高性能三维 CAD 渲染与 AI 智能分析系统)

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)]()
[![C++](https://img.shields.io/badge/Language-C++17-orange.svg)]()
[![Python](https://img.shields.io/badge/Language-Python%203.8+-blue.svg)]()

> 🚀 **零拷贝架构 · 极致性能 · 自然语言驱动的大模型 CAD 交互**

Huhb3D Viewer 是一款专为工业级三维模型（如 STL 格式）设计的极速解析与渲染软件。在最新的 V2.0 版本中，我们**创新性地引入了 AI 大模型（LLM）与具身智能架构**，实现了从底层 C++ 极速渲染到上层 Python 大语言模型意图解析的完整闭环。

用户可以直接使用自然语言（如：“帮我找出这个模型里薄弱的地方”），大模型将精准解析意图，并通过跨进程 HTTP 通信驱动底层 C++ 几何引擎，在微秒级内完成曲率、厚度等复杂几何特征的计算，并在 3D 视口中实时高亮！

## ✨ 核心特性

- **🤖 跨语言“双脑”架构**：Python (Streamlit) 负责接入大模型（DeepSeek/GPT）进行自然语言意图理解；C++ 负责底层千万级面片的极速渲染与核心几何特征计算（曲面、平坦区、锐角、厚度）。
- **⚡ 极致的解析性能 (Zero-copy)**：抛弃传统的逐字节读取，通过内存映射（mmap/VirtualAlloc）与自定义内存池，实现 STL 文件的“零拷贝”级解析。
- **🔮 工业级渲染引擎**：基于 OpenGL 3.3+ Core Profile，实现 PBR (Physically Based Rendering) 基础材质，支持金属度 (Metallic) 与粗糙度 (Roughness) 实时调节。
- **🌲 BVH 空间加速结构**：底层构建了高效的层次包围盒（Bounding Volume Hierarchy），为视锥体裁剪、微秒级射线拾取以及 AI 几何分析提供强大的算力支撑。

## 📸 运行效果

### AI Agent 智能分析演示
![AI交互演示](docs/images/HuhbViewer.gif)
*(注：通过自然语言指令，AI 自动驱动底层 C++ 引擎高亮模型的曲面/锐角等特征)*

### 极致性能渲染
![运行效果截图](docs/images/stl效果图.png)
*(注：加载大疆无人机 STL 模型，包含 46 万三角面片，渲染帧率稳定在 170+ FPS)*

## 🛠️ 编译与运行指南

本项目包含 C++ 渲染端与 Python 大脑端，推荐在 Windows 10/11 配合 Visual Studio 2022 进行编译。

### 1. 环境准备
- **CMake** (>= 3.14)
- **Visual Studio 2022** (包含 "使用 C++ 的桌面开发" 工作负载)
- **Python 3.8+** (建议使用 Anaconda 或 Miniconda)
- *(依赖库 GLFW, GLAD, ImGui, httplib, nlohmann_json 已内置或可通过脚本拉取)*

### 2. 编译 C++ 渲染端
在项目根目录下打开终端（如 PowerShell 或 Developer Command Prompt），依次执行：

```bash
# 1. 创建构建目录并生成项目文件
cmake -B build -DCMAKE_BUILD_TYPE=Release

# 2. 编译项目
cmake --build build --config Release
```

### 3. 运行完整 AI 交互系统
1. **启动 C++ 渲染引擎（含 HTTP 监听服务）：**
   双击运行 `build/src/render/Release/test_render.exe`，点击左侧 "Open STL File" 加载模型。
   *(此时后台会在 `127.0.0.1:8080` 启动 HTTP 服务器监听 AI 指令)*

2. **启动 Python AI 智能体端：**
   打开新的命令行，安装依赖并启动 Streamlit 界面：
   ```bash
   pip install streamlit requests openai
   streamlit run agent_ui.py
   ```
3. **开始对话**：在弹出的网页端聊天框中，输入自然语言指令即可体验！

## 📂 测试数据

为了方便大家快速体验，项目中提供了一些基础测试模型，你也可以在 `test_models` 目录下放入自己的模型。
*(注：仓库发布后，可在此处放置一个云盘链接或指引用户去 Release 下载带有测试数据的压缩包)*

## 📄 协议与授权

本项目开源协议为 **AGPL-3.0**。
这意味着你可以自由地学习、修改和分发本代码。但如果你使用本项目的代码进行商业闭源软件的开发，你必须同样开源你的整个项目。如需商业闭源授权（Dual Licensing），请通过开发者联系方式进行沟通。

---
*Developed by Huhb - 致力于探索图形学与工业软件的极限性能。*
