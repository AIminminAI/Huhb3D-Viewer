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
add_compile_definitions("$<$<CXX_COMPILER_ID:MSVC>:NOMINMAX>")

include_directories(include)
include_directories(include/imgui)

include(FetchContent)

set(GLFW_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(GLFW_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(GLFW_BUILD_DOCS OFF CACHE BOOL "" FORCE)
set(GLFW_BUILD_INSTALL OFF CACHE BOOL "" FORCE)

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
    src/core/tool_registry.cpp
    src/core/embodied_ai_agent.cpp
    src/Algorithm/GeometryExpert.cpp
    src/Algorithm/AICommandManager.cpp
    src/skill/ISkill.h
    src/skill/SkillRegistry.h
    src/skill/AutoRotateSkill.h
    src/skill/ResetCameraSkill.h
    src/skill/ZoomInSkill.h
    src/skill/RotateSkill.h
    src/skill/OptimizeViewSkill.h
    src/skill/MeasureModelSkill.h
    src/skill/AnalyzeGeometrySkill.h
    src/agent/AIAgentController.h
    src/agent/AIAgentController.cpp
    src/agent/DocumentRetriever.h
    src/agent/DocumentRetriever.cpp
)

# 测试可执行文件
add_executable(test_object_pool
    src/core/test_object_pool.cpp
)

# 渲染可执行文件
add_executable(test_render
    src/render/test_render.cpp
    src/render/render_manager.cpp
    src/render/glad.c
    src/render/imgui.cpp
    src/render/imgui_demo.cpp
    src/render/imgui_draw.cpp
    src/render/imgui_impl_glfw.cpp
    src/render/imgui_impl_opengl3.cpp
    src/render/imgui_tables.cpp
    src/render/imgui_widgets.cpp
)

target_link_libraries(test_render hhb_cad_core glfw)

if(WIN32)
    target_link_libraries(test_render opengl32 ws2_32 winhttp)
else()
    target_link_libraries(test_render GL pthread dl m)
endif()