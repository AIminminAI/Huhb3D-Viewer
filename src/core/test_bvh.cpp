#include <iostream>
#include "bvh.h"

int main() {
    hhb::core::ObjectPool<hhb::core::Triangle> pool;
    std::vector<hhb::core::Triangle*> triangles;

    // 创建一些测试三角形
    for (int i = 0; i < 1000; ++i) {
        hhb::core::Triangle* tri = pool.allocate();
        // 生成随机三角形
        float x = i * 0.1f;
        tri->vertex1[0] = x;
        tri->vertex1[1] = 0.0f;
        tri->vertex1[2] = 0.0f;
        
        tri->vertex2[0] = x + 0.1f;
        tri->vertex2[1] = 0.1f;
        tri->vertex2[2] = 0.0f;
        
        tri->vertex3[0] = x + 0.05f;
        tri->vertex3[1] = 0.0f;
        tri->vertex3[2] = 0.1f;
        
        tri->normal[0] = 0.0f;
        tri->normal[1] = 0.0f;
        tri->normal[2] = 1.0f;
        
        tri->attribute_count = 0;
        
        triangles.push_back(tri);
    }

    // 构建 BVH
    hhb::core::BVH bvh;
    bvh.build(triangles);
    std::cout << "BVH built with " << bvh.node_count() << " nodes" << std::endl;

    // 测试光线求交
    float ray_origin[3] = {-1.0f, 0.05f, 0.05f};
    float ray_direction[3] = {1.0f, 0.0f, 0.0f};
    float t_hit;
    hhb::core::Triangle* hit_triangle;

    bool hit = bvh.intersect(ray_origin, ray_direction, t_hit, hit_triangle);
    if (hit) {
        std::cout << "Ray hit triangle at t = " << t_hit << std::endl;
        std::cout << "Hit triangle vertices: (" << hit_triangle->vertex1[0] << ", " << hit_triangle->vertex1[1] << ", " << hit_triangle->vertex1[2] << ")" << std::endl;
    } else {
        std::cout << "Ray did not hit any triangle" << std::endl;
    }

    return 0;
}
