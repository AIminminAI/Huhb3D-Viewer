cmake_minimum_required(VERSION 3.14)
project(STLRenderer)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# 为 MSVC 编译器添加 UTF-8 编码支持
if(MSVC)
    add_compile_options(/utf-8)
endif()



# 源文件
set(SOURCE_FILES
    render_manager.cpp
    test_render.cpp
    glad.c
    imgui.cpp
    imgui_draw.cpp
    imgui_tables.cpp
    imgui_widgets.cpp
    imgui_impl_glfw.cpp
    imgui_impl_opengl3.cpp
)

# 可执行文件
add_executable(test_render ${SOURCE_FILES})

# 包含目录
target_include_directories(test_render PRIVATE
    ${PROJECT_SOURCE_DIR}/../..
    ${PROJECT_SOURCE_DIR}/../../include
    ${PROJECT_SOURCE_DIR}/../../include/imgui
)

# 链接库
target_link_libraries(test_render
    opengl32
    glfw
    hhb_cad_core
)