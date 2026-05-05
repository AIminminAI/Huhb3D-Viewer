#pragma once

#include <string>
#include <map>
#include <vector>
#include <functional>
#include <mutex>
#include "llm_client.h"
#include "geometry_api.h"
#include "highlight_types.h"

namespace hhb {
namespace core {

// 具身智能工具注册表：将 3D 几何分析能力注册为 LLM 可调用的工具
// 核心思想：将 C++ 的几何计算接口（如 BVH 遍历、厚度分析）包装为
// LLM 可理解的函数签名和参数描述，实现"语义-计算"的桥接
class ToolRegistry {
public:
    static ToolRegistry& getInstance();

    // 初始化所有内置工具，绑定 GeometryAPI 实例
    void initialize(GeometryAPI* geometry_api);

    // 将所有已注册工具注册到 LLMClient
    void registerAllToLLM(LLMClient& client);

    // 获取高亮索引（由工具执行结果设置）
    std::vector<int> getHighlightIndices() const;
    HighlightType getHighlightType() const;
    std::string getLastAnalysisDesc() const;
    bool hasNewResult() const;
    void clearNewResult();

    // 直接执行工具（供非 LLM 路径使用）
    std::string executeTool(const std::string& name, const std::string& args_json);

private:
    ToolRegistry() = default;
    ~ToolRegistry() = default;
    ToolRegistry(const ToolRegistry&) = delete;
    ToolRegistry& operator=(const ToolRegistry&) = delete;

    GeometryAPI* geometryAPI_ = nullptr;

    // 工具执行结果：高亮索引和描述
    mutable std::mutex resultMutex_;
    std::vector<int> highlightIndices_;
    HighlightType highlightType_ = HighlightType::None;
    std::string lastAnalysisDesc_;
    bool hasNewResult_ = false;

    // 各工具的执行函数
    // analyze_weak_structure: 找出模型中厚度小于阈值的三角面片
    std::string executeAnalyzeWeakStructure(const std::string& args_json);

    // analyze_curved_surfaces: 检测高曲率区域
    std::string executeAnalyzeCurvedSurfaces(const std::string& args_json);

    // analyze_sharp_edges: 检测锐角棱边
    std::string executeAnalyzeSharpEdges(const std::string& args_json);

    // analyze_flat_surfaces: 检测平面区域
    std::string executeAnalyzeFlatSurfaces(const std::string& args_json);

    // get_model_info: 获取模型基本信息（包围盒、三角形数等）
    std::string executeGetModelInfo(const std::string& args_json);

    // 辅助：将 Triangle 指针列表转为索引列表
    std::vector<int> trianglePtrsToIndices(const std::vector<Triangle*>& tris) const;
};

} // namespace core
} // namespace hhb
