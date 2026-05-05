#pragma once

#include "ISkill.h"
#include "../render/render_manager.h"
#include <sstream>
#include <unordered_set>
#include <cmath>
#include <algorithm>

namespace hhb {
namespace skill {

struct GeometryAnomaly {
    int isolatedTriangles;
    int degenerateTriangles;
    int sharpEdges;
    int duplicateVertices;
    float minGap;
    float maxThickness;
    std::string description;
};

class AnalyzeGeometrySkill : public ISkill {
public:
    AnalyzeGeometrySkill(render::RenderManager& renderManager) : renderManager(renderManager) {}

    std::string execute(const std::string& params = "") override {
        auto spatialInfo = renderManager.getSpatialInfo();
        auto trianglePtrs = renderManager.getTrianglePtrs();

        GeometryAnomaly anomaly;
        anomaly.isolatedTriangles = 0;
        anomaly.degenerateTriangles = 0;
        anomaly.sharpEdges = 0;
        anomaly.duplicateVertices = 0;

        std::unordered_set<std::string> vertexSet;
        float minX = FLT_MAX, minY = FLT_MAX, minZ = FLT_MAX;
        float maxX = -FLT_MAX, maxY = -FLT_MAX, maxZ = -FLT_MAX;

        for (const auto& triangle : trianglePtrs) {
            float v1[3] = {triangle->vertex1[0], triangle->vertex1[1], triangle->vertex1[2]};
            float v2[3] = {triangle->vertex2[0], triangle->vertex2[1], triangle->vertex2[2]};
            float v3[3] = {triangle->vertex3[0], triangle->vertex3[1], triangle->vertex3[2]};

            minX = std::min({minX, v1[0], v2[0], v3[0]});
            minY = std::min({minY, v1[1], v2[1], v3[1]});
            minZ = std::min({minZ, v1[2], v2[2], v3[2]});
            maxX = std::max({maxX, v1[0], v2[0], v3[0]});
            maxY = std::max({maxY, v1[1], v2[1], v3[1]});
            maxZ = std::max({maxZ, v1[2], v2[2], v3[2]});

            float edge1[3] = {v2[0] - v1[0], v2[1] - v1[1], v2[2] - v1[2]};
            float edge2[3] = {v3[0] - v1[0], v3[1] - v1[1], v3[2] - v1[2]};
            float edge3[3] = {v3[0] - v2[0], v3[1] - v2[1], v3[2] - v2[2]};

            float len1 = std::sqrt(edge1[0]*edge1[0] + edge1[1]*edge1[1] + edge1[2]*edge1[2]);
            float len2 = std::sqrt(edge2[0]*edge2[0] + edge2[1]*edge2[1] + edge2[2]*edge2[2]);
            float len3 = std::sqrt(edge3[0]*edge3[0] + edge3[1]*edge3[1] + edge3[2]*edge3[2]);

            if (len1 < 0.001f || len2 < 0.001f || len3 < 0.001f) {
                anomaly.degenerateTriangles++;
            }

            if (len1 > 0.001f && len2 > 0.001f && len3 > 0.001f) {
                float dot12 = (edge1[0]*edge2[0] + edge1[1]*edge2[1] + edge1[2]*edge2[2]) / (len1 * len2);
                float dot13 = (edge1[0]*edge3[0] + edge1[1]*edge3[1] + edge1[2]*edge3[2]) / (len1 * len3);
                float dot23 = (edge2[0]*edge3[0] + edge2[1]*edge3[1] + edge2[2]*edge3[2]) / (len2 * len3);

                float minDot = std::min({dot12, dot13, dot23});
                float angle = std::acos(std::max(-1.0f, std::min(1.0f, minDot))) * 180.0f / 3.14159f;

                if (angle < 10.0f) {
                    anomaly.sharpEdges++;
                }
            }

            std::string key1 = std::to_string(v1[0]) + "," + std::to_string(v1[1]) + "," + std::to_string(v1[2]);
            std::string key2 = std::to_string(v2[0]) + "," + std::to_string(v2[1]) + "," + std::to_string(v2[2]);
            std::string key3 = std::to_string(v3[0]) + "," + std::to_string(v3[1]) + "," + std::to_string(v3[2]);

            if (vertexSet.count(key1)) anomaly.duplicateVertices++;
            if (vertexSet.count(key2)) anomaly.duplicateVertices++;
            if (vertexSet.count(key3)) anomaly.duplicateVertices++;
            vertexSet.insert(key1);
            vertexSet.insert(key2);
            vertexSet.insert(key3);
        }

        float modelSize = std::max({maxX - minX, maxY - minY, maxZ - minZ});
        anomaly.minGap = modelSize * 0.001f;
        anomaly.maxThickness = modelSize * 0.01f;

        int isolatedCount = 0;
        for (size_t i = 0; i < trianglePtrs.size(); ++i) {
            int neighborCount = 0;
            for (size_t j = 0; j < trianglePtrs.size() && j < 100; ++j) {
                if (i != j && areTrianglesAdjacent(trianglePtrs[i], trianglePtrs[j])) {
                    neighborCount++;
                    break;
                }
            }
            if (neighborCount == 0) {
                isolatedCount++;
            }
        }
        anomaly.isolatedTriangles = isolatedCount;

        std::stringstream ss;
        ss << "几何分析结果：\n";
        ss << "总三角面片数: " << trianglePtrs.size() << "\n";

        if (trianglePtrs.empty()) {
            ss << "警告: 模型为空\n";
        } else {
            if (anomaly.degenerateTriangles > 0) {
                ss << "退化三角形: " << anomaly.degenerateTriangles << " (过小或重叠)\n";
            }
            if (anomaly.sharpEdges > 0) {
                ss << "锐角边: " << anomaly.sharpEdges << " (角度<10度)\n";
            }
            if (anomaly.duplicateVertices > 0) {
                ss << "重复顶点: " << anomaly.duplicateVertices << "\n";
            }
            if (anomaly.isolatedTriangles > 0) {
                ss << "孤立三角形: " << anomaly.isolatedTriangles << " (无相邻面片)\n";
            }

            if (anomaly.degenerateTriangles == 0 && anomaly.sharpEdges < 10 &&
                anomaly.duplicateVertices < 100 && anomaly.isolatedTriangles < 10) {
                ss << "模型质量: 良好\n";
            } else {
                ss << "模型质量: 存在异常，建议检查\n";
            }

            ss << "包围盒尺寸: " << (maxX - minX) << " x " << (maxY - minY) << " x " << (maxZ - minZ) << "\n";
        }

        lastResult = ss.str();
        std::cout << lastResult << std::endl;

        return std::string("Geometry analysis completed: ") + (anomaly.degenerateTriangles == 0 && anomaly.sharpEdges < 10 && anomaly.duplicateVertices < 100 && anomaly.isolatedTriangles < 10 ? "Good quality" : "Has anomalies");
    }

    std::string getLastResult() const { return lastResult; }

    std::string getName() const override { return "analyze_geometry"; }

private:
    bool areTrianglesAdjacent(const hhb::core::Triangle* t1, const hhb::core::Triangle* t2) {
        float eps = 0.001f;

        float v1[3][3] = {
            {t1->vertex1[0], t1->vertex1[1], t1->vertex1[2]},
            {t1->vertex2[0], t1->vertex2[1], t1->vertex2[2]},
            {t1->vertex3[0], t1->vertex3[1], t1->vertex3[2]}
        };
        float v2[3][3] = {
            {t2->vertex1[0], t2->vertex1[1], t2->vertex1[2]},
            {t2->vertex2[0], t2->vertex2[1], t2->vertex2[2]},
            {t2->vertex3[0], t2->vertex3[1], t2->vertex3[2]}
        };

        for (int i = 0; i < 3; ++i) {
            for (int j = 0; j < 3; ++j) {
                float dx = v1[i][0] - v2[j][0];
                float dy = v1[i][1] - v2[j][1];
                float dz = v1[i][2] - v2[j][2];
                float dist = std::sqrt(dx*dx + dy*dy + dz*dz);
                if (dist < eps) {
                    return true;
                }
            }
        }
        return false;
    }

    std::string lastResult;
    render::RenderManager& renderManager;
};

} // namespace skill
} // namespace hhb