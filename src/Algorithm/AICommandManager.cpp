#include "AICommandManager.h"
#include <iostream>

namespace hhb {
namespace algorithm {

AICommandManager& AICommandManager::getInstance() {
    static AICommandManager instance;
    return instance;
}

void AICommandManager::setModelLoadedCallback(std::function<void(bool)> callback) {
    modelLoadedCallback = callback;
}

void AICommandManager::setAnalysisCompleteCallback(std::function<void(const std::string&)> callback) {
    analysisCompleteCallback = callback;
}

void AICommandManager::setHighlightCallback(std::function<void(const std::vector<int>&, int)> callback) {
    highlightCallback = callback;
}

bool AICommandManager::loadModel(const std::string& filename) {
    std::cout << "[AICommandManager] Loading model: " << filename << std::endl;
    modelLoaded.store(true);
    if (modelLoadedCallback) {
        modelLoadedCallback(true);
    }
    return true;
}

void AICommandManager::resetCamera() {
    std::cout << "[AICommandManager] Resetting camera" << std::endl;
    cameraPositionX.store(0.0f);
    cameraPositionY.store(0.0f);
    cameraPositionZ.store(5.0f);
    cameraPitch.store(0.0f);
    cameraYaw.store(0.0f);
    zoom.store(1.0f);
}

void AICommandManager::setCameraPosition(float x, float y, float z) {
    std::cout << "[AICommandManager] Setting camera position: (" << x << ", " << y << ", " << z << ")" << std::endl;
    cameraPositionX.store(x);
    cameraPositionY.store(y);
    cameraPositionZ.store(z);
}

void AICommandManager::setCameraRotation(float pitch, float yaw) {
    std::cout << "[AICommandManager] Setting camera rotation: pitch=" << pitch << ", yaw=" << yaw << std::endl;
    cameraPitch.store(pitch);
    cameraYaw.store(yaw);
}

void AICommandManager::setZoom(float z) {
    if (z <= 0.0f) {
        std::cerr << "[AICommandManager] Error: zoom must be positive" << std::endl;
        return;
    }
    std::cout << "[AICommandManager] Setting zoom: " << z << std::endl;
    zoom.store(z);
}

void AICommandManager::setHighlight(int type, const std::vector<int>& indices) {
    std::cout << "[AICommandManager] Setting highlight: type=" << type << ", indices count=" << indices.size() << std::endl;
    
    std::lock_guard<std::mutex> lock(highlightMutex);
    currentHighlightIndices = indices;
    currentHighlightType.store(static_cast<HighlightType>(type));
    
    if (highlightCallback) {
        highlightCallback(indices, type);
    }
}

void AICommandManager::setPBRParams(float m, float r) {
    std::cout << "[AICommandManager] Setting PBR params: metallic=" << m << ", roughness=" << r << std::endl;
    metallic.store(m);
    roughness.store(r);
}

void AICommandManager::clearHighlight() {
    std::cout << "[AICommandManager] Clearing highlight" << std::endl;
    
    std::lock_guard<std::mutex> lock(highlightMutex);
    currentHighlightIndices.clear();
    currentHighlightType.store(HighlightType::None);
    
    if (highlightCallback) {
        highlightCallback({}, 0);
    }
}

void AICommandManager::executeAnalysis(const std::string& command) {
    std::cout << "[AICommandManager] Executing analysis command: " << command << std::endl;
    
    if (!modelLoaded.load()) {
        std::cerr << "[AICommandManager] Error: No model loaded" << std::endl;
        if (analysisCompleteCallback) {
            analysisCompleteCallback("Error: No model loaded");
        }
        return;
    }
    
    if (analysisCompleteCallback) {
        std::string result = "Analysis completed: " + command;
        analysisCompleteCallback(result);
    }
}

} // namespace algorithm
} // namespace hhb