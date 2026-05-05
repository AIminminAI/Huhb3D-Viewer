#pragma once

#include "ISkill.h"
#include "../render/render_manager.h"

namespace hhb {
namespace skill {

class ResetCameraSkill : public ISkill {
public:
    ResetCameraSkill(render::RenderManager& renderManager) : renderManager(renderManager) {}
    
    std::string execute(const std::string& params = "") override {
        renderManager.centerModel();
        std::cout << "ResetCameraSkill executed: camera reset to model center" << std::endl;
        return "Camera reset to model center";
    }
    
    std::string getName() const override {
        return "reset_camera";
    }
    
private:
    render::RenderManager& renderManager;
};

} // namespace skill
} // namespace hhb