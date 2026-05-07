#pragma once

#include "ISkill.h"
#include "../render/render_manager.h"

namespace hhb {
namespace skill {

class RotateSkill : public ISkill {
public:
    RotateSkill(render::RenderManager& renderManager) : renderManager(renderManager) {}
    
    std::string execute(const std::string& params = "") override {
        // 这里需要修改 RenderManager 类，添加获取和设置 cameraRotation 的方法
        // 假设我们已经添加了这些方法
        float* rotation = renderManager.getCameraRotation();
        rotation[1] += 45.0f; // 旋转 45 度
        if (rotation[1] > 360.0f) {
            rotation[1] -= 360.0f;
        }
        std::cout << "RotateSkill executed: model rotated" << std::endl;
        return "Model rotated to " + std::to_string(rotation[1]) + " degrees";
    }
    
    std::string getName() const override {
        return "rotate";
    }
    
private:
    render::RenderManager& renderManager;
};

} // namespace skill
} // namespace hhb