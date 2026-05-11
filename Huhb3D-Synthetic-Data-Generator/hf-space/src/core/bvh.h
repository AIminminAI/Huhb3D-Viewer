#ifndef NOMINMAX
#define NOMINMAX
#endif

#pragma once

#include <array>
#include <vector>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <memory>
#include <limits>
#include <cstring>
#include "object_pool.h"
#include "stl_parser.h"

namespace hhb {
namespace core {

// Bounding box structure
struct Bounds {
    float min[3];
    float max[3];

    Bounds() {
        min[0] = min[1] = min[2] = 1e38f;
        max[0] = max[1] = max[2] = -1e38f;
    }

    Bounds(const float* min, const float* max) {
        std::memcpy(this->min, min, sizeof(float) * 3);
        std::memcpy(this->max, max, sizeof(float) * 3);
    }

    // Expand bounding box to include another point
    void expand(const float* point) {
        for (int i = 0; i < 3; ++i) {
            if (point[i] < min[i]) min[i] = point[i];
            if (point[i] > max[i]) max[i] = point[i];
        }
    }

    // Expand bounding box to include another bounding box
    void expand(const Bounds& other) {
        for (int i = 0; i < 3; ++i) {
            if (other.min[i] < min[i]) min[i] = other.min[i];
            if (other.max[i] > max[i]) max[i] = other.max[i];
        }
    }

    // Calculate surface area of bounding box
    float surface_area() const {
        float dx = max[0] - min[0];
        float dy = max[1] - min[1];
        float dz = max[2] - min[2];
        return 2.0f * (dx * dy + dy * dz + dz * dx);
    }

    // Calculate center of bounding box
    void center(float* c) const {
        for (int i = 0; i < 3; ++i) {
            c[i] = (min[i] + max[i]) * 0.5f;
        }
    }
};

// BVH node structure (64 bytes)
struct BVHNode {
    Bounds bounds;     // 24 bytes
    uint32_t left;     // 4 bytes - Left child offset or triangle index
    uint32_t right;    // 4 bytes - Right child offset or triangle count
    uint8_t split_axis; // 1 byte - Split axis
    uint8_t is_leaf;    // 1 byte - Whether it's a leaf node
    uint16_t padding;   // 2 bytes - Padding

    BVHNode() : left(0), right(0), split_axis(0), is_leaf(0), padding(0) {}
};

// BVH class
class BVH {
public:
    BVH() = default;
    ~BVH() = default;

    // Build BVH
    void build(std::vector<Triangle*>& triangles);

    // Ray-BVH intersection
    bool intersect(const float* ray_origin, const float* ray_direction, float& t_hit, Triangle*& hit_triangle) const;

    // Get BVH node count
    size_t node_count() const {
        return nodes_.size();
    }

    // Get BVH tree depth
    int depth() const {
        return tree_depth_;
    }

    // Get root bounding box
    Bounds get_root_bounds() const {
        if (nodes_.empty()) return Bounds();
        return nodes_[0].bounds;
    }

private:
    // BVH build parameters
    static constexpr size_t MAX_PRIMITIVES_PER_LEAF = 4;
    static constexpr float SAH_COST = 1.0f;
    static constexpr float TRAVERSAL_COST = 0.125f;

    // BVH build recursive function
    uint32_t build_recursive(std::vector<Triangle*>& triangles, size_t start, size_t end, int current_depth);

    // Calculate triangle bounding box
    Bounds compute_bounds(const Triangle* triangle) const;

    // SAH split algorithm
    uint32_t split_sah(std::vector<Triangle*>& triangles, size_t start, size_t end, Bounds& bounds, uint8_t& split_axis);

    // Ray-bounding box intersection
    bool intersect_bounds(const float* ray_origin, const float* ray_direction, const Bounds& bounds, float& t_min, float& t_max) const;

    // Ray-triangle intersection
    bool intersect_triangle(const float* ray_origin, const float* ray_direction, const Triangle* triangle, float& t_hit) const;

    std::vector<BVHNode> nodes_;        // BVH nodes
    std::vector<Triangle*> triangles_;   // Triangle pointers
    int tree_depth_;                     // BVH tree depth
};

} // namespace core
} // namespace hhb