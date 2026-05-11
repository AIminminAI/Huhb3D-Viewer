#ifdef _WIN32
#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#endif

#include <iostream>
#include <cstdlib>
#include <string>
#include <fstream>
#include <vector>
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

std::string getParentPath(const std::string& path) {
    size_t pos = path.find_last_of("\\/");
    return (pos != std::string::npos) ? path.substr(0, pos) : "";
}

int main(int argc, char* argv[]) {
    std::cout << "Starting Huhb3D Synthetic Data Generator..." << std::endl;

    char cwd[1024];
    if (_getcwd(cwd, sizeof(cwd)) != NULL) {
        std::cout << "Current working directory: " << cwd << std::endl;
    }

    std::string stlPath;
    std::string outputDir = "synthetic_output";
    int sampleCount = 1000;
    float cameraRadius = 5.0f;
    int imageWidth = 800;
    int imageHeight = 600;
    bool batchMode = false;
    bool saveMask = true;
    bool saveDepth = false;
    bool instanceSegmentation = true;
    bool multiObjectScene = false;
    bool enableCollisionAvoidance = true;
    bool enableLightRandomization = false;
    bool enableCameraJitter = false;
    bool enableBackgroundRandomization = false;
    std::vector<std::string> sceneObjectPaths;
    std::vector<std::string> backgroundPaths;
    float lightIntensityMin = 0.5f;
    float lightIntensityMax = 2.0f;
    float lightColorTempMin = 3000.0f;
    float lightColorTempMax = 9000.0f;
    float cameraJitterPos = 0.05f;
    float focalJitterRange = 2.0f;
    std::string topologyLabelsPath;
    std::vector<std::string> sceneObjectTopologyPaths;
    bool outputBOPFormat = true;
    float depthScale = 1000.0f;
    std::string modelUnit = "mm";

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
        } else if ((arg == "--height" || arg == "-h") && i + 1 < argc) {
            imageHeight = std::atoi(argv[++i]);
        } else if (arg == "--img-height" && i + 1 < argc) {
            imageHeight = std::atoi(argv[++i]);
        } else if (arg == "--batch" || arg == "-b") {
            batchMode = true;
        } else if (arg == "--no-mask") {
            saveMask = false;
        } else if (arg == "--depth") {
            saveDepth = true;
        } else if (arg == "--instance-segmentation") {
            instanceSegmentation = true;
        } else if (arg == "--no-instance-segmentation") {
            instanceSegmentation = false;
        } else if (arg == "--multi-object") {
            multiObjectScene = true;
        } else if (arg == "--scene-object" && i + 1 < argc) {
            sceneObjectPaths.push_back(argv[++i]);
        } else if (arg == "--light-randomization") {
            enableLightRandomization = true;
        } else if (arg == "--camera-jitter") {
            enableCameraJitter = true;
        } else if (arg == "--background-randomization") {
            enableBackgroundRandomization = true;
        } else if (arg == "--background-dir" && i + 1 < argc) {
            std::string bgDir = argv[++i];
#ifdef _WIN32
            std::string searchPattern = bgDir + "\\*";
            WIN32_FIND_DATAA findData;
            HANDLE hFind = FindFirstFileA(searchPattern.c_str(), &findData);
            if (hFind != INVALID_HANDLE_VALUE) {
                do {
                    std::string fname = findData.cFileName;
                    std::string ext;
                    size_t dotPos = fname.find_last_of('.');
                    if (dotPos != std::string::npos) ext = fname.substr(dotPos);
                    for (auto& c : ext) c = tolower(c);
                    if (ext == ".png" || ext == ".jpg" || ext == ".jpeg" || ext == ".bmp" || ext == ".hdr") {
                        backgroundPaths.push_back(bgDir + "\\" + fname);
                    }
                } while (FindNextFileA(hFind, &findData));
                FindClose(hFind);
            }
#else
            backgroundPaths.push_back(bgDir);
#endif
        } else if (arg == "--background-image" && i + 1 < argc) {
            backgroundPaths.push_back(argv[++i]);
        } else if (arg == "--collision-avoidance") {
            enableCollisionAvoidance = true;
        } else if (arg == "--no-collision-avoidance") {
            enableCollisionAvoidance = false;
        } else if (arg == "--light-intensity-min" && i + 1 < argc) {
            lightIntensityMin = std::atof(argv[++i]);
        } else if (arg == "--light-intensity-max" && i + 1 < argc) {
            lightIntensityMax = std::atof(argv[++i]);
        } else if (arg == "--light-temp-min" && i + 1 < argc) {
            lightColorTempMin = std::atof(argv[++i]);
        } else if (arg == "--light-temp-max" && i + 1 < argc) {
            lightColorTempMax = std::atof(argv[++i]);
        } else if (arg == "--camera-jitter-pos" && i + 1 < argc) {
            cameraJitterPos = std::atof(argv[++i]);
        } else if (arg == "--focal-jitter-range" && i + 1 < argc) {
            focalJitterRange = std::atof(argv[++i]);
        } else if (arg == "--topology-labels" && i + 1 < argc) {
            topologyLabelsPath = argv[++i];
        } else if (arg == "--scene-object-topology" && i + 1 < argc) {
            sceneObjectTopologyPaths.push_back(argv[++i]);
        } else if (arg == "--no-bop-format") {
            outputBOPFormat = false;
        } else if (arg == "--depth-scale" && i + 1 < argc) {
            depthScale = std::atof(argv[++i]);
        } else if (arg == "--model-unit" && i + 1 < argc) {
            modelUnit = argv[++i];
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
    for (auto& p : sceneObjectPaths) p = stripQuotes(p);
    for (auto& p : backgroundPaths) p = stripQuotes(p);

    std::cout << "\n========== PARSED ARGUMENTS ==========" << std::endl;
    std::cout << "  stlPath                : \"" << stlPath << "\"" << std::endl;
    std::cout << "  outputDir              : \"" << outputDir << "\"" << std::endl;
    std::cout << "  sampleCount            : " << sampleCount << std::endl;
    std::cout << "  cameraRadius           : " << cameraRadius << std::endl;
    std::cout << "  imageSize              : " << imageWidth << "x" << imageHeight << std::endl;
    std::cout << "  batchMode              : " << (batchMode ? "true" : "false") << std::endl;
    std::cout << "  saveMask               : " << (saveMask ? "true" : "false") << std::endl;
    std::cout << "  saveDepth              : " << (saveDepth ? "true" : "false") << std::endl;
    std::cout << "  instanceSegmentation   : " << (instanceSegmentation ? "true" : "false") << std::endl;
    std::cout << "  multiObjectScene       : " << (multiObjectScene ? "true" : "false") << std::endl;
    std::cout << "  sceneObjects           : " << sceneObjectPaths.size() << std::endl;
    for (size_t si = 0; si < sceneObjectPaths.size(); ++si) {
        std::cout << "    [" << si << "] " << sceneObjectPaths[si] << std::endl;
    }
    std::cout << "  collisionAvoidance     : " << (enableCollisionAvoidance ? "true" : "false") << std::endl;
    std::cout << "  lightRandomization     : " << (enableLightRandomization ? "true" : "false") << std::endl;
    std::cout << "  lightIntensityRange    : [" << lightIntensityMin << ", " << lightIntensityMax << "]" << std::endl;
    std::cout << "  lightColorTempRange    : [" << lightColorTempMin << ", " << lightColorTempMax << "]" << std::endl;
    std::cout << "  cameraJitter           : " << (enableCameraJitter ? "true" : "false") << std::endl;
    std::cout << "  cameraJitterPos        : " << cameraJitterPos << std::endl;
    std::cout << "  focalJitterRange       : " << focalJitterRange << std::endl;
    std::cout << "  backgroundRandomization: " << (enableBackgroundRandomization ? "true" : "false") << std::endl;
    std::cout << "  backgroundPaths        : " << backgroundPaths.size() << std::endl;
    std::cout << "  topologyLabelsPath     : \"" << topologyLabelsPath << "\"" << std::endl;
    std::cout << "  sceneObjTopologyPaths  : " << sceneObjectTopologyPaths.size() << std::endl;
    std::cout << "  outputBOPFormat        : " << (outputBOPFormat ? "true" : "false") << std::endl;
    std::cout << "======================================\n" << std::endl;

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
    hhb::render::RenderManager renderManager(1280, 720, "Huhb3D Synthetic Data Generator");

    if (!renderManager.initialize()) {
        std::cerr << "Failed to initialize RenderManager" << std::endl;
        return 1;
    }

    if (batchMode) {
        renderManager.setAutomationMode(true);
        std::cout << "Automation mode enabled - ImGui UI rendering disabled" << std::endl;
    }

    if (fileExists(stlPath)) {
        std::cout << "Loading primary STL: " << stlPath << std::endl;
        renderManager.loadFile(stlPath);
    } else {
        std::cerr << "STL file not found: " << stlPath << std::endl;
        if (batchMode) {
            std::cerr << "Cannot run batch mode without a valid STL file!" << std::endl;
            return 1;
        }
        std::cout << "Starting with empty scene." << std::endl;
    }

    if (multiObjectScene && !sceneObjectPaths.empty()) {
        std::cout << "\n--- Loading scene objects ---" << std::endl;
        for (size_t si = 0; si < sceneObjectPaths.size(); ++si) {
            const std::string& objPath = sceneObjectPaths[si];
            if (fileExists(objPath)) {
                std::string objName = "Object_" + std::to_string(si + 2);
                std::cout << "  Adding scene object [" << si << "]: " << objPath << std::endl;
                if (!renderManager.addSceneObject(objPath, objName)) {
                    std::cerr << "  WARNING: Failed to add scene object: " << objPath << std::endl;
                }
            } else {
                std::cerr << "  WARNING: Scene object file not found: " << objPath << std::endl;
            }
        }
        std::cout << "  Total scene objects: " << renderManager.getSceneObjectCount() << std::endl;
    }

    if (batchMode) {
        std::cout << "\n========== BATCH MODE CONFIGURATION ==========" << std::endl;
        std::cout << "  Input           : " << stlPath << std::endl;
        std::cout << "  Output          : " << outputDir << std::endl;
        std::cout << "  Count           : " << sampleCount << std::endl;
        std::cout << "  Radius          : " << cameraRadius << std::endl;
        std::cout << "  Size            : " << imageWidth << "x" << imageHeight << std::endl;
        std::cout << "  Mask            : " << (saveMask ? "YES" : "NO") << std::endl;
        std::cout << "  Depth           : " << (saveDepth ? "YES" : "NO") << std::endl;
        std::cout << "  Instance Seg    : " << (instanceSegmentation ? "YES" : "NO") << std::endl;
        std::cout << "  Multi-Object    : " << (multiObjectScene ? "YES" : "NO") << std::endl;
        std::cout << "  Collision Avoid : " << (enableCollisionAvoidance ? "YES" : "NO") << std::endl;
        std::cout << "  Light Random    : " << (enableLightRandomization ? "YES" : "NO") << std::endl;
        std::cout << "  Camera Jitter   : " << (enableCameraJitter ? "YES" : "NO") << std::endl;
        std::cout << "  Background Rand : " << (enableBackgroundRandomization ? "YES" : "NO") << std::endl;
        std::cout << "===============================================\n" << std::endl;

        hhb::render::RenderManager::CaptureConfig config;
        config.sampleCount = sampleCount;
        config.outputDir = outputDir;
        config.cameraRadius = cameraRadius;
        config.imageWidth = imageWidth;
        config.imageHeight = imageHeight;
        config.saveMask = saveMask;
        config.saveDepth = saveDepth;
        config.instanceSegmentation = instanceSegmentation;
        config.multiObjectScene = multiObjectScene;
        config.enableCollisionAvoidance = enableCollisionAvoidance;

        config.domainRandomization.enableLightRandomization = enableLightRandomization;
        config.domainRandomization.enableCameraJitter = enableCameraJitter;
        config.domainRandomization.enableBackgroundRandomization = enableBackgroundRandomization;
        config.domainRandomization.lightIntensityRange[0] = lightIntensityMin;
        config.domainRandomization.lightIntensityRange[1] = lightIntensityMax;
        config.domainRandomization.lightColorTempRange[0] = lightColorTempMin;
        config.domainRandomization.lightColorTempRange[1] = lightColorTempMax;
        config.domainRandomization.cameraJitterPosRange = cameraJitterPos;
        config.domainRandomization.focalLengthJitterRange = focalJitterRange;
        config.domainRandomization.backgroundPaths = backgroundPaths;

        config.topologyLabelsPath = topologyLabelsPath;
        config.sceneObjectTopologyPaths = sceneObjectTopologyPaths;
        config.outputBOPFormat = outputBOPFormat;
        config.depthScale = depthScale;
        config.modelUnit = modelUnit;

        auto result = renderManager.captureSyntheticData(config);

        std::cout << "\n========== BATCH CAPTURE RESULT ==========" << std::endl;
        std::cout << "  Success : " << result.successFrames << " / " << result.totalFrames << std::endl;
        std::cout << "  Failed  : " << result.failedFrames << std::endl;
        std::cout << "  Time    : " << result.elapsedSeconds << " seconds" << std::endl;
        std::cout << "  Output  : " << result.outputDirectory << std::endl;
        std::cout << "==========================================" << std::endl;

        return (result.failedFrames > 0) ? 1 : 0;
    }

    std::cout << "Entering interactive render loop..." << std::endl;
    while (!renderManager.shouldClose()) {
        renderManager.processInput();
        renderManager.render();
        renderManager.swapBuffers();
    }

    return 0;
}
