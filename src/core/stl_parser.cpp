#include "stl_parser.h"
#include <fstream>
#include <cstring>
#include <iostream>
#include <thread>
#include <vector>
#include <future>
#include <algorithm>
#include <chrono>

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
        nullptr,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        nullptr
    );

    if (hFile == INVALID_HANDLE_VALUE) {
        DWORD error = GetLastError();
        std::cerr << "Failed to open file, error: " << error << std::endl;
        result.error = "Failed to open file";
        return result;
    }
    std::cout << "File opened successfully" << std::endl;

    std::cout << "Getting file size" << std::endl;
    DWORD fileSize = GetFileSize(hFile, nullptr);
    if (fileSize == INVALID_FILE_SIZE) {
        DWORD error = GetLastError();
        std::cerr << "Failed to get file size, error: " << error << std::endl;
        CloseHandle(hFile);
        result.error = "Failed to get file size";
        return result;
    }
    std::cout << "File size: " << fileSize << " bytes" << std::endl;

    std::cout << "Creating file mapping" << std::endl;
    HANDLE hMap = CreateFileMappingA(
        hFile,
        nullptr,
        PAGE_READONLY,
        0,
        fileSize,
        nullptr
    );

    if (hMap == nullptr) {
        DWORD error = GetLastError();
        std::cerr << "Failed to create file mapping, error: " << error << std::endl;
        CloseHandle(hFile);
        result.error = "Failed to create file mapping";
        return result;
    }
    std::cout << "File mapping created successfully" << std::endl;

    std::cout << "Mapping view of file" << std::endl;
    const char* mappedData = reinterpret_cast<const char*>(MapViewOfFile(
        hMap,
        FILE_MAP_READ,
        0,
        0,
        fileSize
    ));

    if (mappedData == nullptr) {
        DWORD error = GetLastError();
        std::cerr << "Failed to map view of file, error: " << error << std::endl;
        CloseHandle(hMap);
        CloseHandle(hFile);
        result.error = "Failed to map view of file";
        return result;
    }
    std::cout << "File mapped successfully" << std::endl;

    // Parse data
    const char* data = mappedData + 80; // Skip 80-byte header
    uint32_t triangle_count = *reinterpret_cast<const uint32_t*>(data);
    std::cout << "Triangle count from file: " << triangle_count << std::endl;
    data += 4;

    // Verify file size is sufficient
    size_t expected_size = 80 + 4 + triangle_count * 50;
    if (fileSize < expected_size) {
        std::cerr << "File size is smaller than expected: " << fileSize << " < " << expected_size << std::endl;
        UnmapViewOfFile(mappedData);
        CloseHandle(hMap);
        CloseHandle(hFile);
        result.error = "File size is smaller than expected";
        return result;
    }

    // Start timing for the actual parsing (zero-copy)
    auto parsing_start = std::chrono::high_resolution_clock::now();

    // Multi-threaded zero-copy parsing
    const int NUM_THREADS = 4;
    size_t parsed_count = 0;
    std::vector<std::future<size_t>> futures;
    
    // Calculate workload per thread
    size_t triangles_per_thread = triangle_count / NUM_THREADS;
    size_t remaining_triangles = triangle_count % NUM_THREADS;
    
    std::cout << "Starting multi-threaded zero-copy parsing with " << NUM_THREADS << " threads" << std::endl;
    std::cout << "Triangles per thread: " << triangles_per_thread << std::endl;
    std::cout << "Remaining triangles: " << remaining_triangles << std::endl;
    
    // Create threads
    for (int i = 0; i < NUM_THREADS; ++i) {
        size_t start_idx = i * triangles_per_thread;
        size_t end_idx = start_idx + triangles_per_thread;
        
        // Handle remaining triangles
        if (i == NUM_THREADS - 1) {
            end_idx += remaining_triangles;
        }
        
        // Calculate thread's start data pointer
        const char* thread_data = data + start_idx * 50;
        
        // Create thread task
        futures.push_back(std::async(std::launch::async, [&pool, thread_data, start_idx, end_idx]() -> size_t {
            size_t thread_parsed = 0;
            const char* current_data = thread_data;
            
            for (size_t j = start_idx; j < end_idx; ++j) {
                try {
                    Triangle* tri = pool.allocate();
                    if (!tri) {
                        std::cerr << "Failed to allocate triangle" << std::endl;
                        break;
                    }
                    
                    // Zero-copy: Directly cast and copy the 50-byte triangle data
                    // This avoids individual field copying and improves performance
                    memcpy(tri, current_data, 50); // Each triangle is fixed 50 bytes in binary STL
                    current_data += 50;
                    thread_parsed++;
                    
                    // Output progress every 10000 triangles
                    if (thread_parsed % 10000 == 0) {
                        std::cout << "Thread " << std::this_thread::get_id() << " parsed " << thread_parsed << " triangles..." << std::endl;
                    }
                } catch (const std::exception& e) {
                    std::cerr << "Exception during parsing triangle " << j << ": " << e.what() << std::endl;
                    break;
                }
            }
            
            std::cout << "Thread " << std::this_thread::get_id() << " finished, parsed " << thread_parsed << " triangles" << std::endl;
            return thread_parsed;
        }));
    }
    
    // Wait for all threads to complete and sum results
    for (auto& future : futures) {
        parsed_count += future.get();
    }
    
    // End timing for parsing
    auto parsing_end = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double, std::micro> parsing_duration = parsing_end - parsing_start;
    std::cout << "Zero-copy parsing completed in " << parsing_duration.count() << " microseconds" << std::endl;

    // Cleanup
    std::cout << "Unmapping file" << std::endl;
    UnmapViewOfFile(mappedData);
    std::cout << "Closing file mapping" << std::endl;
    CloseHandle(hMap);
    std::cout << "Closing file" << std::endl;
    CloseHandle(hFile);

    // End timing for entire process
    auto total_end = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double, std::micro> total_duration = total_end - total_start;
    std::cout << "Total parsing process completed in " << total_duration.count() << " microseconds" << std::endl;

    result.success = true;
    result.count = parsed_count;
    std::cout << "Binary STL parsing completed, " << parsed_count << " triangles parsed" << std::endl;
    return result;
#else
    // Linux memory mapping
    int fd = open(filename.c_str(), O_RDONLY);
    if (fd == -1) {
        result.error = "Failed to open file";
        return result;
    }

    struct stat sb;
    if (fstat(fd, &sb) == -1) {
        close(fd);
        result.error = "Failed to get file size";
        return result;
    }

    const char* mappedData = reinterpret_cast<const char*>(mmap(
        nullptr,
        sb.st_size,
        PROT_READ,
        MAP_PRIVATE,
        fd,
        0
    ));

    if (mappedData == MAP_FAILED) {
        close(fd);
        result.error = "Failed to map file";
        return result;
    }

    // Parse data
    const char* data = mappedData + 80; // Skip 80-byte header
    uint32_t triangle_count = *reinterpret_cast<const uint32_t*>(data);
    data += 4;

    // Verify file size is sufficient
    size_t expected_size = 80 + 4 + triangle_count * 50;
    if (sb.st_size < expected_size) {
        std::cerr << "File size is smaller than expected: " << sb.st_size << " < " << expected_size << std::endl;
        munmap(const_cast<char*>(mappedData), sb.st_size);
        close(fd);
        result.error = "File size is smaller than expected";
        return result;
    }

    // Multi-threaded parsing
    const int NUM_THREADS = 4;
    size_t parsed_count = 0;
    std::vector<std::future<size_t>> futures;
    
    // Calculate workload per thread
    size_t triangles_per_thread = triangle_count / NUM_THREADS;
    size_t remaining_triangles = triangle_count % NUM_THREADS;
    
    std::cout << "Starting multi-threaded parsing with " << NUM_THREADS << " threads" << std::endl;
    std::cout << "Triangles per thread: " << triangles_per_thread << std::endl;
    std::cout << "Remaining triangles: " << remaining_triangles << std::endl;
    
    // Start timing
    auto thread_start = std::chrono::high_resolution_clock::now();
    
    // Create threads
    for (int i = 0; i < NUM_THREADS; ++i) {
        size_t start_idx = i * triangles_per_thread;
        size_t end_idx = start_idx + triangles_per_thread;
        
        // Handle remaining triangles
        if (i == NUM_THREADS - 1) {
            end_idx += remaining_triangles;
        }
        
        // Calculate thread's start data pointer
        const char* thread_data = data + start_idx * 50;
        
        // Create thread task
        futures.push_back(std::async(std::launch::async, [&pool, thread_data, start_idx, end_idx]() -> size_t {
            size_t thread_parsed = 0;
            const char* current_data = thread_data;
            
            for (size_t j = start_idx; j < end_idx; ++j) {
                try {
                    Triangle* tri = pool.allocate();
                    if (!tri) {
                        std::cerr << "Failed to allocate triangle" << std::endl;
                        break;
                    }
                    // Safe data copy
                    memcpy(tri, current_data, sizeof(Triangle));
                    current_data += 50; // Each triangle is fixed 50 bytes in binary STL
                    thread_parsed++;
                    
                    // Output progress every 10000 triangles
                    if (thread_parsed % 10000 == 0) {
                        std::cout << "Thread " << std::this_thread::get_id() << " parsed " << thread_parsed << " triangles..." << std::endl;
                    }
                } catch (const std::exception& e) {
                    std::cerr << "Exception during parsing triangle " << j << ": " << e.what() << std::endl;
                    break;
                }
            }
            
            std::cout << "Thread " << std::this_thread::get_id() << " finished, parsed " << thread_parsed << " triangles" << std::endl;
            return thread_parsed;
        }));
    }
    
    // Wait for all threads to complete and sum results
    for (auto& future : futures) {
        parsed_count += future.get();
    }
    
    // End timing
    auto thread_end = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double, std::milli> thread_duration = thread_end - thread_start;
    std::cout << "Multi-threaded parsing completed in " << thread_duration.count() << " ms" << std::endl;

    // Cleanup
    munmap(const_cast<char*>(mappedData), sb.st_size);
    close(fd);

    result.success = true;
    result.count = parsed_count;
    return result;
#endif
}

// Parse ASCII STL file
ParserResult StlParser::parse_ascii(const std::string& filename, ObjectPool<Triangle>& pool) {
    std::cout << "Parsing ASCII STL file: " << filename << std::endl;
    ParserResult result;
    result.success = false;
    result.count = 0;

    std::ifstream file(filename);
    if (!file) {
        result.error = "Failed to open file";
        return result;
    }

    std::string line;
    size_t parsed_count = 0;

    // Skip file header
    while (std::getline(file, line)) {
        if (line.find("solid") != std::string::npos) {
            break;
        }
    }

    // Parse triangles
    while (file) {
        // Find facet start
        while (std::getline(file, line)) {
            if (line.find("facet normal") != std::string::npos) {
                break;
            }
        }

        if (!file) {
            break;
        }

        // Parse normal vector
        Triangle* tri = pool.allocate();
        sscanf(line.c_str(), "facet normal %f %f %f", &tri->normal[0], &tri->normal[1], &tri->normal[2]);

        // Skip outer loop
        std::getline(file, line);

        // Parse three vertices
        std::getline(file, line);
        sscanf(line.c_str(), "vertex %f %f %f", &tri->vertex1[0], &tri->vertex1[1], &tri->vertex1[2]);

        std::getline(file, line);
        sscanf(line.c_str(), "vertex %f %f %f", &tri->vertex2[0], &tri->vertex2[1], &tri->vertex2[2]);

        std::getline(file, line);
        sscanf(line.c_str(), "vertex %f %f %f", &tri->vertex3[0], &tri->vertex3[1], &tri->vertex3[2]);

        // Skip endloop and endfacet
        std::getline(file, line);
        std::getline(file, line);

        tri->attribute_count = 0;
        parsed_count++;
    }

    result.success = true;
    result.count = parsed_count;
    std::cout << "ASCII STL parsing completed, " << parsed_count << " triangles parsed" << std::endl;
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