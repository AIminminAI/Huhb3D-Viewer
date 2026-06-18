#pragma once

#include "ISkill.h"
#include "../render/render_manager.h"

namespace hhb {
namespace skill {

class AutoRotateSkill : public ISkill {
public:
    AutoRotateSkill(render::RenderManager& renderManager) : renderManager(renderManager) {}
    
    std::string execute(const std::string& params = "") override {
        // 切换自动旋转状态
        bool currentState = renderManager.getAutoRotate();
        renderManager.setAutoRotate(!currentState);
        
        std::string status = (!currentState ? "enabled" : "disabled");
        std::cout << "AutoRotateSkill executed: " << status << std::endl;
        return "Auto rotate " + status;
    }
    
    std::string getName() const override {
        return "auto_rotate";
    }
    
private:
    render::RenderManager& renderManager;
};

} // namespace skill
} // namespace hhb