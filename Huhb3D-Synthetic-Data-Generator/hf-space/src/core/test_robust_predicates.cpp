#include <iostream>
#include "robust_predicates.h"

int main() {
    using namespace hhb::core::predicates;

    // 测试 orient2d
    std::cout << "Testing orient2d..." << std::endl;
    real a2d[2] = {0.0, 0.0};
    real b2d[2] = {1.0, 0.0};
    real c2d_left[2] = {0.5, 1.0};   // 左侧
    real c2d_right[2] = {0.5, -1.0};  // 右侧
    real c2d_colinear[2] = {0.5, 0.0}; // 共线

    int result_left = orient2d(a2d, b2d, c2d_left);
    int result_right = orient2d(a2d, b2d, c2d_right);
    int result_colinear = orient2d(a2d, b2d, c2d_colinear);

    std::cout << "Left point: " << result_left << " (expected: 1)" << std::endl;
    std::cout << "Right point: " << result_right << " (expected: -1)" << std::endl;
    std::cout << "Colinear point: " << result_colinear << " (expected: 0)" << std::endl;

    // 测试 orient3d
    std::cout << "\nTesting orient3d..." << std::endl;
    real a3d[3] = {0.0, 0.0, 0.0};
    real b3d[3] = {1.0, 0.0, 0.0};
    real c3d[3] = {0.0, 1.0, 0.0};
    real d3d_above[3] = {0.0, 0.0, 1.0};   // 上方
    real d3d_below[3] = {0.0, 0.0, -1.0};  // 下方
    real d3d_coplanar[3] = {0.5, 0.5, 0.0}; // 共面

    int result_above = orient3d(a3d, b3d, c3d, d3d_above);
    int result_below = orient3d(a3d, b3d, c3d, d3d_below);
    int result_coplanar = orient3d(a3d, b3d, c3d, d3d_coplanar);

    std::cout << "Above point: " << result_above << " (expected: 1)" << std::endl;
    std::cout << "Below point: " << result_below << " (expected: -1)" << std::endl;
    std::cout << "Coplanar point: " << result_coplanar << " (expected: 0)" << std::endl;

    // 测试 incircle
    std::cout << "\nTesting incircle..." << std::endl;
    real a_circle[2] = {0.0, 0.0};
    real b_circle[2] = {1.0, 0.0};
    real c_circle[2] = {0.0, 1.0};
    real d_circle_inside[2] = {0.25, 0.25};   // 内部
    real d_circle_outside[2] = {1.0, 1.0};     // 外部
    real d_circle_on[2] = {0.5, 0.5};           // 圆上

    int result_inside = incircle(a_circle, b_circle, c_circle, d_circle_inside);
    int result_outside = incircle(a_circle, b_circle, c_circle, d_circle_outside);
    int result_on = incircle(a_circle, b_circle, c_circle, d_circle_on);

    std::cout << "Inside point: " << result_inside << " (expected: 1)" << std::endl;
    std::cout << "Outside point: " << result_outside << " (expected: -1)" << std::endl;
    std::cout << "On circle point: " << result_on << " (expected: 0)" << std::endl;

    // 测试 insphere
    std::cout << "\nTesting insphere..." << std::endl;
    real a_sphere[3] = {0.0, 0.0, 0.0};
    real b_sphere[3] = {1.0, 0.0, 0.0};
    real c_sphere[3] = {0.0, 1.0, 0.0};
    real d_sphere[3] = {0.0, 0.0, 1.0};
    real e_sphere_inside[3] = {0.25, 0.25, 0.25};   // 内部
    real e_sphere_outside[3] = {1.0, 1.0, 1.0};     // 外部

    int result_sphere_inside = insphere(a_sphere, b_sphere, c_sphere, d_sphere, e_sphere_inside);
    int result_sphere_outside = insphere(a_sphere, b_sphere, c_sphere, d_sphere, e_sphere_outside);

    std::cout << "Inside point: " << result_sphere_inside << " (expected: 1)" << std::endl;
    std::cout << "Outside point: " << result_sphere_outside << " (expected: -1)" << std::endl;

    // 测试鲁棒性：处理微小尺度下的浮点误差
    std::cout << "\nTesting robustness..." << std::endl;
    real a_robust[3] = {0.0, 0.0, 0.0};
    real b_robust[3] = {1.0, 0.0, 0.0};
    real c_robust[3] = {0.0, 1.0, 0.0};
    real d_robust[3] = {0.0, 0.0, 1e-16}; // 非常接近共面

    int result_robust = orient3d(a_robust, b_robust, c_robust, d_robust);
    std::cout << "Robust test: " << result_robust << " (expected: 1 or -1, not 0)" << std::endl;

    return 0;
}
