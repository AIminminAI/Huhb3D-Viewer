#include "hhb_cad_c_api.h"
#include <memory>
#include <string>
#include <vector>
#include <array>
#include <unordered_map>
#include <cstdint>
#include <cstring>
#include <sstream>
#include <iomanip>

// Fix for ImGui compatibility
#ifndef ImU32
typedef uint32_t ImU32;
#endif

namespace hhb {
namespace core {
namespace api {

// Entity base class
class Entity {
public:
    virtual ~Entity() = default;
    virtual std::string to_json() const = 0;
};

// Bolt entity
class Bolt : public Entity {
public:
    float radius;
    float thread_pitch;
    float length;

    std::string to_json() const override {
        std::ostringstream oss;
        oss << std::fixed << std::setprecision(6);
        oss << "{\"type\": \"bolt\", \"radius\": " << radius 
            << ", \"thread_pitch\": " << thread_pitch 
            << ", \"length\": " << length << "}";
        return oss.str();
    }
};

// Context class
class Context {
public:
    Context() = default;
    ~Context() = default;

    // Add entity
    void add_entity(std::unique_ptr<Entity> entity) {
        entities.push_back(std::move(entity));
    }

    // Get entities
    const std::vector<std::unique_ptr<Entity>>& get_entities() const {
        return entities;
    }

    // Set selected entity
    void set_selected_entity(size_t index) {
        if (index < entities.size()) {
            selected_entity_index = index;
        }
    }

    // Get selected entity
    Entity* get_selected_entity() const {
        if (selected_entity_index < entities.size()) {
            return entities[selected_entity_index].get();
        }
        return nullptr;
    }

    // Add interference point
    void add_interference_point(float x, float y, float z) {
        interference_points.push_back(std::array<float, 3>{x, y, z});
    }

    // Get interference points
    const std::vector<std::array<float, 3>>& get_interference_points() const {
        return interference_points;
    }

private:
    std::vector<std::unique_ptr<Entity>> entities;
    size_t selected_entity_index = 0;
    std::vector<std::array<float, 3>> interference_points;
};

// Simple JSON parsing helper function
float parse_float_from_json(const std::string& json, const std::string& key) {
    size_t pos = json.find("\"" + key + "\"");
    if (pos == std::string::npos) {
        return 0.0f;
    }
    
    pos = json.find(":", pos);
    if (pos == std::string::npos) {
        return 0.0f;
    }
    
    // Skip colon and whitespace
    pos++;
    while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t')) {
        pos++;
    }
    
    // Parse number
    size_t end_pos = pos;
    while (end_pos < json.size() && (json[end_pos] == '-' || json[end_pos] == '+' || 
           json[end_pos] == '.' || json[end_pos] == 'e' || json[end_pos] == 'E' ||
           (json[end_pos] >= '0' && json[end_pos] <= '9'))) {
        end_pos++;
    }
    
    try {
        return std::stof(json.substr(pos, end_pos - pos));
    } catch (...) {
        return 0.0f;
    }
}

std::string parse_string_from_json(const std::string& json, const std::string& key) {
    size_t pos = json.find("\"" + key + "\"");
    if (pos == std::string::npos) {
        return "";
    }
    
    pos = json.find(":", pos);
    if (pos == std::string::npos) {
        return "";
    }
    
    // Skip colon and whitespace
    pos++;
    while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t')) {
        pos++;
    }
    
    // Check if it's a string
    if (pos < json.size() && json[pos] == '"') {
        pos++;
        size_t end_pos = json.find("\"", pos);
        if (end_pos != std::string::npos) {
            return json.substr(pos, end_pos - pos);
        }
    }
    
    return "";
}

// Handle create bolt command
HHBError handle_create_bolt(Context* context, const std::string& params_str, std::string& response) {
    float radius = parse_float_from_json(params_str, "radius");
    float thread_pitch = parse_float_from_json(params_str, "thread_pitch");
    float length = parse_float_from_json(params_str, "length");
    
    if (length == 0.0f) {
        length = 10.0f;
    }
    
    if (radius <= 0.0f || thread_pitch <= 0.0f) {
        return HHB_ERROR_INVALID_PARAMS;
    }

    // Create bolt entity
    auto bolt = std::make_unique<Bolt>();
    bolt->radius = radius;
    bolt->thread_pitch = thread_pitch;
    bolt->length = length;

    context->add_entity(std::move(bolt));
    context->set_selected_entity(context->get_entities().size() - 1);

    // Generate response
    std::ostringstream oss;
    oss << "{\"status\": \"success\", \"message\": \"Bolt created successfully\", \"entity_id\": " 
        << (context->get_entities().size() - 1) << "}";
    response = oss.str();
    return HHB_SUCCESS;
}

// Handle get entities command
HHBError handle_get_entities(Context* context, std::string& response) {
    std::ostringstream oss;
    oss << "{\"status\": \"success\", \"entities\": [";
    
    const auto& entities = context->get_entities();
    for (size_t i = 0; i < entities.size(); ++i) {
        if (i > 0) {
            oss << ",";
        }
        oss << entities[i]->to_json();
    }
    
    oss << "]}";
    response = oss.str();
    return HHB_SUCCESS;
}

// Handle select entity command
HHBError handle_select_entity(Context* context, const std::string& params_str, std::string& response) {
    float entity_id_f = parse_float_from_json(params_str, "entity_id");
    size_t entity_id = static_cast<size_t>(entity_id_f);
    
    context->set_selected_entity(entity_id);

    response = "{\"status\": \"success\", \"message\": \"Entity selected successfully\"}";
    return HHB_SUCCESS;
}

} // namespace api
} // namespace core
} // namespace hhb

// Create context
HHBError hhb_create_context(HHBContext* context) {
    try {
        auto ctx = new hhb::core::api::Context();
        *context = ctx;
        return HHB_SUCCESS;
    } catch (...) {
        return HHB_ERROR_INTERNAL;
    }
}

// Destroy context
void hhb_destroy_context(HHBContext context) {
    if (context) {
        delete static_cast<hhb::core::api::Context*>(context);
    }
}

// Process JSON command
HHBError hhb_process_command(HHBContext context, const char* json_command, char** response) {
    try {
        auto ctx = static_cast<hhb::core::api::Context*>(context);
        std::string json_str(json_command);
        std::string result;

        // Parse action
        std::string action = hhb::core::api::parse_string_from_json(json_str, "action");
        
        // Extract params section
        size_t params_pos = json_str.find("\"params\"");
        std::string params_str = "{}";
        if (params_pos != std::string::npos) {
            size_t brace_start = json_str.find("{", params_pos);
            if (brace_start != std::string::npos) {
                // Find matching closing brace
                int brace_count = 1;
                size_t brace_end = brace_start + 1;
                while (brace_end < json_str.size() && brace_count > 0) {
                    if (json_str[brace_end] == '{') {
                        brace_count++;
                    } else if (json_str[brace_end] == '}') {
                        brace_count--;
                    }
                    brace_end++;
                }
                params_str = json_str.substr(brace_start, brace_end - brace_start);
            }
        }

        // Execute action
        HHBError error = HHB_SUCCESS;
        if (action == "create_bolt") {
            error = hhb::core::api::handle_create_bolt(ctx, params_str, result);
        } else if (action == "get_entities") {
            error = hhb::core::api::handle_get_entities(ctx, result);
        } else if (action == "select_entity") {
            error = hhb::core::api::handle_select_entity(ctx, params_str, result);
        } else {
            return HHB_ERROR_UNKNOWN_ACTION;
        }

        if (error != HHB_SUCCESS) {
            return error;
        }

        // Allocate response memory
        *response = new char[result.size() + 1];
        std::strcpy(*response, result.c_str());

        return HHB_SUCCESS;
    } catch (...) {
        return HHB_ERROR_INTERNAL;
    }
}

// Free response memory
void hhb_free_response(char* response) {
    if (response) {
        delete[] response;
    }
}

// Get selected entity
HHBError hhb_get_selected_entity(HHBContext context, char** entity_info) {
    try {
        auto ctx = static_cast<hhb::core::api::Context*>(context);
        auto entity = ctx->get_selected_entity();

        if (!entity) {
            *entity_info = new char[3];
            std::strcpy(*entity_info, "{}");
            return HHB_SUCCESS;
        }

        std::string json = entity->to_json();
        *entity_info = new char[json.size() + 1];
        std::strcpy(*entity_info, json.c_str());

        return HHB_SUCCESS;
    } catch (...) {
        return HHB_ERROR_INTERNAL;
    }
}

// Get interference points
HHBError hhb_get_interference_points(HHBContext context, char** points_info) {
    try {
        auto ctx = static_cast<hhb::core::api::Context*>(context);
        const auto& points = ctx->get_interference_points();

        std::ostringstream oss;
        oss << std::fixed << std::setprecision(6);
        oss << "{\"points\": [";
        for (size_t i = 0; i < points.size(); ++i) {
            if (i > 0) {
                oss << ",";
            }
            oss << "[" << points[i][0] << ", " << points[i][1] << ", " << points[i][2] << "]";
        }
        oss << "]}";
        
        std::string json = oss.str();
        *points_info = new char[json.size() + 1];
        std::strcpy(*points_info, json.c_str());

        return HHB_SUCCESS;
    } catch (...) {
        return HHB_ERROR_INTERNAL;
    }
}