#include <iostream>
#include <vector>
#include <chrono>
#include <string>
#include <cstring>
#include "object_pool.h"

// 定义典型的 CAD 几何实体
struct MyEntity {
    float x, y, z;
    int id;
    char metadata[32];

    MyEntity() : x(0.0f), y(0.0f), z(0.0f), id(0) {
        std::memset(metadata, 0, sizeof(metadata));
    }

    MyEntity(float x, float y, float z, int id, const char* meta) 
        : x(x), y(y), z(z), id(id) {
        std::strncpy(metadata, meta, sizeof(metadata) - 1);
        metadata[sizeof(metadata) - 1] = '\0';
    }
};

// 热身函数
void warm_up() {
    std::cout << "Warming up..." << std::endl;
    
    // 热身 std::vector
    std::vector<MyEntity> warm_vec;
    for (int i = 0; i < 100000; ++i) {
        warm_vec.emplace_back(i * 0.1f, i * 0.2f, i * 0.3f, i, "warmup");
    }
    warm_vec.clear();
    
    // 热身 ObjectPool
    hhb::core::ObjectPool<MyEntity> warm_pool;
    std::vector<MyEntity*> warm_objs;
    for (int i = 0; i < 100000; ++i) {
        MyEntity* obj = warm_pool.allocate();
        new (obj) MyEntity(i * 0.1f, i * 0.2f, i * 0.3f, i, "warmup");
        warm_objs.push_back(obj);
    }
    for (MyEntity* obj : warm_objs) {
        obj->~MyEntity();
        warm_pool.deallocate(obj);
    }
    
    std::cout << "Warm up completed." << std::endl;
}

// 测试 std::vector（不使用 reserve）
double test_vector_no_reserve(size_t count) {
    std::vector<MyEntity> vec;
    auto start = std::chrono::high_resolution_clock::now();
    
    for (size_t i = 0; i < count; ++i) {
        vec.emplace_back(i * 0.1f, i * 0.2f, i * 0.3f, static_cast<int>(i), "test");
    }
    
    auto end = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double, std::milli> duration = end - start;
    
    std::cout << "std::vector (no reserve): " << duration.count() << " ms" << std::endl;
    std::cout << "Final size: " << vec.size() << ", Capacity: " << vec.capacity() << std::endl;
    
    return duration.count();
}

// 测试 std::vector（使用 reserve）
double test_vector_with_reserve(size_t count) {
    std::vector<MyEntity> vec;
    vec.reserve(count);
    auto start = std::chrono::high_resolution_clock::now();
    
    for (size_t i = 0; i < count; ++i) {
        vec.emplace_back(i * 0.1f, i * 0.2f, i * 0.3f, static_cast<int>(i), "test");
    }
    
    auto end = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double, std::milli> duration = end - start;
    
    std::cout << "std::vector (with reserve): " << duration.count() << " ms" << std::endl;
    std::cout << "Final size: " << vec.size() << ", Capacity: " << vec.capacity() << std::endl;
    
    return duration.count();
}

// 测试 ObjectPool
double test_object_pool(size_t count) {
    hhb::core::ObjectPool<MyEntity> pool;
    std::vector<MyEntity*> objs;
    objs.reserve(count);
    
    auto start = std::chrono::high_resolution_clock::now();
    
    for (size_t i = 0; i < count; ++i) {
        MyEntity* obj = pool.allocate();
        new (obj) MyEntity(i * 0.1f, i * 0.2f, i * 0.3f, static_cast<int>(i), "test");
        objs.push_back(obj);
    }
    
    auto end = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double, std::milli> duration = end - start;
    
    std::cout << "ObjectPool: " << duration.count() << " ms" << std::endl;
    std::cout << "Final size: " << pool.size() << std::endl;
    
    // 清理对象
    for (MyEntity* obj : objs) {
        obj->~MyEntity();
        pool.deallocate(obj);
    }
    
    return duration.count();
}

int main() {
    const size_t TEST_COUNT = 10000000; // 1000 万次
    
    // 热身
    warm_up();
    
    std::cout << "\nTesting with " << TEST_COUNT << " objects..." << std::endl;
    
    // 测试 std::vector（不使用 reserve）
    double vec_no_reserve_time = test_vector_no_reserve(TEST_COUNT);
    
    // 测试 std::vector（使用 reserve）
    double vec_with_reserve_time = test_vector_with_reserve(TEST_COUNT);
    
    // 测试 ObjectPool
    double pool_time = test_object_pool(TEST_COUNT);
    
    // 输出对比结果
    std::cout << "\n=== Performance Comparison ===" << std::endl;
    std::cout << "std::vector (no reserve): " << vec_no_reserve_time << " ms" << std::endl;
    std::cout << "std::vector (with reserve): " << vec_with_reserve_time << " ms" << std::endl;
    std::cout << "ObjectPool: " << pool_time << " ms" << std::endl;
    std::cout << "\nSpeedup (vs vector no reserve): " << vec_no_reserve_time / pool_time << "x" << std::endl;
    std::cout << "Speedup (vs vector with reserve): " << vec_with_reserve_time / pool_time << "x" << std::endl;
    
    // 等待用户输入，以便查看内存占用
    std::cout << "\nPress Enter to exit..." << std::endl;
    std::cin.get();
    
    return 0;
}
