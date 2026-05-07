#ifdef _WIN32
#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#endif

#include <iostream>
#include <cstdlib>
#include <string>
#include <fstream>
#ifdef _WIN32
#include <Windows.h>
#include <direct.h>
#endif
#include "render_manager.h"
#include "stl_parser.h"

bool fileExists(const std::string& name) {
    std::ifstream f(name.c_str());
    return f.good();
}

// 简单的路径提取
std::string getParentPath(const std::string& path) {
    size_t pos = path.find_last_of("\\/");
    return (pos != std::string::npos) ? path.substr(0, pos) : "";
}

int main(int argc, char* argv[]) {
    std::cout << "Starting STL renderer test..." << std::endl;
    
    char cwd[1024];
    if (_getcwd(cwd, sizeof(cwd)) != NULL) {
        std::cout << "Current working directory: " << cwd << std::endl;
    } else {
        std::cerr << "Error getting current working directory" << std::endl;
    }

    std::string stlPath;
    std::string outputDir = "synthetic_output";
    int sampleCount = 1000;
    float cameraRadius = 5.0f;
    int imageWidth = 800;
    int imageHeight = 600;
    bool batchMode = false;
    bool saveMask = true;

    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if ((arg == "--input" || arg == "-i") && i + 1 < argc) {
            stlPath = argv[++i];
        } else if ((arg == "--output" || arg == "-o") && i + 1 < argc) {
            outputDir = argv[++i];
        } else if ((arg == "--count" || arg == "-n") && i + 1 < argc) {
            sampleCount = std::atoi(argv[++i]);
        } else if ((arg == "--radius" || arg == "-r") && i + 1 < argc) {
            cameraRadius = std::atof(argv[++i]);
        } else if ((arg == "--width" || arg == "-w") && i + 1 < argc) {
            imageWidth = std::atoi(argv[++i]);
        } else if ((arg == "--img-height") && i + 1 < argc) {
            imageHeight = std::atoi(argv[++i]);
        } else if (arg == "--batch" || arg == "-b") {
            batchMode = true;
        } else if (arg == "--no-mask") {
            saveMask = false;
        } else if (stlPath.empty()) {
            stlPath = arg;
        }
    }

    auto stripQuotes = [](const std::string& s) -> std::string {
        if (s.size() >= 2 && ((s.front() == '"' && s.back() == '"') || (s.front() == '\'' && s.back() == '\''))) {
            return s.substr(1, s.size() - 2);
        }
        return s;
    };
    stlPath = stripQuotes(stlPath);
    outputDir = stripQuotes(outputDir);

    std::cout << "[DEBUG] Parsed arguments:" << std::endl;
    std::cout << "[DEBUG]   stlPath     = \"" << stlPath << "\"" << std::endl;
    std::cout << "[DEBUG]   outputDir   = \"" << outputDir << "\"" << std::endl;
    std::cout << "[DEBUG]   sampleCount = " << sampleCount << std::endl;
    std::cout << "[DEBUG]   batchMode   = " << (batchMode ? "true" : "false") << std::endl;
    std::cout << "[DEBUG]   argc        = " << argc << std::endl;
    for (int i = 0; i < argc; ++i) {
        std::cout << "[DEBUG]   argv[" << i << "] = \"" << argv[i] << "\"" << std::endl;
    }

    if (stlPath.empty()) {
        stlPath = "Dji+Avata+2+Simple.stl";
        if (!fileExists(stlPath)) {
            char exePath[1024];
            GetModuleFileNameA(NULL, exePath, sizeof(exePath));
            std::string exeDir = getParentPath(exePath);
            std::string checkPath = exeDir + "\\" + stlPath;
            if (fileExists(checkPath)) {
                stlPath = checkPath;
            } else {
                checkPath = getParentPath(exeDir) + "\\" + stlPath;
                if (fileExists(checkPath)) {
                    stlPath = checkPath;
                }
            }
        }
    }

    std::cout << "Creating RenderManager..." << std::endl;
    hhb::render::RenderManager renderManager(1280, 720, "Huhb CAD Viewer");
    
    if (!renderManager.initialize()) {
        std::cerr << "Failed to initialize RenderManager" << std::endl;
        return 1;
    }

    if (batchMode) {
        renderManager.setAutomationMode(true);
        std::cout << "Automation mode enabled - ImGui UI rendering disabled" << std::endl;
    }

    std::cout << "[DEBUG] stlPath = \"" << stlPath << "\"" << std::endl;
    std::cout << "[DEBUG] stlPath.empty() = " << (stlPath.empty() ? "true" : "false") << std::endl;
    std::cout << "[DEBUG] fileExists(stlPath) = " << (fileExists(stlPath) ? "true" : "false") << std::endl;
    
    if (fileExists(stlPath)) {
        std::cout << "Loading STL: " << stlPath << std::endl;
        renderManager.loadFile(stlPath);
    } else {
        std::cerr << "STL file not found: " << stlPath << std::endl;
        if (batchMode) {
            std::cerr << "Cannot run batch mode without a valid STL file!" << std::endl;
            return 1;
        }
        std::cout << "Starting with empty scene." << std::endl;
    }

    if (batchMode) {
        std::cout << "\n========== BATCH MODE ==========" << std::endl;
        std::cout << "  Input  : " << stlPath << std::endl;
        std::cout << "  Output : " << outputDir << std::endl;
        std::cout << "  Count  : " << sampleCount << std::endl;
        std::cout << "  Radius : " << cameraRadius << std::endl;
        std::cout << "  Size   : " << imageWidth << "x" << imageHeight << std::endl;
        std::cout << "  Mask   : " << (saveMask ? "YES" : "NO") << std::endl;
        std::cout << "================================\n" << std::endl;

        hhb::render::RenderManager::CaptureConfig config;
        config.sampleCount = sampleCount;
        config.outputDir = outputDir;
        config.cameraRadius = cameraRadius;
        config.imageWidth = imageWidth;
        config.imageHeight = imageHeight;
        config.saveMask = saveMask;

        auto result = renderManager.captureSyntheticData(config);

        std::cout << "\nBatch capture result:" << std::endl;
        std::cout << "  Success: " << result.successFrames << " / " << result.totalFrames << std::endl;
        std::cout << "  Failed : " << result.failedFrames << std::endl;
        std::cout << "  Time   : " << result.elapsedSeconds << " seconds" << std::endl;

        return (result.failedFrames > 0) ? 1 : 0;
    }
    
    std::cout << "Entering render loop..." << std::endl;
    while (!renderManager.shouldClose()) {
        renderManager.processInput();
        renderManager.render();
        renderManager.swapBuffers();
    }
    
    return 0;
}