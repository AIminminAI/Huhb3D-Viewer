#include <iostream>
#include "stl_parser_coroutine.h"

int main() {
    hhb::core::ObjectPool<hhb::core::Triangle> pool;
    hhb::core::StlParserCoroutine parser;

    // 测试文件路径（这里使用一个示例路径，实际使用时需要替换为真实的 STL 文件路径）
    std::string filename = "test_ascii.stl";

    // 解析 ASCII STL 文件（协程版）
    auto task = parser.parse_ascii(filename, pool);
    auto result = task.get();

    if (result.has_value()) {
        std::cout << "Successfully parsed " << result.value() << " triangles" << std::endl;
        std::cout << "Total objects in pool: " << pool.size() << std::endl;
    } else {
        std::cerr << "Failed to parse STL file: " << result.error() << std::endl;
    }

    return 0;
}
