#pragma once

#include "ISkill.h"
#include "../render/render_manager.h"

namespace hhb {
namespace skill {

class ZoomInSkill : public ISkill {
public:
    ZoomInSkill(render::RenderManager& renderManager) : renderManager(renderManager) {}
    
    std::string execute(const std::string& params = "") override {
        // 这里需要修改 RenderManager 类，添加获取和设置 zoom 的方法
        // 假设我们已经添加了这些方法
        float currentZoom = renderManager.getZoom();
        renderManager.setZoom(currentZoom * 1.2f); // 放大 20%
        std::cout << "ZoomInSkill executed: zoom level increased" << std::endl;
        return "Zoom level increased to " + std::to_string(renderManager.getZoom());
    }
    
    std::string getName() const override {
        return "zoom_in";
    }
    
private:
    render::RenderManager& renderManager;
};

} // namespace skill
} // namespace hhb