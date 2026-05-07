#include <iostream>
#include <cstring>
#include "object_pool.h"

// Test struct
struct TestStruct {
    int id;
    double value;
    char name[32];
};

int main() {
    hhb::core::ObjectPool<TestStruct> pool;

    // Test allocation and deallocation
    TestStruct* obj1 = pool.allocate();
    obj1->id = 1;
    obj1->value = 3.14;
    strcpy(obj1->name, "Test1");

    TestStruct* obj2 = pool.allocate();
    obj2->id = 2;
    obj2->value = 6.28;
    strcpy(obj2->name, "Test2");

    std::cout << "Allocated objects: " << pool.size() << std::endl;
    std::cout << "Object 1: id=" << obj1->id << ", value=" << obj1->value << ", name=" << obj1->name << std::endl;
    std::cout << "Object 2: id=" << obj2->id << ", value=" << obj2->value << ", name=" << obj2->name << std::endl;

    // Test deallocation
    pool.deallocate(obj1);
    pool.deallocate(obj2);

    // Test reuse
    TestStruct* obj3 = pool.allocate();
    obj3->id = 3;
    obj3->value = 9.42;
    strcpy(obj3->name, "Test3");

    std::cout << "After deallocate and reallocate: " << std::endl;
    std::cout << "Object 3: id=" << obj3->id << ", value=" << obj3->value << ", name=" << obj3->name << std::endl;
    std::cout << "Allocated objects: " << pool.size() << std::endl;

    return 0;
}