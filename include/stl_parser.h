#pragma once

#include <string>
#include <vector>
#include "object_pool.h"

namespace hhb {
namespace core {

// STL triangle structure
// alignas(64): Force alignment to 64 bytes, the size of a cache line
// This helps avoid false sharing in multi-threaded environments and improves cache hit rate
struct alignas(64) Triangle {
    float normal[3];
    float vertex1[3];
    float vertex2[3];
    float vertex3[3];
    uint16_t attribute_count;
    // Padding to ensure the struct size is a multiple of 64 bytes
    char padding[64 - (3*4*4 + 2)]; // 3 floats * 4 vertices * 4 bytes + 2 bytes for attribute_count
};

// STL parser result
typedef struct {
    bool success;
    size_t count;
    std::string error;
} ParserResult;

// STL parser class
class StlParser {
public:
    StlParser() = default;
    ~StlParser() = default;

    // Parse STL file (auto format detection)
    ParserResult parse(const std::string& filename, ObjectPool<Triangle>& pool);

    // Parse binary STL file
    ParserResult parse_binary(const std::string& filename, ObjectPool<Triangle>& pool);

    // Parse ASCII STL file
    ParserResult parse_ascii(const std::string& filename, ObjectPool<Triangle>& pool);

private:
    // Detect file format
    bool is_binary(const std::string& filename);
};

} // namespace core
} // namespace hhb