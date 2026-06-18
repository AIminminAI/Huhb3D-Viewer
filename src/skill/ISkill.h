#pragma once

#include <string>
#include <memory>

namespace hhb {
namespace skill {

class ISkill {
public:
    virtual ~ISkill() = default;
    
    virtual std::string execute(const std::string& params = "") = 0;
    virtual std::string getName() const = 0;
};

} // namespace skill
} // namespace hhb