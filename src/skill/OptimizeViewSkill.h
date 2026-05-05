#pragma once

#include "ISkill.h"
#include "../render/render_manager.h"

namespace hhb {
namespace skill {

class OptimizeViewSkill : public ISkill {
public:
    OptimizeViewSkill(render::RenderManager& renderManager) : renderManager(renderManager) {}
    
    std::string execute(const std::string& params = "") override {
        // 解析参数，确定要查看的部分
        std::string target = "front"; // 默认查看正面
        if (!params.empty()) {
            // 简单的参数解析
            if (params.find("bottom") != std::string::npos) {
                target = "bottom";
            } else if (params.find("top") != std::string::npos) {
                target = "top";
            } else if (params.find("back") != std::string::npos) {
                target = "back";
            } else if (params.find("left") != std::string::npos) {
                target = "left";
            } else if (params.find("right") != std::string::npos) {
                target = "right";
            }
        }
        
        // 获取空间信息
        auto spatialInfo = renderManager.getSpatialInfo();
        
        // 计算模型的尺寸
        float width = spatialInfo.bounds[3] - spatialInfo.bounds[0];
        float height = spatialInfo.bounds[4] - spatialInfo.bounds[1];
        float depth = spatialInfo.bounds[5] - spatialInfo.bounds[2];
        
        // 计算合适的相机位置
        float distance = std::max({width, height, depth}) * 2.0f; // 相机距离模型的距离
        
        // 根据目标位置计算相机旋转
        float pitch = 0.0f; // 俯仰角
        float yaw = 0.0f;   // 偏航角
        
        if (target == "bottom") {
            pitch = 3.14159f / 2.0f; // 90度，看向底部
            yaw = 0.0f;
        } else if (target == "top") {
            pitch = -3.14159f / 2.0f; // -90度，看向顶部
            yaw = 0.0f;
        } else if (target == "back") {
            pitch = 0.0f;
            yaw = 3.14159f; // 180度，看向背面
        } else if (target == "left") {
            pitch = 0.0f;
            yaw = 3.14159f / 2.0f; // 90度，看向左侧
        } else if (target == "right") {
            pitch = 0.0f;
            yaw = -3.14159f / 2.0f; // -90度，看向右侧
        }

        // 计算相机位置
        float targetPos[3];
        float targetRot[2] = {pitch, yaw};

        // 计算相机位置（基于模型中心和旋转角度）
        targetPos[0] = spatialInfo.center[0] + distance * sin(yaw) * cos(pitch);
        targetPos[1] = spatialInfo.center[1] + distance * sin(pitch);
        targetPos[2] = spatialInfo.center[2] + distance * cos(yaw) * cos(pitch);

        // 使用平滑动画设置相机
        const float animDuration = 0.8f; // 800ms 动画
        renderManager.setTargetCameraPosition(targetPos, animDuration);
        renderManager.setTargetCameraRotation(targetRot, animDuration);
        renderManager.setTargetZoom(1.0f, animDuration);

        return "Optimized view to " + target + " with smooth animation";
    }
    
    std::string getName() const override {
        return "optimize_view";
    }
    
private:
    render::RenderManager& renderManager;
};

} // namespace skill
} // namespace hhb