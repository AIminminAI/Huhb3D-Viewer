#include <iostream>
#include "stl_parser.h"

int main() {
    std::cout << "Size of Triangle struct: " << sizeof(hhb::core::Triangle) << " bytes" << std::endl;
    std::cout << "Expected size for binary STL: 50 bytes" << std::endl;
    return 0;
}