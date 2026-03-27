#pragma once

namespace glm {

// 简化版的 vec3 类
template<typename T>
class vec3 {
public:
    T x, y, z;
    
    vec3() : x(0), y(0), z(0) {}
    vec3(T x, T y, T z) : x(x), y(y), z(z) {}
    
    vec3 operator+(const vec3& other) const {
        return vec3(x + other.x, y + other.y, z + other.z);
    }
    
    vec3 operator-(const vec3& other) const {
        return vec3(x - other.x, y - other.y, z - other.z);
    }
    
    vec3 operator*(T scalar) const {
        return vec3(x * scalar, y * scalar, z * scalar);
    }
    
    T dot(const vec3& other) const {
        return x * other.x + y * other.y + z * other.z;
    }
    
    vec3 normalize() const {
        T length = sqrt(x * x + y * y + z * z);
        if (length > 0) {
            return vec3(x / length, y / length, z / length);
        }
        return *this;
    }
    
    vec3 cross(const vec3& other) const {
        return vec3(
            y * other.z - z * other.y,
            z * other.x - x * other.z,
            x * other.y - y * other.x
        );
    }
};

// 简化版的 mat4 类
template<typename T>
class mat4 {
public:
    T data[16];
    
    mat4() {
        // 初始化单位矩阵
        for (int i = 0; i < 16; i++) {
            data[i] = (i % 5 == 0) ? 1 : 0;
        }
    }
    
    mat4(T m00, T m01, T m02, T m03,
         T m10, T m11, T m12, T m13,
         T m20, T m21, T m22, T m23,
         T m30, T m31, T m32, T m33) {
        data[0] = m00; data[1] = m01; data[2] = m02; data[3] = m03;
        data[4] = m10; data[5] = m11; data[6] = m12; data[7] = m13;
        data[8] = m20; data[9] = m21; data[10] = m22; data[11] = m23;
        data[12] = m30; data[13] = m31; data[14] = m32; data[15] = m33;
    }
    
    mat4 operator*(const mat4& other) const {
        mat4 result;
        for (int i = 0; i < 4; i++) {
            for (int j = 0; j < 4; j++) {
                result.data[i * 4 + j] = 0;
                for (int k = 0; k < 4; k++) {
                    result.data[i * 4 + j] += data[i * 4 + k] * other.data[k * 4 + j];
                }
            }
        }
        return result;
    }
    
    vec3<T> operator*(const vec3<T>& v) const {
        return vec3<T>(
            data[0] * v.x + data[1] * v.y + data[2] * v.z + data[3],
            data[4] * v.x + data[5] * v.y + data[6] * v.z + data[7],
            data[8] * v.x + data[9] * v.y + data[10] * v.z + data[11]
        );
    }
};

// 类型别名
typedef vec3<float> vec3f;
typedef mat4<float> mat4f;

} // namespace glm