#include <iostream>
#include "hhb_cad_c_api.h"

int main() {
    HHBContext context;
    HHBError error;
    char* response = nullptr;

    // 创建上下文
    error = hhb_create_context(&context);
    if (error != HHB_SUCCESS) {
        std::cerr << "Failed to create context: " << error << std::endl;
        return 1;
    }

    // 测试创建螺栓
    std::cout << "Testing create_bolt..." << std::endl;
    const char* create_bolt_command = "{\"action\": \"create_bolt\", \"params\": {\"radius\": 5.0, \"thread_pitch\": 1.2, \"length\": 20.0}}";
    error = hhb_process_command(context, create_bolt_command, &response);
    if (error == HHB_SUCCESS) {
        std::cout << "Response: " << response << std::endl;
        hhb_free_response(response);
    } else {
        std::cerr << "Failed to create bolt: " << error << std::endl;
    }

    // 测试获取实体列表
    std::cout << "\nTesting get_entities..." << std::endl;
    const char* get_entities_command = "{\"action\": \"get_entities\"}";
    error = hhb_process_command(context, get_entities_command, &response);
    if (error == HHB_SUCCESS) {
        std::cout << "Response: " << response << std::endl;
        hhb_free_response(response);
    } else {
        std::cerr << "Failed to get entities: " << error << std::endl;
    }

    // 测试选择实体
    std::cout << "\nTesting select_entity..." << std::endl;
    const char* select_entity_command = "{\"action\": \"select_entity\", \"params\": {\"entity_id\": 0}}";
    error = hhb_process_command(context, select_entity_command, &response);
    if (error == HHB_SUCCESS) {
        std::cout << "Response: " << response << std::endl;
        hhb_free_response(response);
    } else {
        std::cerr << "Failed to select entity: " << error << std::endl;
    }

    // 测试获取选中的实体
    std::cout << "\nTesting get_selected_entity..." << std::endl;
    char* entity_info = nullptr;
    error = hhb_get_selected_entity(context, &entity_info);
    if (error == HHB_SUCCESS) {
        std::cout << "Selected entity: " << entity_info << std::endl;
        hhb_free_response(entity_info);
    } else {
        std::cerr << "Failed to get selected entity: " << error << std::endl;
    }

    // 测试获取干涉点
    std::cout << "\nTesting get_interference_points..." << std::endl;
    char* points_info = nullptr;
    error = hhb_get_interference_points(context, &points_info);
    if (error == HHB_SUCCESS) {
        std::cout << "Interference points: " << points_info << std::endl;
        hhb_free_response(points_info);
    } else {
        std::cerr << "Failed to get interference points: " << error << std::endl;
    }

    // 销毁上下文
    hhb_destroy_context(context);

    return 0;
}
