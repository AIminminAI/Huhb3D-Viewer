#include <iostream>
#include <chrono>
#include <fstream>
#include <vector>

// STL 三角形结构体
struct Triangle {
    float normal[3];
    float vertex1[3];
    float vertex2[3];
    float vertex3[3];
    uint16_t attribute_count;
};

int main() {
    std::cout << "Starting STL parser test..." << std::endl;
    
    try {
        // 测试文件路径
        std::string filename = "Dji+Avata+2+Simple.stl";
        std::cout << "Testing file: " << filename << std::endl;

        // 检查文件是否存在
        std::ifstream file(filename);
        if (!file) {
            std::cerr << "File does not exist" << std::endl;
            return 1;
        }
        file.close();
        std::cout << "File exists" << std::endl;

        // 开始计时
        auto start = std::chrono::high_resolution_clock::now();
        std::cout << "Starting parsing..." << std::endl;

        // 打开文件并解析
        std::ifstream stlFile(filename, std::ios::binary);
        if (!stlFile) {
            std::cerr << "Failed to open file" << std::endl;
            return 1;
        }

        // 跳过文件头
        stlFile.seekg(80, std::ios::beg);

        // 读取三角形数量
        uint32_t triangle_count;
        stlFile.read(reinterpret_cast<char*>(&triangle_count), 4);
        std::cout << "Triangle count: " << triangle_count << std::endl;

        // 预留空间
        std::vector<Triangle> triangles;
        triangles.reserve(triangle_count);

        // 解析三角形
        for (uint32_t i = 0; i < triangle_count; ++i) {
            Triangle tri;
            stlFile.read(reinterpret_cast<char*>(&tri), sizeof(Triangle));
            // 跳过剩余的字节（如果有）
            if (sizeof(Triangle) < 50) {
                stlFile.seekg(50 - sizeof(Triangle), std::ios::cur);
            }
            triangles.push_back(tri);
        }

        // 关闭文件
        stlFile.close();

        // 结束计时
        auto end = std::chrono::high_resolution_clock::now();
        std::chrono::duration<double, std::milli> duration = end - start;

        std::cout << "Successfully parsed " << triangles.size() << " triangles" << std::endl;
        std::cout << "Parsing time: " << duration.count() << " ms" << std::endl;
    } catch (const std::exception& e) {
        std::cerr << "Exception caught: " << e.what() << std::endl;
    } catch (...) {
        std::cerr << "Unknown exception caught" << std::endl;
    }

    std::cout << "Test completed." << std::endl;
    return 0;
}