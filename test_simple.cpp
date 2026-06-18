#include <iostream>
#include "object_pool.h"

int main() {
    std::cout << "Starting simple test..." << std::endl;
    
    try {
        std::cout << "Creating ObjectPool..." << std::endl;
        hhb::core::ObjectPool<int> pool;
        std::cout << "ObjectPool created successfully" << std::endl;
        
        std::cout << "Allocating object..." << std::endl;
        int* obj = pool.allocate();
        std::cout << "Object allocated: " << obj << std::endl;
        
        *obj = 42;
        std::cout << "Object value: " << *obj << std::endl;
        
        std::cout << "Deallocating object..." << std::endl;
        pool.deallocate(obj);
        std::cout << "Object deallocated successfully" << std::endl;
        
        std::cout << "Test completed successfully" << std::endl;
    } catch (const std::exception& e) {
        std::cerr << "Exception caught: " << e.what() << std::endl;
    } catch (...) {
        std::cerr << "Unknown exception caught" << std::endl;
    }
    
    return 0;
}