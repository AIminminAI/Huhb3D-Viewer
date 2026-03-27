#pragma once

#include "../glm.hpp"

namespace glm {

// 简化版的获取矩阵数据指针的函数
template<typename T>
const T* value_ptr(const mat4<T>& m) {
    return m.data;
}

// 简化版的获取向量数据指针的函数
template<typename T>
const T* value_ptr(const vec3<T>& v) {
    return &v.x;
}

} // namespace glm