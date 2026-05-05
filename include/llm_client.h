#pragma once

#include <string>
#include <map>
#include <memory>
#include <vector>
#include <functional>
#include <mutex>
#include <future>
#include <atomic>

namespace hhb {
namespace core {

// 具身智能工具调用结构体：将 LLM 的语义指令映射为 C++ 可执行的回调
struct ToolCall {
    std::string id;
    std::string name;
    std::string arguments_json;
};

// 工具执行结果：C++ 几何分析的结果，需转回 LLM 可理解的语义
struct ToolResult {
    std::string tool_call_id;
    bool success;
    std::string result_json;
};

// 工具定义：描述一个可供 LLM 调用的 C++ 能力
struct ToolDefinition {
    std::string name;
    std::string description;
    std::string parameters_json_schema;
    std::function<std::string(const std::string& args_json)> execute;
};

class LLMClient {
public:
    static LLMClient& getInstance();

    void setEndpoint(const std::string& endpoint);
    void setApiKey(const std::string& api_key);
    void setModel(const std::string& model);
    void setTimeout(int timeout_ms);

    // 注册具身智能工具：将 3D 拓扑分析能力暴露给 LLM
    void registerTool(const ToolDefinition& tool);
    void clearTools();

    // 同步发送聊天请求（含 Function Calling）
    std::string sendChat(const std::vector<std::map<std::string, std::string>>& messages);

    // 异步发送聊天请求
    std::future<std::string> sendChatAsync(const std::vector<std::map<std::string, std::string>>& messages);

    // 完整的具身智能闭环：用户自然语言 -> LLM 解析 -> 工具执行 -> 结果反馈 -> LLM 总结
    // 这是核心方法，实现了"感知-推理-行动"的闭环
    std::string embodiedQuery(const std::string& user_input, int max_rounds = 3);

    // 异步具身智能闭环
    std::future<std::string> embodiedQueryAsync(const std::string& user_input, int max_rounds = 3);

    std::string getLastError() const;

    // 获取已注册的工具列表（用于 UI 显示）
    std::vector<std::string> getRegisteredToolNames() const;

private:
    LLMClient();
    ~LLMClient();
    LLMClient(const LLMClient&) = delete;
    LLMClient& operator=(const LLMClient&) = delete;

    struct Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace core
} // namespace hhb
