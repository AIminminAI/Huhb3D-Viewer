#pragma once

#include <cstdint>
#include <glad/glad.h>
#define GLFW_INCLUDE_NONE
#include <GLFW/glfw3.h>
#include <vector>
#include <string>
#include <chrono>
#include "object_pool.h"
#include "stl_parser.h"
#include "bvh.h"
#include "imgui/imgui.h"

namespace hhb {
namespace render {

class RenderManager {
public:
    RenderManager(int width, int height, const std::string& title);
    ~RenderManager();

    // 初始化OpenGL
    bool initialize();

    // 渲染函数
    void render();

    // 处理输入
    void processInput();

    // 检查窗口是否应该关闭
    bool shouldClose();

    // 更新窗口
    void swapBuffers();

    // 设置三角形数据
    void setTriangles(hhb::core::ObjectPool<hhb::core::Triangle>& pool);

    // 文件加载
    void loadFile(const std::string& filename);

    // 居中模型
    void centerModel();
    
    // 重置相机到模型位置（与centerModel相同，提供更明确的命名）
    void resetCameraToModel() { centerModel(); }

private:
    // 窗口相关
    GLFWwindow* window;
    int width;
    int height;
    std::string title;

    // OpenGL相关
    GLuint VAO, VBO;
    GLuint shaderProgram;

    // 数据相关
    std::vector<float> vertexData;
    size_t triangleCount;
    hhb::core::ObjectPool<hhb::core::Triangle>* trianglePool; // 保存三角形池的指针
    std::vector<hhb::core::Triangle*> trianglePtrs; // 用于构建BVH的三角形指针数组
    hhb::core::BVH bvh; // BVH树

    // 相机相关
    float cameraPosition[3];
    float cameraRotation[2];
    float zoom;

    // 时间相关
    std::chrono::steady_clock::time_point lastFrame;
    float deltaTime;
    int frameCount;
    float lastFpsUpdate;
    float fps;

    // PBR 相关参数
    float metallic; // 金属度
    float roughness; // 粗糙度

    // 性能监控相关
    float loadTime; // 加载耗时
    size_t memoryUsage; // 内存占用

    // 拾取相关
    hhb::core::Triangle* selectedTriangle; // 当前选中的三角形
    int selectedTriangleIndex; // 选中三角形的索引
    float pickTime; // 拾取耗时（微秒）

    // BVH 可视化
    bool showBVH; // 是否显示 BVH 包围盒

    // 文件对话框相关
    char filePathBuffer[512]; // 文件路径缓冲区

    // 着色器相关
    GLuint loadShader(GLenum type, const char* source);
    GLuint createShaderProgram(const char* vertexSource, const char* fragmentSource);

    // 初始化着色器
    bool initShaders();

    // 初始化缓冲区
    bool initBuffers();

    // 更新顶点数据
    void updateVertexData(hhb::core::ObjectPool<hhb::core::Triangle>& pool);

    // 更新FPS
    void updateFPS();

    // 构建BVH树
    void buildBVH();

    // 鼠标点击拾取
    void handleMouseClick(double xpos, double ypos);

    // 屏幕坐标转射线
    void screenToRay(double xpos, double ypos, float* rayOrigin, float* rayDirection);

    // ImGui 相关
    void initImGui();
    void updateImGui();
    void renderImGui();
    void shutdownImGui();

    // 文件加载
    void openFileDialog();

    // BVH 可视化渲染
    void renderBVH();
    void renderAABB(const hhb::core::Bounds& bounds, const float* color);
};

} // namespace render
} // namespace hhb