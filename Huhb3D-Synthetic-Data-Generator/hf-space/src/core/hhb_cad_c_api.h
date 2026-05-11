#pragma once

#ifdef __cplusplus
extern "C" {
#endif

#include <stddef.h>
#include <stdint.h>

// C-API 閿欒鐮?
typedef enum {
    HHB_SUCCESS = 0,
    HHB_ERROR_INVALID_JSON = 1,
    HHB_ERROR_UNKNOWN_ACTION = 2,
    HHB_ERROR_INVALID_PARAMS = 3,
    HHB_ERROR_INTERNAL = 4
} HHBError;

// C-API 鍙ユ焺
typedef void* HHBContext;

// 鍒涘缓涓婁笅鏂?
HHBError hhb_create_context(HHBContext* context);

// 閿€姣佷笂涓嬫枃
void hhb_destroy_context(HHBContext context);

// 澶勭悊 JSON 鎸囦护
HHBError hhb_process_command(HHBContext context, const char* json_command, char** response);

// 閲婃斁鍝嶅簲鍐呭瓨
void hhb_free_response(char* response);

// 鑾峰彇褰撳墠閫変腑鐨勫疄浣?
HHBError hhb_get_selected_entity(HHBContext context, char** entity_info);

// 鑾峰彇骞叉秹鐐瑰潗鏍?
HHBError hhb_get_interference_points(HHBContext context, char** points_info);

#ifdef __cplusplus
}
#endif
