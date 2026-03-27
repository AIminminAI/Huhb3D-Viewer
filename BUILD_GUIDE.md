# Huhb-Utopia-Project 工业级构建指南

## 环境检测状态

⚠️ **当前环境缺少 MSVC 编译器**，无法直接构建项目。请按照以下指南配置开发环境。

---

## 方案一：使用 Visual Studio 2022（推荐）

### 1. 安装 Visual Studio 2022

1. 下载 [Visual Studio 2022 Community](https://visualstudio.microsoft.com/vs/community/)
2. 运行安装程序，选择以下工作负载：
   - **使用 C++ 的桌面开发**
   - **通用 Windows 平台开发**（可选）

3. 在右侧"单个组件"中确保选中：
   - MSVC v143 - VS 2022 C++ x64/x86 生成工具
   - Windows 11 SDK 或 Windows 10 SDK
   - C++ CMake 工具 for Windows
   - Git for Windows

### 2. 验证安装

打开"Developer Command Prompt for VS 2022"，运行：
```cmd
cl.exe
```

应显示版本信息：
```
用于 x64 的 Microsoft (R) C/C++ 优化编译器 19.XX.XXXXX 版
版权所有(C) Microsoft Corporation。保留所有权利。

用法: cl [ 选项... ] 文件名... [ /link 链接选项... ]
```

### 3. 构建项目

在 Developer Command Prompt 中：
```cmd
cd D:\Huhb\AIProject\Huhb-Utopia-Project\OpenGL-Core-HuhbPro
mkdir build
cd build
// 检查 CMake 版本
cmake --version
//如果 CMake 版本 < 3.28 ：
cmake .. -G "NMake Makefiles"
cmake --build .
//如果 CMake 版本 >= 3.28 ：
cmake .. -G "Visual Studio 17 2022" -A x64
cmake --build . --config Release
```

---

## 方案二：使用 vcpkg 管理依赖

### 1. 安装 vcpkg

```cmd
cd D:\
git clone https://github.com/Microsoft/vcpkg.git
cd vcpkg
.\bootstrap-vcpkg.bat
```

### 2. 集成到 Visual Studio

```cmd
.\vcpkg integrate install
```

### 3. 安装项目依赖

```cmd
.\vcpkg install glfw3:x64-windows
.\vcpkg install glad:x64-windows
.\vcpkg install glm:x64-windows
.\vcpkg install imgui:x64-windows
.\vcpkg install simdjson:x64-windows
```

### 4. 使用 vcpkg 工具链构建

```cmd
cd D:\Huhb\AIProject\Huhb-Utopia-Project\OpenGL-Core-HuhbPro
mkdir build
cd build
cmake .. -G "Visual Studio 17 2022" -A x64 -DCMAKE_TOOLCHAIN_FILE=D:/vcpkg/scripts/buildsystems/vcpkg.cmake
cmake --build . --config Release
```

---

## 方案三：纯 CMake + Ninja（高级用户）

### 1. 安装 Ninja

```cmd
choco install ninja
```

或从 [GitHub Releases](https://github.com/ninja-build/ninja/releases) 下载并添加到 PATH

### 2. 配置环境变量

确保以下路径在 PATH 中：
- `C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.XX.XXXXX\bin\Hostx64\x64`
- `C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE`

### 3. 构建

```cmd
cd D:\Huhb\AIProject\Huhb-Utopia-Project\OpenGL-Core-HuhbPro
mkdir build
cd build
cmake .. -G Ninja -DCMAKE_C_COMPILER=cl.exe -DCMAKE_CXX_COMPILER=cl.exe -DCMAKE_BUILD_TYPE=Release
ninja
```

---

## 项目依赖清单

| 依赖库 | 用途 | 版本要求 |
|--------|------|----------|
| GLFW3 | 窗口和输入管理 | >= 3.3 |
| GLAD | OpenGL 加载器 | >= 0.1.34 |
| GLM | 数学库（向量、矩阵） | >= 0.9.9 |
| Dear ImGui | 即时模式 GUI | >= 1.89 |
| simdjson | 高性能 JSON 解析 | >= 3.0 |

---

## 项目结构说明

```
OpenGL-Core-HuhbPro/
├── include/              # 头文件目录
│   ├── imgui/           # Dear ImGui 头文件
│   ├── glad/            # OpenGL 加载器
│   ├── GLFW/            # GLFW 头文件
│   ├── bvh.h            # BVH 空间索引
│   ├── object_pool.h    # 高性能内存池
│   ├── stl_parser.h     # STL 文件解析器
│   └── ...
├── src/
│   ├── core/            # 核心算法实现
│   │   ├── bvh.cpp
│   │   ├── stl_parser.cpp
│   │   └── ...
│   └── render/          # 渲染引擎
│       ├── render_manager.cpp
│       ├── imgui.cpp
│       └── ...
├── CMakeLists.txt       # 主 CMake 配置
└── BUILD_GUIDE.md       # 本构建指南
```

---

## 性能优化构建选项

### Release 模式优化标志

项目已配置的优化选项：
- `/O2` - 最大化速度优化
- `/arch:AVX2` - 启用 AVX2 指令集
- `/fp:fast` - 快速浮点模型
- `/GL` - 全程序优化
- `/LTCG` - 链接时代码生成

### 手动添加高级优化

在 CMakeLists.txt 中添加：
```cmake
if(MSVC)
    # 启用链接时优化
    set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} /GL")
    set(CMAKE_EXE_LINKER_FLAGS_RELEASE "${CMAKE_EXE_LINKER_FLAGS_RELEASE} /LTCG")
    
    # 启用 SIMD 指令集
    add_compile_options(/arch:AVX2)
    
    # 快速浮点模型
    add_compile_options(/fp:fast)
endif()
```

---

## 常见问题排查

### Q1: CMake 找不到 Visual Studio 生成器

**解决**：确保在 Developer Command Prompt 中运行 CMake，或设置环境变量：
```cmd
"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
```

### Q2: 链接错误 LNK2019 - 无法解析的外部符号

**解决**：检查是否所有源文件都已添加到 CMakeLists.txt，特别是 ImGui 相关文件。

### Q3: 运行时缺少 DLL

**解决**：将 vcpkg 的 `installed/x64-windows/bin` 目录中的 DLL 复制到可执行文件目录，或添加到 PATH。

### Q4: OpenGL 版本不兼容

**解决**：更新显卡驱动，或在代码中降低 OpenGL 版本要求（当前使用 OpenGL 3.3 Core Profile）。

---

## 验证构建成功

构建完成后，运行以下测试：

```cmd
cd D:\Huhb\AIProject\Huhb-Utopia-Project\OpenGL-Core-HuhbPro\build\Release

# 运行渲染测试
.\test_render.exe

# 运行 BVH 测试
.\test_bvh.exe

# 运行 STL 解析测试
.\test_stl_parser.exe ..\..\test.stl
```

---

## 性能基准测试

构建 Release 版本后，可以运行性能测试：

```cmd
# 生成测试用的百万面片 STL
.\generate_stl.exe 1000000 large_model.stl

# 测试加载性能
.\test_stl_parser.exe large_model.stl
```

预期性能指标：
- **加载时间**：100MB+ STL 文件 < 1 秒
- **拾取响应**：百万面片模型 < 1ms
- **渲染帧率**：稳定 60+ FPS

---

## 联系与支持

如有构建问题，请检查：
1. Visual Studio 版本是否为 2022
2. 是否安装了 C++ 桌面开发工作负载
3. CMake 版本 >= 3.16
4. Windows SDK 是否安装

---

**最后更新**：2025-03-25
**项目版本**：Huhb-Utopia-Project Industrial Grade v1.0
