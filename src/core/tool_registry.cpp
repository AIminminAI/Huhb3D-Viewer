#include "tool_registry.h"
#include <nlohmann/json.hpp>
#include <iostream>
#include <cmath>

namespace hhb {
namespace core {

ToolRegistry& ToolRegistry::getInstance() {
    static ToolRegistry instance;
    return instance;
}

void ToolRegistry::initialize(GeometryAPI* geometry_api) {
    geometryAPI_ = geometry_api;
    std::cout << "[ToolRegistry] Initialized with GeometryAPI at " << geometry_api << std::endl;
}

void ToolRegistry::registerAllToLLM(LLMClient& client) {
    // 注册 analyze_weak_structure 工具
    // 具身智能语义桥接：将"薄弱部位"这个工程概念映射为
    // "厚度 < threshold_mm 的三角面片集合"这一可计算的定义
    ToolDefinition weak_structure_tool;
    weak_structure_tool.name = "analyze_weak_structure";
    weak_structure_tool.description =
        "Analyze the 3D model to find thin/weak structural parts where wall thickness "
        "is below a given threshold. Returns the count and indices of thin triangles "
        "that may be structurally weak.";
    weak_structure_tool.parameters_json_schema = R"({
        "type": "object",
        "properties": {
            "threshold_mm": {
                "type": "number",
                "description": "Thickness threshold in millimeters. Triangles thinner than this will be identified as weak."
            }
        },
        "required": ["threshold_mm"]
    })";
    weak_structure_tool.execute = [this](const std::string& args) -> std::string {
        return executeAnalyzeWeakStructure(args);
    };
    client.registerTool(weak_structure_tool);

    // 注册 analyze_curved_surfaces 工具
    ToolDefinition curved_tool;
    curved_tool.name = "analyze_curved_surfaces";
    curved_tool.description =
        "Find regions of the model with high curvature (curved surfaces). "
        "Useful for identifying bends, fillets, and organic shapes.";
    curved_tool.parameters_json_schema = R"({
        "type": "object",
        "properties": {
            "curvature_threshold": {
                "type": "number",
                "description": "Curvature threshold. Triangles with curvature above this value are considered curved."
            }
        },
        "required": ["curvature_threshold"]
    })";
    curved_tool.execute = [this](const std::string& args) -> std::string {
        return executeAnalyzeCurvedSurfaces(args);
    };
    client.registerTool(curved_tool);

    // 注册 analyze_sharp_edges 工具
    ToolDefinition sharp_tool;
    sharp_tool.name = "analyze_sharp_edges";
    sharp_tool.description =
        "Detect sharp edges in the model where adjacent triangles meet at large angles. "
        "Useful for finding edges, corners, and stress concentration points.";
    sharp_tool.parameters_json_schema = R"({
        "type": "object",
        "properties": {
            "angle_threshold_deg": {
                "type": "number",
                "description": "Angle threshold in degrees. Edges with angles above this are considered sharp."
            }
        },
        "required": ["angle_threshold_deg"]
    })";
    sharp_tool.execute = [this](const std::string& args) -> std::string {
        return executeAnalyzeSharpEdges(args);
    };
    client.registerTool(sharp_tool);

    // 注册 analyze_flat_surfaces 工具
    ToolDefinition flat_tool;
    flat_tool.name = "analyze_flat_surfaces";
    flat_tool.description =
        "Identify flat surface regions in the model. "
        "Useful for finding planar faces suitable for manufacturing or mounting.";
    flat_tool.parameters_json_schema = R"({
        "type": "object",
        "properties": {
            "flatness_threshold": {
                "type": "number",
                "description": "Flatness threshold (0-1). Lower values mean stricter flatness."
            }
        },
        "required": ["flatness_threshold"]
    })";
    flat_tool.execute = [this](const std::string& args) -> std::string {
        return executeAnalyzeFlatSurfaces(args);
    };
    client.registerTool(flat_tool);

    // 注册 get_model_info 工具
    ToolDefinition info_tool;
    info_tool.name = "get_model_info";
    info_tool.description =
        "Get basic information about the loaded 3D model including bounding box dimensions, "
        "triangle count, and estimated volume and surface area.";
    info_tool.parameters_json_schema = R"({
        "type": "object",
        "properties": {}
    })";
    info_tool.execute = [this](const std::string& args) -> std::string {
        return executeGetModelInfo(args);
    };
    client.registerTool(info_tool);

    std::cout << "[ToolRegistry] Registered 5 tools to LLMClient" << std::endl;
}

std::vector<int> ToolRegistry::getHighlightIndices() const {
    std::lock_guard<std::mutex> lock(resultMutex_);
    return highlightIndices_;
}

HighlightType ToolRegistry::getHighlightType() const {
    std::lock_guard<std::mutex> lock(resultMutex_);
    return highlightType_;
}

std::string ToolRegistry::getLastAnalysisDesc() const {
    std::lock_guard<std::mutex> lock(resultMutex_);
    return lastAnalysisDesc_;
}

bool ToolRegistry::hasNewResult() const {
    std::lock_guard<std::mutex> lock(resultMutex_);
    return hasNewResult_;
}

void ToolRegistry::clearNewResult() {
    std::lock_guard<std::mutex> lock(resultMutex_);
    hasNewResult_ = false;
}

std::string ToolRegistry::executeTool(const std::string& name, const std::string& args_json) {
    if (name == "analyze_weak_structure") return executeAnalyzeWeakStructure(args_json);
    if (name == "analyze_curved_surfaces") return executeAnalyzeCurvedSurfaces(args_json);
    if (name == "analyze_sharp_edges") return executeAnalyzeSharpEdges(args_json);
    if (name == "analyze_flat_surfaces") return executeAnalyzeFlatSurfaces(args_json);
    if (name == "get_model_info") return executeGetModelInfo(args_json);
    return R"({"error": "Unknown tool"})";
}

// 核心工具：分析薄弱结构
// 具身智能语义转换：将"这个模型哪里薄弱？"这样的自然语言问题
// 转换为"遍历所有三角形对，计算厚度 < threshold_mm 的面片"这一计算任务
// 再将计算结果（面片索引列表）转换回"发现 N 个薄弱部位"的自然语言描述
std::string ToolRegistry::executeAnalyzeWeakStructure(const std::string& args_json) {
    if (!geometryAPI_) {
        return R"({"error": "No model loaded", "count": 0})";
    }

    float threshold = 1.0f;
    try {
        nlohmann::json args = nlohmann::json::parse(args_json);
        if (args.contains("threshold_mm")) {
            threshold = args["threshold_mm"].as_double();
        }
    } catch (...) {}

    std::vector<Triangle*> thin_parts = geometryAPI_->getThinParts(threshold);
    std::vector<int> indices = trianglePtrsToIndices(thin_parts);

    // 设置高亮结果
    {
        std::lock_guard<std::mutex> lock(resultMutex_);
        highlightIndices_ = indices;
        highlightType_ = HighlightType::ThinParts;
        lastAnalysisDesc_ = "Weak structure (thickness < " + std::to_string(static_cast<int>(threshold)) + "mm)";
        hasNewResult_ = true;
    }

    // 构建返回给 LLM 的语义化结果
    nlohmann::json result;
    result["found"] = true;
    result["thin_triangle_count"] = static_cast<int>(thin_parts.size());
    result["threshold_mm"] = threshold;
    result["description"] = "Found " + std::to_string(thin_parts.size()) +
        " triangles with thickness below " + std::to_string(static_cast<int>(threshold)) + "mm";
    result["highlighted"] = true;

    if (!thin_parts.empty()) {
        result["severity"] = thin_parts.size() > 50 ? "high" : (thin_parts.size() > 10 ? "medium" : "low");
    }

    std::cout << "[ToolRegistry] analyze_weak_structure: found " << thin_parts.size()
              << " thin parts, " << indices.size() << " mapped to indices" << std::endl;

    return result.dump();
}

std::string ToolRegistry::executeAnalyzeCurvedSurfaces(const std::string& args_json) {
    if (!geometryAPI_) {
        return R"({"error": "No model loaded", "count": 0})";
    }

    float threshold = 0.5f;
    try {
        nlohmann::json args = nlohmann::json::parse(args_json);
        if (args.contains("curvature_threshold")) {
            threshold = args["curvature_threshold"].as_double();
        }
    } catch (...) {}

    std::vector<Triangle*> curved = geometryAPI_->getCurvedSurfaces(threshold);
    std::vector<int> indices = trianglePtrsToIndices(curved);

    {
        std::lock_guard<std::mutex> lock(resultMutex_);
        highlightIndices_ = indices;
        highlightType_ = HighlightType::CurvedSurfaces;
        lastAnalysisDesc_ = "Curved surfaces (curvature > " + std::to_string(threshold) + ")";
        hasNewResult_ = true;
    }

    nlohmann::json result;
    result["found"] = true;
    result["curved_triangle_count"] = static_cast<int>(curved.size());
    result["curvature_threshold"] = threshold;
    result["description"] = "Found " + std::to_string(curved.size()) + " curved surface triangles";
    result["highlighted"] = true;

    return result.dump();
}

std::string ToolRegistry::executeAnalyzeSharpEdges(const std::string& args_json) {
    if (!geometryAPI_) {
        return R"({"error": "No model loaded", "count": 0})";
    }

    float threshold = 90.0f;
    try {
        nlohmann::json args = nlohmann::json::parse(args_json);
        if (args.contains("angle_threshold_deg")) {
            threshold = args["angle_threshold_deg"].as_double();
        }
    } catch (...) {}

    std::vector<Triangle*> sharp = geometryAPI_->getSharpEdges(threshold);
    std::vector<int> indices = trianglePtrsToIndices(sharp);

    {
        std::lock_guard<std::mutex> lock(resultMutex_);
        highlightIndices_ = indices;
        highlightType_ = HighlightType::SharpEdges;
        lastAnalysisDesc_ = "Sharp edges (angle > " + std::to_string(static_cast<int>(threshold)) + " deg)";
        hasNewResult_ = true;
    }

    nlohmann::json result;
    result["found"] = true;
    result["sharp_edge_triangle_count"] = static_cast<int>(sharp.size());
    result["angle_threshold_deg"] = threshold;
    result["description"] = "Found " + std::to_string(sharp.size()) + " sharp edge triangles";
    result["highlighted"] = true;

    return result.dump();
}

std::string ToolRegistry::executeAnalyzeFlatSurfaces(const std::string& args_json) {
    if (!geometryAPI_) {
        return R"({"error": "No model loaded", "count": 0})";
    }

    float threshold = 0.1f;
    try {
        nlohmann::json args = nlohmann::json::parse(args_json);
        if (args.contains("flatness_threshold")) {
            threshold = args["flatness_threshold"].as_double();
        }
    } catch (...) {}

    std::vector<Triangle*> flat = geometryAPI_->getFlatSurfaces(threshold);
    std::vector<int> indices = trianglePtrsToIndices(flat);

    {
        std::lock_guard<std::mutex> lock(resultMutex_);
        highlightIndices_ = indices;
        highlightType_ = HighlightType::FlatSurfaces;
        lastAnalysisDesc_ = "Flat surfaces (flatness < " + std::to_string(threshold) + ")";
        hasNewResult_ = true;
    }

    nlohmann::json result;
    result["found"] = true;
    result["flat_triangle_count"] = static_cast<int>(flat.size());
    result["flatness_threshold"] = threshold;
    result["description"] = "Found " + std::to_string(flat.size()) + " flat surface triangles";
    result["highlighted"] = true;

    return result.dump();
}

std::string ToolRegistry::executeGetModelInfo(const std::string& args_json) {
    if (!geometryAPI_) {
        return R"({"error": "No model loaded"})";
    }

    Bounds bounds = geometryAPI_->getModelBounds();
    size_t tri_count = geometryAPI_->getTriangleCount();

    float sizeX = bounds.max[0] - bounds.min[0];
    float sizeY = bounds.max[1] - bounds.min[1];
    float sizeZ = bounds.max[2] - bounds.min[2];

    nlohmann::json result;
    result["triangle_count"] = static_cast<int>(tri_count);
    result["bounding_box"]["min"] = {bounds.min[0], bounds.min[1], bounds.min[2]};
    result["bounding_box"]["max"] = {bounds.max[0], bounds.max[1], bounds.max[2]};
    result["dimensions"]["x_mm"] = sizeX;
    result["dimensions"]["y_mm"] = sizeY;
    result["dimensions"]["z_mm"] = sizeZ;
    result["center"] = {
        (bounds.min[0] + bounds.max[0]) / 2.0f,
        (bounds.min[1] + bounds.max[1]) / 2.0f,
        (bounds.min[2] + bounds.max[2]) / 2.0f
    };

    float volume = sizeX * sizeY * sizeZ;
    result["estimated_bounding_volume_mm3"] = volume;
    result["description"] = "Model: " + std::to_string(static_cast<int>(sizeX)) + " x " +
        std::to_string(static_cast<int>(sizeY)) + " x " +
        std::to_string(static_cast<int>(sizeZ)) + " mm, " +
        std::to_string(tri_count) + " triangles";

    return result.dump();
}

std::vector<int> ToolRegistry::trianglePtrsToIndices(const std::vector<Triangle*>& tris) const {
    std::vector<int> indices;
    if (!geometryAPI_) return indices;

    std::unordered_map<Triangle*, int> ptrToIndex = geometryAPI_->getTriangleIndexMap();

    for (const auto* tri : tris) {
        auto it = ptrToIndex.find(const_cast<Triangle*>(tri));
        if (it != ptrToIndex.end()) {
            indices.push_back(it->second);
        }
    }

    return indices;
}

} // namespace core
} // namespace hhb
