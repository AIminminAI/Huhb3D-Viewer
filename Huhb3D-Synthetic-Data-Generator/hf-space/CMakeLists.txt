cmake_minimum_required(VERSION 3.10)
set(OpenGL_GL_PREFERENCE GLVND)
project(RoboDataSynthesizer)

# 必须开启 C++14 或更高，以支持复杂的机器人智能体逻辑
set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 1. 寻找基础图形库
find_package(OpenGL REQUIRED)
find_package(GLEW REQUIRED)
find_package(PkgConfig REQUIRED)
pkg_check_modules(GLFW REQUIRED glfw3)

# 2. 寻找性能测试库 (这是解决报错的关键)
find_package(benchmark REQUIRED)

# ... 前面的 find_package 保持不变 ...

# 核心修复：添加所有存放头文件的子目录
# 确保包含当前目录和所有相关的源码子目录
# CMAKE_CURRENT_SOURCE_DIR 确保路径是绝对且准确的
include_directories(
    ${CMAKE_CURRENT_SOURCE_DIR}/src
    ${CMAKE_CURRENT_SOURCE_DIR}/src/core
    ${CMAKE_CURRENT_SOURCE_DIR}/src/agent
    ${CMAKE_CURRENT_SOURCE_DIR}/src/Algorithm
    ${CMAKE_CURRENT_SOURCE_DIR}/src/benchmark
    ${GLEW_INCLUDE_DIRS}
    ${GLFW_INCLUDE_DIRS}
)

# 确保源码搜寻逻辑覆盖所有子目录
file(GLOB_RECURSE SOURCES "src/*.cpp")

add_executable(Huhb3D_Generator ${SOURCES})

# ... 后面的 target_link_libraries 保持不变 ...
# 6. 链接所有依赖库
target_link_libraries(Huhb3D_Generator 
    PRIVATE 
    ${OPENGL_LIBRARIES} 
    ${GLEW_LIBRARIES} 
    ${GLFW_LIBRARIES}
    benchmark::benchmark
    -lGLU
    pthread # Google Benchmark 通常需要 pthread 支持
)