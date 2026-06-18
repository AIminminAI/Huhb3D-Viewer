#include "bvh.h"
#include <algorithm>
#include <cmath>

namespace hhb {
namespace core {

// Calculate triangle bounding box
Bounds BVH::compute_bounds(const Triangle* triangle) const {
    Bounds bounds;
    bounds.expand(triangle->vertex1);
    bounds.expand(triangle->vertex2);
    bounds.expand(triangle->vertex3);
    return bounds;
}

// SAH split algorithm
uint32_t BVH::split_sah(std::vector<Triangle*>& triangles, size_t start, size_t end, Bounds& bounds, uint8_t& split_axis) {
    // Calculate best split axis
    float centroid[3];
    bounds.center(centroid);
    
    // Calculate extent for each axis
    float extent[3];
    for (int i = 0; i < 3; ++i) {
        extent[i] = bounds.max[i] - bounds.min[i];
    }
    
    // Select longest axis as split axis
    split_axis = 0;
    if (extent[1] > extent[split_axis]) split_axis = 1;
    if (extent[2] > extent[split_axis]) split_axis = 2;

    if (extent[split_axis] <= 1e-12f) {
        return static_cast<uint32_t>(start + (end - start) / 2);
    }
    
    // Sort triangles
    std::sort(triangles.begin() + start, triangles.begin() + end, [split_axis](const Triangle* a, const Triangle* b) {
        Bounds bounds_a, bounds_b;
        bounds_a.expand(a->vertex1);
        bounds_a.expand(a->vertex2);
        bounds_a.expand(a->vertex3);
        
        bounds_b.expand(b->vertex1);
        bounds_b.expand(b->vertex2);
        bounds_b.expand(b->vertex3);
        
        float centroid_a[3], centroid_b[3];
        bounds_a.center(centroid_a);
        bounds_b.center(centroid_b);
        
        return centroid_a[split_axis] < centroid_b[split_axis];
    });
    
    // Calculate best split point
    const size_t num_triangles = end - start;
    const size_t num_buckets = 16;
    
    struct BucketInfo {
        size_t count = 0;
        Bounds bounds;
    } buckets[num_buckets];
    
    // Statistics for each bucket
    for (size_t i = start; i < end; ++i) {
        const Triangle* triangle = triangles[i];
        Bounds tri_bounds = compute_bounds(triangle);
        float centroid[3];
        tri_bounds.center(centroid);
        
        float t = (centroid[split_axis] - bounds.min[split_axis]) / extent[split_axis];
        size_t bucket_index = (std::min)(static_cast<size_t>(t * num_buckets), num_buckets - 1);
        
        buckets[bucket_index].count++;
        buckets[bucket_index].bounds.expand(tri_bounds);
    }
    
    // Calculate cost for each possible split point
    float costs[num_buckets - 1];
    for (size_t i = 0; i < num_buckets - 1; ++i) {
        Bounds left_bounds, right_bounds;
        size_t left_count = 0, right_count = 0;
        
        for (size_t j = 0; j <= i; ++j) {
            left_bounds.expand(buckets[j].bounds);
            left_count += buckets[j].count;
        }
        
        for (size_t j = i + 1; j < num_buckets; ++j) {
            right_bounds.expand(buckets[j].bounds);
            right_count += buckets[j].count;
        }
        
        float left_sa = left_bounds.surface_area();
        float right_sa = right_bounds.surface_area();
        float total_sa = bounds.surface_area();
        
        costs[i] = TRAVERSAL_COST + (left_count * left_sa + right_count * right_sa) * SAH_COST / total_sa;
    }
    
    // Find minimum cost split point
    float min_cost = costs[0];
    size_t min_bucket = 0;
    for (size_t i = 1; i < num_buckets - 1; ++i) {
        if (costs[i] < min_cost) {
            min_cost = costs[i];
            min_bucket = i;
        }
    }
    
    // Find corresponding triangle index
    size_t split_index = start;
    for (size_t i = start; i < end; ++i) {
        const Triangle* triangle = triangles[i];
        Bounds tri_bounds = compute_bounds(triangle);
        float centroid[3];
        tri_bounds.center(centroid);
        
        float t = (centroid[split_axis] - bounds.min[split_axis]) / extent[split_axis];
        size_t bucket_index = (std::min)(static_cast<size_t>(t * num_buckets), num_buckets - 1);
        
        if (bucket_index > min_bucket) {
            split_index = i;
            break;
        }
    }
    
    // Ensure split point is valid
    if (split_index == start || split_index == end) {
        split_index = start + num_triangles / 2;
    }
    
    return static_cast<uint32_t>(split_index);
}

// BVH build recursive function
uint32_t BVH::build_recursive(std::vector<Triangle*>& triangles, size_t start, size_t end, int current_depth) {
    // Update tree depth
    if (current_depth > tree_depth_) {
        tree_depth_ = current_depth;
    }
    
    // Create new node
    uint32_t node_index = static_cast<uint32_t>(nodes_.size());
    nodes_.emplace_back();
    
    // Calculate bounding box for current triangles
    Bounds bounds;
    for (size_t i = start; i < end; ++i) {
        bounds.expand(compute_bounds(triangles[i]));
    }
    nodes_[node_index].bounds = bounds;
    
    size_t num_triangles = end - start;
    if (num_triangles <= MAX_PRIMITIVES_PER_LEAF) {
        // Create leaf node
        nodes_[node_index].is_leaf = 1;
        nodes_[node_index].left = static_cast<uint32_t>(triangles_.size());
        nodes_[node_index].right = static_cast<uint32_t>(num_triangles);
        
        // Store triangle pointers
        for (size_t i = start; i < end; ++i) {
            triangles_.push_back(triangles[i]);
        }
    } else {
        // Create internal node
        nodes_[node_index].is_leaf = 0;
        uint8_t split_axis;
        uint32_t split_index = split_sah(triangles, start, end, bounds, split_axis);
        nodes_[node_index].split_axis = split_axis;
        
        // Recursively build left and right subtrees
        uint32_t left = build_recursive(triangles, start, split_index, current_depth + 1);
        uint32_t right = build_recursive(triangles, split_index, end, current_depth + 1);
        nodes_[node_index].left = left;
        nodes_[node_index].right = right;
    }
    
    return node_index;
}

// Build BVH
void BVH::build(std::vector<Triangle*>& triangles) {
    nodes_.clear();
    triangles_.clear();
    tree_depth_ = 0;
    
    if (!triangles.empty()) {
        build_recursive(triangles, 0, triangles.size(), 0);
    }
}

// Ray-bounding box intersection
bool BVH::intersect_bounds(const float* ray_origin, const float* ray_direction, const Bounds& bounds, float& t_min, float& t_max) const {
    for (int i = 0; i < 3; ++i) {
        float inv_dir = 1.0f / ray_direction[i];
        float t0 = (bounds.min[i] - ray_origin[i]) * inv_dir;
        float t1 = (bounds.max[i] - ray_origin[i]) * inv_dir;
        
        if (inv_dir < 0.0f) {
            std::swap(t0, t1);
        }
        
        t_min = (std::max)(t_min, t0);
        t_max = (std::min)(t_max, t1);
        
        if (t_min > t_max) {
            return false;
        }
    }
    
    return true;
}

// Ray-triangle intersection
bool BVH::intersect_triangle(const float* ray_origin, const float* ray_direction, const Triangle* triangle, float& t_hit) const {
    const float* v0 = triangle->vertex1;
    const float* v1 = triangle->vertex2;
    const float* v2 = triangle->vertex3;
    
    // Calculate edge vectors
    float e1[3] = {v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2]};
    float e2[3] = {v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2]};
    
    // Calculate normal vector
    float pvec[3] = {
        ray_direction[1] * e2[2] - ray_direction[2] * e2[1],
        ray_direction[2] * e2[0] - ray_direction[0] * e2[2],
        ray_direction[0] * e2[1] - ray_direction[1] * e2[0]
    };
    
    float det = e1[0] * pvec[0] + e1[1] * pvec[1] + e1[2] * pvec[2];
    if (det < 1e-8f) {
        return false;
    }
    
    float inv_det = 1.0f / det;
    
    float tvec[3] = {
        ray_origin[0] - v0[0],
        ray_origin[1] - v0[1],
        ray_origin[2] - v0[2]
    };
    
    float u = (tvec[0] * pvec[0] + tvec[1] * pvec[1] + tvec[2] * pvec[2]) * inv_det;
    if (u < 0.0f || u > 1.0f) {
        return false;
    }
    
    float qvec[3] = {
        tvec[1] * e1[2] - tvec[2] * e1[1],
        tvec[2] * e1[0] - tvec[0] * e1[2],
        tvec[0] * e1[1] - tvec[1] * e1[0]
    };
    
    float v = (ray_direction[0] * qvec[0] + ray_direction[1] * qvec[1] + ray_direction[2] * qvec[2]) * inv_det;
    if (v < 0.0f || u + v > 1.0f) {
        return false;
    }
    
    t_hit = (e2[0] * qvec[0] + e2[1] * qvec[1] + e2[2] * qvec[2]) * inv_det;
    if (t_hit < 0.0f) {
        return false;
    }
    
    return true;
}

// Ray-BVH intersection
bool BVH::intersect(const float* ray_origin, const float* ray_direction, float& t_hit, Triangle*& hit_triangle) const {
    if (nodes_.empty()) {
        return false;
    }
    
    t_hit = 1e38f;
    hit_triangle = nullptr;
    
    // Use pre-allocated stack space to avoid recursion
    static constexpr size_t MAX_STACK_SIZE = 64;
    uint32_t stack[MAX_STACK_SIZE];
    int stack_ptr = 0;
    stack[stack_ptr++] = 0;
    
    while (stack_ptr > 0) {
        uint32_t node_index = stack[--stack_ptr];
        const BVHNode& node = nodes_[node_index];
        
        // Ray-bounding box intersection
        float t_min = 0.0f, t_max = 1e38f;
        if (!intersect_bounds(ray_origin, ray_direction, node.bounds, t_min, t_max)) {
            continue;
        }
        
        if (node.is_leaf) {
            // Traverse triangles in leaf node
            uint32_t start = node.left;
            uint32_t count = node.right;
            for (uint32_t i = 0; i < count; ++i) {
                Triangle* triangle = triangles_[start + i];
                float t;
                if (intersect_triangle(ray_origin, ray_direction, triangle, t) && t < t_hit) {
                    t_hit = t;
                    hit_triangle = triangle;
                }
            }
        } else {
            // Push children to stack in distance order
            float t_min_left = 0.0f, t_max_left = 1e38f;
            float t_min_right = 0.0f, t_max_right = 1e38f;
            
            intersect_bounds(ray_origin, ray_direction, nodes_[node.left].bounds, t_min_left, t_max_left);
            intersect_bounds(ray_origin, ray_direction, nodes_[node.right].bounds, t_min_right, t_max_right);
            
            if (t_min_left < t_min_right) {
                stack[stack_ptr++] = node.right;
                stack[stack_ptr++] = node.left;
            } else {
                stack[stack_ptr++] = node.left;
                stack[stack_ptr++] = node.right;
            }
        }
    }
    
    return hit_triangle != nullptr;
}

} // namespace core
} // namespace hhb
