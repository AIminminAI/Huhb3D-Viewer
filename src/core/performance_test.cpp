#include <iostream>
#include <vector>
#include <chrono>
#include "object_pool.h"

// 测试结构体
truct TestStruct {
    int id;
    double value;
    char name[32];

    TestStruct(int id = 0, double value = 0.0, const char* name = "")
        : id(id), value(value) {
        strcpy(this->name, name);
    }
};

// 性能测试函数
template <typename Func>
double measure_time(Func&& func) {
    auto start = std::chrono::high_resolution_clock::now();
    func();
    auto end = std::chrono::high_resolution_clock::now();
    return std::chrono::duration<double, std::milli>(end - start).count();
}

int main() {
    const size_t TEST_SIZE = 10000000; // 1000万个对象

    std::cout << "Testing ObjectPool vs std::vector performance..." << std::endl;
    std::cout << "Test size: " << TEST_SIZE << " objects" << std::endl;
    std::cout << "=========================================" << std::endl;

    // 测试 ObjectPool
    double pool_time = measure_time([&]() {
        hhb::core::ObjectPool<TestStruct> pool;
        std::vector<TestStruct*> objects;
        objects.reserve(TEST_SIZE);

        // 分配对象
        for (size_t i = 0; i < TEST_SIZE; ++i) {
            TestStruct* obj = pool.allocate();
            new (obj) TestStruct(i, i * 1.0, "test");
            objects.push_back(obj);
        }

        // 释放对象
        for (TestStruct* obj : objects) {
            obj->~TestStruct();
            pool.deallocate(obj);
        }
    });

    // 测试 std::vector
    double vector_time = measure_time([&]() {
        std::vector<TestStruct> objects;
        objects.reserve(TEST_SIZE);

        // 分配对象
        for (size_t i = 0; i < TEST_SIZE; ++i) {
            objects.emplace_back(i, i * 1.0, "test");
        }

        // 释放对象（自动）
    });

    std::cout << "ObjectPool time: " << pool_time << " ms" << std::endl;
    std::cout << "std::vector time: " << vector_time << " ms" << std::endl;
    std::cout << "Speedup: " << (vector_time / pool_time) << "x" << std::endl;
    std::cout << "=========================================" << std::endl;

    // 测试内存碎片率
    std::cout << "Testing memory fragmentation..." << std::endl;

    double pool_frag_time = measure_time([&]() {
        hhb::core::ObjectPool<TestStruct> pool;
        std::vector<TestStruct*> objects;
        objects.reserve(TEST_SIZE);

        // 分配一半对象
        for (size_t i = 0; i < TEST_SIZE / 2; ++i) {
            TestStruct* obj = pool.allocate();
            new (obj) TestStruct(i, i * 1.0, "test");
            objects.push_back(obj);
        }

        // 释放一半对象
        for (size_t i = 0; i < objects.size() / 2; ++i) {
            objects[i]->~TestStruct();
            pool.deallocate(objects[i]);
        }

        // 重新分配对象
        for (size_t i = 0; i < TEST_SIZE / 2; ++i) {
            TestStruct* obj = pool.allocate();
            new (obj) TestStruct(i + TEST_SIZE / 2, (i + TEST_SIZE / 2) * 1.0, "test");
            objects.push_back(obj);
        }

        // 释放所有对象
        for (TestStruct* obj : objects) {
            obj->~TestStruct();
            pool.deallocate(obj);
        }
    });

    double vector_frag_time = measure_time([&]() {
        std::vector<TestStruct> objects;
        objects.reserve(TEST_SIZE);

        // 分配一半对象
        for (size_t i = 0; i < TEST_SIZE / 2; ++i) {
            objects.emplace_back(i, i * 1.0, "test");
        }

        // 释放一半对象
        objects.erase(objects.begin(), objects.begin() + objects.size() / 2);

        // 重新分配对象
        for (size_t i = 0; i < TEST_SIZE / 2; ++i) {
            objects.emplace_back(i + TEST_SIZE / 2, (i + TEST_SIZE / 2) * 1.0, "test");
        }
    });

    std::cout << "ObjectPool fragmentation test time: " << pool_frag_time << " ms" << std::endl;
    std::cout << "std::vector fragmentation test time: " << vector_frag_time << " ms" << std::endl;
    std::cout << "Fragmentation speedup: " << (vector_frag_time / pool_frag_time) << "x" << std::endl;

    return 0;
}
