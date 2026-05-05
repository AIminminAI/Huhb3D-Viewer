#include "embodied_ai_agent.h"
#include <iostream>
#include <chrono>
#include <sstream>
#include <iomanip>

namespace hhb {
namespace core {

EmbodiedAIAgent::EmbodiedAIAgent()
    : llmClient_(LLMClient::getInstance()),
      toolRegistry_(ToolRegistry::getInstance()),
      state_(EmbodiedAIState::Idle),
      processing_(false) {
}

EmbodiedAIAgent::~EmbodiedAIAgent() {
    if (pendingFuture_.valid()) {
        pendingFuture_.wait();
    }
}

void EmbodiedAIAgent::initialize(const std::string& endpoint, const std::string& api_key,
                                  const std::string& model, GeometryAPI* geometry_api) {
    llmClient_.setEndpoint(endpoint);
    llmClient_.setApiKey(api_key);
    llmClient_.setModel(model);
    llmClient_.setTimeout(60000);

    // 初始化工具注册表，将几何分析能力暴露给 LLM
    toolRegistry_.initialize(geometry_api);

    // 清除旧工具并注册所有工具到 LLMClient
    llmClient_.clearTools();
    toolRegistry_.registerAllToLLM(llmClient_);

    std::cout << "[EmbodiedAIAgent] Initialized with endpoint: " << endpoint
              << " model: " << model << std::endl;
    std::cout << "[EmbodiedAIAgent] Registered tools: ";
    for (const auto& name : llmClient_.getRegisteredToolNames()) {
        std::cout << name << " ";
    }
    std::cout << std::endl;
}

void EmbodiedAIAgent::processInputAsync(const std::string& user_input) {
    if (processing_) {
        std::cout << "[EmbodiedAIAgent] Still processing previous request" << std::endl;
        return;
    }

    processing_ = true;
    setState(EmbodiedAIState::Processing);

    // 添加用户消息到历史
    {
        std::lock_guard<std::mutex> lock(historyMutex_);
        auto now = std::chrono::system_clock::now();
        auto time_t = std::chrono::system_clock::to_time_t(now);
        std::stringstream ss;
        ss << std::put_time(std::localtime(&time_t), "%H:%M:%S");
        chatHistory_.push_back({user_input, true, ss.str()});
    }

    // 异步执行具身智能闭环
    pendingFuture_ = std::async(std::launch::async, [this, user_input]() -> std::string {
        std::cout << "[EmbodiedAIAgent] Starting embodied query for: " << user_input << std::endl;

        setState(EmbodiedAIState::Processing);

        // 调用 LLMClient 的 embodiedQuery 方法
        // 该方法实现了完整的闭环：用户输入 -> LLM 解析 -> 工具执行 -> 结果反馈 -> LLM 总结
        std::string response = llmClient_.embodiedQuery(user_input, 3);

        // 检查工具执行结果，更新高亮
        if (toolRegistry_.hasNewResult()) {
            auto indices = toolRegistry_.getHighlightIndices();
            auto type = toolRegistry_.getHighlightType();
            auto desc = toolRegistry_.getLastAnalysisDesc();

            std::cout << "[EmbodiedAIAgent] Tool result: " << indices.size()
                      << " indices, type=" << static_cast<int>(type) << std::endl;

            // 通知渲染层更新高亮
            if (resultCallback_) {
                resultCallback_(indices, type, desc);
            }

            toolRegistry_.clearNewResult();
        }

        return response;
    });
}

std::string EmbodiedAIAgent::processInput(const std::string& user_input) {
    // 添加用户消息到历史
    {
        std::lock_guard<std::mutex> lock(historyMutex_);
        auto now = std::chrono::system_clock::now();
        auto time_t = std::chrono::system_clock::to_time_t(now);
        std::stringstream ss;
        ss << std::put_time(std::localtime(&time_t), "%H:%M:%S");
        chatHistory_.push_back({user_input, true, ss.str()});
    }

    setState(EmbodiedAIState::Processing);

    std::string response = llmClient_.embodiedQuery(user_input, 3);

    // 检查工具执行结果
    if (toolRegistry_.hasNewResult()) {
        auto indices = toolRegistry_.getHighlightIndices();
        auto type = toolRegistry_.getHighlightType();
        auto desc = toolRegistry_.getLastAnalysisDesc();

        if (resultCallback_) {
            resultCallback_(indices, type, desc);
        }

        toolRegistry_.clearNewResult();
    }

    // 添加 AI 回复到历史
    {
        std::lock_guard<std::mutex> lock(historyMutex_);
        auto now = std::chrono::system_clock::now();
        auto time_t = std::chrono::system_clock::to_time_t(now);
        std::stringstream ss;
        ss << std::put_time(std::localtime(&time_t), "%H:%M:%S");
        chatHistory_.push_back({response, false, ss.str()});
    }

    lastResponse_ = response;

    if (response.find("[Error]") != std::string::npos) {
        lastError_ = response;
        setState(EmbodiedAIState::Error);
    } else {
        setState(EmbodiedAIState::Idle);
    }

    return response;
}

EmbodiedAIState EmbodiedAIAgent::getState() const {
    return state_.load();
}

std::string EmbodiedAIAgent::getStateString() const {
    switch (state_.load()) {
        case EmbodiedAIState::Idle: return "Idle";
        case EmbodiedAIState::Processing: return "Processing...";
        case EmbodiedAIState::ToolExecuting: return "Executing Tool...";
        case EmbodiedAIState::Responding: return "Generating Response...";
        case EmbodiedAIState::Error: return "Error";
        default: return "Unknown";
    }
}

std::vector<ChatMessage> EmbodiedAIAgent::getChatHistory() const {
    std::lock_guard<std::mutex> lock(historyMutex_);
    return chatHistory_;
}

std::string EmbodiedAIAgent::getLastResponse() const {
    return lastResponse_;
}

std::string EmbodiedAIAgent::getLastError() const {
    return lastError_;
}

bool EmbodiedAIAgent::isProcessing() const {
    return processing_.load();
}

void EmbodiedAIAgent::clearHistory() {
    std::lock_guard<std::mutex> lock(historyMutex_);
    chatHistory_.clear();
}

void EmbodiedAIAgent::setStateCallback(StateCallback callback) {
    stateCallback_ = callback;
}

void EmbodiedAIAgent::setResultCallback(ResultCallback callback) {
    resultCallback_ = callback;
}

void EmbodiedAIAgent::setState(EmbodiedAIState state) {
    state_.store(state);
    if (stateCallback_) {
        stateCallback_(state);
    }
}

void EmbodiedAIAgent::checkPendingResult() {
    if (!pendingFuture_.valid()) return;

    auto status = pendingFuture_.wait_for(std::chrono::seconds(0));
    if (status == std::future_status::ready) {
        std::string response = pendingFuture_.get();

        // 添加 AI 回复到历史
        {
            std::lock_guard<std::mutex> lock(historyMutex_);
            auto now = std::chrono::system_clock::now();
            auto time_t = std::chrono::system_clock::to_time_t(now);
            std::stringstream ss;
            ss << std::put_time(std::localtime(&time_t), "%H:%M:%S");
            chatHistory_.push_back({response, false, ss.str()});
        }

        lastResponse_ = response;
        processing_ = false;

        if (response.find("[Error]") != std::string::npos) {
            lastError_ = response;
            setState(EmbodiedAIState::Error);
        } else {
            setState(EmbodiedAIState::Idle);
        }
    }
}

} // namespace core
} // namespace hhb
