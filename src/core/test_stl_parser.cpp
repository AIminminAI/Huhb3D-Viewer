#include <iostream>
#include <chrono>
#include "stl_parser.h"

int main() {
    std::cout << "Step 1: Starting test..." << std::endl;
    
    try {
        std::cout << "Step 2: Creating ObjectPool..." << std::endl;
        hhb::core::ObjectPool<hhb::core::Triangle> pool;
        std::cout << "Step 3: ObjectPool created successfully" << std::endl;
        
        std::cout << "Step 4: Creating StlParser..." << std::endl;
        hhb::core::StlParser parser;
        std::cout << "Step 5: StlParser created successfully" << std::endl;

        // 测试文件路径
        std::string filename = "Dji+Avata+2+Simple.stl";
        std::cout << "Step 6: Testing file: " << filename << std::endl;

        // 开始计时
        auto start = std::chrono::high_resolution_clock::now();
        std::cout << "Step 7: Starting parsing..." << std::endl;

        // 解析 STL 文件
        std::cout << "Step 8: Calling parser.parse()..." << std::endl;
        hhb::core::ParserResult result = parser.parse(filename, pool);
        std::cout << "Step 9: parser.parse() returned" << std::endl;

        // 结束计时
        auto end = std::chrono::high_resolution_clock::now();
        std::chrono::duration<double, std::milli> duration = end - start;

        if (result.success) {
            std::cout << "Step 10: Successfully parsed " << result.count << " triangles" << std::endl;
            std::cout << "Step 11: Total objects in pool: " << pool.size() << std::endl;
            std::cout << "Step 12: Parsing time: " << duration.count() << " ms" << std::endl;
        } else {
            std::cerr << "Step 10: Failed to parse STL file: " << result.error << std::endl;
        }

        std::cout << "Step 13: Test completed successfully" << std::endl;
    } catch (const std::exception& e) {
        std::cerr << "Exception caught: " << e.what() << std::endl;
    } catch (...) {
        std::cerr << "Unknown exception caught" << std::endl;
    }

    return 0;
}
