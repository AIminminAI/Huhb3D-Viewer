#include <cstdint>
#include <iostream>
#include <cmath>
#include <vector>
#include <string>
#include <unordered_map>

#include <glad/glad.h>
#define GLFW_INCLUDE_NONE
#include <GLFW/glfw3.h>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
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
#include "render_manager.h"

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

RenderManager::RenderManager(int width, int height, const std::string& title)
    : width(width), height(height), title(title), window(nullptr),
      VAO(0), VBO(0), shaderProgram(0), triangleCount(0),
      trianglePool(nullptr),
      zoom(1.0f), frameCount(0), lastFpsUpdate(0.0f), fps(0.0f),
      metallic(0.5f), roughness(0.5f),
      loadTime(0.0f), memoryUsage(0),
      selectedTriangle(nullptr), selectedTriangleIndex(-1), pickTime(0.0f),
      showBVH(false), showHighlight(false),
      currentHighlightType(HighlightType::None),
      highlightCalculated(false) {
    // 启动命令分发器
    commandDispatcher.start(8080);
    // 初始化相机位置
    cameraPosition[0] = 0.0f;
    cameraPosition[1] = 0.0f;
    cameraPosition[2] = 5.0f;
    
    // 初始化相机旋转
    cameraRotation[0] = 0.0f;
    cameraRotation[1] = 0.0f;
    
    // 初始化时间
    lastFrame = std::chrono::steady_clock::now();
    deltaTime = 0.0f;
    
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
    
    // 清理GLFW
    if (window) {
        glfwDestroyWindow(window);
    }
    glfwTerminate();
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
    
    // 初始化缓冲区
    if (!initBuffers()) {
        return false;
    }
    
    // 初始化ImGui
    initImGui();
    
    return true;
}

void RenderManager::render() {
    // 开始ImGui帧
    ImGui_ImplOpenGL3_NewFrame();
    ImGui_ImplGlfw_NewFrame();
    ImGui::NewFrame();
    updateImGui();
    
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
    
    // 开启深度测试与背景清理
    glEnable(GL_DEPTH_TEST);
    glClearColor(0.1f, 0.1f, 0.1f, 1.0f);
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
    
    // 使用着色器程序
    glUseProgram(shaderProgram);
    
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
    
    // 渲染ImGui（必须在最后，这样它才能覆盖在3D场景之上）
    ImGui::Render();
    renderImGui();
    
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
    
    // AI 交互区域
    ImGui::TextColored(ImVec4(0.5f, 1.0f, 0.5f, 1.0f), "AI Assistant");
    ImGui::InputText("User Input", userInputBuffer, sizeof(userInputBuffer));
    if (ImGui::Button("Send", ImVec2(100, 30))) {
        processUserInput();
    }
    ImGui::Checkbox("Show Highlight", &showHighlight);
    if (showHighlight && !highlightIndices.empty()) {
        const char* typeStr = "Unknown";
        switch (currentHighlightType) {
            case HighlightType::ThinParts: typeStr = "薄弱部位"; break;
            case HighlightType::CurvedSurfaces: typeStr = "曲面/曲线"; break;
            case HighlightType::SharpEdges: typeStr = "锐角/棱边"; break;
            case HighlightType::FlatSurfaces: typeStr = "平面区域"; break;
            default: break;
        }
        ImGui::Text("Analysis: %s", typeStr);
        ImGui::Text("Highlighted parts: %zu", highlightIndices.size());
    }
    
    if (selectedTriangleIndex < 0) {
        ImGui::TextDisabled("No triangle selected");
        ImGui::TextDisabled("Click on the model to pick");
    }
    
    // 显示 AI 结果弹出窗口
    if (ImGui::BeginPopup("AI Result")) {
        ImGui::Text("Analysis Result");
        ImGui::Separator();
        ImGui::Text("Command executed successfully!");
        ImGui::Text("Check console for detailed output.");
        if (ImGui::Button("OK")) {
            ImGui::CloseCurrentPopup();
        }
        ImGui::EndPopup();
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
    
    // 设置控制台输出编码为 UTF-8，确保中文能正确显示
    SetConsoleOutputCP(CP_UTF8);
    
    std::cout << "Processing user input: " << userInput << std::endl;
    
    // 鲁棒性检查：确保模型已加载
    if (!trianglePool || trianglePool->size() == 0) {
        std::cout << "No model loaded, cannot execute geometry algorithms" << std::endl;
        ImGui::OpenPopup("AI Result");
        return;
    }
    
    // 语义匹配逻辑
    if (userInput.find("法线") != std::string::npos || userInput.find("方向") != std::string::npos || userInput.find("normal") != std::string::npos) {
        std::cout << "Detected normal check command" << std::endl;
        
        // 调用 GeometryExpert 执行 check_normals
        std::string response = geometryExpert.executeCommand(R"({"command": "check_normals"})");
        std::cout << "GeometryExpert response: " << response << std::endl;
        
        // 显示结果
        ImGui::OpenPopup("AI Result");
    }
    else if (userInput.find("顶点") != std::string::npos || userInput.find("冗余") != std::string::npos || userInput.find("vertex") != std::string::npos) {
        std::cout << "Detected isolated vertices check command" << std::endl;
        
        // 调用 GeometryExpert 执行 check_isolated_vertices
        std::string response = geometryExpert.executeCommand(R"({"command": "check_isolated_vertices"})");
        std::cout << "GeometryExpert response: " << response << std::endl;
        
        // 显示结果
        ImGui::OpenPopup("AI Result");
    }
    else if (userInput.find("信息") != std::string::npos || userInput.find("大小") != std::string::npos || userInput.find("info") != std::string::npos) {
        std::cout << "Detected model info command" << std::endl;
        
        // 调用 GeometryExpert 执行 get_model_info
        std::string response = geometryExpert.executeCommand(R"({"command": "get_model_info"})");
        std::cout << "GeometryExpert response: " << response << std::endl;
        
        // 显示结果
        ImGui::OpenPopup("AI Result");
    }
    else if (userInput.find("制造错误") != std::string::npos || userInput.find("inject") != std::string::npos) {
        std::cout << "Detected fault injection command" << std::endl;
        
        // 调用 GeometryExpert 执行 inject_fault
        std::string response = geometryExpert.executeCommand(R"({"command": "inject_fault"})");
        std::cout << "GeometryExpert response: " << response << std::endl;
        
        // 显示结果
        ImGui::OpenPopup("AI Result");
    }
    else {
        // 原有的 LLM 逻辑
        std::string response = llmClient.sendToolCallRequest(userInput);
        
        if (!response.empty()) {
            std::cout << "LLM response received" << std::endl;
            
            std::vector<hhb::core::LLMClient::ToolCall> tool_calls = llmClient.parseToolCalls(response);
            
            if (!tool_calls.empty()) {
                std::cout << "Tool calls found: " << tool_calls.size() << std::endl;
                
                for (const auto& tool_call : tool_calls) {
                    std::cout << "Tool name: " << tool_call.name << std::endl;
                    
                    if (tool_call.name == "analyze_model_thickness") {
                        float threshold_mm = 1.0f;
                        auto it = tool_call.parameters.find("threshold_mm");
                        if (it != tool_call.parameters.end()) {
                            try {
                                threshold_mm = std::stof(it->second);
                            } catch (const std::exception& e) {
                                std::cerr << "Failed to parse threshold_mm: " << e.what() << std::endl;
                            }
                        }
                        
                        std::cout << "Analyzing model thickness with threshold: " << threshold_mm << "mm" << std::endl;
                        
                        if (trianglePool) {
                            highlightIndices.clear();
                            
                            std::vector<hhb::core::Triangle*> thin_parts = geometryAPI.getThinParts(threshold_mm);
                            
                            std::cout << "Found " << thin_parts.size() << " thin parts" << std::endl;
                            
                            for (const auto& thin_tri : thin_parts) {
                                for (size_t i = 0; i < triangleCount; ++i) {
                                    if (&(*trianglePool)[i] == thin_tri) {
                                        highlightIndices.push_back(static_cast<int>(i));
                                        break;
                                    }
                                }
                            }
                            
                            currentHighlightType = HighlightType::ThinParts;
                            showHighlight = true;
                            lastAnalysisDesc = "薄弱部位 (厚度<" + std::to_string(static_cast<int>(threshold_mm)) + "mm)";
                        }
                    }
                }
            } else {
                std::cout << "No tool calls found in response." << std::endl;
            }
        } else {
            std::cerr << "Error: " << llmClient.getLastError() << std::endl;
        }
    }
}

void RenderManager::highlightParts() {
    if (!showHighlight || highlightIndices.empty()) {
        return;
    }
    
    GLint isSelectedLoc = glGetUniformLocation(shaderProgram, "isSelected");
    GLint highlightColorLoc = glGetUniformLocation(shaderProgram, "highlightColor");
    
    float color[3] = {1.0f, 0.0f, 0.0f};
    switch (currentHighlightType) {
        case HighlightType::ThinParts:
            color[0] = 1.0f; color[1] = 0.0f; color[2] = 0.0f; break;
        case HighlightType::CurvedSurfaces:
            color[0] = 0.0f; color[1] = 1.0f; color[2] = 0.5f; break;
        case HighlightType::SharpEdges:
            color[0] = 1.0f; color[1] = 0.5f; color[2] = 0.0f; break;
        case HighlightType::FlatSurfaces:
            color[0] = 0.0f; color[1] = 0.5f; color[2] = 1.0f; break;
        default: break;
    }
    
    if (isSelectedLoc != -1 && highlightColorLoc != -1) {
        glUniform1i(isSelectedLoc, GL_TRUE);
        glUniform3fv(highlightColorLoc, 1, color);
        
        for (int index : highlightIndices) {
            glDrawArrays(GL_TRIANGLES, index * 3, 3);
        }
    }
}

void RenderManager::shutdownImGui() {
    // 清理ImGui资源
    ImGui_ImplOpenGL3_Shutdown();
    ImGui_ImplGlfw_Shutdown();
    ImGui::DestroyContext();
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

} // namespace render
} // namespace hhb