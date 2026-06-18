#pragma once

#include <string>
#include <vector>
#include <functional>
#include <mutex>
#include <atomic>

namespace hhb {
namespace algorithm {

class AICommandManager {
public:
    static AICommandManager& getInstance();

    void setModelLoadedCallback(std::function<void(bool)> callback);
    void setAnalysisCompleteCallback(std::function<void(const std::string&)> callback);
    void setHighlightCallback(std::function<void(const std::vector<int>&, int)> callback);

    bool loadModel(const std::string& filename);
    void resetCamera();
    void setCameraPosition(float x, float y, float z);
    void setCameraRotation(float pitch, float yaw);
    void setZoom(float zoom);
    void setHighlight(int type, const std::vector<int>& indices);
    void setPBRParams(float metallic, float roughness);
    void clearHighlight();
    void executeAnalysis(const std::string& command);

    float getCameraPositionX() const { return cameraPositionX.load(); }
    float getCameraPositionY() const { return cameraPositionY.load(); }
    float getCameraPositionZ() const { return cameraPositionZ.load(); }
    float getCameraPitch() const { return cameraPitch.load(); }
    float getCameraYaw() const { return cameraYaw.load(); }
    float getZoom() const { return zoom.load(); }

    bool isModelLoaded() const { return modelLoaded.load(); }

    enum class HighlightType {
        None = 0,
        ThinParts = 1,
        CurvedSurfaces = 2,
        SharpEdges = 3,
        FlatSurfaces = 4
    };

private:
    AICommandManager() = default;
    ~AICommandManager() = default;
    AICommandManager(const AICommandManager&) = delete;
    AICommandManager& operator=(const AICommandManager&) = delete;

    std::atomic<bool> modelLoaded{false};
    std::atomic<float> cameraPositionX{0.0f};
    std::atomic<float> cameraPositionY{0.0f};
    std::atomic<float> cameraPositionZ{5.0f};
    std::atomic<float> cameraPitch{0.0f};
    std::atomic<float> cameraYaw{0.0f};
    std::atomic<float> zoom{1.0f};
    std::atomic<float> metallic{0.5f};
    std::atomic<float> roughness{0.5f};
    std::atomic<HighlightType> currentHighlightType{HighlightType::None};

    std::vector<int> currentHighlightIndices;
    std::mutex highlightMutex;

    std::function<void(bool)> modelLoadedCallback;
    std::function<void(const std::string&)> analysisCompleteCallback;
    std::function<void(const std::vector<int>&, int)> highlightCallback;
};

} // namespace algorithm
} // namespace hhb