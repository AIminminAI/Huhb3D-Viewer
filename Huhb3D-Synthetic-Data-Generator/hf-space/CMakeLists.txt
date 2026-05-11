cmake_minimum_required(VERSION 3.14)
project(Huhb3D_Generator LANGUAGES CXX)

# === C++ 标准：启用 C++20（同时满足协程、结构化绑定等） ===
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)          # 推荐关闭 GNU 扩展，保证可移植性

# === 查找系统库 ===
find_package(OpenGL REQUIRED)
find_package(GLEW REQUIRED)
find_package(glfw3 REQUIRED)
find_package(Threads REQUIRED)

# === 通过 FetchContent 自动下载头文件库（不需要再手动 apt install） ===
include(FetchContent)

# 1. nlohmann/json（替代缺失的 nlohmann/json.hpp）
FetchContent_Declare(json
    GIT_REPOSITORY https://github.com/nlohmann/json.git
    GIT_TAG v3.11.3
)
FetchContent_MakeAvailable(json)

# 3. tl::expected（替代 GCC 11 不支持的 std::expected）
FetchContent_Declare(tl-expected
    GIT_REPOSITORY https://github.com/TartanLlama/expected.git
    GIT_TAG v1.1.0
)
FetchContent_MakeAvailable(tl-expected)

# === 收集所有源文件 ===
file(GLOB_RECURSE SOURCES "src/*.cpp")

# === 生成可执行文件 ===
add_executable(Huhb3D_Generator ${SOURCES})

# === 编译器特殊选项：GCC 11 必须显式开启协程支持 ===
if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
    target_compile_options(Huhb3D_Generator PRIVATE -fcoroutines)
endif()

# === 添加 include 路径 ===
target_include_directories(Huhb3D_Generator PRIVATE
    ${CMAKE_SOURCE_DIR}/src
    ${CMAKE_SOURCE_DIR}/src/core
    ${CMAKE_SOURCE_DIR}/src/agent
    ${CMAKE_SOURCE_DIR}/src/Algorithm
    ${CMAKE_SOURCE_DIR}/src/benchmark
    ${tl-expected_SOURCE_DIR}/include
    ${CMAKE_SOURCE_DIR}/src/glad
    ${CMAKE_SOURCE_DIR}/src/GLFW
    ${CMAKE_SOURCE_DIR}/src/glm
    ${CMAKE_SOURCE_DIR}/src/imgui
    ${CMAKE_SOURCE_DIR}/src/nlohmann
    ${CMAKE_SOURCE_DIR}/src/render
    ${CMAKE_SOURCE_DIR}/src/skill
)

# === 链接所有库 ===
target_link_libraries(Huhb3D_Generator PRIVATE
    OpenGL::GL
    GLEW::GLEW
    glfw
    Threads::Threads
    nlohmann_json::nlohmann_json
    glad
)