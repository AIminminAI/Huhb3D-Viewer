#pragma once

#include <string>
#include <vector>
#include <map>
#include "stl_parser.h"
#include "geometry_api.h"

namespace hhb {
namespace algorithm {

class GeometryExpert {
public:
    GeometryExpert() = default;
    ~GeometryExpert() = default;
    
    /**
     * 执行几何分析命令
     * @param jsonCommand JSON格式的命令
     * @return JSON格式的执行结果
     */
    std::string executeCommand(const std::string& jsonCommand);
    
    /**
     * 加载模型数据
     * @param pool 三角形对象池
     */
    void loadModelFromPool(core::ObjectPool<core::Triangle>& pool);
    
    /**
     * 加载模型文件
     * @param filename 模型文件路径
     * @return 是否加载成功
     */
    bool loadModel(const std::string& filename);
    
    /**
     * 清除模型数据
     */
    void clear();
    
private:
    core::GeometryAPI geometryAPI;
    bool modelLoaded = false;
    int m_injected_normal_errors = 0;
    int m_injected_isolated_vertices = 0;
    
    /**
     * 解析JSON命令
     * @param jsonCommand JSON命令字符串
     * @return 命令类型和参数
     */
    std::pair<std::string, std::map<std::string, std::string>> parseJsonCommand(const std::string& jsonCommand);
    
    /**
     * 生成JSON响应
     * @param success 是否成功
     * @param message 消息
     * @param data 数据
     * @return JSON字符串
     */
    std::string generateJsonResponse(bool success, const std::string& message, const std::string& data = "");
    
    /**
     * 检查法线一致性
     * @return 反向法线的面片数量
     */
    int checkNormalConsistency();
    
    /**
     * 检查孤立顶点
     * @return 孤立顶点的数量
     */
    int checkIsolatedVertices();
};

} // namespace algorithm
} // namespace hhb