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
#include "command_dispatcher.h"
#include "imgui/imgui.h"
#include "../Algorithm/GeometryExpert.h"

namespace hhb {
namespace render {

enum class HighlightType {
    None,
    ThinParts,
    CurvedSurfaces,
    SharpEdges,
    FlatSurfaces
};

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

private:
    GLFWwindow* window;
    int width;
    int height;
    std::string title;

    GLuint VAO, VBO;
    GLuint shaderProgram;

    std::vector<float> vertexData;
    size_t triangleCount;
    hhb::core::ObjectPool<hhb::core::Triangle>* trianglePool;
    std::vector<hhb::core::Triangle*> trianglePtrs;
    hhb::core::BVH bvh;

    float cameraPosition[3];
    float cameraRotation[2];
    float zoom;

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

    hhb::core::LLMClient llmClient;
    hhb::core::GeometryAPI geometryAPI;
    hhb::core::CommandDispatcher commandDispatcher;
    hhb::algorithm::GeometryExpert geometryExpert;
    char userInputBuffer[512];
    
    std::vector<int> highlightIndices;
    std::vector<int> newHighlightIndices;
    HighlightType currentHighlightType;
    bool showHighlight;
    std::atomic<bool> highlightCalculated;
    std::thread calculationThread;
    std::mutex highlightMutex;
    std::string lastAnalysisDesc;

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

    void renderBVH();
    void renderAABB(const hhb::core::Bounds& bounds, const float* color);
};

} // namespace render
} // namespace hhb
