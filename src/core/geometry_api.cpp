#include "geometry_api.h"
#include <iostream>
#include <cmath>
#include <algorithm>
#include <cstring>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

namespace hhb {
namespace core {

bool GeometryAPI::loadModel(const std::string& filename) {
    try {
        clear();
        
        StlParser parser;
        ParserResult result = parser.parse(filename, triangle_pool_);
        
        if (!result.success) {
            std::cerr << "Failed to load model: " << result.error << std::endl;
            return false;
        }
        
        triangles_.clear();
        triangle_pool_.for_each([&](Triangle* tri) {
            triangles_.push_back(tri);
        });
        
        bvh_.build(triangles_);
        
        model_loaded_ = true;
        std::cout << "Model loaded successfully: " << triangles_.size() << " triangles" << std::endl;
        std::cout << "BVH built with " << bvh_.node_count() << " nodes, depth: " << bvh_.depth() << std::endl;
        
        return true;
    } catch (const std::exception& e) {
        std::cerr << "Exception loading model: " << e.what() << std::endl;
        return false;
    }
}

void GeometryAPI::loadFromPool(ObjectPool<Triangle>& pool) {
    clear();
    
    triangles_.clear();
    pool.for_each([&](Triangle* tri) {
        triangles_.push_back(tri);
    });
    
    bvh_.build(triangles_);
    
    model_loaded_ = true;
    std::cout << "GeometryAPI::loadFromPool: " << triangles_.size() << " triangles loaded from external pool" << std::endl;
    std::cout << "BVH built with " << bvh_.node_count() << " nodes, depth: " << bvh_.depth() << std::endl;
}

std::vector<Triangle> GeometryAPI::getAllTriangles() const {
    std::vector<Triangle> result;
    if (!model_loaded_) {
        return result;
    }
    
    result.reserve(triangles_.size());
    for (const auto& tri : triangles_) {
        result.push_back(copyTriangle(tri));
    }
    
    return result;
}

std::vector<Triangle*> GeometryAPI::getThinParts(float max_thickness_mm) const {
    std::vector<Triangle*> thin_parts;
    if (!model_loaded_) {
        return thin_parts;
    }
    
    for (size_t i = 0; i < triangles_.size(); ++i) {
        const Triangle* t1 = triangles_[i];
        bool is_thin = false;
        
        for (size_t j = i + 1; j < triangles_.size(); ++j) {
            const Triangle* t2 = triangles_[j];
            float thickness = calculateThickness(t1, t2);
            
            if (thickness <= max_thickness_mm) {
                is_thin = true;
                break;
            }
        }
        
        if (is_thin) {
            thin_parts.push_back(const_cast<Triangle*>(t1));
        }
    }
    
    return thin_parts;
}

std::vector<Triangle*> GeometryAPI::getCurvedSurfaces(float curvature_threshold) const {
    std::vector<Triangle*> curved_parts;
    if (!model_loaded_) {
        std::cout << "getCurvedSurfaces: model not loaded!" << std::endl;
        return curved_parts;
    }
    
    std::cout << "getCurvedSurfaces: starting with threshold=" << curvature_threshold 
              << ", triangles=" << triangles_.size() << std::endl;
    
    Bounds bounds = bvh_.get_root_bounds();
    float sizeX = bounds.max[0] - bounds.min[0];
    float sizeY = bounds.max[1] - bounds.min[1];
    float sizeZ = bounds.max[2] - bounds.min[2];
    float maxDim = std::max({sizeX, sizeY, sizeZ});
    float neighbor_dist = maxDim * 0.15f;
    
    int checked = 0;
    float max_curvature_found = 0.0f;
    float min_curvature_found = 1e38f;
    
    for (size_t i = 0; i < triangles_.size(); ++i) {
        const Triangle* t = triangles_[i];
        
        std::vector<Triangle*> neighbors;
        findNeighborTriangles(t, neighbors, neighbor_dist);
        
        if (neighbors.size() >= 1) {
            float curvature = computeTriangleCurvature(t, neighbors);
            if (curvature > max_curvature_found) max_curvature_found = curvature;
            if (curvature < min_curvature_found) min_curvature_found = curvature;
            checked++;
            
            if (curvature > curvature_threshold) {
                curved_parts.push_back(const_cast<Triangle*>(t));
            }
        }
    }
    
    std::cout << "getCurvedSurfaces: checked=" << checked 
              << ", curvature range=[" << min_curvature_found << ", " << max_curvature_found << "]"
              << ", found=" << curved_parts.size() << std::endl;
    return curved_parts;
}

std::vector<Triangle*> GeometryAPI::getSharpEdges(float angle_threshold_deg) const {
    std::vector<Triangle*> sharp_parts;
    if (!model_loaded_) {
        return sharp_parts;
    }
    
    float angle_threshold_rad = angle_threshold_deg * static_cast<float>(M_PI) / 180.0f;
    
    Bounds bounds = bvh_.get_root_bounds();
    float sizeX = bounds.max[0] - bounds.min[0];
    float sizeY = bounds.max[1] - bounds.min[1];
    float sizeZ = bounds.max[2] - bounds.min[2];
    float maxDim = std::max({sizeX, sizeY, sizeZ});
    float neighbor_dist = maxDim * 0.02f;
    
    for (size_t i = 0; i < triangles_.size(); ++i) {
        const Triangle* t = triangles_[i];
        float n1[3] = {t->normal[0], t->normal[1], t->normal[2]};
        float len = vectorLength(n1);
        if (len < 1e-8f) continue;
        normalize(n1);
        
        bool has_sharp = false;
        
        for (size_t j = 0; j < triangles_.size(); ++j) {
            if (i == j) continue;
            const Triangle* t2 = triangles_[j];
            
            const float* v1[3] = {t->vertex1, t->vertex2, t->vertex3};
            const float* v2[3] = {t2->vertex1, t2->vertex2, t2->vertex3};
            
            bool adjacent = false;
            for (int a = 0; a < 3 && !adjacent; ++a) {
                for (int b = 0; b < 3 && !adjacent; ++b) {
                    float dx = v1[a][0] - v2[b][0];
                    float dy = v1[a][1] - v2[b][1];
                    float dz = v1[a][2] - v2[b][2];
                    float dist = std::sqrt(dx*dx + dy*dy + dz*dz);
                    if (dist < neighbor_dist) {
                        adjacent = true;
                    }
                }
            }
            
            if (adjacent) {
                float n2[3] = {t2->normal[0], t2->normal[1], t2->normal[2]};
                float len2 = vectorLength(n2);
                if (len2 < 1e-8f) continue;
                normalize(n2);
                
                float angle = angleBetweenNormals(n1, n2);
                if (angle > angle_threshold_rad) {
                    has_sharp = true;
                    break;
                }
            }
        }
        
        if (has_sharp) {
            sharp_parts.push_back(const_cast<Triangle*>(t));
        }
    }
    
    std::cout << "Found " << sharp_parts.size() << " sharp edge triangles (angle_threshold=" << angle_threshold_deg << "deg)" << std::endl;
    return sharp_parts;
}

std::vector<Triangle*> GeometryAPI::getFlatSurfaces(float flatness_threshold) const {
    std::vector<Triangle*> flat_parts;
    if (!model_loaded_) {
        return flat_parts;
    }
    
    Bounds bounds = bvh_.get_root_bounds();
    float sizeX = bounds.max[0] - bounds.min[0];
    float sizeY = bounds.max[1] - bounds.min[1];
    float sizeZ = bounds.max[2] - bounds.min[2];
    float maxDim = std::max({sizeX, sizeY, sizeZ});
    float neighbor_dist = maxDim * 0.15f;
    
    for (size_t i = 0; i < triangles_.size(); ++i) {
        const Triangle* t = triangles_[i];
        
        std::vector<Triangle*> neighbors;
        findNeighborTriangles(t, neighbors, neighbor_dist);
        
        if (neighbors.size() >= 2) {
            float curvature = computeTriangleCurvature(t, neighbors);
            if (curvature < flatness_threshold) {
                flat_parts.push_back(const_cast<Triangle*>(t));
            }
        }
    }
    
    std::cout << "Found " << flat_parts.size() << " flat surface triangles (threshold=" << flatness_threshold << ")" << std::endl;
    return flat_parts;
}

std::vector<Triangle*> GeometryAPI::getHighCurvatureRegions(float curvature_threshold) const {
    return getCurvedSurfaces(curvature_threshold);
}

std::vector<Intersection> GeometryAPI::getIntersectingPoints(const Ray& ray) const {
    std::vector<Intersection> intersections;
    if (!model_loaded_) {
        return intersections;
    }
    
    float ray_origin[3] = {ray.origin.x, ray.origin.y, ray.origin.z};
    float ray_direction[3] = {ray.direction.x, ray.direction.y, ray.direction.z};
    
    float t_hit = 1e38f;
    Triangle* hit_triangle = nullptr;
    
    if (bvh_.intersect(ray_origin, ray_direction, t_hit, hit_triangle)) {
        float hit_point[3] = {
            ray_origin[0] + ray_direction[0] * t_hit,
            ray_origin[1] + ray_direction[1] * t_hit,
            ray_origin[2] + ray_direction[2] * t_hit
        };
        
        intersections.emplace_back(Point(hit_point), hit_triangle, t_hit);
    }
    
    return intersections;
}

size_t GeometryAPI::getTriangleCount() const {
    return triangles_.size();
}

Bounds GeometryAPI::getModelBounds() const {
    if (!model_loaded_) {
        return Bounds();
    }
    
    return bvh_.get_root_bounds();
}

int GeometryAPI::getBVHDepth() const {
    if (!model_loaded_) {
        return 0;
    }
    
    return bvh_.depth();
}

void GeometryAPI::clear() {
    triangles_.clear();
    model_loaded_ = false;
}

float GeometryAPI::calculateThickness(const Triangle* t1, const Triangle* t2) const {
    float min_distance = 1e38f;
    
    const float* v1[3] = {t1->vertex1, t1->vertex2, t1->vertex3};
    const float* v2[3] = {t2->vertex1, t2->vertex2, t2->vertex3};
    
    for (int i = 0; i < 3; ++i) {
        for (int j = 0; j < 3; ++j) {
            float dx = v1[i][0] - v2[j][0];
            float dy = v1[i][1] - v2[j][1];
            float dz = v1[i][2] - v2[j][2];
            float distance = std::sqrt(dx*dx + dy*dy + dz*dz);
            
            if (distance < min_distance) {
                min_distance = distance;
            }
        }
    }
    
    return min_distance;
}

Triangle GeometryAPI::copyTriangle(const Triangle* tri) const {
    Triangle result;
    std::memcpy(&result, tri, sizeof(Triangle));
    return result;
}

float GeometryAPI::triangleArea(const Triangle* t) const {
    float e1[3] = {
        t->vertex2[0] - t->vertex1[0],
        t->vertex2[1] - t->vertex1[1],
        t->vertex2[2] - t->vertex1[2]
    };
    float e2[3] = {
        t->vertex3[0] - t->vertex1[0],
        t->vertex3[1] - t->vertex1[1],
        t->vertex3[2] - t->vertex1[2]
    };
    float cross[3];
    crossProduct(e1, e2, cross);
    return vectorLength(cross) * 0.5f;
}

void GeometryAPI::triangleNormal(const Triangle* t, float* out_normal) const {
    float e1[3] = {
        t->vertex2[0] - t->vertex1[0],
        t->vertex2[1] - t->vertex1[1],
        t->vertex2[2] - t->vertex1[2]
    };
    float e2[3] = {
        t->vertex3[0] - t->vertex1[0],
        t->vertex3[1] - t->vertex1[1],
        t->vertex3[2] - t->vertex1[2]
    };
    crossProduct(e1, e2, out_normal);
    float len = vectorLength(out_normal);
    if (len > 1e-8f) {
        out_normal[0] /= len;
        out_normal[1] /= len;
        out_normal[2] /= len;
    }
}

float GeometryAPI::dotProduct(const float* a, const float* b) const {
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2];
}

void GeometryAPI::crossProduct(const float* a, const float* b, float* out) const {
    out[0] = a[1]*b[2] - a[2]*b[1];
    out[1] = a[2]*b[0] - a[0]*b[2];
    out[2] = a[0]*b[1] - a[1]*b[0];
}

float GeometryAPI::vectorLength(const float* v) const {
    return std::sqrt(v[0]*v[0] + v[1]*v[1] + v[2]*v[2]);
}

void GeometryAPI::normalize(float* v) const {
    float len = vectorLength(v);
    if (len > 1e-8f) {
        v[0] /= len;
        v[1] /= len;
        v[2] /= len;
    }
}

float GeometryAPI::angleBetweenNormals(const float* n1, const float* n2) const {
    float d = dotProduct(n1, n2);
    if (d > 1.0f) d = 1.0f;
    if (d < -1.0f) d = -1.0f;
    return std::acos(d);
}

float GeometryAPI::computeTriangleCurvature(const Triangle* t, const std::vector<Triangle*>& neighbors) const {
    float n1[3] = {t->normal[0], t->normal[1], t->normal[2]};
    float len = vectorLength(n1);
    if (len < 1e-8f) return 0.0f;
    normalize(n1);
    
    float total_angle = 0.0f;
    int count = 0;
    
    for (const Triangle* neighbor : neighbors) {
        float n2[3] = {neighbor->normal[0], neighbor->normal[1], neighbor->normal[2]};
        float len2 = vectorLength(n2);
        if (len2 < 1e-8f) continue;
        normalize(n2);
        
        float angle = angleBetweenNormals(n1, n2);
        total_angle += angle;
        count++;
    }
    
    if (count == 0) return 0.0f;
    return total_angle / static_cast<float>(count);
}

void GeometryAPI::findNeighborTriangles(const Triangle* t, std::vector<Triangle*>& neighbors, float distance_threshold) const {
    float center[3] = {
        (t->vertex1[0] + t->vertex2[0] + t->vertex3[0]) / 3.0f,
        (t->vertex1[1] + t->vertex2[1] + t->vertex3[1]) / 3.0f,
        (t->vertex1[2] + t->vertex2[2] + t->vertex3[2]) / 3.0f
    };
    
    for (size_t i = 0; i < triangles_.size(); ++i) {
        if (triangles_[i] == t) continue;
        
        const Triangle* other = triangles_[i];
        float other_center[3] = {
            (other->vertex1[0] + other->vertex2[0] + other->vertex3[0]) / 3.0f,
            (other->vertex1[1] + other->vertex2[1] + other->vertex3[1]) / 3.0f,
            (other->vertex1[2] + other->vertex2[2] + other->vertex3[2]) / 3.0f
        };
        
        float dx = center[0] - other_center[0];
        float dy = center[1] - other_center[1];
        float dz = center[2] - other_center[2];
        float dist = std::sqrt(dx*dx + dy*dy + dz*dz);
        
        if (dist < distance_threshold) {
            neighbors.push_back(const_cast<Triangle*>(other));
        }
    }
}

} // namespace core
} // namespace hhb
