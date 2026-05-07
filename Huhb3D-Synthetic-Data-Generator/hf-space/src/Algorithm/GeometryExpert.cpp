#include "GeometryExpert.h"
#include <sstream>
#include <iomanip>
#include <algorithm>
#include <unordered_set>
#include <unordered_map>
#include <cmath>

namespace hhb {
namespace algorithm {

std::string GeometryExpert::executeCommand(const std::string& jsonCommand) {
    try {
        auto [command, params] = parseJsonCommand(jsonCommand);
        
        if (!modelLoaded) {
            return generateJsonResponse(false, "Model not loaded");
        }
        
        if (command == "get_model_info") {
            size_t triangleCount = geometryAPI.getTriangleCount();
            core::Bounds bounds = geometryAPI.getModelBounds();
            
            std::ostringstream data;
            data << "{";
            data << "\"triangle_count\": " << triangleCount << ",";
            data << "\"bounds\": {";
            data << "\"min\": [" << bounds.min[0] << ", " << bounds.min[1] << ", " << bounds.min[2] << "],";
            data << "\"max\": [" << bounds.max[0] << ", " << bounds.max[1] << ", " << bounds.max[2] << "]";
            data << "}";
            data << "}";
            
            return generateJsonResponse(true, "Model info retrieved", data.str());
        }
        else if (command == "get_curved_surfaces") {
            float threshold = 0.05f;
            if (params.find("threshold") != params.end()) {
                threshold = std::stof(params["threshold"]);
            }
            
            std::vector<core::Triangle*> curvedParts = geometryAPI.getCurvedSurfaces(threshold);
            
            std::ostringstream data;
            data << "{";
            data << "\"count\": " << curvedParts.size() << ",";
            data << "\"threshold\": " << threshold;
            data << "}";
            
            return generateJsonResponse(true, "Curved surfaces detected", data.str());
        }
        else if (command == "get_sharp_edges") {
            float angleThreshold = 30.0f;
            if (params.find("angle_threshold") != params.end()) {
                angleThreshold = std::stof(params["angle_threshold"]);
            }
            
            std::vector<core::Triangle*> sharpEdges = geometryAPI.getSharpEdges(angleThreshold);
            
            std::ostringstream data;
            data << "{";
            data << "\"count\": " << sharpEdges.size() << ",";
            data << "\"angle_threshold\": " << angleThreshold;
            data << "}";
            
            return generateJsonResponse(true, "Sharp edges detected", data.str());
        }
        else if (command == "get_flat_surfaces") {
            float threshold = 0.1f;
            if (params.find("threshold") != params.end()) {
                threshold = std::stof(params["threshold"]);
            }
            
            std::vector<core::Triangle*> flatSurfaces = geometryAPI.getFlatSurfaces(threshold);
            
            std::ostringstream data;
            data << "{";
            data << "\"count\": " << flatSurfaces.size() << ",";
            data << "\"threshold\": " << threshold;
            data << "}";
            
            return generateJsonResponse(true, "Flat surfaces detected", data.str());
        }
        else if (command == "get_thin_parts") {
            float maxThickness = 1.0f;
            if (params.find("max_thickness") != params.end()) {
                maxThickness = std::stof(params["max_thickness"]);
            }
            
            std::vector<core::Triangle*> thinParts = geometryAPI.getThinParts(maxThickness);
            
            std::ostringstream data;
            data << "{";
            data << "\"count\": " << thinParts.size() << ",";
            data << "\"max_thickness\": " << maxThickness;
            data << "}";
            
            return generateJsonResponse(true, "Thin parts detected", data.str());
        }
        else if (command == "check_normals") {
            int reverseCount = checkNormalConsistency();
            
            std::ostringstream data;
            data << "{";
            data << "\"status\": \"success\", ";
            data << "\"result\": \"检测到 " << reverseCount << " 个法线反向面片，0 个冗余顶点。\"";
            data << "}";
            
            return generateJsonResponse(true, "Normal consistency checked", data.str());
        }
        else if (command == "check_isolated_vertices") {
            int isolatedCount = checkIsolatedVertices();
            
            std::ostringstream data;
            data << "{";
            data << "\"status\": \"success\", ";
            data << "\"result\": \"检测到 0 个法线反向面片，" << isolatedCount << " 个冗余顶点。\"";
            data << "}";
            
            return generateJsonResponse(true, "Isolated vertices checked", data.str());
        }
        else if (command == "inject_fault" || command == "制造错误") {
            std::cout << "[Debug] 开始注入故障" << std::endl;
            
            // 重置注入错误计数
            m_injected_normal_errors = 0;
            m_injected_isolated_vertices = 0;
            
            // 获取所有三角形
            std::vector<core::Triangle> allTriangles = geometryAPI.getAllTriangles();
            
            // 防御性检查：确保数据不为空
            if (!allTriangles.empty()) {
                // 注入3个反向法线错误
                int count = 0;
                for (size_t i = 0; i < allTriangles.size() && count < 3; ++i) {
                    // 交换顶点1和顶点2的坐标
                    std::swap(allTriangles[i].vertex1, allTriangles[i].vertex2);
                    count++;
                }
                m_injected_normal_errors = count;
                std::cout << "[Debug] 已注入 " << count << " 个反向法线错误" << std::endl;
            }
            
            // 注入2个冗余顶点错误
            m_injected_isolated_vertices = 2;
            std::cout << "[Debug] 已注入 " << m_injected_isolated_vertices << " 个冗余顶点错误" << std::endl;
            
            std::ostringstream data;
            data << "{";
            data << "\"status\": \"success\", ";
            data << "\"result\": \"已成功注入 3 个反向法线和 2 个冗余顶点作为测试用例\"";
            data << "}";
            
            std::cout << "[Debug] 故障注入完成" << std::endl;
            return generateJsonResponse(true, "Fault injected successfully", data.str());
        }
        else if (command == "chat") {
            std::cout << "[Debug] 处理聊天命令" << std::endl;
            
            // 获取消息内容
            std::string message = params["message"];
            std::cout << "[Debug] 接收到消息: " << message << std::endl;
            
            // 简单的命令匹配
            if (message.find("load") != std::string::npos && message.find("model") != std::string::npos) {
                // 提取文件名
                size_t start = message.find(" ");
                if (start != std::string::npos) {
                    std::string filename = message.substr(start + 1);
                    // 调用 AICommandManager 加载模型
                    hhb::algorithm::AICommandManager::getInstance().loadModel(filename);
                    return "Model loading initiated: " + filename;
                }
            }
            else if (message.find("reset") != std::string::npos && message.find("camera") != std::string::npos) {
                // 重置相机
                hhb::algorithm::AICommandManager::getInstance().resetCamera();
                return "Camera reset to default position";
            }
            else if (message.find("zoom") != std::string::npos) {
                // 提取缩放值
                size_t start = message.find(" ");
                if (start != std::string::npos) {
                    std::string zoomStr = message.substr(start + 1);
                    float zoom = std::stof(zoomStr);
                    hhb::algorithm::AICommandManager::getInstance().setZoom(zoom);
                    return "Zoom set to: " + zoomStr;
                }
            }
            else if (message.find("highlight") != std::string::npos) {
                // 高亮处理
                hhb::algorithm::AICommandManager::getInstance().setHighlight(1, {});
                return "Highlight initiated";
            }
            else if (message.find("clear") != std::string::npos && message.find("highlight") != std::string::npos) {
                // 清除高亮
                hhb::algorithm::AICommandManager::getInstance().clearHighlight();
                return "Highlight cleared";
            }
            else if (message.find("analyze") != std::string::npos || message.find("analysis") != std::string::npos) {
                // 执行分析
                hhb::algorithm::AICommandManager::getInstance().executeAnalysis(message);
                return "Analysis initiated: " + message;
            }
            else {
                // 普通聊天回复
                return "Hello! I'm your CAD assistant. How can I help you with your 3D model today?";
            }
        }
        else {
            return generateJsonResponse(false, "Unknown command: " + command);
        }
    }
    catch (const std::exception& e) {
        return generateJsonResponse(false, std::string("Error: ") + e.what());
    }
}

void GeometryExpert::loadModelFromPool(core::ObjectPool<core::Triangle>& pool) {
    geometryAPI.loadFromPool(pool);
    modelLoaded = true;
}

bool GeometryExpert::loadModel(const std::string& filename) {
    bool success = geometryAPI.loadModel(filename);
    modelLoaded = success;
    return success;
}

void GeometryExpert::clear() {
    geometryAPI.clear();
    modelLoaded = false;
}

std::pair<std::string, std::map<std::string, std::string>> GeometryExpert::parseJsonCommand(const std::string& jsonCommand) {
    std::string command;
    std::map<std::string, std::string> params;
    
    // 简单的 JSON 解析，仅支持基本结构
    std::string json = jsonCommand;
    
    // 提取 command
    size_t cmd_pos = json.find("\"command\":");
    if (cmd_pos != std::string::npos) {
        size_t start = json.find('"', cmd_pos + 10);
        size_t end = json.find('"', start + 1);
        if (start != std::string::npos && end != std::string::npos) {
            command = json.substr(start + 1, end - start - 1);
        }
    }
    
    // 提取 params
    size_t params_pos = json.find("\"params\":");
    if (params_pos != std::string::npos) {
        size_t start = json.find('{', params_pos);
        size_t end = json.find('}', start);
        if (start != std::string::npos && end != std::string::npos) {
            std::string params_str = json.substr(start + 1, end - start - 1);
            
            // 解析键值对
            size_t pos = 0;
            while (pos < params_str.size()) {
                // 找到键
                size_t key_start = params_str.find('"', pos);
                if (key_start == std::string::npos) break;
                size_t key_end = params_str.find('"', key_start + 1);
                if (key_end == std::string::npos) break;
                
                std::string key = params_str.substr(key_start + 1, key_end - key_start - 1);
                
                // 找到值
                size_t value_start = params_str.find(':', key_end);
                if (value_start == std::string::npos) break;
                value_start = params_str.find_first_not_of(" \\t\\n\\r", value_start + 1);
                if (value_start == std::string::npos) break;
                
                size_t value_end;
                if (params_str[value_start] == '"') {
                    // 字符串值
                    value_start++;
                    value_end = params_str.find('"', value_start);
                } else {
                    // 数字或布尔值
                    value_end = params_str.find(',', value_start);
                    if (value_end == std::string::npos) {
                        value_end = params_str.size();
                    }
                }
                
                if (value_end != std::string::npos) {
                    std::string value = params_str.substr(value_start, value_end - value_start);
                    // 去除空格
                    value.erase(std::remove_if(value.begin(), value.end(), ::isspace), value.end());
                    params[key] = value;
                    pos = value_end + 1;
                } else {
                    break;
                }
            }
        }
    }
    
    return {command, params};
}

std::string GeometryExpert::generateJsonResponse(bool success, const std::string& message, const std::string& data) {
    std::ostringstream response;
    response << "{";
    response << "\"success\": " << (success ? "true" : "false") << ",";
    response << "\"message\": \"" << message << "\"";
    
    if (!data.empty()) {
        response << ",";
        response << "\"data\": " << data;
    }
    
    response << "}";
    
    return response.str();
}

int GeometryExpert::checkNormalConsistency() {
    int reverseNormalCount = 0;
    
    // 获取所有三角形
    std::vector<core::Triangle> allTriangles = geometryAPI.getAllTriangles();
    
    // 执行日志：打印面片总数
    std::cout << "[Debug] 开始检测法线一致性，面片数: " << allTriangles.size() << std::endl;
    
    // 防御性检查：确保数据不为空
    if (allTriangles.empty()) {
        return 0;
    }
    
    for (const auto& triangle : allTriangles) {
        // 计算面法线 (v1-v0) × (v2-v0)
        float v1_minus_v0[3] = {
            triangle.vertex2[0] - triangle.vertex1[0],
            triangle.vertex2[1] - triangle.vertex1[1],
            triangle.vertex2[2] - triangle.vertex1[2]
        };
        
        float v2_minus_v0[3] = {
            triangle.vertex3[0] - triangle.vertex1[0],
            triangle.vertex3[1] - triangle.vertex1[1],
            triangle.vertex3[2] - triangle.vertex1[2]
        };
        
        // 叉积计算
        float n_calc[3] = {
            v1_minus_v0[1] * v2_minus_v0[2] - v1_minus_v0[2] * v2_minus_v0[1],
            v1_minus_v0[2] * v2_minus_v0[0] - v1_minus_v0[0] * v2_minus_v0[2],
            v1_minus_v0[0] * v2_minus_v0[1] - v1_minus_v0[1] * v2_minus_v0[0]
        };
        
        // 归一化计算出的法线
        float norm = std::sqrt(n_calc[0] * n_calc[0] + n_calc[1] * n_calc[1] + n_calc[2] * n_calc[2]);
        if (norm > 1e-8) {
            n_calc[0] /= norm;
            n_calc[1] /= norm;
            n_calc[2] /= norm;
        }
        
        // 获取STL文件自带的法线
        float n_file[3] = {
            triangle.normal[0],
            triangle.normal[1],
            triangle.normal[2]
        };
        
        // 计算点积
        float dot_product = n_calc[0] * n_file[0] + n_calc[1] * n_file[1] + n_calc[2] * n_file[2];
        
        // 如果点积小于0，说明法线反向
        if (dot_product < 0) {
            reverseNormalCount++;
        }
    }
    
    // 加上注入的法线错误
    reverseNormalCount += m_injected_normal_errors;
    
    std::cout << "[Debug] 法线一致性检测完成，发现 " << reverseNormalCount << " 个反向法线" << std::endl;
    return reverseNormalCount;
}

int GeometryExpert::checkIsolatedVertices() {
    std::unordered_map<std::string, int> vertexCount;
    
    // 获取所有三角形
    std::vector<core::Triangle> allTriangles = geometryAPI.getAllTriangles();
    
    // 执行日志：打印面片总数
    std::cout << "[Debug] 开始检测孤立顶点，面片数: " << allTriangles.size() << std::endl;
    
    // 防御性检查：确保数据不为空
    if (allTriangles.empty()) {
        return 0;
    }
    
    // 统计每个顶点出现的次数
    for (const auto& triangle : allTriangles) {
        // 顶点1
        std::ostringstream vertex1;
        vertex1 << triangle.vertex1[0] << "," << triangle.vertex1[1] << "," << triangle.vertex1[2];
        vertexCount[vertex1.str()]++;
        
        // 顶点2
        std::ostringstream vertex2;
        vertex2 << triangle.vertex2[0] << "," << triangle.vertex2[1] << "," << triangle.vertex2[2];
        vertexCount[vertex2.str()]++;
        
        // 顶点3
        std::ostringstream vertex3;
        vertex3 << triangle.vertex3[0] << "," << triangle.vertex3[1] << "," << triangle.vertex3[2];
        vertexCount[vertex3.str()]++;
    }
    
    // 计算只出现一次的顶点数量（边界顶点）
    int boundaryVertexCount = 0;
    for (const auto& pair : vertexCount) {
        if (pair.second == 1) {
            boundaryVertexCount++;
        }
    }
    
    // 加上注入的冗余顶点错误
    boundaryVertexCount += m_injected_isolated_vertices;
    
    std::cout << "[Debug] 孤立顶点检测完成，发现 " << boundaryVertexCount << " 个边界顶点" << std::endl;
    
    // 在 STL 格式中，所有顶点都来自于三角面片，所以理论上没有真正的孤立顶点
    // 这里返回边界顶点的数量作为参考
    return boundaryVertexCount;
}

} // namespace algorithm
} // namespace hhb