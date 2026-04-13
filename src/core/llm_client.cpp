#include "llm_client.h"
#include <httplib.h>
#include <nlohmann/json.hpp>
#include <iostream>

namespace hhb {
namespace core {

struct LLMClient::Impl {
    std::string endpoint;
    std::string api_key;
    int timeout_ms = 30000; // 默认 30 秒
    mutable std::string last_error;
    
    std::string sendRequest(const std::string& json_data) const {
        last_error.clear();
        
        try {
            httplib::Client client(endpoint);
            client.set_timeout_sec(timeout_ms / 1000);
            
            httplib::Client::Headers headers;
            headers["Content-Type"] = "application/json";
            
            if (!api_key.empty()) {
                headers["Authorization"] = "Bearer " + api_key;
            }
            
            auto res = client.Post("", headers, json_data, "application/json");
            
            if (res) {
                if (res->status == 200) {
                    return res->body;
                } else {
                    last_error = "HTTP error: " + std::to_string(res->status) + " - " + res->body;
                    return "";
                }
            } else {
                last_error = "Connection error: Failed to connect to server";
                return "";
            }
        } catch (const std::exception& e) {
            last_error = "Exception: " + std::string(e.what());
            return "";
        }
    }
    
    // 定义工具 schema
    std::string getToolSchema() const {
        return R"({
            "name": "analyze_model_thickness",
            "description": "分析模型中厚度小于指定阈值的薄弱部位",
            "parameters": {
                "type": "object",
                "properties": {
                    "threshold_mm": {
                        "type": "number",
                        "description": "厚度阈值（毫米）"
                    }
                },
                "required": ["threshold_mm"]
            }
        })";
    }
    
    std::string sendToolCallRequest(const std::string& prompt) const {
        try {
            // 手动构建请求数据，因为简化版的 JSON 库不支持数组
            std::string tools = "[" + getToolSchema() + "]";
            
            // 构建包含 prompt 的 JSON 对象
            nlohmann::json request_data = {
                {"prompt", prompt},
                {"temperature", 0.7},
                {"max_tokens", 1000},
                {"tool_choice", "auto"}
            };
            
            // 生成基本 JSON 字符串
            std::string base_json = request_data.dump();
            
            // 手动插入 tools 字段
            size_t last_comma_pos = base_json.rfind(',');
            if (last_comma_pos == std::string::npos) {
                // 没有其他字段，直接构建完整 JSON
                base_json = "{\"prompt\": \"" + prompt + "\", \"temperature\": 0.7, \"max_tokens\": 1000, \"tools\": " + tools + ", \"tool_choice\": \"auto\"}";
            } else {
                // 在最后一个逗号后插入 tools 字段
                base_json.insert(last_comma_pos + 1, " \"tools\": " + tools + ",");
            }
            
            return sendRequest(base_json);
        } catch (const std::exception& e) {
            last_error = "JSON error: " + std::string(e.what());
            return "";
        }
    }
};

LLMClient::LLMClient() : impl_(std::make_unique<Impl>()) {
}

LLMClient::~LLMClient() = default;

void LLMClient::setEndpoint(const std::string& endpoint) {
    impl_->endpoint = endpoint;
}

void LLMClient::setApiKey(const std::string& api_key) {
    impl_->api_key = api_key;
}

void LLMClient::setTimeout(int timeout_ms) {
    impl_->timeout_ms = timeout_ms;
}

std::string LLMClient::sendPrompt(const std::string& prompt) const {
    try {
        nlohmann::json request_data = {
            {"prompt", prompt},
            {"temperature", 0.7},
            {"max_tokens", 1000}
        };
        
        return impl_->sendRequest(request_data.dump());
    } catch (const std::exception& e) {
        impl_->last_error = "JSON error: " + std::string(e.what());
        return "";
    }
}

std::string LLMClient::sendRequest(const std::string& json_data) const {
    return impl_->sendRequest(json_data);
}

std::string LLMClient::sendToolCallRequest(const std::string& prompt) const {
    return impl_->sendToolCallRequest(prompt);
}

std::vector<LLMClient::ToolCall> LLMClient::parseToolCalls(const std::string& response) const {
    std::vector<ToolCall> tool_calls;
    
    try {
        // 简单的字符串解析，提取工具调用信息
        // 注意：这是一个简化的实现，实际项目中应该使用更健壮的 JSON 解析
        
        // 查找 tool_calls 部分
        size_t tool_calls_pos = response.find("\"tool_calls\":");
        if (tool_calls_pos != std::string::npos) {
            size_t start_pos = response.find('[', tool_calls_pos);
            if (start_pos != std::string::npos) {
                size_t end_pos = response.find(']', start_pos);
                if (end_pos != std::string::npos) {
                    std::string tool_calls_str = response.substr(start_pos, end_pos - start_pos + 1);
                    
                    // 查找 function 部分
                    size_t function_pos = tool_calls_str.find("\"function\":");
                    while (function_pos != std::string::npos) {
                        ToolCall call;
                        
                        // 提取 name
                        size_t name_pos = tool_calls_str.find("\"name\":", function_pos);
                        if (name_pos != std::string::npos) {
                            size_t name_start = tool_calls_str.find('"', name_pos + 7);
                            if (name_start != std::string::npos) {
                                size_t name_end = tool_calls_str.find('"', name_start + 1);
                                if (name_end != std::string::npos) {
                                    call.name = tool_calls_str.substr(name_start + 1, name_end - name_start - 1);
                                }
                            }
                        }
                        
                        // 提取 arguments
                        size_t arguments_pos = tool_calls_str.find("\"arguments\":", function_pos);
                        if (arguments_pos != std::string::npos) {
                            size_t args_start = tool_calls_str.find('{', arguments_pos);
                            if (args_start != std::string::npos) {
                                size_t args_end = tool_calls_str.find('}', args_start);
                                if (args_end != std::string::npos) {
                                    std::string args_str = tool_calls_str.substr(args_start + 1, args_end - args_start - 1);
                                    
                                    // 提取 threshold_mm
                                    size_t threshold_pos = args_str.find("\"threshold_mm\":");
                                    if (threshold_pos != std::string::npos) {
                                        size_t threshold_start = threshold_pos + 16;
                                        size_t threshold_end = args_str.find(',', threshold_start);
                                        if (threshold_end == std::string::npos) {
                                            threshold_end = args_str.length();
                                        }
                                        std::string threshold_str = args_str.substr(threshold_start, threshold_end - threshold_start);
                                        call.parameters["threshold_mm"] = threshold_str;
                                    }
                                }
                            }
                        }
                        
                        tool_calls.push_back(call);
                        
                        // 查找下一个 function
                        function_pos = tool_calls_str.find("\"function\":", function_pos + 1);
                    }
                }
            }
        }
    } catch (const std::exception& e) {
        impl_->last_error = "Failed to parse tool calls: " + std::string(e.what());
    }
    
    return tool_calls;
}

std::string LLMClient::getLastError() const {
    return impl_->last_error;
}

} // namespace core
} // namespace hhb