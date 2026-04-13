cmake_minimum_required(VERSION 3.16)
project(Hhb-CAD-Core)
# 设置最低 C++ 标准
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# 为 MSVC 编译器添加 UTF-8 编码支持和其他必要的标志
add_compile_options("$<$<CXX_COMPILER_ID:MSVC>:/utf-8>")
add_compile_options("$<$<CXX_COMPILER_ID:MSVC>:/wd4819>")
add_compile_options("$<$<CXX_COMPILER_ID:MSVC>:/permissive->")

include_directories(include)

include(FetchContent)

set(GLFW_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(GLFW_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(GLFW_BUILD_DOCS OFF CACHE BOOL "" FORCE)
set(GLFW_INSTALL OFF CACHE BOOL "" FORCE)

# 从你本地提供的压缩包中获取 GLFW，避免网络下载失败
FetchContent_Declare(
    glfw
    URL ${CMAKE_CURRENT_SOURCE_DIR}/glfw-3.3.8.zip
)
FetchContent_MakeAvailable(glfw)

# 核心库
add_library(hhb_cad_core STATIC
    src/core/test_object_pool.cpp
    src/core/stl_parser.cpp
    src/core/bvh.cpp
    src/core/hhb_cad_c_api.cpp
    src/core/geometry_api.cpp
    src/core/llm_client.cpp
    src/core/command_dispatcher.cpp
    src/Algorithm/GeometryExpert.cpp
)

# 测试可执行文件
add_executable(test_object_pool
    src/core/test_object_pool.cpp
)

# STL 解析器测试
add_executable(test_stl_parser
    src/core/test_stl_parser.cpp
)

# 协程版 STL 解析器测试
# add_executable(test_stl_parser_coroutine
#     src/core/test_stl_parser_coroutine.cpp
# )

# BVH 测试
add_executable(test_bvh
    src/core/test_bvh.cpp
)

# 鲁棒谓词测试
add_executable(test_robust_predicates
    src/core/test_robust_predicates.cpp
)

# C-API 测试
add_executable(test_c_api
    src/core/test_c_api.cpp
)

# 性能基准测试
add_executable(benchmark_test
    tests/benchmark_test.cpp
)

# Hello Triangle ES 3.0 测试
add_executable(test_hello
    test_hello.cpp
    src/render/glad.c
)
target_include_directories(test_hello PRIVATE include)
target_link_libraries(test_hello PRIVATE opengl32 glfw)

# 简单的 STL 解析测试
add_executable(test_stl_simple
    test_stl_simple.cpp
)

# STL 文件生成工具
add_executable(generate_stl
    src/core/generate_stl.cpp
)

# Geometry API 测试
add_executable(test_geometry_api
    test_geometry_api.cpp
)

# LLM Client 测试
add_executable(test_llm_client
    test_llm_client.cpp
)

# Function Calling 测试
add_executable(test_function_calling
    test_function_calling.cpp
)

# 链接核心库
target_link_libraries(test_object_pool PRIVATE hhb_cad_core)
target_link_libraries(test_stl_parser PRIVATE hhb_cad_core)
# target_link_libraries(test_stl_parser_coroutine PRIVATE hhb_cad_core)
target_link_libraries(test_bvh PRIVATE hhb_cad_core)
target_link_libraries(test_robust_predicates PRIVATE hhb_cad_core)
target_link_libraries(test_c_api PRIVATE hhb_cad_core)
target_link_libraries(benchmark_test PRIVATE hhb_cad_core)
target_link_libraries(generate_stl PRIVATE hhb_cad_core)
target_link_libraries(test_geometry_api PRIVATE hhb_cad_core)
target_link_libraries(test_llm_client PRIVATE hhb_cad_core)
target_link_libraries(test_function_calling PRIVATE hhb_cad_core)

# 为核心库添加依赖
# nlohmann/json.hpp 已直接包含在 include 目录中

# 链接 ws2_32 库用于 Windows Socket API
if(WIN32)
    target_link_libraries(hhb_cad_core PRIVATE ws2_32)
endif()

# 基准测试 - 暂时禁用，因为缺少benchmark库
# find_package(benchmark REQUIRED)

# add_executable(benchmark_object_pool
#     src/benchmark/benchmark_object_pool.cpp
# )

# target_link_libraries(benchmark_object_pool PRIVATE
#     hhb_cad_core
#     benchmark::benchmark
#     benchmark::benchmark_main
# )

# 渲染测试
add_subdirectory(src/render)
