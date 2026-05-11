#ifdef _WIN32
#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#endif

#include <cstdint>
#include <iostream>
#include <cmath>
#include <vector>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <fstream>

#include <glad/glad.h>
#define GLFW_INCLUDE_NONE
#include <GLFW/glfw3.h>

#ifdef _WIN32
#include <Windows.h>
#include <commdlg.h>
#define GLFW_EXPOSE_NATIVE_WIN32
#include <GLFW/glfw3native.h>
#endif
#include <glm/glm.hpp>
#include <glm/gtc/matrix_transform.hpp>
#include <glm/gtc/type_ptr.hpp>
#include "imgui/imgui.h"
#include "imgui/imgui_impl_glfw.h"
#include "imgui/imgui_impl_opengl3.h"

#include <chrono>
#include <thread>
#include <iomanip>
#include <sstream>
#include <filesystem>
#include <set>
#include <memory>

#define STB_IMAGE_WRITE_IMPLEMENTATION
#include "stb_image_write.h"

#define STB_IMAGE_IMPLEMENTATION
#include "stb_image.h"

#include "render_manager.h"
#include "../skill/ISkill.h"
#include "../skill/SkillRegistry.h"
#include "../skill/AutoRotateSkill.h"
#include "../skill/ResetCameraSkill.h"
#include "../skill/ZoomInSkill.h"
#include "../skill/RotateSkill.h"
#include "../skill/OptimizeViewSkill.h"
#include "../skill/MeasureModelSkill.h"
#include "../skill/AnalyzeGeometrySkill.h"

namespace hhb {
namespace render {

// 顶点着色器源代码
const char* vertexShaderSource = "\n"
"#version 330\n"
"layout (location = 0) in vec3 aPos;\n"
"layout (location = 1) in vec3 aNormal;\n"
"\n"
"uniform mat4 model;\n"
"uniform mat4 view;\n"
"uniform mat4 projection;\n"
"\n"
"out vec3 Normal;\n"
"out vec3 FragPos;\n"
"\n"
"void main()\n"
"{\n"
"    FragPos = vec3(model * vec4(aPos, 1.0));\n"
"    Normal = mat3(transpose(inverse(model))) * aNormal;\n"
"    gl_Position = projection * view * model * vec4(aPos, 1.0);\n"
"}\n";

// 片元着色器源代码
const char* fragmentShaderSource = "\n"
"#version 330\n"
"out vec4 FragColor;\n"
"\n"
"in vec3 Normal;\n"
"in vec3 FragPos;\n"
"\n"
"uniform vec3 lightPos;\n"
"uniform vec3 viewPos;\n"
"uniform vec3 objectColor;\n"
"uniform vec3 lightColor;\n"
"uniform float metallic;\n"
"uniform float roughness;\n"
"uniform bool isSelected;\n"
"uniform vec3 highlightColor;\n"
"\n"
"// 法线分布函数 (Trowbridge-Reitz GGX)\n"
"float DistributionGGX(vec3 N, vec3 H, float roughness)\n"
"{\n"
"    float a = roughness * roughness;\n"
"    float a2 = a * a;\n"
"    float NdotH = max(dot(N, H), 0.0);\n"
"    float NdotH2 = NdotH * NdotH;\n"
"    \n"
"    float nom   = a2;\n"
"    float denom = (NdotH2 * (a2 - 1.0) + 1.0);\n"
"    denom = 3.1415926535 * denom * denom;\n"
"    \n"
"    return nom / denom;\n"
"}\n"
"\n"
"// 几何函数 (Schlick-GGX)\n"
"float GeometrySchlickGGX(float NdotV, float roughness)\n"
"{\n"
"    float r = (roughness + 1.0);\n"
"    float k = (r * r) / 8.0;\n"
"    \n"
"    float nom   = NdotV;\n"
"    float denom = NdotV * (1.0 - k) + k;\n"
"    \n"
"    return nom / denom;\n"
"}\n"
"\n"
"// 几何函数 (Smith)\n"
"float GeometrySmith(vec3 N, vec3 V, vec3 L, float roughness)\n"
"{\n"
"    float NdotV = max(dot(N, V), 0.0);\n"
"    float NdotL = max(dot(N, L), 0.0);\n"
"    float ggx2 = GeometrySchlickGGX(NdotV, roughness);\n"
"    float ggx1 = GeometrySchlickGGX(NdotL, roughness);\n"
"    \n"
"    return ggx1 * ggx2;\n"
"}\n"
"\n"
"// 菲涅尔方程 (Fresnel-Schlick)\n"
"vec3 FresnelSchlick(float cosTheta, vec3 F0)\n"
"{\n"
"    return F0 + (1.0 - F0) * pow(clamp(1.0 - cosTheta, 0.0, 1.0), 5.0);\n"
"}\n"
"\n"
"void main()\n"
"{\n"
"    if (isSelected) {\n"
"        FragColor = vec4(highlightColor, 1.0);\n"
"        return;\n"
"    }\n"
"    \n"
"    vec3 N = normalize(Normal);\n"
"    // 对于没有法线的模型或者法线错误的情况，如果面向背对，翻转法线\n"
"    if (!gl_FrontFacing) N = -N;\n"
"    \n"
"    vec3 V = normalize(viewPos - FragPos);\n"
"    \n"
"    vec3 F0 = vec3(0.04); \n"
"    F0 = mix(F0, objectColor, metallic);\n"
"    \n"
"    // 反射率方程\n"
"    vec3 Lo = vec3(0.0);\n"
"    \n"
"    // 计算每个光源的辐射度 (这里只有一个点光源)\n"
"    vec3 L = normalize(lightPos - FragPos);\n"
"    vec3 H = normalize(V + L);\n"
"    \n"
"    // 衰减\n"
"    float distance = length(lightPos - FragPos);\n"
"    float attenuation = 1.0 / (distance * distance * 0.01 + 1.0); // 调整了衰减系数，防止模型全黑\n"
"    vec3 radiance = lightColor * attenuation * 500.0; // 增加了光源强度\n"
"    \n"
"    // Cook-Torrance BRDF\n"
"    float NDF = DistributionGGX(N, H, roughness);\n"
"    float G   = GeometrySmith(N, V, L, roughness);\n"
"    vec3 F    = FresnelSchlick(max(dot(H, V), 0.0), F0);\n"
"    \n"
"    vec3 numerator    = NDF * G * F;\n"
"    float denominator = 4.0 * max(dot(N, V), 0.0) * max(dot(N, L), 0.0) + 0.0001;\n"
"    vec3 specular = numerator / denominator;\n"
"    \n"
"    vec3 kS = F;\n"
"    vec3 kD = vec3(1.0) - kS;\n"
"    kD *= 1.0 - metallic;\n"
"    \n"
"    float NdotL = max(dot(N, L), 0.0);\n"
"    \n"
"    Lo += (kD * objectColor / 3.1415926535 + specular) * radiance * NdotL;\n"
"    \n"
"    // 环境光 (基础的)\n"
"    vec3 ambient = vec3(0.2) * objectColor * (1.0 - metallic);\n"
"    \n"
"    vec3 color = ambient + Lo;\n"
"    \n"
"    // HDR色调映射\n"
"    color = color / (color + vec3(1.0));\n"
"    // Gamma校正\n"
"    color = pow(color, vec3(1.0/2.2)); \n"
"    \n"
"    FragColor = vec4(color, 1.0);\n"
"}\n";

const char* labelVertexShaderSource = "\n"
"#version 330\n"
"layout (location = 0) in vec3 aPos;\n"
"layout (location = 1) in vec3 aLabelColor;\n"
"\n"
"uniform mat4 model;\n"
"uniform mat4 view;\n"
"uniform mat4 projection;\n"
"\n"
"out vec3 LabelColor;\n"
"\n"
"void main()\n"
"{\n"
"    LabelColor = aLabelColor;\n"
"    gl_Position = projection * view * model * vec4(aPos, 1.0);\n"
"}\n";

const char* labelFragmentShaderSource = "\n"
"#version 330\n"
"out vec4 FragColor;\n"
"\n"
"in vec3 LabelColor;\n"
"\n"
"void main()\n"
"{\n"
"    FragColor = vec4(LabelColor, 1.0);\n"
"}\n";

RenderManager::RenderManager(int width, int height, const std::string& title)
    : width(width), height(height), title(title), window(nullptr),
      VAO(0), VBO(0), shaderProgram(0),
      labelVAO(0), labelVBO(0), labelShaderProgram(0),
      labelModeActive(false), faceCategoriesComputed(false),
      triangleCount(0),
      trianglePool(nullptr),
      zoom(1.0f), frameCount(0), lastFpsUpdate(0.0f), fps(0.0f),
      metallic(0.5f), roughness(0.5f),
      loadTime(0.0f), memoryUsage(0),
      selectedTriangle(nullptr), selectedTriangleIndex(-1), pickTime(0.0f),
      showBVH(false), showHighlight(false),
      currentHighlightType(HighlightType::None),
      highlightCalculated(false),
      highlightBlinkTimer_(0.0f), highlightBlinkState_(true),
      backgroundVAO_(0), backgroundVBO_(0), backgroundShaderProgram_(0),
      currentBackgroundIndex_(0), backgroundInitialized_(false) {
    commandDispatcher.start(8080);
    cameraPosition[0] = 0.0f;
    cameraPosition[1] = 0.0f;
    cameraPosition[2] = 5.0f;
    
    // 初始化相机旋转
    cameraRotation[0] = 0.0f;
    cameraRotation[1] = 0.0f;
    
    // 初始化时间
    lastFrame = std::chrono::steady_clock::now();
    deltaTime = 0.0f;
    
    // 自动旋转初始化
    autoRotate = false;
    autoRotateSpeed = 0.5f;
    automationMode = false;

    // 相机动画初始化
    cameraAnimating = false;
    targetCameraPos[0] = targetCameraPos[1] = targetCameraPos[2] = 0.0f;
    targetCameraRot[0] = targetCameraRot[1] = 0.0f;
    cameraPosStart[0] = cameraPosStart[1] = cameraPosStart[2] = 0.0f;
    cameraRotStart[0] = cameraRotStart[1] = 0.0f;
    targetZoom = 1.0f;
    zoomStart = 1.0f;
    cameraAnimDuration = 0.5f;
    
    // 初始化文件路径缓冲区
    memset(filePathBuffer, 0, sizeof(filePathBuffer));
}

RenderManager::~RenderManager() {
    // 等待计算线程完成
    if (calculationThread.joinable()) {
        calculationThread.join();
    }
    
    // 清理对象池
    if (trianglePool) {
        delete trianglePool;
        trianglePool = nullptr;
    }
    
    // 清理ImGui
    shutdownImGui();
    
    // 清理OpenGL资源
    glDeleteVertexArrays(1, &VAO);
    glDeleteBuffers(1, &VBO);
    glDeleteProgram(shaderProgram);
    
    glDeleteVertexArrays(1, &labelVAO);
    glDeleteBuffers(1, &labelVBO);
    glDeleteProgram(labelShaderProgram);
    
    // 清理GLFW
    if (window) {
        glfwDestroyWindow(window);
    }
    glfwTerminate();
}

void RenderManager::initSkills() {
    // 获取技能注册表实例
    auto& registry = skill::SkillRegistry::getInstance();
    
    // 注册技能
    registry.registerSkill("auto_rotate", std::make_unique<skill::AutoRotateSkill>(*this));
    registry.registerSkill("reset_camera", std::make_unique<skill::ResetCameraSkill>(*this));
    registry.registerSkill("zoom_in", std::make_unique<skill::ZoomInSkill>(*this));
    registry.registerSkill("rotate", std::make_unique<skill::RotateSkill>(*this));
    registry.registerSkill("optimize_view", std::make_unique<skill::OptimizeViewSkill>(*this));
    registry.registerSkill("measure_model", std::make_unique<skill::MeasureModelSkill>(*this));
    registry.registerSkill("analyze_geometry", std::make_unique<skill::AnalyzeGeometrySkill>(*this));
    
    std::cout << "Skills initialized successfully" << std::endl;
}

bool RenderManager::initialize() {
    // 初始化GLFW
    if (!glfwInit()) {
        std::cerr << "Failed to initialize GLFW" << std::endl;
        return false;
    }
    
    // 设置GLFW窗口属性
    glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 3);
    glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 3);
    glfwWindowHint(GLFW_OPENGL_PROFILE, GLFW_OPENGL_CORE_PROFILE);
    
    // 创建窗口
    window = glfwCreateWindow(width, height, title.c_str(), nullptr, nullptr);
    if (!window) {
        std::cerr << "Failed to create GLFW window" << std::endl;
        glfwTerminate();
        return false;
    }
    
    // 设置当前上下文
    glfwMakeContextCurrent(window);
    
    // 初始化 GLAD
    if (!gladLoadGL((GLADloadfunc)glfwGetProcAddress)) {
        std::cout << "Failed to initialize GLAD" << std::endl;
        return false;
    }
    
    // 设置视口
    glViewport(0, 0, width, height);
    
    // 启用深度测试
    glEnable(GL_DEPTH_TEST);
    
    // 初始化着色器
    if (!initShaders()) {
        return false;
    }
    
    // 初始化标签模式着色器
    if (!initLabelShaders()) {
        std::cerr << "Warning: Label shader initialization failed" << std::endl;
    }
    
    // 初始化缓冲区
    if (!initBuffers()) {
        return false;
    }
    
    // 初始化ImGui
    initImGui();
    
    initSkills();

    // 初始化具身智能 Agent：将几何分析能力注册为 LLM 可调用的工具
    // 设置结果回调，当工具执行完成后自动更新 OpenGL 高亮
    embodiedAgent_.setResultCallback([this](const std::vector<int>& indices, HighlightType type, const std::string& desc) {
        onToolResult(indices, type, desc);
    });

    // 默认配置（用户可通过 UI 修改）
    embodiedAgent_.initialize(
        "https://api.openai.com",
        "",
        "gpt-4o-mini",
        &geometryAPI
    );
    
    return true;
}

void RenderManager::render() {
    if (!automationMode) {
        ImGui_ImplOpenGL3_NewFrame();
        ImGui_ImplGlfw_NewFrame();
        ImGui::NewFrame();
        updateImGui();
    }
    
    // 处理来自网络的命令
    while (commandDispatcher.hasCommand()) {
        hhb::core::Command cmd = commandDispatcher.getCommand();
        
        std::cout << "Processing command: " << cmd.action << " with value: " << cmd.value << std::endl;
        
        if (trianglePool) {
            if (calculationThread.joinable()) {
                calculationThread.join();
            }
            
            calculationThread = std::thread([this, cmd]() {
                std::cout << "Starting analysis in background thread..." << std::endl;
                
                std::vector<hhb::core::Triangle*> result_parts;
                HighlightType htype = HighlightType::None;
                std::string desc;
                
                if (cmd.action == "check_thickness") {
                    result_parts = geometryAPI.getThinParts(static_cast<float>(cmd.value));
                    htype = HighlightType::ThinParts;
                    desc = "薄弱部位 (厚度<" + std::to_string(static_cast<int>(cmd.value)) + "mm)";
                    std::cout << "Found " << result_parts.size() << " thin parts" << std::endl;
                }
                else if (cmd.action == "find_curved_surfaces") {
                    result_parts = geometryAPI.getCurvedSurfaces(static_cast<float>(cmd.value));
                    htype = HighlightType::CurvedSurfaces;
                    desc = "曲面/曲线区域 (曲率>" + std::to_string(static_cast<float>(cmd.value)) + ")";
                    std::cout << "Found " << result_parts.size() << " curved surface triangles" << std::endl;
                }
                else if (cmd.action == "find_sharp_edges") {
                    result_parts = geometryAPI.getSharpEdges(static_cast<float>(cmd.value));
                    htype = HighlightType::SharpEdges;
                    desc = "锐角/棱边区域 (角度>" + std::to_string(static_cast<int>(cmd.value)) + "°)";
                    std::cout << "Found " << result_parts.size() << " sharp edge triangles" << std::endl;
                }
                else if (cmd.action == "find_flat_surfaces") {
                    result_parts = geometryAPI.getFlatSurfaces(static_cast<float>(cmd.value));
                    htype = HighlightType::FlatSurfaces;
                    desc = "平面区域 (平坦度<" + std::to_string(static_cast<float>(cmd.value)) + ")";
                    std::cout << "Found " << result_parts.size() << " flat surface triangles" << std::endl;
                }
                else {
                    std::cout << "Unknown command action: " << cmd.action << std::endl;
                    return;
                }
                
                std::unordered_map<hhb::core::Triangle*, int> ptrToIndex;
                int idx = 0;
                trianglePool->for_each([&](hhb::core::Triangle* tri) {
                    ptrToIndex[tri] = idx;
                    idx++;
                });
                
                std::vector<int> indices;
                for (const auto& tri : result_parts) {
                    auto it = ptrToIndex.find(tri);
                    if (it != ptrToIndex.end()) {
                        indices.push_back(it->second);
                    }
                }
                
                std::cout << "Matched " << indices.size() << " / " << result_parts.size() 
                          << " triangles to VBO indices" << std::endl;
                
                {
                    std::lock_guard<std::mutex> lock(highlightMutex);
                    newHighlightIndices = std::move(indices);
                    currentHighlightType = htype;
                    lastAnalysisDesc = desc;
                }
                
                highlightCalculated = true;
                std::cout << "Analysis completed: " << desc << std::endl;
            });
        }
    }
    
    if (highlightCalculated) {
        {
            std::lock_guard<std::mutex> lock(highlightMutex);
            highlightIndices = std::move(newHighlightIndices);
        }
        
        showHighlight = true;
        highlightCalculated = false;
        
        std::cout << "Updated highlight indices: " << highlightIndices.size() << " parts (" << lastAnalysisDesc << ")" << std::endl;
    }

    // 检查具身智能 Agent 的异步结果
    if (embodiedAgent_.isProcessing()) {
        embodiedAgent_.checkPendingResult();
    }
    
    // 开启深度测试与背景清理
    glEnable(GL_DEPTH_TEST);
    glClearColor(0.1f, 0.1f, 0.1f, 1.0f);
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
    
    // 使用着色器程序
    glUseProgram(shaderProgram);
    
    // 计算 deltaTime
    auto currentFrame = std::chrono::steady_clock::now();
    deltaTime = std::chrono::duration<float>(currentFrame - lastFrame).count();
    lastFrame = currentFrame;
    
    // 自动旋转逻辑
    if (autoRotate) {
        cameraRotation[1] += autoRotateSpeed * deltaTime;
        if (cameraRotation[1] > 360.0f) {
            cameraRotation[1] -= 360.0f;
        }
    }

    // 相机平滑动画更新
    if (cameraAnimating) {
        auto now = std::chrono::steady_clock::now();
        float elapsed = std::chrono::duration<float>(now - cameraAnimStart).count();
        float t = std::min(elapsed / cameraAnimDuration, 1.0f);

        // 使用 smoothstep 进行平滑插值
        t = t * t * (3.0f - 2.0f * t);

        // 插值相机位置
        cameraPosition[0] = cameraPosStart[0] + (targetCameraPos[0] - cameraPosStart[0]) * t;
        cameraPosition[1] = cameraPosStart[1] + (targetCameraPos[1] - cameraPosStart[1]) * t;
        cameraPosition[2] = cameraPosStart[2] + (targetCameraPos[2] - cameraPosStart[2]) * t;

        // 插值相机旋转
        cameraRotation[0] = cameraRotStart[0] + (targetCameraRot[0] - cameraRotStart[0]) * t;
        cameraRotation[1] = cameraRotStart[1] + (targetCameraRot[1] - cameraRotStart[1]) * t;

        // 插值缩放
        zoom = zoomStart + (targetZoom - zoomStart) * t;

        // 检查动画是否完成
        if (t >= 1.0f) {
            cameraAnimating = false;
            cameraPosition[0] = targetCameraPos[0];
            cameraPosition[1] = targetCameraPos[1];
            cameraPosition[2] = targetCameraPos[2];
            cameraRotation[0] = targetCameraRot[0];
            cameraRotation[1] = targetCameraRot[1];
            zoom = targetZoom;
        }
    }

    // 更新 FPS
    updateFPS();
    
    // 设置模型矩阵 - 简单的单位矩阵
    float model[16] = {
        1.0f, 0.0f, 0.0f, 0.0f,
        0.0f, 1.0f, 0.0f, 0.0f,
        0.0f, 0.0f, 1.0f, 0.0f,
        0.0f, 0.0f, 0.0f, 1.0f
    };
    GLint modelLoc = glGetUniformLocation(shaderProgram, "model");
    glUniformMatrix4fv(modelLoc, 1, GL_FALSE, model);
    
    // 设置视图矩阵 (CAD Orbit Camera)
    float distance = 5.0f / zoom;
    
    // 我们围绕 target (cameraPosition) 进行旋转
    float cx = cosf(cameraRotation[0]);
    float sx = sinf(cameraRotation[0]);
    float cy = cosf(cameraRotation[1]);
    float sy = sinf(cameraRotation[1]);
    
    // 相机在世界坐标系下的实际位置
    // x = target_x + dist * cos(pitch) * sin(yaw)
    // y = target_y + dist * sin(pitch)
    // z = target_z + dist * cos(pitch) * cos(yaw)
    float camPosX = cameraPosition[0] + distance * cx * sy;
    float camPosY = cameraPosition[1] + distance * sx;
    float camPosZ = cameraPosition[2] + distance * cx * cy;
    
    // View矩阵（列主序）
    float view[16] = {
        cy, -sx*sy, -cx*sy, 0.0f,
        0.0f, cx, -sx, 0.0f,
        sy, sx*cy, cx*cy, 0.0f,
        0.0f, 0.0f, -distance, 1.0f
    };
    
    // 还要把 target 平移加进去，由于我们在原点旋转后再平移，其实 View 矩阵是:
    // View = LookAt(camPos, target, up)
    // 根据标准推导，旋转矩阵不变，平移部分为 -R * camPos
    // R 是前 3x3 转置，上面已经是 R 了
    view[12] = -(view[0]*camPosX + view[4]*camPosY + view[8]*camPosZ);
    view[13] = -(view[1]*camPosX + view[5]*camPosY + view[9]*camPosZ);
    view[14] = -(view[2]*camPosX + view[6]*camPosY + view[10]*camPosZ);
    
    GLint viewLoc = glGetUniformLocation(shaderProgram, "view");
    glUniformMatrix4fv(viewLoc, 1, GL_FALSE, view);
    
    // 设置投影矩阵
    float aspect = (float)width / (float)height;
    float fov = 45.0f;
    float nearPlane = 0.1f;
    float farPlane = 1000.0f;
    float f = 1.0f / tanf(fov * 0.5f * 3.1415926535f / 180.0f);
    float projection[16] = {
        f / aspect, 0.0f, 0.0f, 0.0f,
        0.0f, f, 0.0f, 0.0f,
        0.0f, 0.0f, (farPlane + nearPlane) / (nearPlane - farPlane), -1.0f,
        0.0f, 0.0f, (2.0f * farPlane * nearPlane) / (nearPlane - farPlane), 0.0f
    };
    GLint projectionLoc = glGetUniformLocation(shaderProgram, "projection");
    glUniformMatrix4fv(projectionLoc, 1, GL_FALSE, projection);
    
    // 设置光源位置
    float lightPos[3] = { camPosX, camPosY + 10.0f, camPosZ };
    GLint lightPosLoc = glGetUniformLocation(shaderProgram, "lightPos");
    glUniform3fv(lightPosLoc, 1, lightPos);
    
    // 设置观察位置
    float camPosArr[3] = { camPosX, camPosY, camPosZ };
    GLint viewPosLoc = glGetUniformLocation(shaderProgram, "viewPos");
    glUniform3fv(viewPosLoc, 1, camPosArr);
    
    // 设置物体颜色
    float objectColor[3] = { 0.8f, 0.8f, 0.8f }; // 调亮一点的默认颜色
    GLint objectColorLoc = glGetUniformLocation(shaderProgram, "objectColor");
    glUniform3fv(objectColorLoc, 1, objectColor);
    
    // 设置光源颜色
    float lightColor[3] = { 1.0f, 1.0f, 1.0f };
    GLint lightColorLoc = glGetUniformLocation(shaderProgram, "lightColor");
    glUniform3fv(lightColorLoc, 1, lightColor);
    
    // 设置高亮参数
    GLint isSelectedLoc = glGetUniformLocation(shaderProgram, "isSelected");
    GLint highlightColorLoc = glGetUniformLocation(shaderProgram, "highlightColor");
    float highlightColor[3] = {1.0f, 0.5f, 0.0f}; // 橙色高亮
    
    // 绑定VAO
    glBindVertexArray(VAO);
    
    // 绘制普通三角形
    if (isSelectedLoc != -1) {
        glUniform1i(isSelectedLoc, GL_FALSE);
    }
    
    // 设置PBR参数，保证每一帧实时更新到Shader
    GLint metallicLoc = glGetUniformLocation(shaderProgram, "metallic");
    if (metallicLoc != -1) {
        glUniform1f(metallicLoc, metallic);
    }
    GLint roughnessLoc = glGetUniformLocation(shaderProgram, "roughness");
    if (roughnessLoc != -1) {
        glUniform1f(roughnessLoc, roughness);
    }
    
    if (triangleCount > 0) {
        glDrawArrays(GL_TRIANGLES, 0, triangleCount * 3);
    }
    
    // 如果有选中的三角形，高亮显示
    if (selectedTriangleIndex >= 0 && isSelectedLoc != -1 && highlightColorLoc != -1) {
        glUniform1i(isSelectedLoc, GL_TRUE);
        glUniform3fv(highlightColorLoc, 1, highlightColor);
        // 只绘制选中的三角形
        glDrawArrays(GL_TRIANGLES, selectedTriangleIndex * 3, 3);
    }
    
    highlightParts();
    
    // 解绑VAO
    glBindVertexArray(0);
    
    // 渲染BVH可视化（如果开启）
    if (showBVH) {
        renderBVH();
    }
    
    if (!automationMode) {
        ImGui::Render();
        renderImGui();
    }
    
    // 更新FPS
    updateFPS();
}

void RenderManager::processInput() {
    // 检查窗口是否需要关闭
    if (glfwGetKey(window, GLFW_KEY_ESCAPE) == GLFW_PRESS) {
        glfwSetWindowShouldClose(window, true);
    }
    
    ImGuiIO& io = ImGui::GetIO();
    
    // 处理鼠标输入
    static bool firstMouse = true;
    static float lastX = width / 2.0f;
    static float lastY = height / 2.0f;
    static bool leftButtonPressed = false;
    
    double xpos, ypos;
    glfwGetCursorPos(window, &xpos, &ypos);
    
    if (firstMouse) {
        lastX = xpos;
        lastY = ypos;
        firstMouse = false;
    }
    
    float xoffset = xpos - lastX;
    float yoffset = lastY - ypos;
    
    lastX = xpos;
    lastY = ypos;
    
    // 只有当ImGui不需要鼠标时才处理3D场景交互
    if (!io.WantCaptureMouse) {
        // 处理鼠标左键旋转（仅在拖动时，不是点击时）
        if (glfwGetMouseButton(window, GLFW_MOUSE_BUTTON_LEFT) == GLFW_PRESS) {
            // 检测是否是新的点击（用于拾取）
            if (!leftButtonPressed) {
                // 鼠标左键按下，处理点击事件（拾取）
                handleMouseClick(xpos, ypos);
                leftButtonPressed = true;
            }
            
            // 旋转相机
            float sensitivity = 0.005f;
            xoffset *= sensitivity;
            yoffset *= sensitivity;
            
            cameraRotation[1] += xoffset;
            cameraRotation[0] += yoffset;
            
            // 限制视角范围
            if (cameraRotation[0] > 1.57079632679f) {
                cameraRotation[0] = 1.57079632679f;
            }
            if (cameraRotation[0] < -1.57079632679f) {
                cameraRotation[0] = -1.57079632679f;
            }
        } else {
            leftButtonPressed = false;
        }
        
        // 处理鼠标中键平移
        if (glfwGetMouseButton(window, GLFW_MOUSE_BUTTON_MIDDLE) == GLFW_PRESS) {
            float panSensitivity = 0.002f * zoom;
            // 计算相机右向量和上向量以进行平移
            float cos_rot_x = cosf(cameraRotation[0]);
            float sin_rot_x = sinf(cameraRotation[0]);
            float cos_rot_y = cosf(cameraRotation[1]);
            float sin_rot_y = sinf(cameraRotation[1]);
            
            // 相机坐标系下的右向量 (1,0,0) 转换到世界坐标系
            float rightX = cos_rot_y;
            float rightY = 0.0f;
            float rightZ = -sin_rot_y;
            
            // 相机坐标系下的上向量 (0,1,0) 转换到世界坐标系
            float upX = sin_rot_y * sin_rot_x;
            float upY = cos_rot_x;
            float upZ = cos_rot_y * sin_rot_x;
            
            // 移动相机
            cameraPosition[0] -= rightX * xoffset * panSensitivity;
            cameraPosition[1] -= rightY * xoffset * panSensitivity;
            cameraPosition[2] -= rightZ * xoffset * panSensitivity;
            
            cameraPosition[0] += upX * yoffset * panSensitivity;
            cameraPosition[1] += upY * yoffset * panSensitivity;
            cameraPosition[2] += upZ * yoffset * panSensitivity;
        }
    } else {
        // ImGui正在使用鼠标，重置按钮状态
        leftButtonPressed = false;
    }
    
    // 设置窗口用户指针（用于滚轮回调）
    glfwSetWindowUserPointer(window, this);
}

bool RenderManager::shouldClose() {
    return glfwWindowShouldClose(window);
}

void RenderManager::swapBuffers() {
    glfwSwapBuffers(window);
    glfwPollEvents();
    
    // 计算deltaTime
    auto currentFrame = std::chrono::steady_clock::now();
    deltaTime = std::chrono::duration<float>(currentFrame - lastFrame).count();
    lastFrame = currentFrame;
}

void RenderManager::setTriangles(hhb::core::ObjectPool<hhb::core::Triangle>& pool) {
    // 保存三角形池的指针
    trianglePool = &pool;
    
    // 更新顶点数据
    updateVertexData(pool);
    
    // 更新缓冲区
    glBindBuffer(GL_ARRAY_BUFFER, VBO);
    glBufferData(GL_ARRAY_BUFFER, vertexData.size() * sizeof(float), vertexData.data(), GL_STATIC_DRAW);
    
    // 设置顶点属性指针
    // glVertexAttribPointer参数定义：
    // 第一个参数：属性索引，对应着色器中的layout(location = 0)
    // 第二个参数：属性大小，这里是3个顶点数（x, y, z）
    // 第三个参数：数据类型，这里是GL_FLOAT
    // 第四个参数：是否标准化，这里是GL_FALSE
    // 第五个参数：步长，每个顶点的大小（位置3个顶点数 + 法线3个顶点数 = 6个顶点数）
    // 第六个参数：偏移量，从缓冲区开始的偏移量
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 6 * sizeof(float), (void*)0);
    glEnableVertexAttribArray(0);
    
    // 设置法线向量属性指针
    glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 6 * sizeof(float), (void*)(3 * sizeof(float)));
    glEnableVertexAttribArray(1);
    
    glBindBuffer(GL_ARRAY_BUFFER, 0);
    
    // 构建BVH树
    buildBVH();
}

GLuint RenderManager::loadShader(GLenum type, const char* source) {
    GLuint shader = glCreateShader(type);
    glShaderSource(shader, 1, (const GLchar**)&source, nullptr);
    glCompileShader(shader);
    
    // 检查编译错误
    int success;
    char infoLog[512];
    glGetShaderiv(shader, GL_COMPILE_STATUS, &success);
    if (!success) {
        glGetShaderInfoLog(shader, 512, nullptr, (GLchar*)infoLog);
        std::cerr << "Shader compilation error: " << infoLog << std::endl;
        return 0;
    }
    
    return shader;
}

GLuint RenderManager::createShaderProgram(const char* vertexSource, const char* fragmentSource) {
    GLuint vertexShader = loadShader(GL_VERTEX_SHADER, vertexSource);
    GLuint fragmentShader = loadShader(GL_FRAGMENT_SHADER, fragmentSource);
    
    if (!vertexShader || !fragmentShader) {
        return 0;
    }
    
    GLuint program = glCreateProgram();
    glAttachShader(program, vertexShader);
    glAttachShader(program, fragmentShader);
    glLinkProgram(program);
    
    // 检查链接错误
    int success;
    char infoLog[512];
    glGetProgramiv(program, GL_LINK_STATUS, &success);
    if (!success) {
        glGetProgramInfoLog(program, 512, nullptr, (GLchar*)infoLog);
        std::cerr << "Program linking error: " << infoLog << std::endl;
        return 0;
    }
    
    // 删除着色器，因为它们已经链接到程序中
    glDeleteShader(vertexShader);
    glDeleteShader(fragmentShader);
    
    return program;
}

bool RenderManager::initShaders() {
    shaderProgram = createShaderProgram(vertexShaderSource, fragmentShaderSource);
    if (!shaderProgram) {
        return false;
    }
    
    return true;
}

bool RenderManager::initLabelShaders() {
    labelShaderProgram = createShaderProgram(labelVertexShaderSource, labelFragmentShaderSource);
    if (!labelShaderProgram) {
        std::cerr << "Failed to create label shader program" << std::endl;
        return false;
    }

    glGenVertexArrays(1, &labelVAO);
    glGenBuffers(1, &labelVBO);

    glBindVertexArray(labelVAO);
    glBindBuffer(GL_ARRAY_BUFFER, labelVBO);

    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 6 * sizeof(float), (void*)0);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 6 * sizeof(float), (void*)(3 * sizeof(float)));
    glEnableVertexAttribArray(1);

    glBindBuffer(GL_ARRAY_BUFFER, 0);
    glBindVertexArray(0);

    return true;
}

void RenderManager::categoryToColor(int categoryId, float* outR, float* outG, float* outB) {
    switch (categoryId) {
        case 0:  *outR = 0.50f; *outG = 0.50f; *outB = 0.50f; break;
        case 1:  *outR = 0.00f; *outG = 0.00f; *outB = 1.00f; break;
        case 2:  *outR = 0.00f; *outG = 1.00f; *outB = 0.00f; break;
        case 3:  *outR = 1.00f; *outG = 0.00f; *outB = 0.00f; break;
        case 4:  *outR = 1.00f; *outG = 1.00f; *outB = 0.00f; break;
        case 5:  *outR = 1.00f; *outG = 0.00f; *outB = 1.00f; break;
        case 6:  *outR = 0.00f; *outG = 1.00f; *outB = 1.00f; break;
        case 7:  *outR = 1.00f; *outG = 0.50f; *outB = 0.00f; break;
        case 8:  *outR = 0.50f; *outG = 0.00f; *outB = 1.00f; break;
        case 9:  *outR = 0.00f; *outG = 0.50f; *outB = 1.00f; break;
        case 10: *outR = 0.80f; *outG = 0.80f; *outB = 0.00f; break;
        case 11: *outR = 0.00f; *outG = 0.80f; *outB = 0.40f; break;
        default: *outR = 1.00f; *outG = 1.00f; *outB = 1.00f; break;
    }
}

void RenderManager::computeFaceCategories() {
    if (!trianglePool || triangleCount == 0) {
        faceCategoryIds.clear();
        faceCategoriesComputed = false;
        return;
    }

    faceCategoryIds.resize(triangleCount, 0);

    trianglePool->for_each([&](hhb::core::Triangle* tri) {
        static size_t idx = 0;
        if (idx >= triangleCount) {
            idx = 0;
        }

        float nx = tri->normal[0];
        float ny = tri->normal[1];
        float nz = tri->normal[2];
        float nLen = std::sqrt(nx * nx + ny * ny + nz * nz);
        if (nLen > 0.0001f) { nx /= nLen; ny /= nLen; nz /= nLen; }

        float absNx = std::abs(nx);
        float absNy = std::abs(ny);
        float absNz = std::abs(nz);
        float maxComp = std::max({absNx, absNy, absNz});

        float e1[3] = {tri->vertex2[0] - tri->vertex1[0],
                        tri->vertex2[1] - tri->vertex1[1],
                        tri->vertex2[2] - tri->vertex1[2]};
        float e2[3] = {tri->vertex3[0] - tri->vertex1[0],
                        tri->vertex3[1] - tri->vertex1[1],
                        tri->vertex3[2] - tri->vertex1[2]};
        float cross[3] = {
            e1[1] * e2[2] - e1[2] * e2[1],
            e1[2] * e2[0] - e1[0] * e2[2],
            e1[0] * e2[1] - e1[1] * e2[0]
        };
        float area = 0.5f * std::sqrt(cross[0]*cross[0] + cross[1]*cross[1] + cross[2]*cross[2]);

        int category = 0;

        if (area < 0.00001f) {
            category = 7;
        }
        else if (maxComp > 0.98f) {
            if (absNy > 0.98f)       category = 1;
            else if (absNx > 0.98f)  category = 2;
            else                     category = 3;
        }
        else if (maxComp > 0.85f) {
            if (absNy >= absNx && absNy >= absNz) category = 4;
            else if (absNx >= absNz)              category = 5;
            else                                  category = 6;
        }
        else {
            category = 0;
        }

        faceCategoryIds[idx] = category;
        idx++;
    });

    faceCategoriesComputed = true;
    printf("[LabelMode] Face categories computed: %zu triangles classified\n", faceCategoryIds.size());
    fflush(stdout);
}

void RenderManager::computeCurvature() {
    if (!trianglePool || triangleCount == 0) {
        faceGaussianCurvature.clear();
        faceMeanCurvature.clear();
        faceCurvatureIds.clear();
        curvatureComputed = false;
        return;
    }

    faceGaussianCurvature.resize(triangleCount, 0.0f);
    faceMeanCurvature.resize(triangleCount, 0.0f);
    faceCurvatureIds.resize(triangleCount, 0);

    struct VertexInfo {
        float normal[3] = {0, 0, 0};
        float areaSum = 0.0f;
        int valence = 0;
        float pos[3] = {0, 0, 0};
    };

    std::unordered_map<int64_t, VertexInfo> vertexMap;

    auto vertexKey = [](float x, float y, float z) -> int64_t {
        int ix = (int)(x * 10000.0f);
        int iy = (int)(y * 10000.0f);
        int iz = (int)(z * 10000.0f);
        return ((int64_t)(ix & 0xFFFFF) << 40) | ((int64_t)(iy & 0xFFFFF) << 20) | (int64_t)(iz & 0xFFFFF);
    };

    trianglePool->for_each([&](hhb::core::Triangle* tri) {
        float e1[3] = {tri->vertex2[0] - tri->vertex1[0],
                        tri->vertex2[1] - tri->vertex1[1],
                        tri->vertex2[2] - tri->vertex1[2]};
        float e2[3] = {tri->vertex3[0] - tri->vertex1[0],
                        tri->vertex3[1] - tri->vertex1[1],
                        tri->vertex3[2] - tri->vertex1[2]};
        float cross[3] = {
            e1[1] * e2[2] - e1[2] * e2[1],
            e1[2] * e2[0] - e1[0] * e2[2],
            e1[0] * e2[1] - e1[1] * e2[0]
        };
        float area = 0.5f * std::sqrt(cross[0]*cross[0] + cross[1]*cross[1] + cross[2]*cross[2]);

        float nx = tri->normal[0], ny = tri->normal[1], nz = tri->normal[2];
        float nLen = std::sqrt(nx*nx + ny*ny + nz*nz);
        if (nLen > 0.0001f) { nx /= nLen; ny /= nLen; nz /= nLen; }

        int64_t keys[3] = {
            vertexKey(tri->vertex1[0], tri->vertex1[1], tri->vertex1[2]),
            vertexKey(tri->vertex2[0], tri->vertex2[1], tri->vertex2[2]),
            vertexKey(tri->vertex3[0], tri->vertex3[1], tri->vertex3[2])
        };

        float* verts[3] = {&tri->vertex1[0], &tri->vertex2[0], &tri->vertex3[0]};

        for (int v = 0; v < 3; ++v) {
            auto& info = vertexMap[keys[v]];
            info.normal[0] += nx * area;
            info.normal[1] += ny * area;
            info.normal[2] += nz * area;
            info.areaSum += area;
            info.valence++;
            info.pos[0] = verts[v][0];
            info.pos[1] = verts[v][1];
            info.pos[2] = verts[v][2];
        }
    });

    for (auto& [key, info] : vertexMap) {
        if (info.areaSum > 0.00001f) {
            info.normal[0] /= info.areaSum;
            info.normal[1] /= info.areaSum;
            info.normal[2] /= info.areaSum;
            float nLen = std::sqrt(info.normal[0]*info.normal[0] +
                                    info.normal[1]*info.normal[1] +
                                    info.normal[2]*info.normal[2]);
            if (nLen > 0.0001f) {
                info.normal[0] /= nLen;
                info.normal[1] /= nLen;
                info.normal[2] /= nLen;
            }
        }
    }

    size_t idx = 0;
    trianglePool->for_each([&](hhb::core::Triangle* tri) {
        if (idx >= triangleCount) return;

        int64_t keys[3] = {
            vertexKey(tri->vertex1[0], tri->vertex1[1], tri->vertex1[2]),
            vertexKey(tri->vertex2[0], tri->vertex2[1], tri->vertex2[2]),
            vertexKey(tri->vertex3[0], tri->vertex3[1], tri->vertex3[2])
        };

        float e1[3] = {tri->vertex2[0] - tri->vertex1[0],
                        tri->vertex2[1] - tri->vertex1[1],
                        tri->vertex2[2] - tri->vertex1[2]};
        float e2[3] = {tri->vertex3[0] - tri->vertex1[0],
                        tri->vertex3[1] - tri->vertex1[1],
                        tri->vertex3[2] - tri->vertex1[2]};
        float cross[3] = {
            e1[1] * e2[2] - e1[2] * e2[1],
            e1[2] * e2[0] - e1[0] * e2[2],
            e1[0] * e2[1] - e1[1] * e2[0]
        };
        float area = 0.5f * std::sqrt(cross[0]*cross[0] + cross[1]*cross[1] + cross[2]*cross[2]);

        float meanCurv = 0.0f;

        if (area > 0.00001f) {
            for (int v = 0; v < 3; ++v) {
                auto it = vertexMap.find(keys[v]);
                if (it != vertexMap.end()) {
                    float dx = it->second.pos[0] - tri->vertex1[0];
                    float dy = it->second.pos[1] - tri->vertex1[1];
                    float dz = it->second.pos[2] - tri->vertex1[2];
                    float dist = std::sqrt(dx*dx + dy*dy + dz*dz);

                    float dotProd = it->second.normal[0] * tri->normal[0] +
                                    it->second.normal[1] * tri->normal[1] +
                                    it->second.normal[2] * tri->normal[2];
                    float angle = std::acos(std::max(-1.0f, std::min(1.0f, dotProd)));
                    meanCurv += angle / dist;
                }
            }
            meanCurv /= (3.0f * area);
        }

        float gaussianCurv = 0.0f;
        if (area > 0.00001f) {
            float angleSum = 0.0f;
            for (int v = 0; v < 3; ++v) {
                auto it = vertexMap.find(keys[v]);
                if (it != vertexMap.end() && it->second.valence > 0) {
                    angleSum += 2.0f * 3.14159265f / it->second.valence;
                }
            }
            gaussianCurv = (angleSum - 3.14159265f) / area;
        }

        faceMeanCurvature[idx] = meanCurv;
        faceGaussianCurvature[idx] = gaussianCurv;

        float absMean = std::abs(meanCurv);
        float absGauss = std::abs(gaussianCurv);

        if (absMean < 0.5f && absGauss < 0.5f) {
            faceCurvatureIds[idx] = 0;
        } else if (absGauss > 2.0f && gaussianCurv > 0) {
            faceCurvatureIds[idx] = 1;
        } else if (absGauss > 2.0f && gaussianCurv < 0) {
            faceCurvatureIds[idx] = 2;
        } else if (absMean > 1.0f && meanCurv > 0) {
            faceCurvatureIds[idx] = 3;
        } else if (absMean > 1.0f && meanCurv < 0) {
            faceCurvatureIds[idx] = 4;
        } else {
            faceCurvatureIds[idx] = 5;
        }

        idx++;
    });

    curvatureComputed = true;
    printf("[Curvature] Computed for %zu triangles\n", faceMeanCurvature.size());
    fflush(stdout);
}

void RenderManager::computeGeometricFeatures() {
    if (!curvatureComputed) {
        computeCurvature();
    }

    if (!trianglePool || triangleCount == 0) {
        geometricFeaturesComputed = false;
        return;
    }

    faceCategoryIds.resize(triangleCount, 0);

    struct EdgeKey {
        int64_t v0, v1;
        bool operator==(const EdgeKey& o) const { return v0 == o.v0 && v1 == o.v1; }
    };
    struct EdgeKeyHash {
        size_t operator()(const EdgeKey& k) const { return std::hash<int64_t>()(k.v0) ^ (std::hash<int64_t>()(k.v1) << 1); }
    };

    auto vertexKey = [](float x, float y, float z) -> int64_t {
        int ix = (int)(x * 10000.0f);
        int iy = (int)(y * 10000.0f);
        int iz = (int)(z * 10000.0f);
        return ((int64_t)(ix & 0xFFFFF) << 40) | ((int64_t)(iy & 0xFFFFF) << 20) | (int64_t)(iz & 0xFFFFF);
    };

    auto makeEdge = [](int64_t a, int64_t b) -> EdgeKey {
        return a < b ? EdgeKey{a, b} : EdgeKey{b, a};
    };

    std::unordered_map<EdgeKey, std::vector<int>, EdgeKeyHash> edgeToTriangles;
    std::vector<int64_t> triVertexKeys(triangleCount * 3);

    size_t idx = 0;
    trianglePool->for_each([&](hhb::core::Triangle* tri) {
        if (idx >= triangleCount) return;

        int64_t k1 = vertexKey(tri->vertex1[0], tri->vertex1[1], tri->vertex1[2]);
        int64_t k2 = vertexKey(tri->vertex2[0], tri->vertex2[1], tri->vertex2[2]);
        int64_t k3 = vertexKey(tri->vertex3[0], tri->vertex3[1], tri->vertex3[2]);

        triVertexKeys[idx * 3 + 0] = k1;
        triVertexKeys[idx * 3 + 1] = k2;
        triVertexKeys[idx * 3 + 2] = k3;

        edgeToTriangles[makeEdge(k1, k2)].push_back((int)idx);
        edgeToTriangles[makeEdge(k2, k3)].push_back((int)idx);
        edgeToTriangles[makeEdge(k1, k3)].push_back((int)idx);

        idx++;
    });

    std::vector<bool> visited(triangleCount, false);
    std::vector<std::vector<int>> clusters;

    for (size_t start = 0; start < triangleCount; ++start) {
        if (visited[start]) continue;

        int curvId = faceCurvatureIds[start];
        std::vector<int> cluster;
        std::vector<int> stack;
        stack.push_back((int)start);

        while (!stack.empty()) {
            int triIdx = stack.back();
            stack.pop_back();
            if (triIdx < 0 || triIdx >= (int)triangleCount || visited[triIdx]) continue;
            if (faceCurvatureIds[triIdx] != curvId) continue;

            visited[triIdx] = true;
            cluster.push_back(triIdx);

            int64_t k1 = triVertexKeys[triIdx * 3 + 0];
            int64_t k2 = triVertexKeys[triIdx * 3 + 1];
            int64_t k3 = triVertexKeys[triIdx * 3 + 2];

            auto addNeighbors = [&](int64_t a, int64_t b) {
                EdgeKey ek = makeEdge(a, b);
                auto it = edgeToTriangles.find(ek);
                if (it != edgeToTriangles.end()) {
                    for (int nIdx : it->second) {
                        if (!visited[nIdx] && faceCurvatureIds[nIdx] == curvId) {
                            stack.push_back(nIdx);
                        }
                    }
                }
            };

            addNeighbors(k1, k2);
            addNeighbors(k2, k3);
            addNeighbors(k1, k3);
        }

        if (!cluster.empty()) {
            clusters.push_back(std::move(cluster));
        }
    }

    printf("[GeoFeature] Found %zu curvature clusters\n", clusters.size());

    int boundaryEdgeCount = 0;
    for (const auto& [ek, tris] : edgeToTriangles) {
        if (tris.size() == 1) boundaryEdgeCount++;
    }

    for (auto& cluster : clusters) {
        float totalArea = 0.0f;
        float centerX = 0, centerY = 0, centerZ = 0;
        float avgMeanCurv = 0;
        float avgGaussCurv = 0;
        int boundaryEdges = 0;

        std::unordered_set<int> clusterSet(cluster.begin(), cluster.end());

        for (int triIdx : cluster) {
            float e1[3], e2[3];
            trianglePool->for_each([&](hhb::core::Triangle* tri) {
                static size_t counter = 0;
                if (counter == (size_t)triIdx) {
                    e1[0] = tri->vertex2[0] - tri->vertex1[0];
                    e1[1] = tri->vertex2[1] - tri->vertex1[1];
                    e1[2] = tri->vertex2[2] - tri->vertex1[2];
                    e2[0] = tri->vertex3[0] - tri->vertex1[0];
                    e2[1] = tri->vertex3[1] - tri->vertex1[1];
                    e2[2] = tri->vertex3[2] - tri->vertex1[2];
                    centerX += (tri->vertex1[0] + tri->vertex2[0] + tri->vertex3[0]) / 3.0f;
                    centerY += (tri->vertex1[1] + tri->vertex2[1] + tri->vertex3[1]) / 3.0f;
                    centerZ += (tri->vertex1[2] + tri->vertex2[2] + tri->vertex3[2]) / 3.0f;
                }
                counter++;
                if (counter >= triangleCount) counter = 0;
            });

            float cross[3] = {
                e1[1]*e2[2] - e1[2]*e2[1],
                e1[2]*e2[0] - e1[0]*e2[2],
                e1[0]*e2[1] - e1[1]*e2[0]
            };
            float area = 0.5f * std::sqrt(cross[0]*cross[0] + cross[1]*cross[1] + cross[2]*cross[2]);
            totalArea += area;
            avgMeanCurv += faceMeanCurvature[triIdx];
            avgGaussCurv += faceGaussianCurvature[triIdx];

            int64_t k1 = triVertexKeys[triIdx * 3 + 0];
            int64_t k2 = triVertexKeys[triIdx * 3 + 1];
            int64_t k3 = triVertexKeys[triIdx * 3 + 2];

            auto checkBoundary = [&](int64_t a, int64_t b) {
                EdgeKey ek = makeEdge(a, b);
                auto it = edgeToTriangles.find(ek);
                if (it != edgeToTriangles.end() && it->second.size() == 1) {
                    boundaryEdges++;
                } else if (it != edgeToTriangles.end()) {
                    bool hasExternal = false;
                    for (int nIdx : it->second) {
                        if (clusterSet.find(nIdx) == clusterSet.end()) {
                            hasExternal = true;
                            break;
                        }
                    }
                    if (hasExternal) boundaryEdges++;
                }
            };
            checkBoundary(k1, k2);
            checkBoundary(k2, k3);
            checkBoundary(k1, k3);
        }

        if (cluster.empty()) continue;
        avgMeanCurv /= cluster.size();
        avgGaussCurv /= cluster.size();
        centerX /= cluster.size();
        centerY /= cluster.size();
        centerZ /= cluster.size();

        int featureCategory = 0;

        if (cluster.size() < 5) {
            featureCategory = 0;
        }
        else if (avgGaussCurv > 1.5f && avgMeanCurv > 0.5f && totalArea < 0.5f) {
            featureCategory = 8;
        }
        else if (avgGaussCurv > 1.5f && avgMeanCurv < -0.5f && totalArea < 0.3f) {
            featureCategory = 9;
        }
        else if (avgMeanCurv < -1.0f && boundaryEdges >= 3) {
            featureCategory = 10;
        }
        else if (avgMeanCurv > 1.0f && totalArea > 0.1f && totalArea < 2.0f) {
            featureCategory = 11;
        }
        else if (std::abs(avgMeanCurv) < 0.5f && std::abs(avgGaussCurv) < 0.5f) {
            featureCategory = 1;
        }
        else {
            featureCategory = 0;
        }

        for (int triIdx : cluster) {
            faceCategoryIds[triIdx] = featureCategory;
        }
    }

    faceCategoriesComputed = true;
    geometricFeaturesComputed = true;
    printf("[GeoFeature] Geometric feature classification complete\n");
    fflush(stdout);
}

void RenderManager::updateLabelVertexData() {
    if (!faceCategoriesComputed || faceCategoryIds.empty()) {
        computeFaceCategories();
    }

    std::vector<float> labelData;
    labelData.reserve(triangleCount * 3 * 6);

    size_t triIdx = 0;
    if (trianglePool) {
        trianglePool->for_each([&](hhb::core::Triangle* tri) {
            int catId = (triIdx < faceCategoryIds.size()) ? faceCategoryIds[triIdx] : 0;
            float r, g, b;
            categoryToColor(catId, &r, &g, &b);

            labelData.push_back(tri->vertex1[0]); labelData.push_back(tri->vertex1[1]); labelData.push_back(tri->vertex1[2]);
            labelData.push_back(r); labelData.push_back(g); labelData.push_back(b);

            labelData.push_back(tri->vertex2[0]); labelData.push_back(tri->vertex2[1]); labelData.push_back(tri->vertex2[2]);
            labelData.push_back(r); labelData.push_back(g); labelData.push_back(b);

            labelData.push_back(tri->vertex3[0]); labelData.push_back(tri->vertex3[1]); labelData.push_back(tri->vertex3[2]);
            labelData.push_back(r); labelData.push_back(g); labelData.push_back(b);

            triIdx++;
        });
    }

    glBindBuffer(GL_ARRAY_BUFFER, labelVBO);
    glBufferData(GL_ARRAY_BUFFER, labelData.size() * sizeof(float), labelData.data(), GL_STATIC_DRAW);
    glBindBuffer(GL_ARRAY_BUFFER, 0);
}

void RenderManager::renderLabelMode() {
    if (!labelShaderProgram || triangleCount == 0) return;

    glUseProgram(labelShaderProgram);

    float modelMat[16] = {
        1.0f, 0.0f, 0.0f, 0.0f,
        0.0f, 1.0f, 0.0f, 0.0f,
        0.0f, 0.0f, 1.0f, 0.0f,
        0.0f, 0.0f, 0.0f, 1.0f
    };
    GLint modelLoc = glGetUniformLocation(labelShaderProgram, "model");
    glUniformMatrix4fv(modelLoc, 1, GL_FALSE, modelMat);

    float distance = 5.0f / zoom;
    float cx = cosf(cameraRotation[0]);
    float sx = sinf(cameraRotation[0]);
    float cy = cosf(cameraRotation[1]);
    float sy = sinf(cameraRotation[1]);
    float camPosX = cameraPosition[0] + distance * cx * sy;
    float camPosY = cameraPosition[1] + distance * sx;
    float camPosZ = cameraPosition[2] + distance * cx * cy;

    float view[16] = {
        cy, -sx*sy, -cx*sy, 0.0f,
        0.0f, cx, -sx, 0.0f,
        sy, sx*cy, cx*cy, 0.0f,
        0.0f, 0.0f, -distance, 1.0f
    };
    view[12] = -(view[0]*camPosX + view[4]*camPosY + view[8]*camPosZ);
    view[13] = -(view[1]*camPosX + view[5]*camPosY + view[9]*camPosZ);
    view[14] = -(view[2]*camPosX + view[6]*camPosY + view[10]*camPosZ);

    GLint viewLoc = glGetUniformLocation(labelShaderProgram, "view");
    glUniformMatrix4fv(viewLoc, 1, GL_FALSE, view);

    float aspect = (float)width / (float)height;
    float fov = 45.0f;
    float nearPlane = 0.1f;
    float farPlane = 1000.0f;
    float f = 1.0f / tanf(fov * 0.5f * 3.1415926535f / 180.0f);
    float projection[16] = {
        f / aspect, 0.0f, 0.0f, 0.0f,
        0.0f, f, 0.0f, 0.0f,
        0.0f, 0.0f, (farPlane + nearPlane) / (nearPlane - farPlane), -1.0f,
        0.0f, 0.0f, (2.0f * farPlane * nearPlane) / (nearPlane - farPlane), 0.0f
    };
    GLint projectionLoc = glGetUniformLocation(labelShaderProgram, "projection");
    glUniformMatrix4fv(projectionLoc, 1, GL_FALSE, projection);

    glBindVertexArray(labelVAO);
    glDrawArrays(GL_TRIANGLES, 0, triangleCount * 3);
    glBindVertexArray(0);

    glUseProgram(0);
}

void RenderManager::setLabelMode(bool active) {
    labelModeActive = active;
    if (active && !faceCategoriesComputed) {
        computeFaceCategories();
        updateLabelVertexData();
    }
}

bool RenderManager::initBuffers() {
    // 创建VAO和VBO
    glGenVertexArrays(1, &VAO);
    glGenBuffers(1, &VBO);
    
    // 绑定VAO
    glBindVertexArray(VAO);
    
    // 绑定VBO
    glBindBuffer(GL_ARRAY_BUFFER, VBO);
    
    // 解绑VAO和VBO
    glBindBuffer(GL_ARRAY_BUFFER, 0);
    glBindVertexArray(0);
    
    return true;
}

void RenderManager::updateVertexData(hhb::core::ObjectPool<hhb::core::Triangle>& pool) {
    // 清空顶点数据
    vertexData.clear();
    
    // 遍历ObjectPool中的所有三角形
    triangleCount = 0;
    
    // 使用ObjectPool的for_each方法遍历所有三角形
    pool.for_each([&](hhb::core::Triangle* tri) {
        // 添加顶点1
        vertexData.push_back(tri->vertex1[0]);
        vertexData.push_back(tri->vertex1[1]);
        vertexData.push_back(tri->vertex1[2]);
        // 添加法线
        vertexData.push_back(tri->normal[0]);
        vertexData.push_back(tri->normal[1]);
        vertexData.push_back(tri->normal[2]);
        
        // 添加顶点2
        vertexData.push_back(tri->vertex2[0]);
        vertexData.push_back(tri->vertex2[1]);
        vertexData.push_back(tri->vertex2[2]);
        // 添加法线
        vertexData.push_back(tri->normal[0]);
        vertexData.push_back(tri->normal[1]);
        vertexData.push_back(tri->normal[2]);
        
        // 添加顶点3
        vertexData.push_back(tri->vertex3[0]);
        vertexData.push_back(tri->vertex3[1]);
        vertexData.push_back(tri->vertex3[2]);
        // 添加法线
        vertexData.push_back(tri->normal[0]);
        vertexData.push_back(tri->normal[1]);
        vertexData.push_back(tri->normal[2]);
        
        triangleCount++;
    });
    
    std::cout << "Extracted " << triangleCount << " triangles from ObjectPool" << std::endl;
}

void RenderManager::updateFPS() {
    frameCount++;
    lastFpsUpdate += deltaTime;
    
    if (lastFpsUpdate >= 1.0f) {
        fps = frameCount / lastFpsUpdate;
        frameCount = 0;
        lastFpsUpdate = 0.0f;
        
        // 更新窗口标题
        std::string newTitle = title + " - FPS: " + std::to_string((int)fps);
        glfwSetWindowTitle(window, newTitle.c_str());
    }
}

void RenderManager::buildBVH() {
    std::cout << "Building BVH tree..." << std::endl;
    
    // 清空三角形指针数组
    trianglePtrs.clear();
    
    // 收集所有三角形指针
    trianglePool->for_each([&](hhb::core::Triangle* tri) {
        trianglePtrs.push_back(tri);
    });
    
    std::cout << "Collected " << trianglePtrs.size() << " triangles for BVH build" << std::endl;
    
    // 构建BVH树
    auto start_time = std::chrono::high_resolution_clock::now();
    bvh.build(trianglePtrs);
    auto end_time = std::chrono::high_resolution_clock::now();
    
    std::chrono::duration<double, std::micro> build_duration = end_time - start_time;
    std::cout << "BVH build completed in " << build_duration.count() << " microseconds" << std::endl;
    std::cout << "BVH node count: " << bvh.node_count() << std::endl;
}

void RenderManager::centerModel() {
    printf("centerModel() called\n");
    fflush(stdout);
    
    if (triangleCount == 0) {
        printf("No triangles loaded, using default camera position\n");
        fflush(stdout);
        cameraPosition[0] = 0.0f;
        cameraPosition[1] = 0.0f;
        cameraPosition[2] = 0.0f;
        cameraRotation[0] = 0.0f;
        cameraRotation[1] = 0.0f;
        zoom = 1.0f;
        return;
    }
    
    // 获取BVH根节点包围盒
    hhb::core::Bounds rootBounds = bvh.get_root_bounds();
    
    // 计算包围盒尺寸
    float sizeX = rootBounds.max[0] - rootBounds.min[0];
    float sizeY = rootBounds.max[1] - rootBounds.min[1];
    float sizeZ = rootBounds.max[2] - rootBounds.min[2];
    float maxDim = (std::max)((std::max)(sizeX, sizeY), sizeZ);
    
    // 计算包围盒中心
    float centerX = (rootBounds.max[0] + rootBounds.min[0]) / 2.0f;
    float centerY = (rootBounds.max[1] + rootBounds.min[1]) / 2.0f;
    float centerZ = (rootBounds.max[2] + rootBounds.min[2]) / 2.0f;
    
    printf("Model bounding box: (%.2f, %.2f, %.2f) to (%.2f, %.2f, %.2f)\n",
           rootBounds.min[0], rootBounds.min[1], rootBounds.min[2],
           rootBounds.max[0], rootBounds.max[1], rootBounds.max[2]);
    printf("Model center: (%.2f, %.2f, %.2f), max dimension: %.2f\n",
           centerX, centerY, centerZ, maxDim);
    fflush(stdout);
    
    // 设置相机目标点为模型中心
    cameraPosition[0] = centerX;
    cameraPosition[1] = centerY;
    cameraPosition[2] = centerZ;
    
    // 重置相机旋转
    cameraRotation[0] = 0.0f;
    cameraRotation[1] = 0.0f;
    
    // 计算合适的缩放级别
    // 基础距离是5.0，我们需要让模型在视口中占据合适的比例
    float targetDistance = maxDim > 0 ? maxDim * 1.5f : 5.0f;
    zoom = 5.0f / targetDistance;
    
    printf("Camera set to center (%.2f, %.2f, %.2f), zoom: %.4f\n",
           cameraPosition[0], cameraPosition[1], cameraPosition[2], zoom);
    fflush(stdout);
}

void RenderManager::screenToRay(double xpos, double ypos, float* rayOrigin, float* rayDirection) {
    // 将屏幕坐标转换为标准化设备坐标 (NDC)
    float ndc_x = (2.0f * static_cast<float>(xpos)) / static_cast<float>(width) - 1.0f;
    float ndc_y = 1.0f - (2.0f * static_cast<float>(ypos)) / static_cast<float>(height);
    
    // 计算射线方向（在相机空间中）
    float aspect = static_cast<float>(width) / static_cast<float>(height);
    float fov = 45.0f;
    float tan_half_fov = tan(fov * 0.5f * 3.1415926535f / 180.0f);
    
    rayDirection[0] = ndc_x * aspect * tan_half_fov;
    rayDirection[1] = ndc_y * tan_half_fov;
    rayDirection[2] = -1.0f; // 相机看向负Z轴
    
    // 应用相机旋转
    float cos_rot_x = cos(cameraRotation[0]);
    float sin_rot_x = sin(cameraRotation[0]);
    float cos_rot_y = cos(cameraRotation[1]);
    float sin_rot_y = sin(cameraRotation[1]);
    
    // 绕X轴旋转
    float temp_y = rayDirection[1];
    float temp_z = rayDirection[2];
    rayDirection[1] = temp_y * cos_rot_x - temp_z * sin_rot_x;
    rayDirection[2] = temp_y * sin_rot_x + temp_z * cos_rot_x;
    
    // 绕Y轴旋转
    float temp_x = rayDirection[0];
    temp_z = rayDirection[2];
    rayDirection[0] = temp_x * cos_rot_y + temp_z * sin_rot_y;
    rayDirection[2] = -temp_x * sin_rot_y + temp_z * cos_rot_y;
    
    // 归一化射线方向
    float length = sqrt(rayDirection[0] * rayDirection[0] + rayDirection[1] * rayDirection[1] + rayDirection[2] * rayDirection[2]);
    rayDirection[0] /= length;
    rayDirection[1] /= length;
    rayDirection[2] /= length;
    
    // 射线原点就是相机位置
    rayOrigin[0] = cameraPosition[0];
    rayOrigin[1] = cameraPosition[1];
    rayOrigin[2] = cameraPosition[2];
}

void RenderManager::handleMouseClick(double xpos, double ypos) {
    // 关键：检查 ImGui 是否想捕获鼠标事件
    ImGuiIO& io = ImGui::GetIO();
    if (io.WantCaptureMouse) {
        // std::cout << "ImGui captured mouse click, ignoring ray picking." << std::endl;
        return;
    }

    // std::cout << "Mouse clicked at: " << xpos << ", " << ypos << std::endl;
    
    // 计算射线
    float rayOrigin[3];
    float rayDirection[3];
    screenToRay(xpos, ypos, rayOrigin, rayDirection);
    
    std::cout << "Ray origin: (" << rayOrigin[0] << ", " << rayOrigin[1] << ", " << rayOrigin[2] << ")" << std::endl;
    std::cout << "Ray direction: (" << rayDirection[0] << ", " << rayDirection[1] << ", " << rayDirection[2] << ")" << std::endl;
    
    // 射线与BVH树相交
    auto start_time = std::chrono::high_resolution_clock::now();
    float t_hit;
    hhb::core::Triangle* hit_triangle = nullptr;
    bool hit = bvh.intersect(rayOrigin, rayDirection, t_hit, hit_triangle);
    auto end_time = std::chrono::high_resolution_clock::now();
    
    std::chrono::duration<double, std::micro> intersect_duration = end_time - start_time;
    pickTime = static_cast<float>(intersect_duration.count());
    std::cout << "Ray intersection completed in " << pickTime << " microseconds" << std::endl;
    
    if (hit) {
        selectedTriangle = hit_triangle;
        // 查找三角形索引
        selectedTriangleIndex = -1;
        if (trianglePool) {
            for (size_t i = 0; i < triangleCount; ++i) {
                if (&(*trianglePool)[i] == hit_triangle) {
                    selectedTriangleIndex = static_cast<int>(i);
                    break;
                }
            }
        }
        
        std::cout << "Hit triangle found! Index: " << selectedTriangleIndex << std::endl;
        std::cout << "Intersection distance: " << t_hit << std::endl;
        std::cout << "Triangle vertices:" << std::endl;
        std::cout << "  Vertex 1: (" << hit_triangle->vertex1[0] << ", " << hit_triangle->vertex1[1] << ", " << hit_triangle->vertex1[2] << ")" << std::endl;
        std::cout << "  Vertex 2: (" << hit_triangle->vertex2[0] << ", " << hit_triangle->vertex2[1] << ", " << hit_triangle->vertex2[2] << ")" << std::endl;
        std::cout << "  Vertex 3: (" << hit_triangle->vertex3[0] << ", " << hit_triangle->vertex3[1] << ", " << hit_triangle->vertex3[2] << ")" << std::endl;
        std::cout << "  Normal: (" << hit_triangle->normal[0] << ", " << hit_triangle->normal[1] << ", " << hit_triangle->normal[2] << ")" << std::endl;
    } else {
        selectedTriangle = nullptr;
        selectedTriangleIndex = -1;
        std::cout << "No triangle hit." << std::endl;
    }
}

void RenderManager::initImGui() {
    // 创建ImGui上下文
    ImGui::CreateContext();
    
    // 设置ImGui样式
    ImGui::StyleColorsDark();
    
    // 配置ImGui以支持Unicode
    ImGuiIO& io = ImGui::GetIO();
    // 禁用键盘导航，避免键位映射问题
    // io.ConfigFlags |= ImGuiConfigFlags_NavEnableKeyboard;     // 启用键盘控制
    
    // 尝试加载系统字体以支持中文
    // 首先添加默认字体
    io.Fonts->AddFontDefault();
    
    // 直接加载微软雅黑字体并指定中文字符范围
    ImFontConfig config;
    config.MergeMode = false;
    config.PixelSnapH = true;
    if (ImFont* font = io.Fonts->AddFontFromFileTTF("C:\\Windows\\Fonts\\msyh.ttc", 18.0f, &config, io.Fonts->GetGlyphRangesChineseFull())) {
        std::cout << "Loaded Chinese font: C:\\Windows\\Fonts\\msyh.ttc" << std::endl;
    } else {
        // 尝试其他字体路径
        if (ImFont* font = io.Fonts->AddFontFromFileTTF("C:\\Windows\\Fonts\\msyh.ttf", 18.0f, &config, io.Fonts->GetGlyphRangesChineseFull())) {
            std::cout << "Loaded Chinese font: C:\\Windows\\Fonts\\msyh.ttf" << std::endl;
        } else {
            std::cout << "Warning: Failed to load Chinese font" << std::endl;
        }
    }
    
    // 确保ImGui能够处理Unicode字符
    io.Fonts->Build();
    
    // 初始化ImGui与GLFW的绑定
    // 第二个参数 false 表示不自动安装回调，我们手动处理事件
    ImGui_ImplGlfw_InitForOpenGL(window, false);
    
    // 设置GLFW回调，确保ImGui能接收键盘和鼠标事件
    glfwSetMouseButtonCallback(window, [](GLFWwindow* w, int button, int action, int mods) {
        ImGui_ImplGlfw_MouseButtonCallback(w, button, action, mods);
    });
    glfwSetScrollCallback(window, [](GLFWwindow* w, double xoffset, double yoffset) {
        ImGui_ImplGlfw_ScrollCallback(w, xoffset, yoffset);
    });
    glfwSetKeyCallback(window, [](GLFWwindow* w, int key, int scancode, int action, int mods) {
        ImGui_ImplGlfw_KeyCallback(w, key, scancode, action, mods);
    });
    glfwSetCharCallback(window, [](GLFWwindow* w, unsigned int c) {
        ImGui_ImplGlfw_CharCallback(w, c);
    });
    
    // 初始化ImGui与OpenGL的绑定
    ImGui_ImplOpenGL3_Init("#version 330");
    
    std::cout << "ImGui initialized successfully" << std::endl;
}

void RenderManager::updateImGui() {
    // 渲染主菜单栏
    if (ImGui::BeginMainMenuBar()) {
        if (ImGui::BeginMenu("File")) {
            if (ImGui::MenuItem("Open STL...")) {
                printf("UI: Open STL Clicked from Menu!\n");
                fflush(stdout);
                openFileDialog();
            }
            ImGui::Separator();
            if (ImGui::MenuItem("Exit")) {
                glfwSetWindowShouldClose(window, true);
            }
            ImGui::EndMenu();
        }
        if (ImGui::BeginMenu("View")) {
            ImGui::MenuItem("Show BVH Bounds", NULL, &showBVH);
            if (ImGui::MenuItem("Reset Camera")) {
                centerModel();
            }
            ImGui::EndMenu();
        }
        ImGui::EndMainMenuBar();
    }

    // 创建主控制面板 - 左侧常驻面板
    ImGui::SetNextWindowPos(ImVec2(10, 30), ImGuiCond_Always);
    ImGui::SetNextWindowSize(ImVec2(280, 0), ImGuiCond_Always);
    
    ImGui::Begin("Huhb CAD Control Panel", nullptr, 
        ImGuiWindowFlags_NoResize | ImGuiWindowFlags_NoMove | 
        ImGuiWindowFlags_NoSavedSettings);
    
    // 标题
    ImGui::TextColored(ImVec4(0.0f, 0.8f, 1.0f, 1.0f), "Huhb CAD Industrial Viewer");
    ImGui::Separator();
    
    // 文件操作区域 - 主要的 Open STL 按钮
    ImGui::Text("File Operations");
    ImGui::PushStyleColor(ImGuiCol_Button, ImVec4(0.2f, 0.6f, 0.8f, 1.0f));
    ImGui::PushStyleColor(ImGuiCol_ButtonHovered, ImVec4(0.3f, 0.7f, 0.9f, 1.0f));
    if (ImGui::Button("Open STL File", ImVec2(200, 35))) {
        printf("UI: Open STL Button Clicked!\n");
        fflush(stdout);
        openFileDialog();
    }
    ImGui::PopStyleColor(2);
    ImGui::Separator();
    
    // 性能监控区域
    ImGui::TextColored(ImVec4(1.0f, 0.8f, 0.0f, 1.0f), "Model & Performance");
    ImGui::Text("FPS: %.1f", fps);
    ImGui::Text("Vertices: %zu", triangleCount * 3);
    ImGui::Text("Triangles: %zu", triangleCount);
    
    // 显示包围盒大小
    hhb::core::Bounds rootBounds = bvh.get_root_bounds();
    float sizeX = rootBounds.max[0] - rootBounds.min[0];
    float sizeY = rootBounds.max[1] - rootBounds.min[1];
    float sizeZ = rootBounds.max[2] - rootBounds.min[2];
    if (sizeX < 0) sizeX = sizeY = sizeZ = 0.0f;
    ImGui::Text("Bounding Box:");
    ImGui::Text("  Size: %.2f x %.2f x %.2f", sizeX, sizeY, sizeZ);
    
    ImGui::Text("BVH Depth: %d", bvh.depth());
    ImGui::Text("Load Time: %.2f ms", loadTime);
    ImGui::Text("Memory Usage: %.2f MB", memoryUsage / (1024.0f * 1024.0f));
    ImGui::Separator();
    
    // PBR参数调节区域
    ImGui::TextColored(ImVec4(0.0f, 1.0f, 0.5f, 1.0f), "PBR Material");
    ImGui::SliderFloat("Metallic", &metallic, 0.0f, 1.0f);
    ImGui::SliderFloat("Roughness", &roughness, 0.0f, 1.0f);
    ImGui::Separator();
    
    // BVH可视化开关
    ImGui::TextColored(ImVec4(1.0f, 0.5f, 0.0f, 1.0f), "Debug Options");
    ImGui::Checkbox("Show BVH Bounds", &showBVH);
    if (ImGui::Button("Reset Camera to Model", ImVec2(200, 25))) {
        printf("UI: Reset Camera Clicked!\n");
        fflush(stdout);
        centerModel();
    }
    ImGui::Separator();
    
    // 拾取信息区域
    ImGui::TextColored(ImVec4(0.8f, 0.5f, 1.0f, 1.0f), "Pick Information");
    ImGui::Text("Pick Time: %.2f us", pickTime);
    
    if (selectedTriangleIndex >= 0) {
        ImGui::Text("Selected Triangle Index: %d", selectedTriangleIndex);
        ImGui::Text("Normal: (%.3f, %.3f, %.3f)", 
            selectedTriangle->normal[0], 
            selectedTriangle->normal[1], 
            selectedTriangle->normal[2]);
        ImGui::Text("Vertex 1: (%.3f, %.3f, %.3f)", 
            selectedTriangle->vertex1[0], 
            selectedTriangle->vertex1[1], 
            selectedTriangle->vertex1[2]);
        ImGui::Text("Vertex 2: (%.3f, %.3f, %.3f)", 
            selectedTriangle->vertex2[0], 
            selectedTriangle->vertex2[1], 
            selectedTriangle->vertex2[2]);
        ImGui::Text("Vertex 3: (%.3f, %.3f, %.3f)", 
            selectedTriangle->vertex3[0], 
            selectedTriangle->vertex3[1], 
            selectedTriangle->vertex3[2]);
    }
    ImGui::Separator();
    
    // 具身智能 AI 助手交互区域
    ImGui::TextColored(ImVec4(0.5f, 1.0f, 0.5f, 1.0f), "Embodied AI Assistant");
    ImGui::Separator();

    // 显示 Agent 状态
    auto agentState = embodiedAgent_.getState();
    if (agentState == hhb::core::EmbodiedAIState::Processing ||
        agentState == hhb::core::EmbodiedAIState::ToolExecuting) {
        ImGui::TextColored(ImVec4(1.0f, 1.0f, 0.0f, 1.0f), "State: %s", embodiedAgent_.getStateString().c_str());
    } else if (agentState == hhb::core::EmbodiedAIState::Error) {
        ImGui::TextColored(ImVec4(1.0f, 0.3f, 0.3f, 1.0f), "State: %s", embodiedAgent_.getStateString().c_str());
    } else {
        ImGui::TextColored(ImVec4(0.5f, 1.0f, 0.5f, 1.0f), "State: Ready");
    }

    ImGui::InputText("##AIInput", userInputBuffer, sizeof(userInputBuffer));
    ImGui::SameLine();
    if (ImGui::Button("Send", ImVec2(80, 20))) {
        processUserInput();
    }

    ImGui::Checkbox("Show Highlight", &showHighlight);
    if (showHighlight && !highlightIndices.empty()) {
        const char* typeStr = "Unknown";
        switch (currentHighlightType) {
            case HighlightType::ThinParts: typeStr = "Weak Structure"; break;
            case HighlightType::CurvedSurfaces: typeStr = "Curved Surfaces"; break;
            case HighlightType::SharpEdges: typeStr = "Sharp Edges"; break;
            case HighlightType::FlatSurfaces: typeStr = "Flat Surfaces"; break;
            default: break;
        }
        ImGui::TextColored(ImVec4(1.0f, 0.3f, 0.3f, 1.0f), "Highlight: %s (%zu parts)",
            typeStr, highlightIndices.size());
    }

    // 显示最后的 AI 回复
    std::string lastResp = embodiedAgent_.getLastResponse();
    if (!lastResp.empty()) {
        ImGui::TextWrapped("AI: %s", lastResp.c_str());
    }

    // 显示错误信息
    std::string lastErr = embodiedAgent_.getLastError();
    if (!lastErr.empty() && lastErr.find("[Error]") != std::string::npos) {
        ImGui::TextColored(ImVec4(1.0f, 0.2f, 0.2f, 1.0f), "Error: %s", lastErr.c_str());
    }

    if (selectedTriangleIndex < 0) {
        ImGui::TextDisabled("No triangle selected");
    }
    
    ImGui::End();

    // 具身智能 AI 聊天面板（右侧悬浮窗口）
    ImGui::SetNextWindowPos(ImVec2(width - 340, 30), ImGuiCond_FirstUseEver);
    ImGui::SetNextWindowSize(ImVec2(330, height - 40), ImGuiCond_FirstUseEver);
    
    ImGui::Begin("Embodied AI Chat", nullptr, ImGuiWindowFlags_NoSavedSettings);
    
    ImGui::TextColored(ImVec4(0.2f, 1.0f, 0.8f, 1.0f), "Embodied AI CAD Assistant");
    ImGui::SameLine();
    if (embodiedAgent_.isProcessing()) {
        ImGui::TextColored(ImVec4(1.0f, 1.0f, 0.0f, 1.0f), "[Processing...]");
    }
    ImGui::Separator();

    // 显示已注册的工具列表
    auto toolNames = hhb::core::LLMClient::getInstance().getRegisteredToolNames();
    if (!toolNames.empty()) {
        if (ImGui::CollapsingHeader("Available Tools")) {
            for (const auto& name : toolNames) {
                ImGui::BulletText("%s", name.c_str());
            }
        }
    }
    
    // 聊天历史区域
    auto chatHistory = embodiedAgent_.getChatHistory();
    ImGui::BeginChild("ChatHistory", ImVec2(0, -60), true);
    for (const auto& msg : chatHistory) {
        if (msg.isUser) {
            ImGui::TextColored(ImVec4(0.0f, 0.8f, 1.0f, 1.0f), "[%s] You: %s",
                msg.timestamp.c_str(), msg.content.c_str());
        } else {
            ImGui::TextColored(ImVec4(0.5f, 1.0f, 0.5f, 1.0f), "[%s] AI: %s",
                msg.timestamp.c_str(), msg.content.c_str());
        }
        ImGui::Separator();
    }

    // 自动滚动到底部
    if (ImGui::GetScrollY() >= ImGui::GetScrollMaxY())
        ImGui::SetScrollHereY(1.0f);
    ImGui::EndChild();
    
    // 输入区域
    static char chatInputBuffer[512];
    ImGuiInputTextFlags flags = embodiedAgent_.isProcessing() ? ImGuiInputTextFlags_ReadOnly : 0;
    bool inputEnter = ImGui::InputText("##ChatInput", chatInputBuffer, sizeof(chatInputBuffer),
        flags | ImGuiInputTextFlags_EnterReturnsTrue);
    ImGui::SameLine();
    if (ImGui::Button("Send##ChatSend", ImVec2(80, 20)) || inputEnter) {
        std::string chatInput(chatInputBuffer);
        if (!chatInput.empty() && !embodiedAgent_.isProcessing()) {
            strncpy(userInputBuffer, chatInputBuffer, sizeof(userInputBuffer) - 1);
            processUserInput();
            memset(chatInputBuffer, 0, sizeof(chatInputBuffer));
        }
    }
    
    ImGui::End();
}

void RenderManager::renderImGui() {
    // 渲染ImGui
    ImGui_ImplOpenGL3_RenderDrawData(ImGui::GetDrawData());
}

void RenderManager::processUserInput() {
    std::string userInput(userInputBuffer);
    if (userInput.empty()) {
        return;
    }
    
    SetConsoleOutputCP(CP_UTF8);
    std::cout << "[RenderManager] User input: " << userInput << std::endl;

    // 优先使用具身智能 Agent 闭环处理
    // 闭环流程：用户自然语言 -> LLM 解析为工具调用 -> C++ 执行几何分析 -> OpenGL 高亮显示
    if (!trianglePool || trianglePool->size() == 0) {
        std::cout << "[RenderManager] No model loaded" << std::endl;
        return;
    }

    // 异步调用具身智能 Agent
    embodiedAgent_.processInputAsync(userInput);
}

void RenderManager::onToolResult(const std::vector<int>& indices, HighlightType type, const std::string& desc) {
    // 具身智能工具执行结果回调：将分析结果映射到 OpenGL 高亮缓冲区
    std::lock_guard<std::mutex> lock(highlightMutex);
    newHighlightIndices = indices;
    currentHighlightType = type;
    lastAnalysisDesc = desc;
    highlightCalculated = true;
    std::cout << "[RenderManager] Tool result received: " << indices.size()
              << " indices, desc=" << desc << std::endl;
}

void RenderManager::highlightParts() {
    if (!showHighlight || highlightIndices.empty()) {
        return;
    }
    
    // 闪烁效果：使用正弦波调制透明度/亮度，周期约 0.5 秒
    highlightBlinkTimer_ += deltaTime;
    float blink = 0.5f + 0.5f * sinf(highlightBlinkTimer_ * 6.2831853f);
    // 闪烁时在暗色和亮色之间切换，实现"呼吸"效果
    float blinkAlpha = 0.6f + 0.4f * blink;

    GLint isSelectedLoc = glGetUniformLocation(shaderProgram, "isSelected");
    GLint highlightColorLoc = glGetUniformLocation(shaderProgram, "highlightColor");
    
    // 基础颜色：薄弱部位使用高亮红 (R:1.0, G:0.2, B:0.2)
    float color[3] = {1.0f, 0.2f, 0.2f};
    switch (currentHighlightType) {
        case HighlightType::ThinParts:
            color[0] = 1.0f * blinkAlpha; color[1] = 0.2f * blinkAlpha; color[2] = 0.2f * blinkAlpha; break;
        case HighlightType::CurvedSurfaces:
            color[0] = 0.0f; color[1] = 1.0f * blinkAlpha; color[2] = 0.5f * blinkAlpha; break;
        case HighlightType::SharpEdges:
            color[0] = 1.0f * blinkAlpha; color[1] = 0.5f * blinkAlpha; color[2] = 0.0f; break;
        case HighlightType::FlatSurfaces:
            color[0] = 0.0f; color[1] = 0.5f * blinkAlpha; color[2] = 1.0f * blinkAlpha; break;
        default: break;
    }
    
    if (isSelectedLoc != -1 && highlightColorLoc != -1) {
        glUniform1i(isSelectedLoc, GL_TRUE);
        glUniform3fv(highlightColorLoc, 1, color);
        
        // 关闭深度写入，使高亮始终可见
        glDepthMask(GL_FALSE);
        for (int index : highlightIndices) {
            glDrawArrays(GL_TRIANGLES, index * 3, 3);
        }
        glDepthMask(GL_TRUE);
    }
}

void RenderManager::shutdownImGui() {
    // 清理ImGui资源
    ImGui_ImplOpenGL3_Shutdown();
    ImGui_ImplGlfw_Shutdown();
    ImGui::DestroyContext();
}

// 保存截图
bool RenderManager::saveScreenshot(const std::string& filename) {
    printf("saveScreenshot() called with: %s\n", filename.c_str());
    fflush(stdout);
    
    // 创建目录（如果不存在）
    size_t lastSlash = filename.find_last_of("\\/");
    if (lastSlash != std::string::npos) {
        std::string dir = filename.substr(0, lastSlash);
        #ifdef _WIN32
        CreateDirectoryA(dir.c_str(), NULL);
        #else
        mkdir(dir.c_str(), 0755);
        #endif
    }
    
    // 读取像素数据
    std::vector<unsigned char> pixels(width * height * 3);
    glReadPixels(0, 0, width, height, GL_RGB, GL_UNSIGNED_BYTE, pixels.data());
    
    // 翻转图像（因为OpenGL坐标系统与图像坐标系统不同）
    for (int i = 0; i < height / 2; ++i) {
        for (int j = 0; j < width * 3; ++j) {
            std::swap(pixels[i * width * 3 + j], pixels[(height - i - 1) * width * 3 + j]);
        }
    }
    
    // 保存为PPM格式（简单的图像格式，无需外部库）
    std::ofstream file(filename);
    if (!file) {
        printf("Failed to open file for writing: %s\n", filename.c_str());
        fflush(stdout);
        return false;
    }
    
    file << "P6\n" << width << " " << height << "\n255\n";
    file.write(reinterpret_cast<const char*>(pixels.data()), pixels.size());
    file.close();
    
    printf("Screenshot saved to: %s\n", filename.c_str());
    fflush(stdout);
    return true;
}

// 捕获模型的三个视角
void RenderManager::captureModelViews(const std::string& modelName) {
    printf("captureModelViews() called for model: %s\n", modelName.c_str());
    fflush(stdout);
    
    // 保存原始相机状态
    float originalPos[3] = {cameraPosition[0], cameraPosition[1], cameraPosition[2]};
    float originalRot[2] = {cameraRotation[0], cameraRotation[1]};
    float originalZoom = zoom;
    
    // 确保模型已加载
    if (triangleCount == 0) {
        printf("No model loaded, cannot capture views\n");
        fflush(stdout);
        return;
    }
    
    // 重置相机到模型中心
    centerModel();
    
    // 视角1：正面
    cameraRotation[0] = 0.0f;  // 俯仰角
    cameraRotation[1] = 0.0f;  // 偏航角
    zoom = 1.0f;
    
    // 渲染一帧
    render();
    swapBuffers();
    
    // 保存截图
    std::string view1 = "screenshots/" + modelName + "_view1.ppm";
    saveScreenshot(view1);
    
    // 视角2：侧面
    cameraRotation[1] = 3.14159f / 2.0f;  // 90度偏航
    
    // 渲染一帧
    render();
    swapBuffers();
    
    // 保存截图
    std::string view2 = "screenshots/" + modelName + "_view2.ppm";
    saveScreenshot(view2);
    
    // 视角3：顶部
    cameraRotation[0] = -3.14159f / 2.0f;  // -90度俯仰
    cameraRotation[1] = 0.0f;
    
    // 渲染一帧
    render();
    swapBuffers();
    
    // 保存截图
    std::string view3 = "screenshots/" + modelName + "_view3.ppm";
    saveScreenshot(view3);
    
    // 恢复原始相机状态
    cameraPosition[0] = originalPos[0];
    cameraPosition[1] = originalPos[1];
    cameraPosition[2] = originalPos[2];
    cameraRotation[0] = originalRot[0];
    cameraRotation[1] = originalRot[1];
    zoom = originalZoom;
    
    // 调用Python脚本进行模型描述和向量存储
    std::string apiKey = "YOUR_OPENAI_API_KEY"; // 请替换为实际的API密钥
    std::string pythonScript = "model_describer.py";
    std::string command = "python " + pythonScript + " " + apiKey + " " + modelName + " " + view1 + " " + view2 + " " + view3;
    
    printf("Executing Python script: %s\n", command.c_str());
    fflush(stdout);
    
    // 执行Python脚本
    int result = system(command.c_str());
    if (result == 0) {
        printf("Python script executed successfully\n");
    } else {
        printf("Python script execution failed with code: %d\n", result);
    }
    fflush(stdout);
    
    printf("Captured 3 views for model: %s\n", modelName.c_str());
    fflush(stdout);
}

void RenderManager::sphericalFibonacciSample(int index, int total, float radius,
                                              float* outX, float* outY, float* outZ) {
    const float goldenRatio = 1.6180339887498948482f;
    const float phi = 2.0f * 3.14159265358979323846f * index / goldenRatio;

    float cosTheta = 1.0f - 2.0f * (index + 0.5f) / total;
    float sinTheta = std::sqrt(1.0f - cosTheta * cosTheta);

    *outX = radius * sinTheta * std::cos(phi);
    *outY = radius * cosTheta;
    *outZ = radius * sinTheta * std::sin(phi);
}

bool RenderManager::saveFrameAsPNG(const std::string& filename, int w, int h,
                                    const std::vector<unsigned char>& pixels) {
    std::vector<unsigned char> flipped(pixels.size());

    for (int row = 0; row < h; ++row) {
        const unsigned char* srcRow = pixels.data() + (h - 1 - row) * w * 3;
        unsigned char* dstRow = flipped.data() + row * w * 3;
        std::memcpy(dstRow, srcRow, w * 3);
    }

    int result = stbi_write_png(filename.c_str(), w, h, 3, flipped.data(), w * 3);

    if (!result) {
        printf("[CaptureSynthetic] Failed to save PNG: %s\n", filename.c_str());
        fflush(stdout);
        return false;
    }

    return true;
}

void RenderManager::computeViewMatrixFromPosition(float camX, float camY, float camZ,
                                                   float targetX, float targetY, float targetZ,
                                                   float* outView16) {
    float fx = targetX - camX, fy = targetY - camY, fz = targetZ - camZ;
    float fLen = std::sqrt(fx*fx + fy*fy + fz*fz);
    if (fLen > 0.0001f) { fx /= fLen; fy /= fLen; fz /= fLen; }

    float rx = fy*0.0f - fz*1.0f;
    float ry = fz*0.0f - fx*0.0f;
    float rz = fx*1.0f - fy*0.0f;
    float rLen = std::sqrt(rx*rx + ry*ry + rz*rz);
    if (rLen > 0.0001f) { rx /= rLen; ry /= rLen; rz /= rLen; }
    else {
        rx = fz*0.0f - fy*1.0f;
        ry = fx*0.0f - fz*0.0f;
        rz = fy*1.0f - fx*0.0f;
        rLen = std::sqrt(rx*rx + ry*ry + rz*rz);
        if (rLen > 0.0001f) { rx /= rLen; ry /= rLen; rz /= rLen; }
    }

    float ux = ry*fz - rz*fy;
    float uy = rz*fx - rx*fz;
    float uz = rx*fy - ry*fx;

    float rd = rx*camX + ry*camY + rz*camZ;
    float ud = ux*camX + uy*camY + uz*camZ;
    float fd = fx*camX + fy*camY + fz*camZ;

    outView16[0] = rx;  outView16[4] = ry;  outView16[8]  = rz;  outView16[12] = -rd;
    outView16[1] = ux;  outView16[5] = uy;  outView16[9]  = uz;  outView16[13] = -ud;
    outView16[2] = -fx; outView16[6] = -fy; outView16[10] = -fz; outView16[14] = fd;
    outView16[3] = 0.0f; outView16[7] = 0.0f; outView16[11] = 0.0f; outView16[15] = 1.0f;
}

RenderManager::CaptureResult RenderManager::captureSyntheticData(const CaptureConfig& config) {
    CaptureResult result;
    result.totalFrames = config.sampleCount;
    result.successFrames = 0;
    result.failedFrames = 0;
    result.outputDirectory = config.outputDir;

    printf("\n========== CaptureSyntheticData START ==========\n");
    printf("  Sample count        : %d\n", config.sampleCount);
    printf("  Output dir          : %s\n", config.outputDir.c_str());
    printf("  Camera radius       : %.2f\n", config.cameraRadius);
    printf("  Image size          : %dx%d\n", config.imageWidth, config.imageHeight);
    printf("  Save mask           : %s\n", config.saveMask ? "YES" : "NO");
    printf("  Save depth          : %s\n", config.saveDepth ? "YES" : "NO");
    printf("  Instance seg        : %s\n", config.instanceSegmentation ? "YES" : "NO");
    printf("  Multi-object scene  : %s\n", config.multiObjectScene ? "YES" : "NO");
    printf("  Scene objects       : %zu\n", sceneObjects_.size());
    fflush(stdout);

    bool useMultiObject = config.multiObjectScene && !sceneObjects_.empty();

    if (!useMultiObject && triangleCount == 0) {
        printf("[CaptureSynthetic] ERROR: No model loaded and no scene objects!\n");
        fflush(stdout);
        return result;
    }

    if (config.saveMask && !useMultiObject) {
        if (!config.topologyLabelsPath.empty() && loadTopologyLabels(config.topologyLabelsPath)) {
            printf("[CaptureSynthetic] Using STEP topology labels as GROUND TRUTH (not curvature)\n");
            faceCategoryIds = topologyFaceLabels_;
            faceCategoriesComputed = true;
            geometricFeaturesComputed = true;
            updateLabelVertexData();
        } else {
            computeGeometricFeatures();
            updateLabelVertexData();
        }
    }

    if (useMultiObject) {
        bool allHaveTopology = true;
        for (size_t si = 0; si < sceneObjects_.size(); ++si) {
            auto& obj = sceneObjects_[si];
            if (si < config.sceneObjectTopologyPaths.size() &&
                !config.sceneObjectTopologyPaths[si].empty()) {
                loadSceneObjectTopologyLabels(obj, config.sceneObjectTopologyPaths[si]);
            } else if (!config.topologyLabelsPath.empty() && si == 0) {
                loadSceneObjectTopologyLabels(obj, config.topologyLabelsPath);
            } else {
                allHaveTopology = false;
            }
        }
        if (!allHaveTopology) {
            computeAllFeatureInstances();
        } else {
            printf("[CaptureSynthetic] All objects use STEP topology GROUND TRUTH labels\n");
        }
    }

    if (config.domainRandomization.enableBackgroundRandomization) {
        initBackgroundRenderer();
        if (!config.domainRandomization.backgroundPaths.empty()) {
            loadBackgroundImages(config.domainRandomization.backgroundPaths);
        }
        printf("[CaptureSynthetic] Background randomization: %zu textures + %zu preset colors\n",
               backgroundTextures_.size(), backgroundColors_.size() / 3);
    }

    namespace fs = std::filesystem;
    fs::create_directories(config.outputDir);
    fs::create_directories(config.outputDir + "/rgb");
    if (config.saveMask) {
        if (config.instanceSegmentation) {
            fs::create_directories(config.outputDir + "/mask_instance");
        }
        fs::create_directories(config.outputDir + "/mask");
    }
    if (config.saveDepth) {
        fs::create_directories(config.outputDir + "/depth");
    }

    float origPos[3] = {cameraPosition[0], cameraPosition[1], cameraPosition[2]};
    float origRot[2] = {cameraRotation[0], cameraRotation[1]};
    float origZoom = zoom;

    float targetX, targetY, targetZ;
    if (useMultiObject) {
        targetX = 0.0f; targetY = 0.0f; targetZ = 0.0f;
    } else {
        SpatialInfo info = getSpatialInfo();
        targetX = info.center[0];
        targetY = info.center[1];
        targetZ = info.center[2];
    }

    float origWidth = (float)width;
    float origHeight = (float)height;

    glfwSetWindowSize(window, config.imageWidth, config.imageHeight);
    glViewport(0, 0, config.imageWidth, config.imageHeight);
    width = config.imageWidth;
    height = config.imageHeight;

    auto timeStart = std::chrono::steady_clock::now();

    std::ostringstream cameraPosesJson;
    cameraPosesJson << "{\n";

    struct PerFramePose {
        float camR3x3[9];
        float camT[3];
        float camK[5];
        std::vector<float> objPositions;
        std::vector<float> objRotations;
        std::vector<float> objScales;
        std::vector<int> objIds;
    };
    std::vector<PerFramePose> framePoses;

    float fov = 45.0f;
    float nearPlane = 0.1f;
    float farPlane = 1000.0f;
    float aspect = (float)config.imageWidth / (float)config.imageHeight;
    float f = 1.0f / tanf(fov * 0.5f * 3.1415926535f / 180.0f);
    float projectionArr[16] = {
        f / aspect, 0.0f, 0.0f, 0.0f,
        0.0f, f, 0.0f, 0.0f,
        0.0f, 0.0f, (farPlane + nearPlane) / (nearPlane - farPlane), -1.0f,
        0.0f, 0.0f, (2.0f * farPlane * nearPlane) / (nearPlane - farPlane), 0.0f
    };

    for (int i = 0; i < config.sampleCount; ++i) {
        if (useMultiObject) {
            randomizeSceneLayout();
        }

        float camX, camY, camZ;
        sphericalFibonacciSample(i, config.sampleCount, config.cameraRadius,
                                  &camX, &camY, &camZ);

        camX += targetX;
        camY += targetY;
        camZ += targetZ;

        float lightAngle = 0.0f;
        float lightIntensity = 1.0f;
        float lightColorArr[3] = {1.0f, 1.0f, 1.0f};
        float camJitterX = 0.0f, camJitterY = 0.0f, camJitterZ = 0.0f;
        float focalJitter = 0.0f;

        if (config.domainRandomization.enableLightRandomization ||
            config.domainRandomization.enableCameraJitter) {
            applyDomainRandomization(config.domainRandomization,
                                      lightAngle, lightIntensity, lightColorArr,
                                      camJitterX, camJitterY, camJitterZ, focalJitter);
        }

        camX += camJitterX;
        camY += camJitterY;
        camZ += camJitterZ;

        float jitteredFov = fov + focalJitter;
        float fj = 1.0f / tanf(jitteredFov * 0.5f * 3.1415926535f / 180.0f);
        float currentProjection[16] = {
            fj / aspect, 0.0f, 0.0f, 0.0f,
            0.0f, fj, 0.0f, 0.0f,
            0.0f, 0.0f, (farPlane + nearPlane) / (nearPlane - farPlane), -1.0f,
            0.0f, 0.0f, (2.0f * farPlane * nearPlane) / (nearPlane - farPlane), 0.0f
        };

        cameraPosition[0] = targetX;
        cameraPosition[1] = targetY;
        cameraPosition[2] = targetZ;

        float dx = camX - targetX;
        float dy = camY - targetY;
        float dz = camZ - targetZ;
        float dist = std::sqrt(dx * dx + dy * dy + dz * dz);
        cameraRotation[0] = std::asin(dy / dist);
        cameraRotation[1] = std::atan2(dx, dz);
        zoom = 5.0f / dist;

        float viewMatrix[16];
        computeViewMatrixFromPosition(camX, camY, camZ,
                                       targetX, targetY, targetZ,
                                       viewMatrix);

        PerFramePose fp;
        fp.camR3x3[0] = viewMatrix[0]; fp.camR3x3[1] = viewMatrix[4]; fp.camR3x3[2] = viewMatrix[8];
        fp.camR3x3[3] = viewMatrix[1]; fp.camR3x3[4] = viewMatrix[5]; fp.camR3x3[5] = viewMatrix[9];
        fp.camR3x3[6] = viewMatrix[2]; fp.camR3x3[7] = viewMatrix[6]; fp.camR3x3[8] = viewMatrix[10];
        fp.camT[0] = viewMatrix[12]; fp.camT[1] = viewMatrix[13]; fp.camT[2] = viewMatrix[14];
        float fj2 = 1.0f / tanf(jitteredFov * 0.5f * 3.1415926535f / 180.0f);
        fp.camK[0] = config.imageWidth * fj2 * 0.5f;
        fp.camK[1] = config.imageHeight * fj2 * 0.5f;
        fp.camK[2] = config.imageWidth * 0.5f;
        fp.camK[3] = config.imageHeight * 0.5f;
        fp.camK[4] = jitteredFov;
        if (useMultiObject) {
            for (const auto& obj : sceneObjects_) {
                fp.objPositions.push_back(obj.position[0]);
                fp.objPositions.push_back(obj.position[1]);
                fp.objPositions.push_back(obj.position[2]);
                fp.objRotations.push_back(obj.rotation[0]);
                fp.objRotations.push_back(obj.rotation[1]);
                fp.objRotations.push_back(obj.rotation[2]);
                fp.objScales.push_back(obj.scale);
                fp.objIds.push_back(obj.instanceId);
            }
        }
        framePoses.push_back(fp);

        if (i > 0) cameraPosesJson << ",\n";
        cameraPosesJson << "  \"" << (i + 1) << "\": {\n";
        cameraPosesJson << "    \"position\": [" << camX << ", " << camY << ", " << camZ << "],\n";
        cameraPosesJson << "    \"target\": [" << targetX << ", " << targetY << ", " << targetZ << "],\n";
        cameraPosesJson << "    \"rotation\": [" << cameraRotation[0] << ", " << cameraRotation[1] << "],\n";
        cameraPosesJson << "    \"view_matrix\": [";
        for (int vi = 0; vi < 16; ++vi) {
            cameraPosesJson << viewMatrix[vi];
            if (vi < 15) cameraPosesJson << ", ";
        }
        cameraPosesJson << "],\n";
        cameraPosesJson << "    \"projection_matrix\": [";
        for (int pi = 0; pi < 16; ++pi) {
            cameraPosesJson << currentProjection[pi];
            if (pi < 15) cameraPosesJson << ", ";
        }
        cameraPosesJson << "],\n";
        cameraPosesJson << "    \"fov_degrees\": " << jitteredFov << ",\n";
        cameraPosesJson << "    \"near_plane\": " << nearPlane << ",\n";
        cameraPosesJson << "    \"far_plane\": " << farPlane << ",\n";
        cameraPosesJson << "    \"image_width\": " << config.imageWidth << ",\n";
        cameraPosesJson << "    \"image_height\": " << config.imageHeight;

        if (useMultiObject) {
            cameraPosesJson << ",\n    \"scene_objects\": [";
            for (size_t oi = 0; oi < sceneObjects_.size(); ++oi) {
                const auto& obj = sceneObjects_[oi];
                cameraPosesJson << "\n      {\"instance_id\": " << obj.instanceId
                    << ", \"name\": \"" << obj.name << "\""
                    << ", \"position\": [" << obj.position[0] << ", " << obj.position[1] << ", " << obj.position[2] << "]"
                    << ", \"rotation\": [" << obj.rotation[0] << ", " << obj.rotation[1] << ", " << obj.rotation[2] << "]"
                    << ", \"scale\": " << obj.scale << "}";
                if (oi < sceneObjects_.size() - 1) cameraPosesJson << ",";
            }
            cameraPosesJson << "\n    ]";
        }

        cameraPosesJson << "\n  }";

        // === Pass 1: RGB rendering ===
        if (useMultiObject) {
            glClearColor(0.1f, 0.1f, 0.1f, 1.0f);
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);

            if (config.domainRandomization.enableBackgroundRandomization) {
                int bgIdx = selectRandomBackground();
                if (bgIdx >= 0) renderBackground(bgIdx);
            }

            glEnable(GL_DEPTH_TEST);

            float lightPos[3] = {camX + lightAngle * 2.0f, camY + 10.0f, camZ};
            renderSceneRGB(config, viewMatrix, currentProjection, lightPos, lightColorArr, lightIntensity);
            swapBuffers();
        } else {
            glClearColor(0.1f, 0.1f, 0.1f, 1.0f);
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);

            if (config.domainRandomization.enableBackgroundRandomization) {
                int bgIdx = selectRandomBackground();
                if (bgIdx >= 0) renderBackground(bgIdx);
            }

            render();
            swapBuffers();
        }

        std::vector<unsigned char> rgbPixels(config.imageWidth * config.imageHeight * 3);
        glReadPixels(0, 0, config.imageWidth, config.imageHeight,
                     GL_RGB, GL_UNSIGNED_BYTE, rgbPixels.data());

        std::ostringstream rgbOss;
        rgbOss << config.outputDir << "/rgb/frame_"
               << std::setfill('0') << std::setw(4) << (i + 1) << ".png";

        if (saveFrameAsPNG(rgbOss.str(), config.imageWidth, config.imageHeight, rgbPixels)) {
            result.successFrames++;
        } else {
            result.failedFrames++;
        }

        // === Pass 2: Mask rendering ===
        if (config.saveMask && labelShaderProgram) {
            if (useMultiObject && config.instanceSegmentation) {
                glClearColor(0.0f, 0.0f, 0.0f, 1.0f);
                glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
                glEnable(GL_DEPTH_TEST);

                renderSceneInstanceMask(config, viewMatrix, currentProjection);
                swapBuffers();

                std::vector<unsigned char> maskPixels(config.imageWidth * config.imageHeight * 3);
                glReadPixels(0, 0, config.imageWidth, config.imageHeight,
                             GL_RGB, GL_UNSIGNED_BYTE, maskPixels.data());

                std::ostringstream maskOss;
                maskOss << config.outputDir << "/mask_instance/instance_"
                        << std::setfill('0') << std::setw(4) << (i + 1) << ".png";

                saveFrameAsPNG(maskOss.str(), config.imageWidth, config.imageHeight, maskPixels);
            }

            if (useMultiObject) {
                glClearColor(0.0f, 0.0f, 0.0f, 1.0f);
                glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
                glEnable(GL_DEPTH_TEST);

                renderSceneSemanticMask(config, viewMatrix, currentProjection);
                swapBuffers();

                std::vector<unsigned char> maskPixels(config.imageWidth * config.imageHeight * 3);
                glReadPixels(0, 0, config.imageWidth, config.imageHeight,
                             GL_RGB, GL_UNSIGNED_BYTE, maskPixels.data());

                std::ostringstream maskOss;
                maskOss << config.outputDir << "/mask/mask_"
                        << std::setfill('0') << std::setw(4) << (i + 1) << ".png";

                saveFrameAsPNG(maskOss.str(), config.imageWidth, config.imageHeight, maskPixels);
            } else {
                glClearColor(0.0f, 0.0f, 0.0f, 1.0f);
                glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
                glEnable(GL_DEPTH_TEST);

                renderLabelMode();
                swapBuffers();

                std::vector<unsigned char> maskPixels(config.imageWidth * config.imageHeight * 3);
                glReadPixels(0, 0, config.imageWidth, config.imageHeight,
                             GL_RGB, GL_UNSIGNED_BYTE, maskPixels.data());

                std::ostringstream maskOss;
                maskOss << config.outputDir << "/mask/mask_"
                        << std::setfill('0') << std::setw(4) << (i + 1) << ".png";

                saveFrameAsPNG(maskOss.str(), config.imageWidth, config.imageHeight, maskPixels);
            }

            glClearColor(0.1f, 0.1f, 0.1f, 1.0f);
        }

        // === Pass 3: Depth map rendering ===
        if (config.saveDepth) {
            std::vector<float> depthPixels(config.imageWidth * config.imageHeight);
            glReadPixels(0, 0, config.imageWidth, config.imageHeight,
                         GL_DEPTH_COMPONENT, GL_FLOAT, depthPixels.data());

            std::vector<uint16_t> depth16(config.imageWidth * config.imageHeight);
            std::vector<float> linearDepthMeters(config.imageWidth * config.imageHeight, 0.0f);

            float depthScale = config.depthScale;
            if (config.modelUnit == "m") {
                depthScale = 1000.0f;
            } else if (config.modelUnit == "cm") {
                depthScale = 10.0f;
            } else if (config.modelUnit == "mm") {
                depthScale = 1.0f;
            } else if (config.modelUnit == "inch") {
                depthScale = 1.0f / 25.4f;
            }
            float maxLinearDepth = (farPlane > 0 && farPlane < 10000.0f) ? farPlane : 10.0f;

            for (int px = 0; px < config.imageWidth * config.imageHeight; ++px) {
                float zNdc = depthPixels[px];
                if (zNdc >= 1.0f || zNdc <= 0.0f) {
                    depth16[px] = 0;
                    linearDepthMeters[px] = 0.0f;
                } else {
                    float zLinear = (2.0f * nearPlane * farPlane) /
                                    (farPlane + nearPlane - zNdc * (farPlane - nearPlane));
                    linearDepthMeters[px] = zLinear;
                    float depthMm = zLinear * depthScale;
                    if (depthMm > 65535.0f) depthMm = 65535.0f;
                    depth16[px] = static_cast<uint16_t>(depthMm);
                }
            }

            std::ostringstream depthOss;
            depthOss << config.outputDir << "/depth/depth_"
                     << std::setfill('0') << std::setw(4) << (i + 1) << ".png";

            std::vector<unsigned char> depthPngBytes(config.imageWidth * config.imageHeight * 2);
            for (int px = 0; px < config.imageWidth * config.imageHeight; ++px) {
                depthPngBytes[px * 2 + 0] = static_cast<unsigned char>(depth16[px] & 0xFF);
                depthPngBytes[px * 2 + 1] = static_cast<unsigned char>((depth16[px] >> 8) & 0xFF);
            }
            stbi_write_png(depthOss.str().c_str(), config.imageWidth, config.imageHeight,
                           2, depthPngBytes.data(), config.imageWidth * 2);

            std::ostringstream npyOss;
            npyOss << config.outputDir << "/depth/depth_"
                   << std::setfill('0') << std::setw(4) << (i + 1) << ".npy";
            std::ofstream npyFile(npyOss.str(), std::ios::binary);
            if (npyFile.is_open()) {
                std::string header = "\x93NUMPY\x01\x00";
                std::ostringstream dictStr;
                dictStr << "{'descr': '<f4', 'fortran_order': False, 'shape': ("
                        << config.imageHeight << ", " << config.imageWidth << ")}";
                std::string dict = dictStr.str();
                int headerLen = (int)dict.size() + 10;
                int padding = 64 - (headerLen % 64);
                if (padding < 1) padding += 64;
                dict.append(padding, ' ');
                dict.back() = '\n';
                uint16_t hLen = (uint16_t)dict.size();
                header += std::string((char*)&hLen, 2);
                header += dict;
                npyFile.write(header.data(), header.size());
                npyFile.write(reinterpret_cast<const char*>(linearDepthMeters.data()),
                              linearDepthMeters.size() * sizeof(float));
                npyFile.close();
            }
        }

        glfwPollEvents();

        if ((i + 1) % 50 == 0 || i == 0) {
            printf("[CaptureSynthetic] Progress: %d/%d (%.1f%%)\n",
                   i + 1, config.sampleCount,
                   100.0f * (i + 1) / config.sampleCount);
            fflush(stdout);
        }
    }

    cameraPosesJson << "\n}\n";
    {
        std::string posesPath = config.outputDir + "/camera_poses.json";
        std::ofstream posesFile(posesPath);
        if (posesFile.is_open()) {
            posesFile << cameraPosesJson.str();
            posesFile.close();
            printf("[CaptureSynthetic] Camera poses saved to: %s\n", posesPath.c_str());
        }
    }

    if (useMultiObject) {
        std::ostringstream manifestJson;
        manifestJson << "{\n";
        manifestJson << "  \"scene_type\": \"multi_object\",\n";
        manifestJson << "  \"instance_segmentation\": " << (config.instanceSegmentation ? "true" : "false") << ",\n";
        manifestJson << "  \"total_frames\": " << config.sampleCount << ",\n";
        manifestJson << "  \"objects\": [\n";
        for (size_t oi = 0; oi < sceneObjects_.size(); ++oi) {
            const auto& obj = sceneObjects_[oi];
            manifestJson << "    {\n";
            manifestJson << "      \"instance_id\": " << obj.instanceId << ",\n";
            manifestJson << "      \"name\": \"" << obj.name << "\",\n";
            manifestJson << "      \"file_path\": \"" << obj.filePath << "\",\n";
            manifestJson << "      \"triangle_count\": " << obj.triangleCount << ",\n";
            manifestJson << "      \"position\": [" << obj.position[0] << ", " << obj.position[1] << ", " << obj.position[2] << "],\n";
            manifestJson << "      \"rotation\": [" << obj.rotation[0] << ", " << obj.rotation[1] << ", " << obj.rotation[2] << "],\n";
            manifestJson << "      \"scale\": " << obj.scale << ",\n";

            std::unordered_map<int, std::vector<int>> featureGroups;
            for (size_t fi = 0; fi < obj.faceCategoryIds.size(); ++fi) {
                int catId = obj.faceCategoryIds[fi];
                int featIdx = (fi < obj.featureInstanceIds.size()) ? obj.featureInstanceIds[fi] : 0;
                if (catId != 0 && catId != 7) {
                    featureGroups[catId].push_back(featIdx);
                }
            }

            manifestJson << "      \"features\": [\n";
            const char* categoryNames[] = {
                "FreeSurface", "HorizontalPlane", "LateralPlane_X",
                "LateralPlane_Z", "NearHorizontal", "NearLateral_X",
                "NearLateral_Z", "Degenerate", "ConvexFeature_Bolt",
                "ConcaveFeature_Hole", "Flange", "Boss"
            };
            bool firstFeature = true;
            for (const auto& [catId, instances] : featureGroups) {
                if (!firstFeature) manifestJson << ",\n";
                firstFeature = false;
                std::set<int> uniqueInstances(instances.begin(), instances.end());
                manifestJson << "        {\"feature_type\": \"" << categoryNames[catId] << "\""
                    << ", \"feature_type_id\": " << catId
                    << ", \"instance_count\": " << uniqueInstances.size()
                    << ", \"instance_ids\": [";
                size_t ii = 0;
                for (int inst : uniqueInstances) {
                    manifestJson << inst;
                    if (ii < uniqueInstances.size() - 1) manifestJson << ", ";
                    ii++;
                }
                manifestJson << "]}";
            }
            manifestJson << "\n      ]\n";
            manifestJson << "    }";
            if (oi < sceneObjects_.size() - 1) manifestJson << ",";
            manifestJson << "\n";
        }
        manifestJson << "  ],\n";
        manifestJson << "  \"hierarchy\": \"Scene -> Object -> Feature_Instance\"\n";
        manifestJson << "}\n";

        std::string manifestPath = config.outputDir + "/manifest.json";
        std::ofstream manifestFile(manifestPath);
        if (manifestFile.is_open()) {
            manifestFile << manifestJson.str();
            manifestFile.close();
            printf("[CaptureSynthetic] Manifest saved to: %s\n", manifestPath.c_str());
        }
    }

    auto timeEnd = std::chrono::steady_clock::now();
    result.elapsedSeconds = std::chrono::duration<float>(timeEnd - timeStart).count();

    cameraPosition[0] = origPos[0];
    cameraPosition[1] = origPos[1];
    cameraPosition[2] = origPos[2];
    cameraRotation[0] = origRot[0];
    cameraRotation[1] = origRot[1];
    zoom = origZoom;

    glfwSetWindowSize(window, (int)origWidth, (int)origHeight);
    glViewport(0, 0, (int)origWidth, (int)origHeight);
    width = (int)origWidth;
    height = (int)origHeight;

    if (config.saveMask) {
        std::string legendPath = config.outputDir + "/label_legend.txt";
        std::ofstream legendFile(legendPath);
        if (legendFile.is_open()) {
            legendFile << "# Semantic Label Color Legend\n";
            legendFile << "# Category -> (R, G, B) in 0-255 range\n\n";
            const char* categoryNames[] = {
                "FreeSurface", "HorizontalPlane", "LateralPlane_X",
                "LateralPlane_Z", "NearHorizontal", "NearLateral_X",
                "NearLateral_Z", "Degenerate", "ConvexFeature_Bolt",
                "ConcaveFeature_Hole", "Flange", "Boss"
            };
            for (int c = 0; c < 12; ++c) {
                float r, g, b;
                categoryToColor(c, &r, &g, &b);
                legendFile << c << " " << categoryNames[c] << " "
                           << (int)(r * 255) << " " << (int)(g * 255) << " " << (int)(b * 255) << "\n";
            }

            if (config.instanceSegmentation) {
                legendFile << "\n# Instance Segmentation Encoding\n";
                legendFile << "# Pixel (R, G, B) = (InstanceID, FeatureTypeID, FeatureIndex)\n";
                legendFile << "# InstanceID: unique per object in scene (1-255)\n";
                legendFile << "# FeatureTypeID: semantic category (0-11)\n";
                legendFile << "# FeatureIndex: instance index within that feature type\n";
            }

            legendFile.close();
            printf("[CaptureSynthetic] Label legend saved to: %s\n", legendPath.c_str());
        }
    }

    if (config.outputBOPFormat) {
        printf("[CaptureSynthetic] Generating BOP format output...\n");
        fflush(stdout);

        float bopDepthScale = config.depthScale;
        if (config.modelUnit == "m") {
            bopDepthScale = 1000.0f;
        } else if (config.modelUnit == "cm") {
            bopDepthScale = 10.0f;
        } else if (config.modelUnit == "mm") {
            bopDepthScale = 1.0f;
        } else if (config.modelUnit == "inch") {
            bopDepthScale = 1.0f / 25.4f;
        }

        std::ostringstream sceneCameraJson;
        sceneCameraJson << "{\n";
        std::ostringstream sceneGtJson;
        sceneGtJson << "{\n";

        for (int i = 0; i < config.sampleCount && i < (int)framePoses.size(); ++i) {
            const auto& fp = framePoses[i];

            if (i > 0) sceneCameraJson << ",\n";
            sceneCameraJson << "  \"" << (i + 1) << "\": {\n";
            sceneCameraJson << "    \"cam_K\": [" << fp.camK[0] << ", 0.0, " << fp.camK[2] << ", 0.0, " << fp.camK[1] << ", " << fp.camK[3] << ", 0.0, 0.0, 1.0],\n";
            sceneCameraJson << "    \"depth_scale\": " << bopDepthScale << ",\n";
            sceneCameraJson << "    \"model_unit\": \"" << config.modelUnit << "\",\n";
            sceneCameraJson << "    \"cam_R_w2c\": [" << fp.camR3x3[0];
            for (int ri = 1; ri < 9; ++ri) sceneCameraJson << ", " << fp.camR3x3[ri];
            sceneCameraJson << "],\n";
            sceneCameraJson << "    \"cam_t_w2c\": [" << fp.camT[0] << ", " << fp.camT[1] << ", " << fp.camT[2] << "]\n";
            sceneCameraJson << "  }";

            if (useMultiObject && !fp.objIds.empty()) {
                if (i > 0) sceneGtJson << ",\n";
                sceneGtJson << "  \"" << (i + 1) << "\": [";
                for (size_t oi = 0; oi < fp.objIds.size(); ++oi) {
                    float rx = fp.objRotations[oi * 3 + 0];
                    float ry = fp.objRotations[oi * 3 + 1];
                    float rz = fp.objRotations[oi * 3 + 2];
                    float cosRx = cosf(rx), sinRx = sinf(rx);
                    float cosRy = cosf(ry), sinRy = sinf(ry);
                    float cosRz = cosf(rz), sinRz = sinf(rz);
                    float Robj[9] = {
                        cosRy*cosRz, -cosRy*sinRz, sinRy,
                        sinRx*sinRy*cosRz + cosRx*sinRz, -sinRx*sinRy*sinRz + cosRx*cosRz, -sinRx*cosRy,
                        -cosRx*sinRy*cosRz + sinRx*sinRz, cosRx*sinRy*sinRz + sinRx*cosRz, cosRx*cosRy
                    };
                    float tObj[3] = { fp.objPositions[oi * 3 + 0], fp.objPositions[oi * 3 + 1], fp.objPositions[oi * 3 + 2] };
                    if (oi > 0) sceneGtJson << ",";
                    sceneGtJson << "\n    {\"obj_id\": " << fp.objIds[oi]
                        << ", \"cam_R_m2c\": [" << Robj[0];
                    for (int ri = 1; ri < 9; ++ri) sceneGtJson << ", " << Robj[ri];
                    sceneGtJson << "], \"cam_t_m2c\": [" << tObj[0] << ", " << tObj[1] << ", " << tObj[2] << "]";
                    sceneGtJson << "}";
                }
                sceneGtJson << "\n  ]";
            } else if (!useMultiObject) {
                if (i > 0) sceneGtJson << ",\n";
                sceneGtJson << "  \"" << (i + 1) << "\": [\n";
                sceneGtJson << "    {\"obj_id\": 1, \"cam_R_m2c\": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0], \"cam_t_m2c\": [0.0, 0.0, 0.0]}\n";
                sceneGtJson << "  ]";
            }
        }

        sceneCameraJson << "\n}\n";
        sceneGtJson << "\n}\n";

        std::string bopCameraPath = config.outputDir + "/scene_camera.json";
        std::ofstream bopCameraFile(bopCameraPath);
        if (bopCameraFile.is_open()) {
            bopCameraFile << sceneCameraJson.str();
            bopCameraFile.close();
            printf("[CaptureSynthetic] BOP scene_camera.json saved\n");
        }

        {
            std::string bopGtPath = config.outputDir + "/scene_gt.json";
            std::ofstream bopGtFile(bopGtPath);
            if (bopGtFile.is_open()) {
                bopGtFile << sceneGtJson.str();
                bopGtFile.close();
                printf("[CaptureSynthetic] BOP scene_gt.json saved (6DoF poses, %s mode)\n",
                       useMultiObject ? "multi-object" : "single-object");
            }
        }

        std::ostringstream gt6dofJson;
        gt6dofJson << "{\n";
        gt6dofJson << "  \"description\": \"6DoF Ground Truth - Object poses per frame\",\n";
        gt6dofJson << "  \"frame_count\": " << config.sampleCount << ",\n";
        gt6dofJson << "  \"object_count\": " << (useMultiObject ? sceneObjects_.size() : 1) << ",\n";
        gt6dofJson << "  \"frames\": [\n";
        for (int i = 0; i < config.sampleCount && i < (int)framePoses.size(); ++i) {
            const auto& fp = framePoses[i];
            if (i > 0) gt6dofJson << ",\n";
            gt6dofJson << "    {\n";
            gt6dofJson << "      \"frame_id\": " << (i + 1) << ",\n";
            gt6dofJson << "      \"objects\": [\n";

            auto writeObjPose = [&](int objId, const char* objName,
                                     float px, float py, float pz,
                                     float rx, float ry, float rz, float s) {
                float cosRx = cosf(rx), sinRx = sinf(rx);
                float cosRy = cosf(ry), sinRy = sinf(ry);
                float cosRz = cosf(rz), sinRz = sinf(rz);
                float R00 = cosRy*cosRz, R01 = -cosRy*sinRz, R02 = sinRy;
                float R10 = sinRx*sinRy*cosRz + cosRx*sinRz;
                float R11 = -sinRx*sinRy*sinRz + cosRx*cosRz;
                float R12 = -sinRx*cosRy;
                float R20 = -cosRx*sinRy*cosRz + sinRx*sinRz;
                float R21 = cosRx*sinRy*sinRz + sinRx*cosRz;
                float R22 = cosRx*cosRy;
                float trace = R00 + R11 + R22;
                float qw, qx, qy, qz;
                if (trace > 0) {
                    float s2 = sqrtf(trace + 1.0f) * 2.0f;
                    qw = 0.25f * s2;
                    qx = (R12 - R21) / s2;
                    qy = (R20 - R02) / s2;
                    qz = (R01 - R10) / s2;
                } else if (R00 > R11 && R00 > R22) {
                    float s2 = sqrtf(1.0f + R00 - R11 - R22) * 2.0f;
                    qw = (R12 - R21) / s2;
                    qx = 0.25f * s2;
                    qy = (R01 + R10) / s2;
                    qz = (R02 + R20) / s2;
                } else if (R11 > R22) {
                    float s2 = sqrtf(1.0f + R11 - R00 - R22) * 2.0f;
                    qw = (R20 - R02) / s2;
                    qx = (R01 + R10) / s2;
                    qy = 0.25f * s2;
                    qz = (R12 + R21) / s2;
                } else {
                    float s2 = sqrtf(1.0f + R22 - R00 - R11) * 2.0f;
                    qw = (R01 - R10) / s2;
                    qx = (R02 + R20) / s2;
                    qy = (R12 + R21) / s2;
                    qz = 0.25f * s2;
                }
                gt6dofJson << "        {\"obj_id\": " << objId
                    << ", \"name\": \"" << objName << "\""
                    << ", \"translation\": [" << px << ", " << py << ", " << pz << "]"
                    << ", \"rotation_euler\": [" << rx << ", " << ry << ", " << rz << "]"
                    << ", \"rotation_quaternion\": [" << qx << ", " << qy << ", " << qz << ", " << qw << "]"
                    << ", \"scale\": " << s
                    << ", \"rotation_matrix_3x3\": ["
                    << R00 << ", " << R01 << ", " << R02 << ", "
                    << R10 << ", " << R11 << ", " << R12 << ", "
                    << R20 << ", " << R21 << ", " << R22 << "]"
                    << "}";
            };

            if (useMultiObject && !fp.objIds.empty()) {
                for (size_t oi = 0; oi < fp.objIds.size(); ++oi) {
                    if (oi > 0) gt6dofJson << ",";
                    gt6dofJson << "\n";
                    writeObjPose(fp.objIds[oi], "object",
                                 fp.objPositions[oi * 3 + 0], fp.objPositions[oi * 3 + 1], fp.objPositions[oi * 3 + 2],
                                 fp.objRotations[oi * 3 + 0], fp.objRotations[oi * 3 + 1], fp.objRotations[oi * 3 + 2],
                                 fp.objScales[oi]);
                }
            } else {
                gt6dofJson << "\n";
                writeObjPose(1, "primary_object", 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 1.0f);
            }
            gt6dofJson << "\n      ]\n    }";
        }
        gt6dofJson << "\n  ]\n}\n";

        std::string gt6dofPath = config.outputDir + "/gt_6dof.json";
        std::ofstream gt6dofFile(gt6dofPath);
        if (gt6dofFile.is_open()) {
            gt6dofFile << gt6dofJson.str();
            gt6dofFile.close();
            printf("[CaptureSynthetic] 6DoF Ground Truth saved to: %s\n", gt6dofPath.c_str());
        }
    }

    printf("\n========== CaptureSyntheticData COMPLETE ==========\n");
    printf("  Total   : %d\n", result.totalFrames);
    printf("  Success : %d\n", result.successFrames);
    printf("  Failed  : %d\n", result.failedFrames);
    printf("  Time    : %.2f seconds\n", result.elapsedSeconds);
    printf("  Output  : %s\n", result.outputDirectory.c_str());
    fflush(stdout);

    return result;
}

void RenderManager::openFileDialog() {
    printf("openFileDialog() called - opening Windows native file dialog...\n");
    fflush(stdout);
    
#ifdef _WIN32
    OPENFILENAMEA ofn;
    ZeroMemory(&ofn, sizeof(ofn));
    ofn.lStructSize = sizeof(ofn);
    ofn.hwndOwner = glfwGetWin32Window(window);
    
    char localPathBuffer[512] = {0};
    ofn.lpstrFile = localPathBuffer;
    ofn.nMaxFile = sizeof(localPathBuffer);
    ofn.lpstrFilter = "STL Files (*.stl)\0*.stl\0All Files (*.*)\0*.*\0";
    ofn.nFilterIndex = 1;
    ofn.lpstrFileTitle = nullptr;
    ofn.nMaxFileTitle = 0;
    ofn.lpstrInitialDir = nullptr;
    ofn.Flags = OFN_PATHMUSTEXIST | OFN_FILEMUSTEXIST | OFN_NOCHANGEDIR;
    
    printf("Calling GetOpenFileNameA...\n");
    fflush(stdout);
    
    if (GetOpenFileNameA(&ofn)) {
        printf("File selected: %s\n", localPathBuffer);
        fflush(stdout);
        loadFile(localPathBuffer);
    } else {
        DWORD err = CommDlgExtendedError();
        if (err != 0) {
            printf("GetOpenFileNameA failed with error code: %lu\n", err);
            fflush(stdout);
        } else {
            printf("User cancelled file selection\n");
            fflush(stdout);
        }
    }
#else
    printf("File dialog not implemented for this platform\n");
    fflush(stdout);
#endif
}

void RenderManager::loadFile(const std::string& filename) {
    printf("loadFile() called with: %s\n", filename.c_str());
    fflush(stdout);
    
    // 记录加载开始时间
    auto load_start = std::chrono::high_resolution_clock::now();
    
    // 创建新的对象池
    if (trianglePool) {
        delete trianglePool;
    }
    trianglePool = new hhb::core::ObjectPool<hhb::core::Triangle>();
    
    // 解析STL文件
    hhb::core::StlParser parser;
    hhb::core::ParserResult result = parser.parse(filename, *trianglePool);
    
    // 记录加载结束时间
    auto load_end = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double, std::milli> load_duration = load_end - load_start;
    loadTime = static_cast<float>(load_duration.count());
    
    if (result.success) {
        printf("File loaded successfully in %.2f ms\n", loadTime);
        printf("Triangles parsed: %zu\n", result.count);
        fflush(stdout);
        
        // 更新顶点数据
        updateVertexData(*trianglePool);
        printf("Vertex data updated, vertexData.size() = %zu\n", vertexData.size());
        fflush(stdout);
        
        // 绑定VAO和VBO
        glBindVertexArray(VAO);
        glBindBuffer(GL_ARRAY_BUFFER, VBO);
        glBufferData(GL_ARRAY_BUFFER, vertexData.size() * sizeof(float), vertexData.data(), GL_STATIC_DRAW);
        
        // 设置顶点属性指针
        // 位置属性 (location = 0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 6 * sizeof(float), (void*)0);
        glEnableVertexAttribArray(0);
        
        // 法线属性 (location = 1)
        glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 6 * sizeof(float), (void*)(3 * sizeof(float)));
        glEnableVertexAttribArray(1);
        
        glBindBuffer(GL_ARRAY_BUFFER, 0);
        glBindVertexArray(0);
        
        // 构建BVH树
        buildBVH();
        
        // 加载完模型后，自动适配视角
        centerModel();
        
        // 更新内存使用统计
        memoryUsage = triangleCount * sizeof(hhb::core::Triangle);
        
        // 重置选中状态
        selectedTriangle = nullptr;
        selectedTriangleIndex = -1;
        pickTime = 0.0f;
        
        geometryAPI.loadFromPool(*trianglePool);
        std::cout << "Model loaded into GeometryAPI from shared pool: " << geometryAPI.getTriangleCount() << " triangles" << std::endl;
        
        // 加载模型到 GeometryExpert
        geometryExpert.loadModelFromPool(*trianglePool);
        std::cout << "Model loaded into GeometryExpert from shared pool" << std::endl;
        
        // 捕获模型的三个视角
        std::string modelName = filename.substr(filename.find_last_of("\\/") + 1);
        modelName = modelName.substr(0, modelName.find_last_of("."));
        captureModelViews(modelName);
        
        printf("Model loading complete. Triangle count: %zu\n", triangleCount);
        fflush(stdout);
    } else {
        printf("Failed to load file: %s\n", result.error.c_str());
        fflush(stdout);
    }
}

void RenderManager::renderBVH() {
    if (!showBVH || bvh.node_count() == 0) {
        return;
    }
    
    // 使用线框模式渲染BVH包围盒
    glPolygonMode(GL_FRONT_AND_BACK, GL_LINE);
    
    // 设置线框颜色（绿色）
    float bvhColor[3] = {0.0f, 1.0f, 0.0f};
    GLint objectColorLoc = glGetUniformLocation(shaderProgram, "objectColor");
    glUniform3fv(objectColorLoc, 1, bvhColor);
    
    // 关闭光照影响，直接渲染纯色
    GLint metallicLoc = glGetUniformLocation(shaderProgram, "metallic");
    GLint roughnessLoc = glGetUniformLocation(shaderProgram, "roughness");
    if (metallicLoc != -1) glUniform1f(metallicLoc, 0.0f);
    if (roughnessLoc != -1) glUniform1f(roughnessLoc, 1.0f);
    
    // 仅渲染根节点包围盒作为示例（完整遍历需要访问BVH内部节点）
    hhb::core::Bounds rootBounds = bvh.get_root_bounds();
    renderAABB(rootBounds, bvhColor);
    
    // 恢复填充模式
    glPolygonMode(GL_FRONT_AND_BACK, GL_FILL);
}

void RenderManager::renderAABB(const hhb::core::Bounds& bounds, const float* color) {
    // 构建AABB的8个顶点
    float vertices[] = {
        bounds.min[0], bounds.min[1], bounds.min[2],
        bounds.max[0], bounds.min[1], bounds.min[2],
        bounds.max[0], bounds.max[1], bounds.min[2],
        bounds.min[0], bounds.max[1], bounds.min[2],
        bounds.min[0], bounds.min[1], bounds.max[2],
        bounds.max[0], bounds.min[1], bounds.max[2],
        bounds.max[0], bounds.max[1], bounds.max[2],
        bounds.min[0], bounds.max[1], bounds.max[2]
    };
    
    // 12条线段的索引 (每条线2个顶点)
    unsigned int indices[] = {
        0,1, 1,2, 2,3, 3,0, // 底面
        4,5, 5,6, 6,7, 7,4, // 顶面
        0,4, 1,5, 2,6, 3,7  // 侧面
    };

    GLuint vao, vbo, ebo;
    glGenVertexArrays(1, &vao);
    glGenBuffers(1, &vbo);
    glGenBuffers(1, &ebo);

    glBindVertexArray(vao);
    
    glBindBuffer(GL_ARRAY_BUFFER, vbo);
    glBufferData(GL_ARRAY_BUFFER, sizeof(vertices), vertices, GL_STATIC_DRAW);

    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ebo);
    glBufferData(GL_ELEMENT_ARRAY_BUFFER, sizeof(indices), indices, GL_STATIC_DRAW);

    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 3 * sizeof(float), (void*)0);
    glEnableVertexAttribArray(0);

    // 禁用法线属性，因为这里只有顶点
    glDisableVertexAttribArray(1);

    // 绘制线框
    glDrawElements(GL_LINES, 24, GL_UNSIGNED_INT, 0);

    // 清理
    glDeleteVertexArrays(1, &vao);
    glDeleteBuffers(1, &vbo);
    glDeleteBuffers(1, &ebo);
}

void RenderManager::setTargetCameraPosition(const float pos[3], float duration) {
    if (duration <= 0.0f) {
        duration = 0.001f;
    }

    if (cameraAnimating) {
        cameraPosStart[0] = cameraPosition[0];
        cameraPosStart[1] = cameraPosition[1];
        cameraPosStart[2] = cameraPosition[2];
    } else {
        memcpy(cameraPosStart, cameraPosition, sizeof(cameraPosStart));
    }

    targetCameraPos[0] = pos[0];
    targetCameraPos[1] = pos[1];
    targetCameraPos[2] = pos[2];

    cameraAnimStart = std::chrono::steady_clock::now();
    cameraAnimDuration = duration;
    cameraAnimating = true;
}

void RenderManager::setTargetCameraRotation(const float rot[2], float duration) {
    if (duration <= 0.0f) {
        duration = 0.001f;
    }

    if (cameraAnimating) {
        cameraRotStart[0] = cameraRotation[0];
        cameraRotStart[1] = cameraRotation[1];
    } else {
        memcpy(cameraRotStart, cameraRotation, sizeof(cameraRotStart));
    }

    targetCameraRot[0] = rot[0];
    targetCameraRot[1] = rot[1];

    cameraAnimStart = std::chrono::steady_clock::now();
    cameraAnimDuration = duration;
    cameraAnimating = true;
}

void RenderManager::setTargetZoom(float target, float duration) {
    if (duration <= 0.0f) {
        duration = 0.001f;
    }

    if (cameraAnimating) {
        zoomStart = zoom;
    } else {
        zoomStart = zoom;
    }

    targetZoom = target;

    cameraAnimStart = std::chrono::steady_clock::now();
    cameraAnimDuration = duration;
    cameraAnimating = true;
}

bool RenderManager::isCameraAnimating() const {
    return cameraAnimating;
}

void RenderManager::stopCameraAnimation() {
    cameraAnimating = false;
}

RenderManager::SpatialInfo RenderManager::getSpatialInfo() {
    SpatialInfo info;
    
    // 计算模型的几何中心和包围盒
    if (trianglePtrs.empty()) {
        // 模型为空，返回默认值
        memset(info.center, 0, sizeof(info.center));
        memset(info.bounds, 0, sizeof(info.bounds));
    } else {
        // 计算包围盒
        float minX = FLT_MAX, minY = FLT_MAX, minZ = FLT_MAX;
        float maxX = -FLT_MAX, maxY = -FLT_MAX, maxZ = -FLT_MAX;
        
        for (const auto& triangle : trianglePtrs) {
            // 处理第一个顶点
            minX = std::min(minX, triangle->vertex1[0]);
            minY = std::min(minY, triangle->vertex1[1]);
            minZ = std::min(minZ, triangle->vertex1[2]);
            maxX = std::max(maxX, triangle->vertex1[0]);
            maxY = std::max(maxY, triangle->vertex1[1]);
            maxZ = std::max(maxZ, triangle->vertex1[2]);
            
            // 处理第二个顶点
            minX = std::min(minX, triangle->vertex2[0]);
            minY = std::min(minY, triangle->vertex2[1]);
            minZ = std::min(minZ, triangle->vertex2[2]);
            maxX = std::max(maxX, triangle->vertex2[0]);
            maxY = std::max(maxY, triangle->vertex2[1]);
            maxZ = std::max(maxZ, triangle->vertex2[2]);
            
            // 处理第三个顶点
            minX = std::min(minX, triangle->vertex3[0]);
            minY = std::min(minY, triangle->vertex3[1]);
            minZ = std::min(minZ, triangle->vertex3[2]);
            maxX = std::max(maxX, triangle->vertex3[0]);
            maxY = std::max(maxY, triangle->vertex3[1]);
            maxZ = std::max(maxZ, triangle->vertex3[2]);
        }
        
        // 计算几何中心
        info.center[0] = (minX + maxX) / 2.0f;
        info.center[1] = (minY + maxY) / 2.0f;
        info.center[2] = (minZ + maxZ) / 2.0f;
        
        // 保存包围盒信息
        info.bounds[0] = minX;
        info.bounds[1] = minY;
        info.bounds[2] = minZ;
        info.bounds[3] = maxX;
        info.bounds[4] = maxY;
        info.bounds[5] = maxZ;
    }
    
    // 保存摄像头信息
    memcpy(info.cameraPos, cameraPosition, sizeof(info.cameraPos));
    memcpy(info.cameraRot, cameraRotation, sizeof(info.cameraRot));
    info.currentZoom = zoom;
    
    return info;
}

void RenderManager::instanceColorEncode(int instanceId, int featureTypeId, int featureIndex,
                                          float* outR, float* outG, float* outB) {
    int clampedInstance = (instanceId > 0 && instanceId < 256) ? instanceId : 0;
    int clampedFeature = (featureTypeId >= 0 && featureTypeId < 256) ? featureTypeId : 0;
    int clampedIndex = (featureIndex >= 0 && featureIndex < 256) ? featureIndex : 0;
    *outR = clampedInstance / 255.0f;
    *outG = clampedFeature / 255.0f;
    *outB = clampedIndex / 255.0f;
}

void RenderManager::instanceColorDecode(unsigned char r, unsigned char g, unsigned char b,
                                          int& instanceId, int& featureTypeId, int& featureIndex) {
    instanceId = static_cast<int>(r);
    featureTypeId = static_cast<int>(g);
    featureIndex = static_cast<int>(b);
}

bool RenderManager::addSceneObject(const std::string& filePath, const std::string& name) {
    SceneObject obj;
    obj.instanceId = static_cast<int>(sceneObjects_.size()) + 1;
    obj.name = name.empty() ? "Object_" + std::to_string(obj.instanceId) : name;
    obj.filePath = filePath;

    if (!loadSceneObjectGeometry(obj)) {
        printf("[SceneManager] Failed to load geometry for: %s\n", filePath.c_str());
        fflush(stdout);
        return false;
    }

    computeSceneObjectBounds(obj);
    computeSceneObjectFeatures(obj);

    uploadSceneObjectGPU(obj);

    sceneObjects_.push_back(std::move(obj));

    printf("[SceneManager] Added object #%d: %s (%zu triangles)\n",
           sceneObjects_.back().instanceId, sceneObjects_.back().name.c_str(),
           sceneObjects_.back().triangleCount);
    fflush(stdout);
    return true;
}

void RenderManager::clearSceneObjects() {
    for (auto& obj : sceneObjects_) {
        if (obj.VAO) { glDeleteVertexArrays(1, &obj.VAO); obj.VAO = 0; }
        if (obj.VBO) { glDeleteBuffers(1, &obj.VBO); obj.VBO = 0; }
        if (obj.labelVAO) { glDeleteVertexArrays(1, &obj.labelVAO); obj.labelVAO = 0; }
        if (obj.labelVBO) { glDeleteBuffers(1, &obj.labelVBO); obj.labelVBO = 0; }
    }
    sceneObjects_.clear();
}

bool RenderManager::loadSceneObjectGeometry(SceneObject& obj) {
    hhb::core::StlParser parser;
    hhb::core::ParserResult result = parser.parse(obj.filePath, *obj.trianglePool);
    if (!result.success) {
        printf("[SceneObject] Failed to load: %s\n", obj.filePath.c_str());
        fflush(stdout);
        return false;
    }

    obj.triangleCount = 0;
    obj.trianglePtrs.clear();
    obj.vertexData.clear();

    obj.trianglePool->for_each([&](hhb::core::Triangle* tri) {
        obj.trianglePtrs.push_back(tri);
        obj.triangleCount++;

        float* verts[3] = {tri->vertex1, tri->vertex2, tri->vertex3};
        for (int v = 0; v < 3; ++v) {
            obj.vertexData.push_back(verts[v][0]);
            obj.vertexData.push_back(verts[v][1]);
            obj.vertexData.push_back(verts[v][2]);
            obj.vertexData.push_back(tri->normal[0]);
            obj.vertexData.push_back(tri->normal[1]);
            obj.vertexData.push_back(tri->normal[2]);
        }
    });

    printf("[SceneObject] Loaded %zu triangles from %s\n", obj.triangleCount, obj.filePath.c_str());
    fflush(stdout);
    return true;
}

void RenderManager::computeSceneObjectBounds(SceneObject& obj) {
    obj.bounds[0] = obj.bounds[1] = obj.bounds[2] = 1e9f;
    obj.bounds[3] = obj.bounds[4] = obj.bounds[5] = -1e9f;

    obj.trianglePool->for_each([&](hhb::core::Triangle* tri) {
        float* verts[3] = {tri->vertex1, tri->vertex2, tri->vertex3};
        for (int v = 0; v < 3; ++v) {
            for (int ax = 0; ax < 3; ++ax) {
                obj.bounds[ax] = std::min(obj.bounds[ax], verts[v][ax]);
                obj.bounds[ax + 3] = std::max(obj.bounds[ax + 3], verts[v][ax]);
            }
        }
    });

    obj.center[0] = (obj.bounds[0] + obj.bounds[3]) * 0.5f;
    obj.center[1] = (obj.bounds[1] + obj.bounds[4]) * 0.5f;
    obj.center[2] = (obj.bounds[2] + obj.bounds[5]) * 0.5f;

    float dx = obj.bounds[3] - obj.bounds[0];
    float dy = obj.bounds[4] - obj.bounds[1];
    float dz = obj.bounds[5] - obj.bounds[2];
    obj.maxDim = std::max({dx, dy, dz});
}

void RenderManager::computeSceneObjectFeatures(SceneObject& obj) {
    if (obj.triangleCount == 0) return;

    obj.faceCategoryIds.resize(obj.triangleCount, 0);
    obj.featureInstanceIds.resize(obj.triangleCount, 0);
    obj.categoriesComputed = false;

    struct VertexInfo {
        float normal[3] = {0, 0, 0};
        float areaSum = 0.0f;
        int valence = 0;
        float pos[3] = {0, 0, 0};
    };

    auto vertexKey = [](float x, float y, float z) -> int64_t {
        int ix = (int)(x * 10000.0f);
        int iy = (int)(y * 10000.0f);
        int iz = (int)(z * 10000.0f);
        return ((int64_t)(ix & 0xFFFFF) << 40) | ((int64_t)(iy & 0xFFFFF) << 20) | (int64_t)(iz & 0xFFFFF);
    };

    std::unordered_map<int64_t, VertexInfo> vertexMap;

    obj.trianglePool->for_each([&](hhb::core::Triangle* tri) {
        float e1[3] = {tri->vertex2[0] - tri->vertex1[0],
                        tri->vertex2[1] - tri->vertex1[1],
                        tri->vertex2[2] - tri->vertex1[2]};
        float e2[3] = {tri->vertex3[0] - tri->vertex1[0],
                        tri->vertex3[1] - tri->vertex1[1],
                        tri->vertex3[2] - tri->vertex1[2]};
        float cross[3] = {
            e1[1] * e2[2] - e1[2] * e2[1],
            e1[2] * e2[0] - e1[0] * e2[2],
            e1[0] * e2[1] - e1[1] * e2[0]
        };
        float area = 0.5f * std::sqrt(cross[0]*cross[0] + cross[1]*cross[1] + cross[2]*cross[2]);

        float nx = tri->normal[0], ny = tri->normal[1], nz = tri->normal[2];
        float nLen = std::sqrt(nx*nx + ny*ny + nz*nz);
        if (nLen > 0.0001f) { nx /= nLen; ny /= nLen; nz /= nLen; }

        int64_t keys[3] = {
            vertexKey(tri->vertex1[0], tri->vertex1[1], tri->vertex1[2]),
            vertexKey(tri->vertex2[0], tri->vertex2[1], tri->vertex2[2]),
            vertexKey(tri->vertex3[0], tri->vertex3[1], tri->vertex3[2])
        };
        float* verts[3] = {tri->vertex1, tri->vertex2, tri->vertex3};

        for (int v = 0; v < 3; ++v) {
            auto& info = vertexMap[keys[v]];
            info.normal[0] += nx * area;
            info.normal[1] += ny * area;
            info.normal[2] += nz * area;
            info.areaSum += area;
            info.valence++;
            info.pos[0] = verts[v][0];
            info.pos[1] = verts[v][1];
            info.pos[2] = verts[v][2];
        }
    });

    for (auto& [key, info] : vertexMap) {
        if (info.areaSum > 0.00001f) {
            info.normal[0] /= info.areaSum;
            info.normal[1] /= info.areaSum;
            info.normal[2] /= info.areaSum;
            float nLen = std::sqrt(info.normal[0]*info.normal[0] +
                                    info.normal[1]*info.normal[1] +
                                    info.normal[2]*info.normal[2]);
            if (nLen > 0.0001f) {
                info.normal[0] /= nLen;
                info.normal[1] /= nLen;
                info.normal[2] /= nLen;
            }
        }
    }

    std::vector<float> faceMeanCurv(obj.triangleCount, 0.0f);
    std::vector<float> faceGaussCurv(obj.triangleCount, 0.0f);
    std::vector<int> faceCurvIds(obj.triangleCount, 0);

    size_t idx = 0;
    obj.trianglePool->for_each([&](hhb::core::Triangle* tri) {
        if (idx >= obj.triangleCount) return;

        int64_t keys[3] = {
            vertexKey(tri->vertex1[0], tri->vertex1[1], tri->vertex1[2]),
            vertexKey(tri->vertex2[0], tri->vertex2[1], tri->vertex2[2]),
            vertexKey(tri->vertex3[0], tri->vertex3[1], tri->vertex3[2])
        };

        float e1[3] = {tri->vertex2[0] - tri->vertex1[0],
                        tri->vertex2[1] - tri->vertex1[1],
                        tri->vertex2[2] - tri->vertex1[2]};
        float e2[3] = {tri->vertex3[0] - tri->vertex1[0],
                        tri->vertex3[1] - tri->vertex1[1],
                        tri->vertex3[2] - tri->vertex1[2]};
        float cross[3] = {
            e1[1] * e2[2] - e1[2] * e2[1],
            e1[2] * e2[0] - e1[0] * e2[2],
            e1[0] * e2[1] - e1[1] * e2[0]
        };
        float area = 0.5f * std::sqrt(cross[0]*cross[0] + cross[1]*cross[1] + cross[2]*cross[2]);

        float meanCurv = 0.0f;
        if (area > 0.00001f) {
            for (int v = 0; v < 3; ++v) {
                auto it = vertexMap.find(keys[v]);
                if (it != vertexMap.end()) {
                    float dx = it->second.pos[0] - tri->vertex1[0];
                    float dy = it->second.pos[1] - tri->vertex1[1];
                    float dz = it->second.pos[2] - tri->vertex1[2];
                    float dist = std::sqrt(dx*dx + dy*dy + dz*dz);
                    float dotProd = it->second.normal[0] * tri->normal[0] +
                                    it->second.normal[1] * tri->normal[1] +
                                    it->second.normal[2] * tri->normal[2];
                    float angle = std::acos(std::max(-1.0f, std::min(1.0f, dotProd)));
                    meanCurv += angle / dist;
                }
            }
            meanCurv /= (3.0f * area);
        }

        float gaussianCurv = 0.0f;
        if (area > 0.00001f) {
            float angleSum = 0.0f;
            for (int v = 0; v < 3; ++v) {
                auto it = vertexMap.find(keys[v]);
                if (it != vertexMap.end() && it->second.valence > 0) {
                    angleSum += 2.0f * 3.14159265f / it->second.valence;
                }
            }
            gaussianCurv = (angleSum - 3.14159265f) / area;
        }

        faceMeanCurv[idx] = meanCurv;
        faceGaussCurv[idx] = gaussianCurv;

        float absMean = std::abs(meanCurv);
        float absGauss = std::abs(gaussianCurv);

        if (absMean < 0.5f && absGauss < 0.5f) {
            faceCurvIds[idx] = 0;
        } else if (absGauss > 2.0f && gaussianCurv > 0) {
            faceCurvIds[idx] = 1;
        } else if (absGauss > 2.0f && gaussianCurv < 0) {
            faceCurvIds[idx] = 2;
        } else if (absMean > 1.0f && meanCurv > 0) {
            faceCurvIds[idx] = 3;
        } else if (absMean > 1.0f && meanCurv < 0) {
            faceCurvIds[idx] = 4;
        } else {
            faceCurvIds[idx] = 5;
        }

        idx++;
    });

    struct EdgeKey {
        int64_t v0, v1;
        bool operator==(const EdgeKey& o) const { return v0 == o.v0 && v1 == o.v1; }
    };
    struct EdgeKeyHash {
        size_t operator()(const EdgeKey& k) const { return std::hash<int64_t>()(k.v0) ^ (std::hash<int64_t>()(k.v1) << 1); }
    };

    auto makeEdge = [](int64_t a, int64_t b) -> EdgeKey {
        return a < b ? EdgeKey{a, b} : EdgeKey{b, a};
    };

    std::unordered_map<EdgeKey, std::vector<int>, EdgeKeyHash> edgeToTriangles;
    std::vector<int64_t> triVertexKeys(obj.triangleCount * 3);

    idx = 0;
    obj.trianglePool->for_each([&](hhb::core::Triangle* tri) {
        if (idx >= obj.triangleCount) return;

        int64_t k1 = vertexKey(tri->vertex1[0], tri->vertex1[1], tri->vertex1[2]);
        int64_t k2 = vertexKey(tri->vertex2[0], tri->vertex2[1], tri->vertex2[2]);
        int64_t k3 = vertexKey(tri->vertex3[0], tri->vertex3[1], tri->vertex3[2]);

        triVertexKeys[idx * 3 + 0] = k1;
        triVertexKeys[idx * 3 + 1] = k2;
        triVertexKeys[idx * 3 + 2] = k3;

        edgeToTriangles[makeEdge(k1, k2)].push_back((int)idx);
        edgeToTriangles[makeEdge(k2, k3)].push_back((int)idx);
        edgeToTriangles[makeEdge(k1, k3)].push_back((int)idx);

        idx++;
    });

    std::vector<bool> visited(obj.triangleCount, false);
    std::vector<std::vector<int>> clusters;

    for (size_t start = 0; start < obj.triangleCount; ++start) {
        if (visited[start]) continue;

        int curvId = faceCurvIds[start];
        std::vector<int> cluster;
        std::vector<int> stack;
        stack.push_back((int)start);

        while (!stack.empty()) {
            int triIdx = stack.back();
            stack.pop_back();
            if (triIdx < 0 || triIdx >= (int)obj.triangleCount || visited[triIdx]) continue;
            if (faceCurvIds[triIdx] != curvId) continue;

            visited[triIdx] = true;
            cluster.push_back(triIdx);

            int64_t k1 = triVertexKeys[triIdx * 3 + 0];
            int64_t k2 = triVertexKeys[triIdx * 3 + 1];
            int64_t k3 = triVertexKeys[triIdx * 3 + 2];

            auto addNeighbors = [&](int64_t a, int64_t b) {
                EdgeKey ek = makeEdge(a, b);
                auto it = edgeToTriangles.find(ek);
                if (it != edgeToTriangles.end()) {
                    for (int nIdx : it->second) {
                        if (!visited[nIdx] && faceCurvIds[nIdx] == curvId) {
                            stack.push_back(nIdx);
                        }
                    }
                }
            };

            addNeighbors(k1, k2);
            addNeighbors(k2, k3);
            addNeighbors(k1, k3);
        }

        if (!cluster.empty()) {
            clusters.push_back(std::move(cluster));
        }
    }

    printf("[SceneObjFeature] Object '%s': %zu curvature clusters from %zu triangles\n",
           obj.name.c_str(), clusters.size(), obj.triangleCount);

    for (auto& cluster : clusters) {
        float totalArea = 0.0f;
        float avgMeanCurv = 0;
        float avgGaussCurv = 0;
        int boundaryEdges = 0;

        std::unordered_set<int> clusterSet(cluster.begin(), cluster.end());

        for (int triIdx : cluster) {
            float e1[3], e2[3];
            size_t localIdx = 0;
            obj.trianglePool->for_each([&](hhb::core::Triangle* tri) {
                if (localIdx != (size_t)triIdx) { localIdx++; return; }
                e1[0] = tri->vertex2[0] - tri->vertex1[0];
                e1[1] = tri->vertex2[1] - tri->vertex1[1];
                e1[2] = tri->vertex2[2] - tri->vertex1[2];
                e2[0] = tri->vertex3[0] - tri->vertex1[0];
                e2[1] = tri->vertex3[1] - tri->vertex1[1];
                e2[2] = tri->vertex3[2] - tri->vertex1[2];
                localIdx++;
            });

            float cross[3] = {
                e1[1]*e2[2] - e1[2]*e2[1],
                e1[2]*e2[0] - e1[0]*e2[2],
                e1[0]*e2[1] - e1[1]*e2[0]
            };
            float area = 0.5f * std::sqrt(cross[0]*cross[0] + cross[1]*cross[1] + cross[2]*cross[2]);
            totalArea += area;
            avgMeanCurv += faceMeanCurv[triIdx];
            avgGaussCurv += faceGaussCurv[triIdx];

            int64_t k1 = triVertexKeys[triIdx * 3 + 0];
            int64_t k2 = triVertexKeys[triIdx * 3 + 1];
            int64_t k3 = triVertexKeys[triIdx * 3 + 2];

            auto checkBoundary = [&](int64_t a, int64_t b) {
                EdgeKey ek = makeEdge(a, b);
                auto it = edgeToTriangles.find(ek);
                if (it != edgeToTriangles.end() && it->second.size() == 1) {
                    boundaryEdges++;
                } else if (it != edgeToTriangles.end()) {
                    bool hasExternal = false;
                    for (int nIdx : it->second) {
                        if (clusterSet.find(nIdx) == clusterSet.end()) {
                            hasExternal = true;
                            break;
                        }
                    }
                    if (hasExternal) boundaryEdges++;
                }
            };
            checkBoundary(k1, k2);
            checkBoundary(k2, k3);
            checkBoundary(k1, k3);
        }

        if (cluster.empty()) continue;
        avgMeanCurv /= cluster.size();
        avgGaussCurv /= cluster.size();

        int featureCategory = 0;

        if (cluster.size() < 5) {
            featureCategory = 0;
        }
        else if (avgGaussCurv > 1.5f && avgMeanCurv > 0.5f && totalArea < 0.5f) {
            featureCategory = 8;
        }
        else if (avgGaussCurv > 1.5f && avgMeanCurv < -0.5f && totalArea < 0.3f) {
            featureCategory = 9;
        }
        else if (avgMeanCurv < -1.0f && boundaryEdges >= 3) {
            featureCategory = 10;
        }
        else if (avgMeanCurv > 1.0f && totalArea > 0.1f && totalArea < 2.0f) {
            featureCategory = 11;
        }
        else if (std::abs(avgMeanCurv) < 0.5f && std::abs(avgGaussCurv) < 0.5f) {
            featureCategory = 1;
        }
        else {
            featureCategory = 0;
        }

        for (int triIdx : cluster) {
            obj.faceCategoryIds[triIdx] = featureCategory;
        }
    }

    std::unordered_map<int, int> categoryInstanceIndex;
    for (size_t fi = 0; fi < obj.triangleCount; ++fi) {
        int catId = obj.faceCategoryIds[fi];
        if (catId == 0 || catId == 7) {
            obj.featureInstanceIds[fi] = 0;
        } else {
            obj.featureInstanceIds[fi] = ++categoryInstanceIndex[catId];
        }
    }

    obj.categoriesComputed = true;
    printf("[SceneObjFeature] Object '%s': feature classification complete\n", obj.name.c_str());
    fflush(stdout);
}

void RenderManager::computeAllFeatureInstances() {
    for (auto& obj : sceneObjects_) {
        if (!obj.categoriesComputed) {
            computeSceneObjectFeatures(obj);
        }
    }
}

bool RenderManager::loadTopologyLabels(const std::string& jsonPath) {
    std::ifstream file(jsonPath);
    if (!file.is_open()) {
        printf("[TopologyLabels] ERROR: Cannot open %s\n", jsonPath.c_str());
        fflush(stdout);
        return false;
    }

    std::string content((std::istreambuf_iterator<char>(file)),
                         std::istreambuf_iterator<char>());
    file.close();

    auto skipWS = [](const std::string& s, size_t& pos) {
        while (pos < s.size() && (s[pos] == ' ' || s[pos] == '\t' || s[pos] == '\n' || s[pos] == '\r'))
            pos++;
    };

    auto expectChar = [](const std::string& s, size_t& pos, char c) -> bool {
        if (pos < s.size() && s[pos] == c) { pos++; return true; }
        return false;
    };

    auto findKey = [&](const std::string& s, size_t& pos, const std::string& key) -> bool {
        size_t found = s.find("\"" + key + "\"", pos);
        if (found == std::string::npos) return false;
        pos = found + key.size() + 2;
        skipWS(s, pos);
        if (!expectChar(s, pos, ':')) return false;
        skipWS(s, pos);
        return true;
    };

    auto parseArray = [&](const std::string& s, size_t& pos) -> std::vector<int> {
        std::vector<int> result;
        if (!expectChar(s, pos, '[')) return result;
        skipWS(s, pos);
        while (pos < s.size() && s[pos] != ']') {
            skipWS(s, pos);
            int val = 0;
            bool neg = false;
            if (pos < s.size() && s[pos] == '-') { neg = true; pos++; }
            while (pos < s.size() && s[pos] >= '0' && s[pos] <= '9') {
                val = val * 10 + (s[pos] - '0');
                pos++;
            }
            if (neg) val = -val;
            result.push_back(val);
            skipWS(s, pos);
            if (pos < s.size() && s[pos] == ',') pos++;
            skipWS(s, pos);
        }
        if (pos < s.size() && s[pos] == ']') pos++;
        return result;
    };

    size_t pos = 0;
    skipWS(content, pos);
    if (!expectChar(content, pos, '{')) {
        printf("[TopologyLabels] ERROR: Invalid JSON format\n");
        return false;
    }

    if (!findKey(content, pos, "triangle_labels")) {
        printf("[TopologyLabels] ERROR: 'triangle_labels' key not found\n");
        return false;
    }

    topologyFaceLabels_ = parseArray(content, pos);

    if (topologyFaceLabels_.empty()) {
        printf("[TopologyLabels] ERROR: Empty triangle_labels array\n");
        return false;
    }

    topologyLabelsLoaded = true;

    std::unordered_map<int, int> catCounts;
    for (int label : topologyFaceLabels_) {
        catCounts[label]++;
    }

    const char* catNames[] = {
        "FreeSurface", "HorizontalPlane", "LateralPlane_X",
        "LateralPlane_Z", "NearHorizontal", "NearLateral_X",
        "NearLateral_Z", "Degenerate", "ConvexFeature_Bolt",
        "ConcaveFeature_Hole", "Flange", "Boss",
        "Chamfer", "Fillet", "SphericalSurface"
    };

    printf("[TopologyLabels] Loaded %zu labels from %s\n",
           topologyFaceLabels_.size(), jsonPath.c_str());
    for (auto& [catId, count] : catCounts) {
        const char* name = (catId >= 0 && catId < 15) ? catNames[catId] : "Unknown";
        printf("  %2d %-25s: %d triangles\n", catId, name, count);
    }
    fflush(stdout);

    return true;
}

bool RenderManager::loadSceneObjectTopologyLabels(SceneObject& obj, const std::string& jsonPath) {
    std::ifstream file(jsonPath);
    if (!file.is_open()) {
        printf("[TopologyLabels] ERROR: Cannot open %s for object '%s'\n",
               jsonPath.c_str(), obj.name.c_str());
        fflush(stdout);
        return false;
    }

    std::string content((std::istreambuf_iterator<char>(file)),
                         std::istreambuf_iterator<char>());
    file.close();

    auto skipWS = [](const std::string& s, size_t& pos) {
        while (pos < s.size() && (s[pos] == ' ' || s[pos] == '\t' || s[pos] == '\n' || s[pos] == '\r'))
            pos++;
    };

    auto expectChar = [](const std::string& s, size_t& pos, char c) -> bool {
        if (pos < s.size() && s[pos] == c) { pos++; return true; }
        return false;
    };

    auto findKey = [&](const std::string& s, size_t& pos, const std::string& key) -> bool {
        size_t found = s.find("\"" + key + "\"", pos);
        if (found == std::string::npos) return false;
        pos = found + key.size() + 2;
        skipWS(s, pos);
        if (!expectChar(s, pos, ':')) return false;
        skipWS(s, pos);
        return true;
    };

    auto parseArray = [&](const std::string& s, size_t& pos) -> std::vector<int> {
        std::vector<int> result;
        if (!expectChar(s, pos, '[')) return result;
        skipWS(s, pos);
        while (pos < s.size() && s[pos] != ']') {
            skipWS(s, pos);
            int val = 0;
            bool neg = false;
            if (pos < s.size() && s[pos] == '-') { neg = true; pos++; }
            while (pos < s.size() && s[pos] >= '0' && s[pos] <= '9') {
                val = val * 10 + (s[pos] - '0');
                pos++;
            }
            if (neg) val = -val;
            result.push_back(val);
            skipWS(s, pos);
            if (pos < s.size() && s[pos] == ',') pos++;
            skipWS(s, pos);
        }
        if (pos < s.size() && s[pos] == ']') pos++;
        return result;
    };

    size_t pos = 0;
    skipWS(content, pos);
    if (!expectChar(content, pos, '{')) return false;

    if (!findKey(content, pos, "triangle_labels")) return false;

    std::vector<int> labels = parseArray(content, pos);

    if (labels.empty()) {
        printf("[TopologyLabels] ERROR: Empty labels for object '%s'\n", obj.name.c_str());
        return false;
    }

    if (labels.size() != obj.triangleCount) {
        printf("[TopologyLabels] WARNING: Label count (%zu) != triangle count (%zu) for '%s'\n",
               labels.size(), obj.triangleCount, obj.name.c_str());
        size_t minCount = std::min(labels.size(), obj.triangleCount);
        obj.faceCategoryIds.resize(obj.triangleCount, 0);
        for (size_t i = 0; i < minCount; ++i) {
            obj.faceCategoryIds[i] = labels[i];
        }
    } else {
        obj.faceCategoryIds = labels;
    }

    std::unordered_map<int, int> catInstanceIndex;
    obj.featureInstanceIds.resize(obj.triangleCount, 0);
    for (size_t fi = 0; fi < obj.triangleCount; ++fi) {
        int catId = obj.faceCategoryIds[fi];
        if (catId == 0 || catId == 7) {
            obj.featureInstanceIds[fi] = 0;
        } else {
            obj.featureInstanceIds[fi] = ++catInstanceIndex[catId];
        }
    }

    obj.categoriesComputed = true;

    printf("[TopologyLabels] Object '%s': %zu topology labels applied (GROUND TRUTH from STEP)\n",
           obj.name.c_str(), labels.size());
    fflush(stdout);
    return true;
}

void RenderManager::uploadSceneObjectGPU(SceneObject& obj) {
    if (obj.vertexData.empty()) return;

    glGenVertexArrays(1, &obj.VAO);
    glGenBuffers(1, &obj.VBO);

    glBindVertexArray(obj.VAO);
    glBindBuffer(GL_ARRAY_BUFFER, obj.VBO);
    glBufferData(GL_ARRAY_BUFFER, obj.vertexData.size() * sizeof(float),
                 obj.vertexData.data(), GL_STATIC_DRAW);

    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 6 * sizeof(float), (void*)0);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 6 * sizeof(float), (void*)(3 * sizeof(float)));
    glEnableVertexAttribArray(1);

    glBindBuffer(GL_ARRAY_BUFFER, 0);
    glBindVertexArray(0);
}

void RenderManager::buildSceneObjectLabelData(SceneObject& obj) {
    if (!obj.categoriesComputed || obj.triangleCount == 0) return;

    obj.labelVertexData.clear();
    obj.labelVertexData.reserve(obj.triangleCount * 18);

    size_t fi = 0;
    obj.trianglePool->for_each([&](hhb::core::Triangle* tri) {
        int catId = (fi < obj.faceCategoryIds.size()) ? obj.faceCategoryIds[fi] : 0;
        float r, g, b;
        categoryToColor(catId, &r, &g, &b);

        float* verts[3] = {tri->vertex1, tri->vertex2, tri->vertex3};
        for (int v = 0; v < 3; ++v) {
            obj.labelVertexData.push_back(verts[v][0]);
            obj.labelVertexData.push_back(verts[v][1]);
            obj.labelVertexData.push_back(verts[v][2]);
            obj.labelVertexData.push_back(r);
            obj.labelVertexData.push_back(g);
            obj.labelVertexData.push_back(b);
        }
        fi++;
    });

    if (obj.labelVAO == 0) glGenVertexArrays(1, &obj.labelVAO);
    if (obj.labelVBO == 0) glGenBuffers(1, &obj.labelVBO);

    glBindVertexArray(obj.labelVAO);
    glBindBuffer(GL_ARRAY_BUFFER, obj.labelVBO);
    glBufferData(GL_ARRAY_BUFFER, obj.labelVertexData.size() * sizeof(float),
                 obj.labelVertexData.data(), GL_STATIC_DRAW);

    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 6 * sizeof(float), (void*)0);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 6 * sizeof(float), (void*)(3 * sizeof(float)));
    glEnableVertexAttribArray(1);

    glBindBuffer(GL_ARRAY_BUFFER, 0);
    glBindVertexArray(0);
}

void RenderManager::buildSceneObjectInstanceLabelData(SceneObject& obj) {
    if (!obj.categoriesComputed || obj.triangleCount == 0) return;

    obj.labelVertexData.clear();
    obj.labelVertexData.reserve(obj.triangleCount * 18);

    size_t fi = 0;
    obj.trianglePool->for_each([&](hhb::core::Triangle* tri) {
        int catId = (fi < obj.faceCategoryIds.size()) ? obj.faceCategoryIds[fi] : 0;
        int featIdx = (fi < obj.featureInstanceIds.size()) ? obj.featureInstanceIds[fi] : 0;

        float r, g, b;
        instanceColorEncode(obj.instanceId, catId, featIdx, &r, &g, &b);

        float* verts[3] = {tri->vertex1, tri->vertex2, tri->vertex3};
        for (int v = 0; v < 3; ++v) {
            obj.labelVertexData.push_back(verts[v][0]);
            obj.labelVertexData.push_back(verts[v][1]);
            obj.labelVertexData.push_back(verts[v][2]);
            obj.labelVertexData.push_back(r);
            obj.labelVertexData.push_back(g);
            obj.labelVertexData.push_back(b);
        }
        fi++;
    });

    if (obj.labelVAO == 0) glGenVertexArrays(1, &obj.labelVAO);
    if (obj.labelVBO == 0) glGenBuffers(1, &obj.labelVBO);

    glBindVertexArray(obj.labelVAO);
    glBindBuffer(GL_ARRAY_BUFFER, obj.labelVBO);
    glBufferData(GL_ARRAY_BUFFER, obj.labelVertexData.size() * sizeof(float),
                 obj.labelVertexData.data(), GL_STATIC_DRAW);

    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 6 * sizeof(float), (void*)0);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 6 * sizeof(float), (void*)(3 * sizeof(float)));
    glEnableVertexAttribArray(1);

    glBindBuffer(GL_ARRAY_BUFFER, 0);
    glBindVertexArray(0);
}

void RenderManager::randomizeSceneLayout() {
    static std::mt19937 rng(42);
    std::uniform_real_distribution<float> posDist(-3.0f, 3.0f);
    std::uniform_real_distribution<float> rotDist(0.0f, 6.283185f);
    std::uniform_real_distribution<float> scaleDist(0.5f, 2.0f);

    struct PlacedBox {
        float cx, cy, cz;
        float halfW, halfH, halfD;
    };
    std::vector<PlacedBox> placed;

    auto aabbOverlap = [](const PlacedBox& a, const PlacedBox& b) -> bool {
        return (std::abs(a.cx - b.cx) < (a.halfW + b.halfW)) &&
               (std::abs(a.cy - b.cy) < (a.halfH + b.halfH)) &&
               (std::abs(a.cz - b.cz) < (a.halfD + b.halfD));
    };

    for (auto& obj : sceneObjects_) {
        obj.rotation[0] = rotDist(rng);
        obj.rotation[1] = rotDist(rng);
        obj.rotation[2] = rotDist(rng);
        obj.scale = scaleDist(rng);

        float halfW = (obj.bounds[3] - obj.bounds[0]) * 0.5f * obj.scale;
        float halfH = (obj.bounds[4] - obj.bounds[1]) * 0.5f * obj.scale;
        float halfD = (obj.bounds[5] - obj.bounds[2]) * 0.5f * obj.scale;
        float padding = 0.15f;
        halfW += padding;
        halfH += padding;
        halfD += padding;

        bool collisionFree = false;
        int attempts = 0;
        const int maxAttempts = 50;

        while (!collisionFree && attempts < maxAttempts) {
            obj.position[0] = posDist(rng);
            obj.position[1] = 0.0f;
            obj.position[2] = posDist(rng);

            PlacedBox candidate{obj.position[0], obj.position[1], obj.position[2], halfW, halfH, halfD};

            collisionFree = true;
            for (const auto& p : placed) {
                if (aabbOverlap(candidate, p)) {
                    collisionFree = false;
                    break;
                }
            }
            attempts++;
        }

        if (!collisionFree) {
            obj.position[0] = posDist(rng);
            obj.position[1] = 0.0f;
            obj.position[2] = posDist(rng);
        }

        placed.push_back({obj.position[0], obj.position[1], obj.position[2], halfW, halfH, halfD});
    }
}

void RenderManager::applyDomainRandomization(const DomainRandomizationConfig& config,
                                               float& lightAngle, float& lightIntensity,
                                               float lightColor[3],
                                               float& camJitterX, float& camJitterY,
                                               float& camJitterZ, float& focalJitter) {
    static std::mt19937 rng(std::random_device{}());

    if (config.enableLightRandomization) {
        std::uniform_real_distribution<float> angleDist(-config.lightAngleRange, config.lightAngleRange);
        lightAngle = angleDist(rng);

        std::uniform_real_distribution<float> intDist(config.lightIntensityRange[0],
                                                       config.lightIntensityRange[1]);
        lightIntensity = intDist(rng);

        float cctMin = config.lightColorTempRange[0];
        float cctMax = config.lightColorTempRange[1];
        std::uniform_real_distribution<float> cctDist(cctMin, cctMax);
        float cct = cctDist(rng);

        float t = (cct - 1000.0f) / 9000.0f;
        t = std::max(0.0f, std::min(1.0f, t));
        if (t < 0.5f) {
            lightColor[0] = 1.0f;
            lightColor[1] = 0.6f + t * 0.8f;
            lightColor[2] = 0.3f + t * 1.4f;
        } else {
            lightColor[0] = 1.0f - (t - 0.5f) * 0.3f;
            lightColor[1] = 1.0f - (t - 0.5f) * 0.1f;
            lightColor[2] = 1.0f;
        }
    }

    if (config.enableCameraJitter) {
        std::uniform_real_distribution<float> posJitter(-config.cameraJitterPosRange,
                                                         config.cameraJitterPosRange);
        camJitterX = posJitter(rng);
        camJitterY = posJitter(rng);
        camJitterZ = posJitter(rng);

        std::uniform_real_distribution<float> focalDist(-config.focalLengthJitterRange,
                                                         config.focalLengthJitterRange);
        focalJitter = focalDist(rng);
    }
}

void RenderManager::renderSceneRGB(const CaptureConfig& config,
                                     const float* viewMatrix,
                                     const float* projectionMatrix,
                                     const float* lightPos,
                                     const float* lightColor,
                                     float lightIntensity) {
    if (!shaderProgram) return;

    glUseProgram(shaderProgram);

    GLint viewLoc = glGetUniformLocation(shaderProgram, "view");
    GLint projLoc = glGetUniformLocation(shaderProgram, "projection");
    glUniformMatrix4fv(viewLoc, 1, GL_FALSE, viewMatrix);
    glUniformMatrix4fv(projLoc, 1, GL_FALSE, projectionMatrix);

    GLint lightPosLoc = glGetUniformLocation(shaderProgram, "lightPos");
    GLint lightColorLoc = glGetUniformLocation(shaderProgram, "lightColor");
    GLint lightIntLoc = glGetUniformLocation(shaderProgram, "lightIntensity");
    if (lightPosLoc != -1) glUniform3fv(lightPosLoc, 1, lightPos);
    if (lightColorLoc != -1) glUniform3fv(lightColorLoc, 1, lightColor);
    if (lightIntLoc != -1) glUniform1f(lightIntLoc, lightIntensity);

    GLint modelLoc = glGetUniformLocation(shaderProgram, "model");

    for (auto& obj : sceneObjects_) {
        float model[16] = {
            obj.scale, 0.0f, 0.0f, 0.0f,
            0.0f, obj.scale, 0.0f, 0.0f,
            0.0f, 0.0f, obj.scale, 0.0f,
            obj.position[0], obj.position[1], obj.position[2], 1.0f
        };

        float cosRx = cosf(obj.rotation[0]), sinRx = sinf(obj.rotation[0]);
        float cosRy = cosf(obj.rotation[1]), sinRy = sinf(obj.rotation[1]);
        float cosRz = cosf(obj.rotation[2]), sinRz = sinf(obj.rotation[2]);

        float rotX[16] = {1,0,0,0, 0,cosRx,sinRx,0, 0,-sinRx,cosRx,0, 0,0,0,1};
        float rotY[16] = {cosRy,0,-sinRy,0, 0,1,0,0, sinRy,0,cosRy,0, 0,0,0,1};
        float rotZ[16] = {cosRz,sinRz,0,0, -sinRz,cosRz,0,0, 0,0,1,0, 0,0,0,1};

        float temp[16] = {0};
        for (int row = 0; row < 4; ++row)
            for (int col = 0; col < 4; ++col)
                for (int k = 0; k < 4; ++k)
                    temp[row * 4 + col] += rotZ[row * 4 + k] * rotY[k * 4 + col];

        float rotZY[16] = {0};
        for (int row = 0; row < 4; ++row)
            for (int col = 0; col < 4; ++col)
                for (int k = 0; k < 4; ++k)
                    rotZY[row * 4 + col] += temp[row * 4 + k] * rotX[k * 4 + col];

        float finalModel[16] = {0};
        for (int row = 0; row < 4; ++row)
            for (int col = 0; col < 4; ++col)
                for (int k = 0; k < 4; ++k)
                    finalModel[row * 4 + col] += model[row * 4 + k] * rotZY[k * 4 + col];

        glUniformMatrix4fv(modelLoc, 1, GL_FALSE, finalModel);

        glBindVertexArray(obj.VAO);
        glDrawArrays(GL_TRIANGLES, 0, static_cast<GLsizei>(obj.triangleCount * 3));
    }

    glBindVertexArray(0);
    glUseProgram(0);
}

void RenderManager::renderSceneSemanticMask(const CaptureConfig& config,
                                              const float* viewMatrix,
                                              const float* projectionMatrix) {
    if (!labelShaderProgram) return;

    for (auto& obj : sceneObjects_) {
        if (obj.labelVertexData.empty() || !obj.categoriesComputed) {
            buildSceneObjectLabelData(obj);
        }
    }

    glUseProgram(labelShaderProgram);

    GLint viewLoc = glGetUniformLocation(labelShaderProgram, "view");
    GLint projLoc = glGetUniformLocation(labelShaderProgram, "projection");
    glUniformMatrix4fv(viewLoc, 1, GL_FALSE, viewMatrix);
    glUniformMatrix4fv(projLoc, 1, GL_FALSE, projectionMatrix);

    GLint modelLoc = glGetUniformLocation(labelShaderProgram, "model");

    for (auto& obj : sceneObjects_) {
        float model[16] = {
            obj.scale, 0.0f, 0.0f, 0.0f,
            0.0f, obj.scale, 0.0f, 0.0f,
            0.0f, 0.0f, obj.scale, 0.0f,
            obj.position[0], obj.position[1], obj.position[2], 1.0f
        };

        float cosRx = cosf(obj.rotation[0]), sinRx = sinf(obj.rotation[0]);
        float cosRy = cosf(obj.rotation[1]), sinRy = sinf(obj.rotation[1]);
        float cosRz = cosf(obj.rotation[2]), sinRz = sinf(obj.rotation[2]);

        float rotX[16] = {1,0,0,0, 0,cosRx,sinRx,0, 0,-sinRx,cosRx,0, 0,0,0,1};
        float rotY[16] = {cosRy,0,-sinRy,0, 0,1,0,0, sinRy,0,cosRy,0, 0,0,0,1};
        float rotZ[16] = {cosRz,sinRz,0,0, -sinRz,cosRz,0,0, 0,0,1,0, 0,0,0,1};

        float temp[16] = {0};
        for (int row = 0; row < 4; ++row)
            for (int col = 0; col < 4; ++col)
                for (int k = 0; k < 4; ++k)
                    temp[row * 4 + col] += rotZ[row * 4 + k] * rotY[k * 4 + col];

        float rotZY[16] = {0};
        for (int row = 0; row < 4; ++row)
            for (int col = 0; col < 4; ++col)
                for (int k = 0; k < 4; ++k)
                    rotZY[row * 4 + col] += temp[row * 4 + k] * rotX[k * 4 + col];

        float finalModel[16] = {0};
        for (int row = 0; row < 4; ++row)
            for (int col = 0; col < 4; ++col)
                for (int k = 0; k < 4; ++k)
                    finalModel[row * 4 + col] += model[row * 4 + k] * rotZY[k * 4 + col];

        glUniformMatrix4fv(modelLoc, 1, GL_FALSE, finalModel);

        glBindVertexArray(obj.labelVAO);
        glDrawArrays(GL_TRIANGLES, 0, static_cast<GLsizei>(obj.triangleCount * 3));
    }

    glBindVertexArray(0);
    glUseProgram(0);
}

void RenderManager::renderSceneInstanceMask(const CaptureConfig& config,
                                              const float* viewMatrix,
                                              const float* projectionMatrix) {
    if (!labelShaderProgram) return;

    for (auto& obj : sceneObjects_) {
        buildSceneObjectInstanceLabelData(obj);
    }

    glUseProgram(labelShaderProgram);

    GLint viewLoc = glGetUniformLocation(labelShaderProgram, "view");
    GLint projLoc = glGetUniformLocation(labelShaderProgram, "projection");
    glUniformMatrix4fv(viewLoc, 1, GL_FALSE, viewMatrix);
    glUniformMatrix4fv(projLoc, 1, GL_FALSE, projectionMatrix);

    GLint modelLoc = glGetUniformLocation(labelShaderProgram, "model");

    for (auto& obj : sceneObjects_) {
        float model[16] = {
            obj.scale, 0.0f, 0.0f, 0.0f,
            0.0f, obj.scale, 0.0f, 0.0f,
            0.0f, 0.0f, obj.scale, 0.0f,
            obj.position[0], obj.position[1], obj.position[2], 1.0f
        };

        float cosRx = cosf(obj.rotation[0]), sinRx = sinf(obj.rotation[0]);
        float cosRy = cosf(obj.rotation[1]), sinRy = sinf(obj.rotation[1]);
        float cosRz = cosf(obj.rotation[2]), sinRz = sinf(obj.rotation[2]);

        float rotX[16] = {1,0,0,0, 0,cosRx,sinRx,0, 0,-sinRx,cosRx,0, 0,0,0,1};
        float rotY[16] = {cosRy,0,-sinRy,0, 0,1,0,0, sinRy,0,cosRy,0, 0,0,0,1};
        float rotZ[16] = {cosRz,sinRz,0,0, -sinRz,cosRz,0,0, 0,0,1,0, 0,0,0,1};

        float temp[16] = {0};
        for (int row = 0; row < 4; ++row)
            for (int col = 0; col < 4; ++col)
                for (int k = 0; k < 4; ++k)
                    temp[row * 4 + col] += rotZ[row * 4 + k] * rotY[k * 4 + col];

        float rotZY[16] = {0};
        for (int row = 0; row < 4; ++row)
            for (int col = 0; col < 4; ++col)
                for (int k = 0; k < 4; ++k)
                    rotZY[row * 4 + col] += temp[row * 4 + k] * rotX[k * 4 + col];

        float finalModel[16] = {0};
        for (int row = 0; row < 4; ++row)
            for (int col = 0; col < 4; ++col)
                for (int k = 0; k < 4; ++k)
                    finalModel[row * 4 + col] += model[row * 4 + k] * rotZY[k * 4 + col];

        glUniformMatrix4fv(modelLoc, 1, GL_FALSE, finalModel);

        glBindVertexArray(obj.labelVAO);
        glDrawArrays(GL_TRIANGLES, 0, static_cast<GLsizei>(obj.triangleCount * 3));
    }

    glBindVertexArray(0);
    glUseProgram(0);
}

void RenderManager::initBackgroundRenderer() {
    if (backgroundInitialized_) return;

    const char* bgVertSrc = R"(
#version 330
layout (location = 0) in vec2 aPos;
layout (location = 1) in vec2 aTexCoord;
out vec2 TexCoord;
void main() {
    gl_Position = vec4(aPos, 0.9999, 1.0);
    TexCoord = aTexCoord;
}
)";

    const char* bgFragSrc = R"(
#version 330
out vec4 FragColor;
in vec2 TexCoord;
uniform sampler2D bgTexture;
uniform bool useTexture;
uniform vec3 bgColor;
void main() {
    if (useTexture) {
        FragColor = texture(bgTexture, TexCoord);
    } else {
        FragColor = vec4(bgColor, 1.0);
    }
}
)";

    backgroundShaderProgram_ = createShaderProgram(bgVertSrc, bgFragSrc);

    float bgVertices[] = {
        -1.0f,  1.0f,  0.0f, 1.0f,
        -1.0f, -1.0f,  0.0f, 0.0f,
         1.0f, -1.0f,  1.0f, 0.0f,
        -1.0f,  1.0f,  0.0f, 1.0f,
         1.0f, -1.0f,  1.0f, 0.0f,
         1.0f,  1.0f,  1.0f, 1.0f,
    };

    glGenVertexArrays(1, &backgroundVAO_);
    glGenBuffers(1, &backgroundVBO_);
    glBindVertexArray(backgroundVAO_);
    glBindBuffer(GL_ARRAY_BUFFER, backgroundVBO_);
    glBufferData(GL_ARRAY_BUFFER, sizeof(bgVertices), bgVertices, GL_STATIC_DRAW);
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 4 * sizeof(float), (void*)0);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 4 * sizeof(float), (void*)(2 * sizeof(float)));
    glEnableVertexAttribArray(1);
    glBindBuffer(GL_ARRAY_BUFFER, 0);
    glBindVertexArray(0);

    backgroundColors_ = {
        0.15f, 0.15f, 0.18f,
        0.25f, 0.22f, 0.20f,
        0.20f, 0.25f, 0.22f,
        0.18f, 0.20f, 0.28f,
        0.30f, 0.28f, 0.25f,
        0.12f, 0.14f, 0.18f,
        0.35f, 0.32f, 0.28f,
        0.22f, 0.24f, 0.30f,
    };

    backgroundInitialized_ = true;
    printf("[Background] Renderer initialized with %zu preset colors\n", backgroundColors_.size() / 3);
    fflush(stdout);
}

void RenderManager::cleanupBackgroundRenderer() {
    for (auto tex : backgroundTextures_) {
        if (tex) glDeleteTextures(1, &tex);
    }
    backgroundTextures_.clear();
    if (backgroundVAO_) { glDeleteVertexArrays(1, &backgroundVAO_); backgroundVAO_ = 0; }
    if (backgroundVBO_) { glDeleteBuffers(1, &backgroundVBO_); backgroundVBO_ = 0; }
    if (backgroundShaderProgram_) { glDeleteProgram(backgroundShaderProgram_); backgroundShaderProgram_ = 0; }
    backgroundInitialized_ = false;
}

void RenderManager::loadBackgroundImages(const std::vector<std::string>& paths) {
    for (auto tex : backgroundTextures_) {
        if (tex) glDeleteTextures(1, &tex);
    }
    backgroundTextures_.clear();

    for (const auto& path : paths) {
        int w, h, channels;
        unsigned char* data = stbi_load(path.c_str(), &w, &h, &channels, 3);
        if (!data) {
            printf("[Background] Failed to load: %s\n", path.c_str());
            fflush(stdout);
            continue;
        }

        GLuint texId;
        glGenTextures(1, &texId);
        glBindTexture(GL_TEXTURE_2D, texId);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, w, h, 0, GL_RGB, GL_UNSIGNED_BYTE, data);
        glBindTexture(GL_TEXTURE_2D, 0);

        stbi_image_free(data);
        backgroundTextures_.push_back(texId);

        printf("[Background] Loaded: %s (%dx%d)\n", path.c_str(), w, h);
        fflush(stdout);
    }

    printf("[Background] Total textures loaded: %zu\n", backgroundTextures_.size());
    fflush(stdout);
}

void RenderManager::renderBackground(int backgroundIndex) {
    if (!backgroundInitialized_) initBackgroundRenderer();

    glDepthFunc(GL_ALWAYS);
    glDisable(GL_DEPTH_TEST);

    glUseProgram(backgroundShaderProgram_);

    GLint useTexLoc = glGetUniformLocation(backgroundShaderProgram_, "useTexture");
    GLint bgColorLoc = glGetUniformLocation(backgroundShaderProgram_, "bgTexture");

    if (backgroundIndex >= 0 && backgroundIndex < (int)backgroundTextures_.size()) {
        glUniform1i(useTexLoc, 1);
        glActiveTexture(GL_TEXTURE0);
        glBindTexture(GL_TEXTURE_2D, backgroundTextures_[backgroundIndex]);
        glUniform1i(bgColorLoc, 0);
    } else {
        glUniform1i(useTexLoc, 0);
        int colorIdx = backgroundIndex - (int)backgroundTextures_.size();
        if (colorIdx < 0) colorIdx = 0;
        if (backgroundColors_.size() >= 3) {
            colorIdx = colorIdx % ((int)backgroundColors_.size() / 3);
            float r = backgroundColors_[colorIdx * 3 + 0];
            float g = backgroundColors_[colorIdx * 3 + 1];
            float b = backgroundColors_[colorIdx * 3 + 2];
            GLint bgColLoc = glGetUniformLocation(backgroundShaderProgram_, "bgColor");
            glUniform3f(bgColLoc, r, g, b);
        }
    }

    glBindVertexArray(backgroundVAO_);
    glDrawArrays(GL_TRIANGLES, 0, 6);
    glBindVertexArray(0);

    glUseProgram(0);
    glEnable(GL_DEPTH_TEST);
    glDepthFunc(GL_LESS);
}

int RenderManager::selectRandomBackground() {
    int totalOptions = (int)backgroundTextures_.size() + (int)(backgroundColors_.size() / 3);
    if (totalOptions == 0) return -1;
    static std::mt19937 bgRng(std::random_device{}());
    std::uniform_int_distribution<int> dist(0, totalOptions - 1);
    return dist(bgRng);
}

} // namespace render
} // namespace hhb