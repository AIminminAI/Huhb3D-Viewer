#pragma once

#include <string>
#include <vector>
#include <mutex>
#include <future>
#include <functional>
#include <atomic>
#include "llm_client.h"
#include "tool_registry.h"
#include "highlight_types.h"

namespace hhb {
namespace core {

// 具身智能 Agent 状态
enum class EmbodiedAIState {
    Idle,
    Processing,
    ToolExecuting,
    Responding,
    Error
};

// 聊天消息
struct ChatMessage {
    std::string content;
    bool isUser;
    std::string timestamp;
};

// 具身智能 Agent：协调 LLM 推理、工具执行和视觉反馈的闭环
// 工作流程：
// 1. 用户输入自然语言 -> 2. LLM 解析为工具调用 -> 3. C++ 执行几何分析
// -> 4. 结果反馈给 LLM -> 5. LLM 生成自然语言回复 -> 6. OpenGL 高亮显示结果
class EmbodiedAIAgent {
public:
    EmbodiedAIAgent();
    ~EmbodiedAIAgent();

    // 初始化：设置 API 端点和工具
    void initialize(const std::string& endpoint, const std::string& api_key,
                    const std::string& model, GeometryAPI* geometry_api);

    // 处理用户输入（异步）
    void processInputAsync(const std::string& user_input);

    // 处理用户输入（同步）
    std::string processInput(const std::string& user_input);

    // 获取当前状态
    EmbodiedAIState getState() const;
    std::string getStateString() const;

    // 获取聊天历史
    std::vector<ChatMessage> getChatHistory() const;

    // 获取最后的 AI 回复
    std::string getLastResponse() const;

    // 获取最后的错误信息
    std::string getLastError() const;

    // 是否正在处理
    bool isProcessing() const;

    // 清空聊天历史
    void clearHistory();

    // 设置状态回调（用于 UI 更新通知）
    using StateCallback = std::function<void(EmbodiedAIState)>;
    void setStateCallback(StateCallback callback);

    // 设置结果回调（当工具执行完成后通知渲染层更新高亮）
    using ResultCallback = std::function<void(const std::vector<int>&, HighlightType, const std::string&)>;
    void setResultCallback(ResultCallback callback);

private:
    LLMClient& llmClient_;
    ToolRegistry& toolRegistry_;

    std::atomic<EmbodiedAIState> state_;
    std::string lastResponse_;
    std::string lastError_;
    std::vector<ChatMessage> chatHistory_;
    mutable std::mutex historyMutex_;

    std::future<std::string> pendingFuture_;
    std::atomic<bool> processing_;

    StateCallback stateCallback_;
    ResultCallback resultCallback_;

    void setState(EmbodiedAIState state);

public:
    void checkPendingResult();

private:
};

} // namespace core
} // namespace hhb
