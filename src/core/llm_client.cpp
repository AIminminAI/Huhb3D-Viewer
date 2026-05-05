#ifdef _WIN32
#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#endif

#include "llm_client.h"
#include <httplib.h>
#include <nlohmann/json.hpp>
#include <iostream>
#include <sstream>
#include <thread>

namespace hhb {
namespace core {

struct LLMClient::Impl {
    std::string endpoint;
    std::string api_key;
    std::string model = "gpt-4o-mini";
    int timeout_ms = 60000;
    mutable std::string last_error;
    mutable std::mutex mutex;

    // 具身智能工具注册表：存储 LLM 可调用的 C++ 能力
    std::map<std::string, ToolDefinition> tools;

    std::string buildToolsJson() const {
        nlohmann::json tools_arr = nlohmann::json::array();
        for (const auto& [name, tool] : tools) {
            nlohmann::json tool_obj;
            tool_obj["type"] = "function";
            tool_obj["function"]["name"] = tool.name;
            tool_obj["function"]["description"] = tool.description;

            nlohmann::json params;
            try {
                params = nlohmann::json::parse(tool.parameters_json_schema);
            } catch (...) {
                params = nlohmann::json::parse(R"({"type":"object","properties":{}})");
            }
            tool_obj["function"]["parameters"] = params;
            tools_arr.push_back(tool_obj);
        }
        return tools_arr.dump();
    }

    std::string sendHttpRequest(const std::string& json_body) const {
        last_error.clear();

        try {
            httplib::Client client(endpoint);
            client.set_timeout_sec(timeout_ms / 1000);

            httplib::Headers headers;
            headers["Content-Type"] = "application/json";
            if (!api_key.empty()) {
                headers["Authorization"] = "Bearer " + api_key;
            }

            auto res = client.Post("/v1/chat/completions", headers, json_body, "application/json");

            if (res) {
                if (res->status == 200) {
                    return res->body;
                } else {
                    last_error = "HTTP " + std::to_string(res->status) + ": " + res->body.substr(0, 500);
                    return "";
                }
            } else {
                last_error = client.get_last_error();
                if (last_error.empty()) last_error = "Connection failed";
                return "";
            }
        } catch (const std::exception& e) {
            last_error = std::string("Exception: ") + e.what();
            return "";
        }
    }

    // 解析 LLM 返回的 tool_calls，将语义指令映射为 C++ 可执行结构
    std::vector<ToolCall> parseToolCallsFromResponse(const std::string& response_body) const {
        std::vector<ToolCall> result;
        try {
            nlohmann::json resp = nlohmann::json::parse(response_body);

            if (!resp.contains("choices") || resp["choices"].size() == 0) return result;

            auto& choice = resp["choices"][0];
            if (!choice.contains("message")) return result;
            auto& message = choice["message"];

            if (!message.contains("tool_calls")) return result;
            auto& tool_calls = message["tool_calls"];

            for (size_t i = 0; i < tool_calls.size(); ++i) {
                auto& tc = tool_calls[i];
                ToolCall call;
                call.id = tc.contains("id") ? tc["id"].as_string() : ("call_" + std::to_string(i));
                if (tc.contains("function")) {
                    auto& func = tc["function"];
                    call.name = func.contains("name") ? func["name"].as_string() : "";
                    call.arguments_json = func.contains("arguments") ? func["arguments"].as_string() : "{}";
                }
                result.push_back(call);
            }
        } catch (const std::exception& e) {
            last_error = std::string("Parse tool_calls error: ") + e.what();
        }
        return result;
    }

    // 提取 LLM 文本回复
    std::string extractTextContent(const std::string& response_body) const {
        try {
            nlohmann::json resp = nlohmann::json::parse(response_body);
            if (!resp.contains("choices") || resp["choices"].size() == 0) return "";
            auto& choice = resp["choices"][0];
            if (!choice.contains("message")) return "";
            auto& message = choice["message"];
            if (message.contains("content") && !message["content"].is_null()) {
                return message["content"].as_string();
            }
        } catch (...) {}
        return "";
    }

    // 执行工具调用：将 LLM 的语义参数传入 C++ 回调，获取几何分析结果
    ToolResult executeToolCall(const ToolCall& call) const {
        ToolResult result;
        result.tool_call_id = call.id;

        auto it = tools.find(call.name);
        if (it == tools.end()) {
            result.success = false;
            result.result_json = R"({"error": "Unknown tool: )" + call.name + R"("})";
            return result;
        }

        try {
            std::string exec_result = it->second.execute(call.arguments_json);
            result.success = true;
            result.result_json = exec_result;
        } catch (const std::exception& e) {
            result.success = false;
            result.result_json = R"({"error": ")" + std::string(e.what()) + R"("})";
        }
        return result;
    }
};

LLMClient::LLMClient() : impl_(std::make_unique<Impl>()) {}

LLMClient::~LLMClient() = default;

LLMClient& LLMClient::getInstance() {
    static LLMClient instance;
    return instance;
}

void LLMClient::setEndpoint(const std::string& endpoint) {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    impl_->endpoint = endpoint;
}

void LLMClient::setApiKey(const std::string& api_key) {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    impl_->api_key = api_key;
}

void LLMClient::setModel(const std::string& model) {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    impl_->model = model;
}

void LLMClient::setTimeout(int timeout_ms) {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    impl_->timeout_ms = timeout_ms;
}

void LLMClient::registerTool(const ToolDefinition& tool) {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    impl_->tools[tool.name] = tool;
}

void LLMClient::clearTools() {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    impl_->tools.clear();
}

std::string LLMClient::sendChat(const std::vector<std::map<std::string, std::string>>& messages) {
    std::lock_guard<std::mutex> lock(impl_->mutex);

    nlohmann::json request;
    request["model"] = impl_->model;
    request["temperature"] = 0.7;
    request["max_tokens"] = 2048;

    nlohmann::json msgs = nlohmann::json::array();
    for (const auto& msg : messages) {
        nlohmann::json m;
        for (const auto& [key, val] : msg) {
            m[key] = val;
        }
        msgs.push_back(m);
    }
    request["messages"] = msgs;

    if (!impl_->tools.empty()) {
        request["tools"] = nlohmann::json::parse(impl_->buildToolsJson());
        request["tool_choice"] = "auto";
    }

    return impl_->sendHttpRequest(request.dump());
}

std::future<std::string> LLMClient::sendChatAsync(const std::vector<std::map<std::string, std::string>>& messages) {
    return std::async(std::launch::async, [this, messages]() {
        return sendChat(messages);
    });
}

std::string LLMClient::embodiedQuery(const std::string& user_input, int max_rounds) {
    std::lock_guard<std::mutex> lock(impl_->mutex);

    // 构建初始消息列表
    // 具身智能接口：将 3D 拓扑数据转换为 LLM 可理解的语义上下文
    nlohmann::json messages = nlohmann::json::array();

    nlohmann::json sys_msg;
    sys_msg["role"] = "system";
    sys_msg["content"] =
        "You are an embodied AI CAD assistant. You can analyze 3D models using the provided tools. "
        "When the user asks about model properties, weaknesses, or geometry, use the appropriate tool. "
        "Always respond in the user's language. Be concise and specific about what you found.";
    messages.push_back(sys_msg);

    nlohmann::json user_msg;
    user_msg["role"] = "user";
    user_msg["content"] = user_input;
    messages.push_back(user_msg);

    for (int round = 0; round < max_rounds; ++round) {
        // 构建 OpenAI 兼容的请求体
        nlohmann::json request;
        request["model"] = impl_->model;
        request["temperature"] = 0.7;
        request["max_tokens"] = 2048;
        request["messages"] = messages;

        if (!impl_->tools.empty()) {
            request["tools"] = nlohmann::json::parse(impl_->buildToolsJson());
            request["tool_choice"] = "auto";
        }

        std::string response_body = impl_->sendHttpRequest(request.dump());
        if (response_body.empty()) {
            return "[Error] " + impl_->last_error;
        }

        // 解析 LLM 响应，检查是否有工具调用
        auto tool_calls = impl_->parseToolCallsFromResponse(response_body);

        if (tool_calls.empty()) {
            // LLM 没有调用工具，直接返回文本回复
            return impl_->extractTextContent(response_body);
        }

        // 将 LLM 的 assistant 消息（含 tool_calls）加入上下文
        nlohmann::json assistant_msg;
        assistant_msg["role"] = "assistant";

        // 重新解析原始响应以保留完整结构
        try {
            nlohmann::json resp = nlohmann::json::parse(response_body);
            assistant_msg = resp["choices"][0]["message"];
        } catch (...) {
            assistant_msg["content"] = impl_->extractTextContent(response_body);
        }
        messages.push_back(assistant_msg);

        // 执行每个工具调用，将结果反馈给 LLM
        for (const auto& tc : tool_calls) {
            std::cout << "[EmbodiedAI] Tool call: " << tc.name
                      << " args: " << tc.arguments_json << std::endl;

            ToolResult result = impl_->executeToolCall(tc);

            std::cout << "[EmbodiedAI] Tool result: success=" << result.success
                      << " result=" << result.result_json.substr(0, 200) << std::endl;

            // 将工具执行结果作为 tool message 反馈给 LLM
            nlohmann::json tool_msg;
            tool_msg["role"] = "tool";
            tool_msg["tool_call_id"] = result.tool_call_id;
            tool_msg["content"] = result.result_json;
            messages.push_back(tool_msg);
        }
    }

    // 达到最大轮次，做最后一次请求获取最终文本回复
    nlohmann::json final_request;
    final_request["model"] = impl_->model;
    final_request["temperature"] = 0.7;
    final_request["max_tokens"] = 2048;
    final_request["messages"] = messages;

    std::string final_response = impl_->sendHttpRequest(final_request.dump());
    if (final_response.empty()) {
        return "[Error] " + impl_->last_error;
    }

    return impl_->extractTextContent(final_response);
}

std::future<std::string> LLMClient::embodiedQueryAsync(const std::string& user_input, int max_rounds) {
    return std::async(std::launch::async, [this, user_input, max_rounds]() {
        return embodiedQuery(user_input, max_rounds);
    });
}

std::string LLMClient::getLastError() const {
    return impl_->last_error;
}

std::vector<std::string> LLMClient::getRegisteredToolNames() const {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    std::vector<std::string> names;
    for (const auto& [name, _] : impl_->tools) {
        names.push_back(name);
    }
    return names;
}

} // namespace core
} // namespace hhb
