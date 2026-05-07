#include "stl_parser_coroutine.h"
#include <coroutine>  // 必须包含，用于协程 handle 和 traits
#include <expected>   // 必须包含，用于 std::expected 和 std::unexpected
#include <string>
#include <fstream>
#include <filesystem>

namespace hhb {
namespace core {

// Asynchronously read file line
ParserTask<std::string> StlParserCoroutine::read_line(std::ifstream& file) {
    std::string line;
    if (std::getline(file, line)) {
        co_return std::move(line);
    } else {
        co_return std::unexpected("End of file");
    }
}

// Parse ASCII STL file (coroutine version)
ParserTask<size_t> StlParserCoroutine::parse_ascii(const std::string& filename, ObjectPool<Triangle>& pool) {
    std::ifstream file(filename);
    if (!file) {
        co_return std::unexpected("Failed to open file");
    }

    size_t parsed_count = 0;

    // Skip file header
    while (true) {
        auto line_result = co_await read_line(file);
        if (!line_result.has_value()) {
            co_return std::unexpected("Unexpected end of file");
        }
        if (line_result.value().find("solid") != std::string::npos) {
            break;
        }
    }

    // Parse triangles
    while (true) {
        // Find facet start
        std::string facet_line;
        while (true) {
            auto line_result = co_await read_line(file);
            if (!line_result.has_value()) {
                co_return parsed_count;
            }
            if (line_result.value().find("facet normal") != std::string::npos) {
                facet_line = std::move(line_result.value());
                break;
            }
        }

        // Parse normal vector
        Triangle* tri = pool.allocate();
        sscanf(facet_line.c_str(), "facet normal %f %f %f", &tri->normal[0], &tri->normal[1], &tri->normal[2]);

        // Skip outer loop
        auto loop_result = co_await read_line(file);
        if (!loop_result.has_value()) {
            pool.deallocate(tri);
            co_return std::unexpected("Unexpected end of file");
        }

        // Parse three vertices
        auto vertex1_result = co_await read_line(file);
        if (!vertex1_result.has_value()) {
            pool.deallocate(tri);
            co_return std::unexpected("Unexpected end of file");
        }
        sscanf(vertex1_result.value().c_str(), "vertex %f %f %f", &tri->vertex1[0], &tri->vertex1[1], &tri->vertex1[2]);

        auto vertex2_result = co_await read_line(file);
        if (!vertex2_result.has_value()) {
            pool.deallocate(tri);
            co_return std::unexpected("Unexpected end of file");
        }
        sscanf(vertex2_result.value().c_str(), "vertex %f %f %f", &tri->vertex2[0], &tri->vertex2[1], &tri->vertex2[2]);

        auto vertex3_result = co_await read_line(file);
        if (!vertex3_result.has_value()) {
            pool.deallocate(tri);
            co_return std::unexpected("Unexpected end of file");
        }
        sscanf(vertex3_result.value().c_str(), "vertex %f %f %f", &tri->vertex3[0], &tri->vertex3[1], &tri->vertex3[2]);

        // Skip endloop and endfacet
        auto endloop_result = co_await read_line(file);
        if (!endloop_result.has_value()) {
            pool.deallocate(tri);
            co_return std::unexpected("Unexpected end of file");
        }

        auto endfacet_result = co_await read_line(file);
        if (!endfacet_result.has_value()) {
            pool.deallocate(tri);
            co_return std::unexpected("Unexpected end of file");
        }

        tri->attribute_count = 0;
        parsed_count++;
    }
}

} // namespace core
} // namespace hhb