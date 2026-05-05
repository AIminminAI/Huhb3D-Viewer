#include "AIAgentController.h"
#include <iostream>
#include <sstream>
#include <algorithm>
#include <string>
#include "../skill/SkillRegistry.h"

namespace hhb {
namespace agent {

AIAgentController::AIAgentController(render::RenderManager& renderManager)
    : currentTriangleCount_(0), renderManager(renderManager) {
    // 设置默认的 API 端点
    llmClient.setEndpoint("https://api.openai.com/v1/chat/completions");
    // 初始化文档检索器
    documentRetriever.initialize();
}

AIAgentController::~AIAgentController() {
}

void AIAgentController::setApiKey(const std::string& api_key) {
    llmClient.setApiKey(api_key);
}

void AIAgentController::setEndpoint(const std::string& endpoint) {
    llmClient.setEndpoint(endpoint);
}

void AIAgentController::setModelMetadata(const std::string& modelName, size_t triangleCount, const std::string& filePath) {
    currentModelName_ = modelName;
    currentTriangleCount_ = triangleCount;
    currentFilePath_ = filePath;
}

std::string AIAgentController::buildModelMetadata() const {
    if (currentModelName_.empty()) {
        return "";
    }

    std::stringstream ss;
    ss << "\n\n[当前加载模型的信息]\n";
    ss << "模型名称: " << currentModelName_ << "\n";
    ss << "三角面片数: " << currentTriangleCount_ << "\n";
    ss << "文件路径: " << currentFilePath_ << "\n";
    return ss.str();
}

std::string AIAgentController::buildSystemPrompt() const {
    return R"(
你是一位专业的 3D 建模专家，擅长将用户的自然语言指令转换为具体的 3D 模型操作。

你将接收到以下空间信息作为上下文：
- 模型的几何中心
- 模型的包围盒信息（最小和最大坐标）
- 当前摄像头的位置和旋转角度
- 当前的缩放级别

请根据这些空间信息，结合用户的自然语言指令，生成合适的技能序列。

请将用户的自然语言指令解析为一个 JSON 格式的技能序列，每个技能包含以下字段：
- "skill": 技能名称（如 "auto_rotate", "reset_camera", "zoom_in", "rotate", "optimize_view"）
- "params": 技能参数（可选，根据技能需要）

技能说明：
- "auto_rotate": 切换模型的自动旋转状态
- "reset_camera": 重置相机视角到模型中心
- "zoom_in": 放大模型
- "zoom_out": 缩小模型
- "rotate": 旋转模型
- "optimize_view": 自动寻优视角，根据目标位置调整相机
  - 参数："target"，可选值包括 "front", "back", "top", "bottom", "left", "right"
- "measure_model": 测量模型的几何属性
  - 返回：模型的宽度、高度、深度、表面积和体积
  - 当用户询问尺寸相关问题时使用，如"这个模型有多大"、"能放进去吗"等
- "analyze_geometry": 分析模型几何质量
  - 检测：孤立三角形、退化三角形、锐角边、重复顶点等异常
  - 当用户要求"检查模型"或"分析质量"时使用

示例：
用户输入："我看不到模型的底部"
输出：
{
  "skills": [
    { "skill": "optimize_view", "params": { "target": "bottom" } }
  ]
}

用户输入："帮我把模型放大 2 倍并转到背面"
输出：
{
  "skills": [
    { "skill": "zoom_in", "params": { "factor": "2" } },
    { "skill": "rotate", "params": { "angle": "180" } }
  ]
}

用户输入："这个模型放得进一个 10x10x10 的盒子吗？"
输出：
{
  "skills": [
    { "skill": "measure_model" }
  ]
}

请严格按照 JSON 格式输出，不要包含任何其他内容。
)";
}

std::string AIAgentController::buildUserPrompt(const std::string& command) const {
    return "用户指令：" + command;
}

bool AIAgentController::processUserCommand(const std::string& command, const std::string& spatialInfo) {
    try {
        // 构建完整的提示词
        std::string systemPrompt = buildSystemPrompt();
        std::string userPrompt = buildUserPrompt(command);

        // 如果提供了空间信息，将其添加到用户提示词中
        if (!spatialInfo.empty()) {
            userPrompt += "\n\n空间信息：\n" + spatialInfo;
        }

        // 如果当前有加载的模型，添加模型元数据
        std::string modelMetadata = buildModelMetadata();
        if (!modelMetadata.empty()) {
            userPrompt += modelMetadata;
        }

        // 检查是否需要检索文档（RAG）
        if (documentRetriever.needsDocumentRetrieval(command)) {
            std::string retrievedDocs = documentRetriever.retrieve(command, 3);
            if (!retrievedDocs.empty()) {
                userPrompt += "\n\n请结合以下检索到的文档内容来回答用户的问题：";
                userPrompt += retrievedDocs;
            }
        }

        std::vector<std::map<std::string, std::string>> messages;
        std::map<std::string, std::string> sysMsg;
        sysMsg["role"] = "system";
        sysMsg["content"] = systemPrompt;
        messages.push_back(sysMsg);

        std::map<std::string, std::string> userMsg;
        userMsg["role"] = "user";
        userMsg["content"] = userPrompt;
        messages.push_back(userMsg);

        std::string response = llmClient.sendChat(messages);

        // 解析 LLM 响应
        return parseLLMResponse(response);
    } catch (const std::exception& e) {
        lastError = "处理用户命令时出错：" + std::string(e.what());
        return false;
    }
}

bool AIAgentController::parseLLMResponse(const std::string& response) {
    try {
        // 简单的字符串解析，提取技能序列
        // 查找 skills 数组
        size_t skills_pos = response.find("\"skills\":");
        if (skills_pos == std::string::npos) {
            lastError = "LLM 响应格式错误，缺少 skills 字段";
            return false;
        }
        
        size_t start_pos = response.find('[', skills_pos);
        if (start_pos == std::string::npos) {
            lastError = "LLM 响应格式错误，缺少 skills 数组开始标记";
            return false;
        }
        
        size_t end_pos = response.find(']', start_pos);
        if (end_pos == std::string::npos) {
            lastError = "LLM 响应格式错误，缺少 skills 数组结束标记";
            return false;
        }
        
        std::string skills_str = response.substr(start_pos, end_pos - start_pos + 1);
        
        // 提取技能列表
        std::vector<std::map<std::string, std::string>> skills;
        size_t skill_start = skills_str.find('{');
        while (skill_start != std::string::npos) {
            size_t skill_end = skills_str.find('}', skill_start);
            if (skill_end == std::string::npos) {
                lastError = "LLM 响应格式错误，缺少技能对象结束标记";
                return false;
            }
            
            std::string skill_str = skills_str.substr(skill_start, skill_end - skill_start + 1);
            
            // 提取技能名称
            size_t skill_name_pos = skill_str.find("\"skill\":");
            if (skill_name_pos == std::string::npos) {
                lastError = "LLM 响应格式错误，缺少 skill 字段";
                return false;
            }
            
            size_t name_start = skill_str.find('"', skill_name_pos + 8);
            if (name_start == std::string::npos) {
                lastError = "LLM 响应格式错误，缺少 skill 名称开始标记";
                return false;
            }
            
            size_t name_end = skill_str.find('"', name_start + 1);
            if (name_end == std::string::npos) {
                lastError = "LLM 响应格式错误，缺少 skill 名称结束标记";
                return false;
            }
            
            std::string skill_name = skill_str.substr(name_start + 1, name_end - name_start - 1);
            
            // 提取参数
            std::map<std::string, std::string> skill;
            skill["skill"] = skill_name;
            
            size_t params_pos = skill_str.find("\"params\":");
            if (params_pos != std::string::npos) {
                size_t params_start = skill_str.find('{', params_pos);
                if (params_start != std::string::npos) {
                    size_t params_end = skill_str.find('}', params_start);
                    if (params_end != std::string::npos) {
                        std::string params_str = skill_str.substr(params_start + 1, params_end - params_start - 1);
                        
                        // 提取参数键值对
                        size_t param_start = 0;
                        while (param_start < params_str.length()) {
                            // 跳过空白字符
                            param_start = params_str.find_first_not_of(" \t\n\r", param_start);
                            if (param_start == std::string::npos) {
                                break;
                            }
                            
                            // 提取参数名
                            size_t param_name_start = params_str.find('"', param_start);
                            if (param_name_start == std::string::npos) {
                                break;
                            }
                            
                            size_t param_name_end = params_str.find('"', param_name_start + 1);
                            if (param_name_end == std::string::npos) {
                                break;
                            }
                            
                            std::string param_name = params_str.substr(param_name_start + 1, param_name_end - param_name_start - 1);
                            
                            // 提取参数值
                            size_t param_value_start = params_str.find('"', param_name_end + 1);
                            if (param_value_start == std::string::npos) {
                                break;
                            }
                            
                            size_t param_value_end = params_str.find('"', param_value_start + 1);
                            if (param_value_end == std::string::npos) {
                                break;
                            }
                            
                            std::string param_value = params_str.substr(param_value_start + 1, param_value_end - param_value_start - 1);
                            
                            skill[param_name] = param_value;
                            
                            param_start = param_value_end + 1;
                        }
                    }
                }
            }
            
            skills.push_back(skill);
            
            // 查找下一个技能
            skill_start = skills_str.find('{', skill_end + 1);
        }
        
        // 执行技能序列
        return executeSkills(skills);
    } catch (const std::exception& e) {
        lastError = "解析 LLM 响应时出错：" + std::string(e.what());
        return false;
    }
}

bool AIAgentController::executeSkills(const std::vector<std::map<std::string, std::string>>& skills) {
    try {
        auto& registry = skill::SkillRegistry::getInstance();
        
        for (const auto& skill : skills) {
            if (skill.find("skill") == skill.end()) {
                lastError = "技能缺少 skill 字段";
                return false;
            }
            
            std::string skillName = skill.at("skill");
            std::string params = "";
            
            // 构建参数字符串
            if (skill.size() > 1) {
                std::stringstream paramsStream;
                paramsStream << "{";
                for (const auto& param : skill) {
                    if (param.first != "skill") {
                        paramsStream << "\"" << param.first << "\": \"" << param.second << "\",";
                    }
                }
                std::string paramsStr = paramsStream.str();
                if (!paramsStr.empty() && paramsStr.back() == ',') {
                    paramsStr.pop_back();
                }
                paramsStr += "}";
                params = paramsStr;
            }
            
            // 记录执行前的状态（用于视觉验证）
            auto preState = renderManager.getSpatialInfo();
            
            // 执行技能
            std::string executionResult = registry.executeSkill(skillName, params);
            
            // 记录执行后的状态
            auto postState = renderManager.getSpatialInfo();
            
            // 输出执行反馈
            std::cout << "\n=== 技能执行反馈 ===" << std::endl;
            std::cout << "技能: " << skillName << std::endl;
            std::cout << "参数: " << params << std::endl;
            std::cout << "执行结果: " << executionResult << std::endl;
            
            // 视觉验证：对比执行前后的状态
            std::cout << "\n=== 视觉验证 ===" << std::endl;
            std::cout << "执行前 - 相机位置: (" << preState.cameraPos[0] << ", " << preState.cameraPos[1] << ", " << preState.cameraPos[2] << ")" << std::endl;
            std::cout << "执行后 - 相机位置: (" << postState.cameraPos[0] << ", " << postState.cameraPos[1] << ", " << postState.cameraPos[2] << ")" << std::endl;
            
            // 自我纠错逻辑
            if (skillName == "optimize_view") {
                // 分析用户意图
                std::string target = "front";
                if (!params.empty()) {
                    if (params.find("back") != std::string::npos) target = "back";
                    else if (params.find("left") != std::string::npos) target = "left";
                    else if (params.find("right") != std::string::npos) target = "right";
                    else if (params.find("top") != std::string::npos) target = "top";
                    else if (params.find("bottom") != std::string::npos) target = "bottom";
                }
                
                // 检查相机位置是否符合预期
                bool success = true;
                std::string errorReason = "";
                
                float* camPos = postState.cameraPos;
                float* center = postState.center;
                
                if (target == "back") {
                    // 相机应该在模型后方
                    if (camPos[2] < center[2]) {
                        success = false;
                        errorReason = "相机仍在模型前方";
                    }
                } else if (target == "left") {
                    // 相机应该在模型左侧
                    if (camPos[0] > center[0]) {
                        success = false;
                        errorReason = "相机仍在模型右侧";
                    }
                } else if (target == "right") {
                    // 相机应该在模型右侧
                    if (camPos[0] < center[0]) {
                        success = false;
                        errorReason = "相机仍在模型左侧";
                    }
                } else if (target == "top") {
                    // 相机应该在模型上方
                    if (camPos[1] < center[1]) {
                        success = false;
                        errorReason = "相机仍在模型下方";
                    }
                } else if (target == "bottom") {
                    // 相机应该在模型下方
                    if (camPos[1] > center[1]) {
                        success = false;
                        errorReason = "相机仍在模型上方";
                    }
                } else if (target == "front") {
                    // 相机应该在模型前方
                    if (camPos[2] > center[2]) {
                        success = false;
                        errorReason = "相机仍在模型后方";
                    }
                }
                
                if (!success) {
                    std::cout << "\n=== 自我纠错 ===" << std::endl;
                    std::cout << "检测到失败: " << errorReason << std::endl;
                    std::cout << "尝试重试执行..." << std::endl;
                    
                    // 重试执行技能
                    executionResult = registry.executeSkill(skillName, params);
                    std::cout << "重试结果: " << executionResult << std::endl;
                    
                    // 再次验证
                    auto retryState = renderManager.getSpatialInfo();
                    std::cout << "重试后 - 相机位置: (" << retryState.cameraPos[0] << ", " << retryState.cameraPos[1] << ", " << retryState.cameraPos[2] << ")" << std::endl;
                }
            }
        }
        
        return true;
    } catch (const std::exception& e) {
        lastError = "执行技能时出错：" + std::string(e.what());
        return false;
    }
}

std::string AIAgentController::getLastError() const {
    return lastError;
}

} // namespace agent
} // namespace hhb