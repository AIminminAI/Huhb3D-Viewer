#include <iostream>
#include "geometry_api.h"

int main() {
    hhb::core::GeometryAPI geo_api;
    
    // 测试加载模型
    std::string filename = "Cube.stl";
    std::cout << "Loading model: " << filename << std::endl;
    
    if (geo_api.loadModel(filename)) {
        std::cout << "Model loaded successfully!" << std::endl;
        
        // 测试获取三角形数量
        std::cout << "Triangle count: " << geo_api.getTriangleCount() << std::endl;
        
        // 测试获取模型边界框
        hhb::core::Bounds bounds = geo_api.getModelBounds();
        std::cout << "Model bounds: min(" << bounds.min[0] << ", " << bounds.min[1] << ", " << bounds.min[2] 
                  << "), max(" << bounds.max[0] << ", " << bounds.max[1] << ", " << bounds.max[2] << ")" << std::endl;
        
        // 测试获取 BVH 深度
        std::cout << "BVH depth: " << geo_api.getBVHDepth() << std::endl;
        
        // 测试获取所有三角形
        std::vector<hhb::core::Triangle> all_triangles = geo_api.getAllTriangles();
        std::cout << "All triangles retrieved: " << all_triangles.size() << std::endl;
        
        // 测试获取薄部分
        float max_thickness = 0.1f; // 0.1mm
        std::vector<hhb::core::Triangle*> thin_parts = geo_api.getThinParts(max_thickness);
        std::cout << "Thin parts found: " << thin_parts.size() << std::endl;
        
        // 测试射线相交
        hhb::core::Ray ray(hhb::core::Point(0, 0, 5), hhb::core::Point(0, 0, -1));
        std::vector<hhb::core::Intersection> intersections = geo_api.getIntersectingPoints(ray);
        std::cout << "Intersections found: " << intersections.size() << std::endl;
        
        if (!intersections.empty()) {
            hhb::core::Intersection& hit = intersections[0];
            std::cout << "Closest intersection at: (" << hit.point.x << ", " << hit.point.y << ", " << hit.point.z << ")" << std::endl;
            std::cout << "Distance: " << hit.distance << std::endl;
        }
        
        // 测试清除模型
        geo_api.clear();
        std::cout << "Model cleared. Triangle count: " << geo_api.getTriangleCount() << std::endl;
    } else {
        std::cerr << "Failed to load model!" << std::endl;
        return 1;
    }
    
    return 0;
}