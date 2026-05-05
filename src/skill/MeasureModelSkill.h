#pragma once

#include "ISkill.h"
#include "../render/render_manager.h"
#include <sstream>
#include <cmath>

namespace hhb {
namespace skill {

struct ModelMeasurement {
    float width;
    float height;
    float depth;
    float volume;
    float surfaceArea;
    float boundingBox[6];
};

class MeasureModelSkill : public ISkill {
public:
    MeasureModelSkill(render::RenderManager& renderManager) : renderManager(renderManager) {}

    std::string execute(const std::string& params = "") override {
        auto spatialInfo = renderManager.getSpatialInfo();

        ModelMeasurement measurement;
        measurement.boundingBox[0] = spatialInfo.bounds[0];
        measurement.boundingBox[1] = spatialInfo.bounds[1];
        measurement.boundingBox[2] = spatialInfo.bounds[2];
        measurement.boundingBox[3] = spatialInfo.bounds[3];
        measurement.boundingBox[4] = spatialInfo.bounds[4];
        measurement.boundingBox[5] = spatialInfo.bounds[5];

        measurement.width = spatialInfo.bounds[3] - spatialInfo.bounds[0];
        measurement.height = spatialInfo.bounds[4] - spatialInfo.bounds[1];
        measurement.depth = spatialInfo.bounds[5] - spatialInfo.bounds[2];

        float volume = 0.0f;
        float surfaceArea = 0.0f;

        auto trianglePtrs = renderManager.getTrianglePtrs();
        for (const auto& triangle : trianglePtrs) {
            float v1[3] = {triangle->vertex1[0], triangle->vertex1[1], triangle->vertex1[2]};
            float v2[3] = {triangle->vertex2[0], triangle->vertex2[1], triangle->vertex2[2]};
            float v3[3] = {triangle->vertex3[0], triangle->vertex3[1], triangle->vertex3[2]};

            float edge1[3] = {v2[0] - v1[0], v2[1] - v1[1], v2[2] - v1[2]};
            float edge2[3] = {v3[0] - v1[0], v3[1] - v1[1], v3[2] - v1[2]};

            float cross[3];
            cross[0] = edge1[1] * edge2[2] - edge1[2] * edge2[1];
            cross[1] = edge1[2] * edge2[0] - edge1[0] * edge2[2];
            cross[2] = edge1[0] * edge2[1] - edge1[1] * edge2[0];

            float triangleArea = std::sqrt(cross[0] * cross[0] + cross[1] * cross[1] + cross[2] * cross[2]) * 0.5f;
            surfaceArea += triangleArea;

            float base = triangleArea * 2.0f;
            float height = std::abs(v1[1]);
            volume += base * height / 3.0f;
        }

        measurement.volume = volume;
        measurement.surfaceArea = surfaceArea;

        std::stringstream ss;
        ss << "模型测量结果：\n";
        ss << "长(宽度): " << measurement.width << "\n";
        ss << "高(高度): " << measurement.height << "\n";
        ss << "深(深度): " << measurement.depth << "\n";
        ss << "包围盒: (" << measurement.boundingBox[0] << ", " << measurement.boundingBox[1] << ", " << measurement.boundingBox[2] << ") - ("
           << measurement.boundingBox[3] << ", " << measurement.boundingBox[4] << ", " << measurement.boundingBox[5] << ")\n";
        ss << "表面积: " << measurement.surfaceArea << "\n";
        ss << "体积: " << measurement.volume << "\n";

        lastResult = ss.str();
        std::cout << lastResult << std::endl;

        return "Model measurements calculated: " + std::to_string(measurement.width) + "x" + std::to_string(measurement.height) + "x" + std::to_string(measurement.depth);
    }

    std::string getLastResult() const { return lastResult; }

    std::string getName() const override { return "measure_model"; }

    static ModelMeasurement getMeasurement(render::RenderManager& renderManager) {
        ModelMeasurement measurement;
        auto spatialInfo = renderManager.getSpatialInfo();

        measurement.width = spatialInfo.bounds[3] - spatialInfo.bounds[0];
        measurement.height = spatialInfo.bounds[4] - spatialInfo.bounds[1];
        measurement.depth = spatialInfo.bounds[5] - spatialInfo.bounds[2];

        float surfaceArea = 0.0f;
        auto trianglePtrs = renderManager.getTrianglePtrs();
        for (const auto& triangle : trianglePtrs) {
            float v1[3] = {triangle->vertex1[0], triangle->vertex1[1], triangle->vertex1[2]};
            float v2[3] = {triangle->vertex2[0], triangle->vertex2[1], triangle->vertex2[2]};
            float v3[3] = {triangle->vertex3[0], triangle->vertex3[1], triangle->vertex3[2]};

            float edge1[3] = {v2[0] - v1[0], v2[1] - v1[1], v2[2] - v1[2]};
            float edge2[3] = {v3[0] - v1[0], v3[1] - v1[1], v3[2] - v1[2]};

            float cross[3];
            cross[0] = edge1[1] * edge2[2] - edge1[2] * edge2[1];
            cross[1] = edge1[2] * edge2[0] - edge1[0] * edge2[2];
            cross[2] = edge1[0] * edge2[1] - edge1[1] * edge2[0];

            float triangleArea = std::sqrt(cross[0] * cross[0] + cross[1] * cross[1] + cross[2] * cross[2]) * 0.5f;
            surfaceArea += triangleArea;
        }

        measurement.surfaceArea = surfaceArea;
        measurement.volume = measurement.width * measurement.height * measurement.depth;
        memcpy(measurement.boundingBox, spatialInfo.bounds, sizeof(measurement.boundingBox));

        return measurement;
    }

private:
    std::string lastResult;
    render::RenderManager& renderManager;
};

} // namespace skill
} // namespace hhb