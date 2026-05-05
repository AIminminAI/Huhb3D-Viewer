#include <iostream>
#include "llm_client.h"
#include "geometry_api.h"

int main() {
    // 创建 LLMClient 实例
    hhb::core::LLMClient llm_client;
    
    // 设置 API 端点（使用模拟实现）
    llm_client.setEndpoint("https://api.openai.com/v1/chat/completions");
    
    // 注意：实际使用时需要设置真实的 API 密钥
    // llm_client.setApiKey("your-api-key-here");
    
    // 设置超时时间
    llm_client.setTimeout(30000);
    
    // 创建 GeometryAPI 实例
    hhb::core::GeometryAPI geo_api;
    
    // 加载测试模型
    std::string model_path = "Cube.stl";
    std::cout << "Loading model: " << model_path << std::endl;
    if (!geo_api.loadModel(model_path)) {
        std::cerr << "Failed to load model!" << std::endl;
        return 1;
    }
    std::cout << "Model loaded successfully!" << std::endl;
    
    // 测试 Function Calling
    std::string user_query = "帮我找出模型中厚度小于1mm的薄弱部位";
    std::cout << "\nSending user query: " << user_query << std::endl;
    
    // 发送工具调用请求
    std::string response = llm_client.sendToolCallRequest(user_query);
    
    if (!response.empty()) {
        std::cout << "\nLLM response received:" << std::endl;
        std::cout << response << std::endl;
        
        // 解析工具调用
        std::vector<hhb::core::LLMClient::ToolCall> tool_calls = llm_client.parseToolCalls(response);
        
        if (!tool_calls.empty()) {
            std::cout << "\nTool calls found: " << tool_calls.size() << std::endl;
            
            for (const auto& tool_call : tool_calls) {
                std::cout << "Tool name: " << tool_call.name << std::endl;
                
                // 显示参数
                std::cout << "Parameters:" << std::endl;
                for (const auto& [key, value] : tool_call.parameters) {
                    std::cout << "  " << key << ": " << value << std::endl;
                }
                
                // 处理工具调用
                if (tool_call.name == "analyze_model_thickness") {
                    // 提取 threshold_mm 参数
                    float threshold_mm = 1.0f; // 默认值
                    auto it = tool_call.parameters.find("threshold_mm");
                    if (it != tool_call.parameters.end()) {
                        try {
                            threshold_mm = std::stof(it->second);
                        } catch (const std::exception& e) {
                            std::cerr << "Failed to parse threshold_mm: " << e.what() << std::endl;
                        }
                    }
                    
                    std::cout << "\nAnalyzing model thickness with threshold: " << threshold_mm << "mm" << std::endl;
                    
                    // 调用 GeometryAPI 的方法
                    std::vector<hhb::core::Triangle*> thin_parts = geo_api.getThinParts(threshold_mm);
                    
                    std::cout << "Found " << thin_parts.size() << " thin parts" << std::endl;
                    
                    // 显示结果
                    if (!thin_parts.empty()) {
                        std::cout << "\nThin parts found:" << std::endl;
                        for (size_t i = 0; i < thin_parts.size(); ++i) {
                            const auto& tri = *thin_parts[i];
                            std::cout << "Part " << i+1 << ":" << std::endl;
                            std::cout << "  Normal: (" << tri.normal[0] << ", " << tri.normal[1] << ", " << tri.normal[2] << ")" << std::endl;
                            std::cout << "  Vertex 1: (" << tri.vertex1[0] << ", " << tri.vertex1[1] << ", " << tri.vertex1[2] << ")" << std::endl;
                            std::cout << "  Vertex 2: (" << tri.vertex2[0] << ", " << tri.vertex2[1] << ", " << tri.vertex2[2] << ")" << std::endl;
                            std::cout << "  Vertex 3: (" << tri.vertex3[0] << ", " << tri.vertex3[1] << ", " << tri.vertex3[2] << ")" << std::endl;
                        }
                    }
                }
            }
        } else {
            std::cout << "\nNo tool calls found in response." << std::endl;
        }
    } else {
        std::cerr << "Error: " << llm_client.getLastError() << std::endl;
    }
    
    // 清除模型
    geo_api.clear();
    
    return 0;
}