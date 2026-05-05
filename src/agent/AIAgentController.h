#pragma once

#include <string>
#include <vector>
#include <map>
#include "llm_client.h"
#include "../skill/SkillRegistry.h"
#include "DocumentRetriever.h"
#include "../render/render_manager.h"

namespace hhb {
namespace agent {

class AIAgentController {
public:
    AIAgentController(render::RenderManager& renderManager);
    ~AIAgentController();

    // 设置 LLM API 密钥
    void setApiKey(const std::string& api_key);

    // 设置 LLM API 端点
    void setEndpoint(const std::string& endpoint);

    // 处理用户输入的自然语言指令
    bool processUserCommand(const std::string& command, const std::string& spatialInfo = "");

    // 设置模型元数据（用于 RAG）
    void setModelMetadata(const std::string& modelName, size_t triangleCount, const std::string& filePath);

    // 获取最后一次错误信息
    std::string getLastError() const;

private:
    // 构建系统提示词
    std::string buildSystemPrompt() const;

    // 构建用户提示词
    std::string buildUserPrompt(const std::string& command) const;

    // 解析 LLM 返回的 JSON
    bool parseLLMResponse(const std::string& response);

    // 执行技能序列
    bool executeSkills(const std::vector<std::map<std::string, std::string>>& skills);

    // 构建模型元数据字符串
    std::string buildModelMetadata() const;

    core::LLMClient llmClient;
    rag::DocumentRetriever documentRetriever;
    std::string lastError;

    // 模型元数据
    std::string currentModelName_;
    size_t currentTriangleCount_;
    std::string currentFilePath_;
    
    // 渲染管理器（用于视觉验证）
    render::RenderManager& renderManager;
};

} // namespace agent
} // namespace hhb