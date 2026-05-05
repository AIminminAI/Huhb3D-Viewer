#pragma once

#include <vector>
#include <string>
#include <optional>
#include <unordered_map>
#include "stl_parser.h"
#include "bvh.h"

namespace hhb {
namespace core {

struct Point {
    float x, y, z;
    
    Point() : x(0), y(0), z(0) {}
    Point(float x, float y, float z) : x(x), y(y), z(z) {}
    Point(const float* arr) : x(arr[0]), y(arr[1]), z(arr[2]) {}
};

struct Ray {
    Point origin;
    Point direction;
    
    Ray() {}
    Ray(const Point& origin, const Point& direction) : origin(origin), direction(direction) {}
};

struct Intersection {
    Point point;
    Triangle* triangle;
    float distance;
    
    Intersection() : distance(0), triangle(nullptr) {}
    Intersection(const Point& point, Triangle* triangle, float distance) 
        : point(point), triangle(triangle), distance(distance) {}
};

class GeometryAPI {
public:
    GeometryAPI() = default;
    ~GeometryAPI() = default;
    
    bool loadModel(const std::string& filename);
    
    void loadFromPool(ObjectPool<Triangle>& pool);
    
    std::vector<Triangle> getAllTriangles() const;
    
    std::vector<Triangle*> getThinParts(float max_thickness_mm) const;
    
    std::vector<Triangle*> getCurvedSurfaces(float curvature_threshold) const;
    
    std::vector<Triangle*> getSharpEdges(float angle_threshold_deg) const;
    
    std::vector<Triangle*> getFlatSurfaces(float flatness_threshold) const;
    
    std::vector<Triangle*> getHighCurvatureRegions(float curvature_threshold) const;
    
    std::unordered_map<Triangle*, int> getTriangleIndexMap() const;
    
    std::vector<Intersection> getIntersectingPoints(const Ray& ray) const;
    
    size_t getTriangleCount() const;
    
    Bounds getModelBounds() const;
    
    int getBVHDepth() const;
    
    void clear();
    
private:
    ObjectPool<Triangle> triangle_pool_;
    std::vector<Triangle*> triangles_;
    BVH bvh_;
    bool model_loaded_ = false;
    
    float calculateThickness(const Triangle* t1, const Triangle* t2) const;
    
    Triangle copyTriangle(const Triangle* tri) const;
    
    float triangleArea(const Triangle* t) const;
    
    void triangleNormal(const Triangle* t, float* out_normal) const;
    
    float dotProduct(const float* a, const float* b) const;
    
    void crossProduct(const float* a, const float* b, float* out) const;
    
    float vectorLength(const float* v) const;
    
    void normalize(float* v) const;
    
    float angleBetweenNormals(const float* n1, const float* n2) const;
    
    float computeTriangleCurvature(const Triangle* t, const std::vector<Triangle*>& neighbors) const;
    
    void findNeighborTriangles(const Triangle* t, std::vector<Triangle*>& neighbors, float distance_threshold) const;
};

} // namespace core
} // namespace hhb
