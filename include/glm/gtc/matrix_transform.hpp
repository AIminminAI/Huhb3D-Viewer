#pragma once

#include "../glm.hpp"

namespace glm {

// 简化版的旋转矩阵生成函数
template<typename T>
mat4<T> rotate(const mat4<T>& m, T angle, const vec3<T>& axis) {
    // 简化实现，返回单位矩阵
    return m;
}

// 简化版的平移矩阵生成函数
template<typename T>
mat4<T> translate(const mat4<T>& m, const vec3<T>& v) {
    // 简化实现，返回单位矩阵
    return m;
}

// 简化版的缩放矩阵生成函数
template<typename T>
mat4<T> scale(const mat4<T>& m, const vec3<T>& v) {
    // 简化实现，返回单位矩阵
    return m;
}

} // namespace glm