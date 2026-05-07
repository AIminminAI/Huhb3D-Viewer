#include <benchmark/benchmark.h>
#include <vector>
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

// 测试 ObjectPool 分配
static void BM_ObjectPool_Allocate(benchmark::State& state) {
    hhb::core::ObjectPool<TestStruct> pool;
    std::vector<TestStruct*> objects;
    objects.reserve(state.range(0));

    for (auto _ : state) {
        for (int i = 0; i < state.range(0); ++i) {
            TestStruct* obj = pool.allocate();
            new (obj) TestStruct(i, i * 1.0, "test");
            objects.push_back(obj);
        }

        // 释放所有对象
        for (TestStruct* obj : objects) {
            obj->~TestStruct();
            pool.deallocate(obj);
        }
        objects.clear();
    }
}

// 测试 std::vector 分配
static void BM_Vector_Allocate(benchmark::State& state) {
    std::vector<TestStruct> objects;

    for (auto _ : state) {
        objects.reserve(state.range(0));
        for (int i = 0; i < state.range(0); ++i) {
            objects.emplace_back(i, i * 1.0, "test");
        }
        objects.clear();
    }
}

// 测试内存碎片率（通过分配和释放模式）
static void BM_ObjectPool_Fragmentation(benchmark::State& state) {
    hhb::core::ObjectPool<TestStruct> pool;
    std::vector<TestStruct*> objects;
    objects.reserve(state.range(0));

    for (auto _ : state) {
        // 分配一半对象
        for (int i = 0; i < state.range(0) / 2; ++i) {
            TestStruct* obj = pool.allocate();
            new (obj) TestStruct(i, i * 1.0, "test");
            objects.push_back(obj);
        }

        // 释放一半对象
        for (int i = 0; i < objects.size() / 2; ++i) {
            objects[i]->~TestStruct();
            pool.deallocate(objects[i]);
        }

        // 重新分配对象
        for (int i = 0; i < state.range(0) / 2; ++i) {
            TestStruct* obj = pool.allocate();
            new (obj) TestStruct(i + state.range(0) / 2, (i + state.range(0) / 2) * 1.0, "test");
            objects.push_back(obj);
        }

        // 释放所有对象
        for (TestStruct* obj : objects) {
            obj->~TestStruct();
            pool.deallocate(obj);
        }
        objects.clear();
    }
}

static void BM_Vector_Fragmentation(benchmark::State& state) {
    std::vector<TestStruct> objects;

    for (auto _ : state) {
        // 分配一半对象
        objects.reserve(state.range(0));
        for (int i = 0; i < state.range(0) / 2; ++i) {
            objects.emplace_back(i, i * 1.0, "test");
        }

        // 释放一半对象
        objects.erase(objects.begin(), objects.begin() + objects.size() / 2);

        // 重新分配对象
        for (int i = 0; i < state.range(0) / 2; ++i) {
            objects.emplace_back(i + state.range(0) / 2, (i + state.range(0) / 2) * 1.0, "test");
        }

        objects.clear();
    }
}

// 注册测试
BENCHMARK(BM_ObjectPool_Allocate)->RangeMultiplier(10)->Range(1000, 10000000);
BENCHMARK(BM_Vector_Allocate)->RangeMultiplier(10)->Range(1000, 10000000);
BENCHMARK(BM_ObjectPool_Fragmentation)->RangeMultiplier(10)->Range(1000, 10000000);
BENCHMARK(BM_Vector_Fragmentation)->RangeMultiplier(10)->Range(1000, 10000000);

BENCHMARK_MAIN();
