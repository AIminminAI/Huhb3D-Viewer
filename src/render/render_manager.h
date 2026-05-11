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
#include <random>
#include <memory>
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

struct SceneObject {
    int instanceId;
    std::string name;
    std::string filePath;
    std::unique_ptr<hhb::core::ObjectPool<hhb::core::Triangle>> trianglePool;
    std::vector<hhb::core::Triangle*> trianglePtrs;
    size_t triangleCount;
    float position[3];
    float rotation[3];
    float scale;
    float bounds[6];
    float center[3];
    float maxDim;
    std::vector<int> faceCategoryIds;
    std::vector<int> featureInstanceIds;
    bool categoriesComputed;
    GLuint VAO, VBO;
    GLuint labelVAO, labelVBO;
    std::vector<float> vertexData;
    std::vector<float> labelVertexData;

    SceneObject() : instanceId(0), triangleCount(0), scale(1.0f),
                    categoriesComputed(false), VAO(0), VBO(0), labelVAO(0), labelVBO(0),
                    maxDim(0.0f) {
        position[0] = position[1] = position[2] = 0.0f;
        rotation[0] = rotation[1] = rotation[2] = 0.0f;
        bounds[0] = bounds[1] = bounds[2] = 1e9f;
        bounds[3] = bounds[4] = bounds[5] = -1e9f;
        center[0] = center[1] = center[2] = 0.0f;
        trianglePool = std::make_unique<hhb::core::ObjectPool<hhb::core::Triangle>>();
    }
    SceneObject(SceneObject&&) = default;
    SceneObject& operator=(SceneObject&&) = default;
    SceneObject(const SceneObject&) = delete;
    SceneObject& operator=(const SceneObject&) = delete;
};

struct DomainRandomizationConfig {
    bool enableLightRandomization;
    bool enableCameraJitter;
    bool enableBackgroundRandomization;
    float lightAngleRange;
    float lightIntensityRange[2];
    float lightColorTempRange[2];
    float cameraJitterPosRange;
    float cameraJitterRotRange;
    float focalLengthJitterRange;
    std::vector<std::string> backgroundPaths;
    DomainRandomizationConfig()
        : enableLightRandomization(true),
          enableCameraJitter(true),
          enableBackgroundRandomization(false),
          lightAngleRange(3.14159f),
          lightIntensityRange{0.5f, 2.0f},
          lightColorTempRange{3000.0f, 9000.0f},
          cameraJitterPosRange(0.05f),
          cameraJitterRotRange(0.02f),
          focalLengthJitterRange(2.0f) {}
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

    void onToolResult(const std::vector<int>& indices, HighlightType type, const std::string& desc);

    struct CaptureConfig {
        int sampleCount;
        std::string outputDir;
        float cameraRadius;
        int imageWidth;
        int imageHeight;
        bool saveDepth;
        bool saveMask;
        bool instanceSegmentation;
        bool multiObjectScene;
        int objectCount;
        float sceneBounds[3];
        bool enableCollisionAvoidance;
        DomainRandomizationConfig domainRandomization;
        std::string topologyLabelsPath;
        std::vector<std::string> sceneObjectTopologyPaths;
        bool outputBOPFormat;
        float depthScale;
        std::string modelUnit;
        CaptureConfig()
            : sampleCount(1000), outputDir("synthetic_output"),
              cameraRadius(5.0f), imageWidth(800), imageHeight(600),
              saveDepth(false), saveMask(false),
              instanceSegmentation(true),
              multiObjectScene(false), objectCount(5),
              enableCollisionAvoidance(true),
              outputBOPFormat(true),
              depthScale(1000.0f),
              modelUnit("mm") {
            sceneBounds[0] = 4.0f;
            sceneBounds[1] = 4.0f;
            sceneBounds[2] = 2.0f;
        }
    };

    struct CaptureResult {
        int totalFrames;
        int successFrames;
        int failedFrames;
        float elapsedSeconds;
        std::string outputDirectory;
    };

    CaptureResult captureSyntheticData(const CaptureConfig& config);

    bool addSceneObject(const std::string& filePath, const std::string& name);
    void clearSceneObjects();
    size_t getSceneObjectCount() const { return sceneObjects_.size(); }
    void randomizeSceneLayout();
    void computeAllFeatureInstances();
    bool loadTopologyLabels(const std::string& jsonPath);
    bool loadSceneObjectTopologyLabels(SceneObject& obj, const std::string& jsonPath);

    static void instanceColorEncode(int instanceId, int featureTypeId, int featureIndex,
                                     float* outR, float* outG, float* outB);
    static void instanceColorDecode(unsigned char r, unsigned char g, unsigned char b,
                                     int& instanceId, int& featureTypeId, int& featureIndex);

    static void categoryToColor(int categoryId, float* outR, float* outG, float* outB);

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

    hhb::core::EmbodiedAIAgent embodiedAgent_;
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

    float highlightBlinkTimer_;
    bool highlightBlinkState_;

    std::vector<SceneObject> sceneObjects_;
    std::mt19937 rng_;

    GLuint backgroundVAO_, backgroundVBO_, backgroundShaderProgram_;
    std::vector<GLuint> backgroundTextures_;
    std::vector<float> backgroundColors_;
    int currentBackgroundIndex_;
    bool backgroundInitialized_;

    void initBackgroundRenderer();
    void cleanupBackgroundRenderer();
    void loadBackgroundImages(const std::vector<std::string>& paths);
    void renderBackground(int backgroundIndex);
    int selectRandomBackground();

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

    void computeCurvature();
    void computeGeometricFeatures();
    std::vector<int> faceCurvatureIds;
    std::vector<float> faceGaussianCurvature;
    std::vector<float> faceMeanCurvature;
    bool curvatureComputed = false;
    bool geometricFeaturesComputed = false;
    bool topologyLabelsLoaded = false;
    std::vector<int> topologyFaceLabels_;

    void renderBVH();
    void renderAABB(const hhb::core::Bounds& bounds, const float* color);

    bool loadSceneObjectGeometry(SceneObject& obj);
    void computeSceneObjectBounds(SceneObject& obj);
    void computeSceneObjectFeatures(SceneObject& obj);
    void uploadSceneObjectGPU(SceneObject& obj);
    void buildSceneObjectLabelData(SceneObject& obj);
    void buildSceneObjectInstanceLabelData(SceneObject& obj);
    void renderSceneRGB(const CaptureConfig& config, const float* viewMatrix,
                        const float* projectionMatrix, const float* lightPos,
                        const float* lightColor, float lightIntensity);
    void renderSceneInstanceMask(const CaptureConfig& config, const float* viewMatrix,
                                 const float* projectionMatrix);
    void renderSceneSemanticMask(const CaptureConfig& config, const float* viewMatrix,
                                  const float* projectionMatrix);

    void applyDomainRandomization(const DomainRandomizationConfig& domConfig,
                                   float& lightAngle, float& lightIntensity, float lightColor[3],
                                   float& camJitterX, float& camJitterY, float& camJitterZ,
                                   float& focalJitter);
};

} // namespace render
} // namespace hhb
