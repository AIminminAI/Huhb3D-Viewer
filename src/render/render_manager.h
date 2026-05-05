#pragma once

#include <cstdint>
#include <glad/glad.h>
#define GLFW_INCLUDE_NONE
#include <GLFW/glfw3.h>
#include <vector>
#include <string>
#include <chrono>
#include <thread>
#include <atomic>
#include <mutex>
#include "object_pool.h"
#include "stl_parser.h"
#include "bvh.h"
#include "geometry_api.h"
#include "llm_client.h"
#include "tool_registry.h"
#include "embodied_ai_agent.h"
#include "highlight_types.h"
#include "command_dispatcher.h"
#include "imgui/imgui.h"
#include "../Algorithm/GeometryExpert.h"

namespace hhb {
namespace render {

using HighlightType = hhb::core::HighlightType;

class RenderManager {
public:
    RenderManager(int width, int height, const std::string& title);
    ~RenderManager();

    bool initialize();
    void render();
    void processInput();
    bool shouldClose();
    void swapBuffers();
    void setTriangles(hhb::core::ObjectPool<hhb::core::Triangle>& pool);
    void loadFile(const std::string& filename);
    void centerModel();
    void resetCameraToModel() { centerModel(); }
    
    void setAutoRotate(bool enabled) { autoRotate = enabled; }
    bool getAutoRotate() const { return autoRotate; }

    void setAutomationMode(bool enabled) { automationMode = enabled; }
    bool getAutomationMode() const { return automationMode; }
    
    void setZoom(float value) { zoom = value; }
    float getZoom() const { return zoom; }
    
    float* getCameraRotation() { return cameraRotation; }
    float* getCameraPosition() { return cameraPosition; }

    void setTargetCameraPosition(const float pos[3], float duration = 0.5f);
    void setTargetCameraRotation(const float rot[2], float duration = 0.5f);
    void setTargetZoom(float target, float duration = 0.5f);
    bool isCameraAnimating() const;
    void stopCameraAnimation();

    void initSkills();

    const std::vector<hhb::core::Triangle*>& getTrianglePtrs() const { return trianglePtrs; }

    struct SpatialInfo {
        float center[3];
        float bounds[6];
        float cameraPos[3];
        float cameraRot[2];
        float currentZoom;
    };
    
    SpatialInfo getSpatialInfo();

    // 具身智能 Agent 的结果回调：当工具执行完成后更新高亮
    void onToolResult(const std::vector<int>& indices, HighlightType type, const std::string& desc);

    struct CaptureConfig {
        int sampleCount;
        std::string outputDir;
        float cameraRadius;
        int imageWidth;
        int imageHeight;
        bool saveDepth;
        bool saveMask;
        CaptureConfig()
            : sampleCount(1000), outputDir("synthetic_output"),
              cameraRadius(5.0f), imageWidth(800), imageHeight(600),
              saveDepth(false), saveMask(false) {}
    };

    struct CaptureResult {
        int totalFrames;
        int successFrames;
        int failedFrames;
        float elapsedSeconds;
        std::string outputDirectory;
    };

    CaptureResult captureSyntheticData(const CaptureConfig& config);

private:
    GLFWwindow* window;
    int width;
    int height;
    std::string title;

    GLuint VAO, VBO;
    GLuint shaderProgram;

    GLuint labelVAO, labelVBO;
    GLuint labelShaderProgram;
    bool labelModeActive;
    std::vector<int> faceCategoryIds;
    bool faceCategoriesComputed;

    std::vector<float> vertexData;
    size_t triangleCount;
    hhb::core::ObjectPool<hhb::core::Triangle>* trianglePool;
    std::vector<hhb::core::Triangle*> trianglePtrs;
    hhb::core::BVH bvh;

    float cameraPosition[3];
    float cameraRotation[2];
    float zoom;
    
    bool autoRotate;
    float autoRotateSpeed;
    bool automationMode;

    bool cameraAnimating;
    float targetCameraPos[3];
    float targetCameraRot[2];
    float targetZoom;
    float cameraPosStart[3];
    float cameraRotStart[2];
    float zoomStart;
    std::chrono::steady_clock::time_point cameraAnimStart;
    float cameraAnimDuration;

    std::chrono::steady_clock::time_point lastFrame;
    float deltaTime;
    int frameCount;
    float lastFpsUpdate;
    float fps;

    float metallic;
    float roughness;

    float loadTime;
    size_t memoryUsage;

    hhb::core::Triangle* selectedTriangle;
    int selectedTriangleIndex;
    float pickTime;

    bool showBVH;

    char filePathBuffer[512];

    // 具身智能 Agent：协调 LLM 推理、工具执行和视觉反馈的闭环
    hhb::core::EmbodiedAIAgent embodiedAgent_;
    hhb::core::GeometryAPI geometryAPI;
    hhb::core::CommandDispatcher commandDispatcher;
    hhb::algorithm::GeometryExpert geometryExpert;
    char userInputBuffer[512];
    
    // 高亮相关
    std::vector<int> highlightIndices;
    std::vector<int> newHighlightIndices;
    HighlightType currentHighlightType;
    bool showHighlight;
    std::atomic<bool> highlightCalculated;
    std::thread calculationThread;
    std::mutex highlightMutex;
    std::string lastAnalysisDesc;

    // 高亮闪烁效果
    float highlightBlinkTimer_;
    bool highlightBlinkState_;

    GLuint loadShader(GLenum type, const char* source);
    
    void processUserInput();
    void highlightParts();
    GLuint createShaderProgram(const char* vertexSource, const char* fragmentSource);

    bool initShaders();
    bool initBuffers();
    void updateVertexData(hhb::core::ObjectPool<hhb::core::Triangle>& pool);
    void updateFPS();
    void buildBVH();
    void handleMouseClick(double xpos, double ypos);
    void screenToRay(double xpos, double ypos, float* rayOrigin, float* rayDirection);

    void initImGui();
    void updateImGui();
    void renderImGui();
    void shutdownImGui();

    void openFileDialog();
    
    bool saveScreenshot(const std::string& filename);
    void captureModelViews(const std::string& modelName);

    void sphericalFibonacciSample(int index, int total, float radius, float* outX, float* outY, float* outZ);
    bool saveFrameAsPNG(const std::string& filename, int w, int h, const std::vector<unsigned char>& pixels);
    void computeViewMatrixFromPosition(float camX, float camY, float camZ,
                                        float targetX, float targetY, float targetZ,
                                        float* outView16);

    bool initLabelShaders();
    void computeFaceCategories();
    void updateLabelVertexData();
    void renderLabelMode();
    void setLabelMode(bool active);
    static void categoryToColor(int categoryId, float* outR, float* outG, float* outB);

    void renderBVH();
    void renderAABB(const hhb::core::Bounds& bounds, const float* color);
};

} // namespace render
} // namespace hhb
