#ifdef _WIN32
#define NOMINMAX
#endif

#include "stl_parser.h"
#include <fstream>
#include <cstring>
#include <iostream>
#include <thread>
#include <vector>
#include <future>
#include <algorithm>
#include <chrono>
#include <sstream>

#ifdef _WIN32
#include <Windows.h>
#else
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#endif

namespace hhb {
namespace core {

// Detect file format
bool StlParser::is_binary(const std::string& filename) {
    try {
        std::cout << "Checking if file is binary: " << filename << std::endl;
        std::ifstream file(filename, std::ios::binary | std::ios::ate);
        if (!file) {
            std::cerr << "Failed to open file for binary check" << std::endl;
            return false;
        }

        std::streampos size = file.tellg();
        std::cout << "File size: " << size << " bytes" << std::endl;
        file.seekg(0, std::ios::beg);

        // Binary STL file minimum size: 80-byte header + 4-byte triangle count + 50 bytes per triangle
        if (size < 80 + 4 + 50) {
            std::cout << "File too small for binary STL" << std::endl;
            return false;
        }

        // Read file header
        char header[80];
        file.read(header, 80);
        if (!file) {
            std::cerr << "Failed to read file header" << std::endl;
            return false;
        }
        std::cout << "File header read successfully" << std::endl;

        // Read triangle count
        uint32_t triangle_count;
        file.read(reinterpret_cast<char*>(&triangle_count), 4);
        if (!file) {
            std::cerr << "Failed to read triangle count" << std::endl;
            return false;
        }
        std::cout << "Triangle count: " << triangle_count << std::endl;

        // Verify file size matches triangle count
        bool is_binary = (size == 80 + 4 + triangle_count * 50);
        std::cout << "Is binary: " << (is_binary ? "yes" : "no") << std::endl;
        return is_binary;
    } catch (const std::exception& e) {
        std::cerr << "Exception in is_binary: " << e.what() << std::endl;
        return false;
    }
}

// Check if file exists
bool file_exists(const std::string& filename) {
    try {
        std::cout << "Checking if file exists: " << filename << std::endl;
        std::ifstream file(filename);
        bool exists = file.good();
        std::cout << "File exists: " << (exists ? "yes" : "no") << std::endl;
        return exists;
    } catch (const std::exception& e) {
        std::cerr << "Exception in file_exists: " << e.what() << std::endl;
        return false;
    }
}

// Parse binary STL file
ParserResult StlParser::parse_binary(const std::string& filename, ObjectPool<Triangle>& pool) {
    std::cout << "Parsing binary STL file: " << filename << std::endl;
    ParserResult result;
    result.success = false;
    result.count = 0;

    // Start timing for the entire parsing process
    auto total_start = std::chrono::high_resolution_clock::now();

#ifdef _WIN32
    // Windows memory mapping
    std::cout << "Opening file with CreateFileA" << std::endl;
    HANDLE hFile = CreateFileA(
        filename.c_str(),
        GENERIC_READ,
        FILE_SHARE_READ,
        NULL,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        NULL
    );

    if (hFile == INVALID_HANDLE_VALUE) {
        std::cerr << "Failed to open file: " << GetLastError() << std::endl;
        result.error = "Failed to open file";
        return result;
    }

    // Get file size
    LARGE_INTEGER fileSize;
    if (!GetFileSizeEx(hFile, &fileSize)) {
        std::cerr << "Failed to get file size: " << GetLastError() << std::endl;
        CloseHandle(hFile);
        result.error = "Failed to get file size";
        return result;
    }

    // Create file mapping
    HANDLE hMapFile = CreateFileMappingA(
        hFile,
        NULL,
        PAGE_READONLY,
        0,
        0,
        NULL
    );

    if (hMapFile == NULL) {
        std::cerr << "Failed to create file mapping: " << GetLastError() << std::endl;
        CloseHandle(hFile);
        result.error = "Failed to create file mapping";
        return result;
    }

    // Map view of file
    LPVOID lpMapAddress = MapViewOfFile(
        hMapFile,
        FILE_MAP_READ,
        0,
        0,
        0
    );

    if (lpMapAddress == NULL) {
        std::cerr << "Failed to map view of file: " << GetLastError() << std::endl;
        CloseHandle(hMapFile);
        CloseHandle(hFile);
        result.error = "Failed to map view of file";
        return result;
    }

    // Process the mapped file
    const char* data = static_cast<const char*>(lpMapAddress);
    size_t size = static_cast<size_t>(fileSize.QuadPart);

    // Skip 80-byte header
    size_t offset = 80;

    // Read triangle count
    uint32_t triangle_count;
    memcpy(&triangle_count, data + offset, sizeof(uint32_t));
    offset += sizeof(uint32_t);

    std::cout << "Binary STL: Found " << triangle_count << " triangles" << std::endl;

    // Process triangles in parallel
    const size_t batch_size = 10000;
    const size_t num_batches = (triangle_count + batch_size - 1) / batch_size;
    std::vector<std::future<size_t>> futures;

    for (size_t batch = 0; batch < num_batches; ++batch) {
        size_t start = batch * batch_size;
        size_t end = std::min(start + batch_size, static_cast<size_t>(triangle_count));

        futures.push_back(std::async(std::launch::async, [&, start, end]() {
            size_t local_count = 0;
            for (size_t i = start; i < end; ++i) {
                Triangle tri;
                size_t triangle_offset = offset + i * 50;
                
                // Read normal
                memcpy(tri.normal, data + triangle_offset, 12);
                
                // Read vertices
                memcpy(tri.vertex1, data + triangle_offset + 12, 12);
                memcpy(tri.vertex2, data + triangle_offset + 24, 12);
                memcpy(tri.vertex3, data + triangle_offset + 36, 12);
                
                // Read attribute count
                memcpy(&tri.attribute_count, data + triangle_offset + 48, 2);
                
                // Add to pool
                Triangle* tri_ptr = pool.allocate();
                new (tri_ptr) Triangle(tri);
                local_count++;
            }
            return local_count;
        }));
    }

    // Collect results
    size_t total_triangles = 0;
    for (auto& future : futures) {
        total_triangles += future.get();
    }

    // Unmap view and close handles
    UnmapViewOfFile(lpMapAddress);
    CloseHandle(hMapFile);
    CloseHandle(hFile);

#else
    // POSIX memory mapping
    int fd = open(filename.c_str(), O_RDONLY);
    if (fd == -1) {
        std::cerr << "Failed to open file: " << strerror(errno) << std::endl;
        result.error = "Failed to open file";
        return result;
    }

    struct stat sb;
    if (fstat(fd, &sb) == -1) {
        std::cerr << "Failed to get file size: " << strerror(errno) << std::endl;
        close(fd);
        result.error = "Failed to get file size";
        return result;
    }

    size_t size = sb.st_size;
    char* data = static_cast<char*>(mmap(NULL, size, PROT_READ, MAP_PRIVATE, fd, 0));
    if (data == MAP_FAILED) {
        std::cerr << "Failed to map file: " << strerror(errno) << std::endl;
        close(fd);
        result.error = "Failed to map file";
        return result;
    }

    // Process the mapped file
    size_t offset = 80;
    uint32_t triangle_count;
    memcpy(&triangle_count, data + offset, sizeof(uint32_t));
    offset += sizeof(uint32_t);

    std::cout << "Binary STL: Found " << triangle_count << " triangles" << std::endl;

    // Process triangles in parallel
    const size_t batch_size = 10000;
    const size_t num_batches = (triangle_count + batch_size - 1) / batch_size;
    std::vector<std::future<size_t>> futures;

    for (size_t batch = 0; batch < num_batches; ++batch) {
        size_t start = batch * batch_size;
        size_t end = std::min(start + batch_size, static_cast<size_t>(triangle_count));

        futures.push_back(std::async(std::launch::async, [&, start, end]() {
            size_t local_count = 0;
            for (size_t i = start; i < end; ++i) {
                Triangle tri;
                size_t triangle_offset = offset + i * 50;
                
                // Read normal
                memcpy(tri.normal, data + triangle_offset, 12);
                
                // Read vertices
                memcpy(tri.vertex1, data + triangle_offset + 12, 12);
                memcpy(tri.vertex2, data + triangle_offset + 24, 12);
                memcpy(tri.vertex3, data + triangle_offset + 36, 12);
                
                // Read attribute count
                memcpy(&tri.attribute_count, data + triangle_offset + 48, 2);
                
                // Add to pool
                Triangle* tri_ptr = pool.allocate();
                new (tri_ptr) Triangle(tri);
                local_count++;
            }
            return local_count;
        }));
    }

    // Collect results
    size_t total_triangles = 0;
    for (auto& future : futures) {
        total_triangles += future.get();
    }

    // Unmap and close
    munmap(data, size);
    close(fd);
#endif

    // End timing
    auto total_end = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double, std::milli> total_duration = total_end - total_start;

    result.success = true;
    result.count = total_triangles;
    std::cout << "Binary STL parsing completed, " << total_triangles << " triangles parsed" << std::endl;
    std::cout << "Total parsing time: " << total_duration.count() << " ms" << std::endl;
    return result;
}

// Parse ASCII STL file
ParserResult StlParser::parse_ascii(const std::string& filename, ObjectPool<Triangle>& pool) {
    std::cout << "Parsing ASCII STL file: " << filename << std::endl;
    ParserResult result;
    result.success = false;
    result.count = 0;

    auto start = std::chrono::high_resolution_clock::now();

    try {
        std::ifstream file(filename);
        if (!file) {
            result.error = "Failed to open file";
            return result;
        }

        std::string line;
        size_t parsed_count = 0;

        while (std::getline(file, line)) {
            // Trim whitespace
            line.erase(0, line.find_first_not_of(" \t\r\n"));
            line.erase(line.find_last_not_of(" \t\r\n") + 1);

            if (line.empty()) continue;

            // Check for 'solid' keyword (start of file)
            if (line.substr(0, 5) == "solid") {
                // Found solid, start parsing triangles
                while (std::getline(file, line)) {
                    // Trim whitespace
                    line.erase(0, line.find_first_not_of(" \t\r\n"));
                    line.erase(line.find_last_not_of(" \t\r\n") + 1);

                    if (line.empty()) continue;

                    // Check for 'endsolid' keyword (end of file)
                    if (line.substr(0, 8) == "endsolid") {
                        break;
                    }

                    // Check for 'facet normal' keyword (start of triangle)
                    if (line.substr(0, 12) == "facet normal") {
                        Triangle tri;
                        
                        // Read normal
                        std::istringstream iss(line.substr(12));
                        iss >> tri.normal[0] >> tri.normal[1] >> tri.normal[2];

                        // Read 'outer loop'
                        std::getline(file, line);
                        line.erase(0, line.find_first_not_of(" \t\r\n"));

                        // Read three vertices
                        for (int i = 0; i < 3; ++i) {
                            std::getline(file, line);
                            line.erase(0, line.find_first_not_of(" \t\r\n"));
                            
                            if (line.substr(0, 6) == "vertex") {
                                std::istringstream viss(line.substr(6));
                                if (i == 0) {
                                    viss >> tri.vertex1[0] >> tri.vertex1[1] >> tri.vertex1[2];
                                } else if (i == 1) {
                                    viss >> tri.vertex2[0] >> tri.vertex2[1] >> tri.vertex2[2];
                                } else if (i == 2) {
                                    viss >> tri.vertex3[0] >> tri.vertex3[1] >> tri.vertex3[2];
                                }
                            }
                        }

                        // Read 'endloop' and 'endfacet'
                        std::getline(file, line); // endloop
                        std::getline(file, line); // endfacet

                        // Add to pool
                        Triangle* tri_ptr = pool.allocate();
                        new (tri_ptr) Triangle(tri);
                        parsed_count++;
                    }
                }
            }
        }

        result.success = true;
        result.count = parsed_count;
        std::cout << "ASCII STL parsing completed, " << parsed_count << " triangles parsed" << std::endl;
    } catch (const std::exception& e) {
        std::cerr << "Exception during ASCII parsing: " << e.what() << std::endl;
        result.error = std::string("Exception during parsing: ") + e.what();
    }

    auto end = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double, std::milli> duration = end - start;
    std::cout << "ASCII parsing time: " << duration.count() << " ms" << std::endl;

    return result;
}

// Parse STL file (auto format detection)
ParserResult StlParser::parse(const std::string& filename, ObjectPool<Triangle>& pool) {
    std::cout << "Starting to parse STL file: " << filename << std::endl;
    if (!file_exists(filename)) {
        ParserResult result;
        result.success = false;
        result.count = 0;
        result.error = "File does not exist";
        return result;
    }

    if (is_binary(filename)) {
        return parse_binary(filename, pool);
    } else {
        return parse_ascii(filename, pool);
    }
}

} // namespace core
} // namespace hhb