#pragma once

#include <string>
#include <unordered_map>
#include <memory>
#include "ISkill.h"

namespace hhb {
namespace skill {

class SkillRegistry {
public:
    static SkillRegistry& getInstance() {
        static SkillRegistry instance;
        return instance;
    }
    
    void registerSkill(const std::string& name, std::unique_ptr<ISkill> skill) {
        skills[name] = std::move(skill);
    }
    
    std::string executeSkill(const std::string& name, const std::string& params = "") {
        auto it = skills.find(name);
        if (it != skills.end()) {
            return it->second->execute(params);
        }
        return "Skill not found: " + name;
    }
    
    bool hasSkill(const std::string& name) const {
        return skills.find(name) != skills.end();
    }
    
private:
    SkillRegistry() = default;
    
    std::unordered_map<std::string, std::unique_ptr<ISkill>> skills;
};

} // namespace skill
} // namespace hhb