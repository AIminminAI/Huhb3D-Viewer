#include <iostream>
#include <chrono>
#include <fstream>
#include <vector>
#include <string>

// STL 三角形结构体
struct Triangle {
    float normal[3];
    float vertex1[3];
    float vertex2[3];
    float vertex3[3];
    uint16_t attribute_count;
};

// 检查文件是否存在
bool file_exists(const std::string& filename) {
    std::ifstream file(filename);
    return file.good();
}

// 检测文件格式
bool is_binary(const std::string& filename) {
    std::ifstream file(filename, std::ios::binary | std::ios::ate);
    if (!file) {
        return false;
    }

    std::streampos size = file.tellg();
    file.seekg(0, std::ios::beg);

    // 二进制 STL 文件最小大小：80字节头 + 4字节三角形数量 + 每个三角形50字节
    if (size < 80 + 4 + 50) {
        return false;
    }

    // 读取文件头
    char header[80];
    file.read(header, 80);

    // 读取三角形数量
    uint32_t triangle_count;
    file.read(reinterpret_cast<char*>(&triangle_count), 4);

    // 验证文件大小是否与三角形数量匹配
    return (size == 80 + 4 + triangle_count * 50);
}

// 解析二进制 STL 文件
size_t parse_binary(const std::string& filename, std::vector<Triangle>& triangles) {
    std::ifstream file(filename, std::ios::binary);
    if (!file) {
        return 0;
    }

    // 跳过80字节头
    file.seekg(80, std::ios::beg);

    // 读取三角形数量
    uint32_t triangle_count;
    file.read(reinterpret_cast<char*>(&triangle_count), 4);

    // 预留空间
    triangles.reserve(triangle_count);

    // 解析三角形
    for (uint32_t i = 0; i < triangle_count; ++i) {
        Triangle tri;
        file.read(reinterpret_cast<char*>(&tri), sizeof(Triangle));
        // 跳过剩余的字节（如果有）
        if (sizeof(Triangle) < 50) {
            file.seekg(50 - sizeof(Triangle), std::ios::cur);
        }
        triangles.push_back(tri);
    }

    return triangles.size();
}

// 解析 ASCII STL 文件
size_t parse_ascii(const std::string& filename, std::vector<Triangle>& triangles) {
    std::ifstream file(filename);
    if (!file) {
        return 0;
    }

    std::string line;

    // 跳过文件头
    while (std::getline(file, line)) {
        if (line.find("solid") != std::string::npos) {
            break;
        }
    }

    // 解析三角形
    while (file) {
        // 查找 facet 开始
        while (std::getline(file, line)) {
            if (line.find("facet normal") != std::string::npos) {
                break;
            }
        }

        if (!file) {
            break;
        }

        // 解析法向量
        Triangle tri;
        sscanf(line.c_str(), "facet normal %f %f %f", &tri.normal[0], &tri.normal[1], &tri.normal[2]);

        // 跳过 outer loop
        std::getline(file, line);

        // 解析三个顶点
        std::getline(file, line);
        sscanf(line.c_str(), "vertex %f %f %f", &tri.vertex1[0], &tri.vertex1[1], &tri.vertex1[2]);

        std::getline(file, line);
        sscanf(line.c_str(), "vertex %f %f %f", &tri.vertex2[0], &tri.vertex2[1], &tri.vertex2[2]);

        std::getline(file, line);
        sscanf(line.c_str(), "vertex %f %f %f", &tri.vertex3[0], &tri.vertex3[1], &tri.vertex3[2]);

        // 跳过 endloop 和 endfacet
        std::getline(file, line);
        std::getline(file, line);

        tri.attribute_count = 0;
        triangles.push_back(tri);
    }

    return triangles.size();
}

// 解析 STL 文件（自动检测格式）
size_t parse_stl(const std::string& filename, std::vector<Triangle>& triangles) {
    if (!file_exists(filename)) {
        return 0;
    }

    if (is_binary(filename)) {
        return parse_binary(filename, triangles);
    } else {
        return parse_ascii(filename, triangles);
    }
}

int main() {
    std::cout << "Starting STL parser test..." << std::endl;
    
    try {
        // 测试文件路径
        std::string filename = "Dji+Avata+2+Simple.stl";
        std::cout << "Testing file: " << filename << std::endl;

        // 开始计时
        auto start = std::chrono::high_resolution_clock::now();
        std::cout << "Starting parsing..." << std::endl;

        // 解析 STL 文件
        std::vector<Triangle> triangles;
        size_t count = parse_stl(filename, triangles);

        // 结束计时
        auto end = std::chrono::high_resolution_clock::now();
        std::chrono::duration<double, std::milli> duration = end - start;

        if (count > 0) {
            std::cout << "Successfully parsed " << count << " triangles" << std::endl;
            std::cout << "Total objects: " << triangles.size() << std::endl;
            std::cout << "Parsing time: " << duration.count() << " ms" << std::endl;
            
            // 打印第一个三角形的顶点坐标以供验证
            if (!triangles.empty()) {
                const auto& first_tri = triangles[0];
                std::cout << "First triangle vertices:" << std::endl;
                std::cout << "  v1: (" << first_tri.vertex1[0] << ", " << first_tri.vertex1[1] << ", " << first_tri.vertex1[2] << ")" << std::endl;
                std::cout << "  v2: (" << first_tri.vertex2[0] << ", " << first_tri.vertex2[1] << ", " << first_tri.vertex2[2] << ")" << std::endl;
                std::cout << "  v3: (" << first_tri.vertex3[0] << ", " << first_tri.vertex3[1] << ", " << first_tri.vertex3[2] << ")" << std::endl;
                std::cout << "  normal: (" << first_tri.normal[0] << ", " << first_tri.normal[1] << ", " << first_tri.normal[2] << ")" << std::endl;
            }
        } else {
            std::cerr << "Failed to parse STL file" << std::endl;
        }
    } catch (const std::exception& e) {
        std::cerr << "Exception caught: " << e.what() << std::endl;
    } catch (...) {
        std::cerr << "Unknown exception caught" << std::endl;
    }

    std::cout << "Test completed." << std::endl;
    return 0;
}