#include <iostream>
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

        std::cout << "Step 7: Checking if file exists..." << std::endl;
        bool exists = hhb::core::file_exists(filename);
        std::cout << "Step 8: File exists: " << (exists ? "yes" : "no") << std::endl;

        if (exists) {
            std::cout << "Step 9: Checking if file is binary..." << std::endl;
            bool is_binary = parser.is_binary(filename);
            std::cout << "Step 10: File is binary: " << (is_binary ? "yes" : "no") << std::endl;
        }

        std::cout << "Step 11: Test completed successfully" << std::endl;
    } catch (const std::exception& e) {
        std::cerr << "Exception caught: " << e.what() << std::endl;
    } catch (...) {
        std::cerr << "Unknown exception caught" << std::endl;
    }

    return 0;
}