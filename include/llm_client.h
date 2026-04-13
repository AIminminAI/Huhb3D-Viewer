#pragma once

#include <string>
#include <map>
#include <memory>
#include <vector>

namespace hhb {
namespace core {

class LLMClient {
public:
    LLMClient();
    ~LLMClient();
    
    // 设置 API 端点
    void setEndpoint(const std::string& endpoint);
    
    // 设置 API 密钥
    void setApiKey(const std::string& api_key);
    
    // 设置超时时间（毫秒）
    void setTimeout(int timeout_ms);
    
    // 发送自然语言提示词并获取响应
    std::string sendPrompt(const std::string& prompt) const;
    
    // 发送自定义 JSON 请求
    std::string sendRequest(const std::string& json_data) const;
    
    // Function Calling 相关方法
    std::string sendToolCallRequest(const std::string& prompt) const;
    
    // 解析工具调用响应
    struct ToolCall {
        std::string name;
        std::map<std::string, std::string> parameters;
    };
    
    std::vector<ToolCall> parseToolCalls(const std::string& response) const;
    
    // 获取最后一次错误信息
    std::string getLastError() const;
    
private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace core
} // namespace hhb