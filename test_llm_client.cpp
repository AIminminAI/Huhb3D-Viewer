#include <iostream>
#include "llm_client.h"

int main() {
    hhb::core::LLMClient client;
    
    // 示例：设置 OpenAI API 端点
    client.setEndpoint("https://api.openai.com/v1/completions");
    
    // 注意：实际使用时需要设置真实的 API 密钥
    // client.setApiKey("your-api-key-here");
    
    // 设置超时时间（30秒）
    client.setTimeout(30000);
    
    // 测试提示词
    std::string prompt = "Explain the concept of zero-copy memory mapping in C++ in simple terms.";
    
    std::cout << "Sending prompt to LLM..." << std::endl;
    std::string response = client.sendPrompt(prompt);
    
    if (!response.empty()) {
        std::cout << "Response received:" << std::endl;
        std::cout << response << std::endl;
    } else {
        std::cerr << "Error: " << client.getLastError() << std::endl;
        std::cerr << "Note: You need to set a valid API key to test this functionality." << std::endl;
    }
    
    // 测试自定义 JSON 请求
    std::string custom_json = R"({
        "prompt": "Write a short poem about 3D geometry.",
        "temperature": 0.8,
        "max_tokens": 200
    })";
    
    std::cout << "\nSending custom JSON request..." << std::endl;
    response = client.sendRequest(custom_json);
    
    if (!response.empty()) {
        std::cout << "Custom response received:" << std::endl;
        std::cout << response << std::endl;
    } else {
        std::cerr << "Error: " << client.getLastError() << std::endl;
    }
    
    return 0;
}