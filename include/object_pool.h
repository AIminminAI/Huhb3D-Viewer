#pragma once

#include <atomic>      // Atomic operations library for lock-free programming
#include <cstddef>     // Standard definitions, including size_t
#include <cstdint>     // Standard integer types
#include <memory>      // Memory management
#include <type_traits> // Type traits
#include <iostream>    // Input/output stream
#include <vector>
#include <stdexcept>

#ifdef _WIN32
#include <Windows.h>   // Windows system calls
#else
#include <sys/mman.h>  // Linux memory mapping
#include <unistd.h>    // Linux system calls
#endif

namespace hhb {
namespace core {

// Object pool configuration
template <typename T>
struct ObjectPoolConfig {
    static constexpr size_t DEFAULT_BLOCK_SIZE = 1024 * 1024; // 1MB block size
    static constexpr size_t DEFAULT_OBJECTS_PER_BLOCK = 1024;  // Default objects per block
};

// Memory block header structure
// alignas(64): Force alignment to 64 bytes, the size of a cache line
struct alignas(64) BlockHeader {
    std::atomic<BlockHeader*> next; // Atomic pointer to next block
    std::atomic<size_t> used;       // Number of used objects
    size_t capacity;                // Block capacity
    char data[];                    // Flexible array for actual objects
};

// Free object node
struct FreeNode {
    std::atomic<FreeNode*> next; // Atomic pointer to next free node
};

// High-performance object pool
template <typename T>
class ObjectPool {
public:
    // Constructor: Initialize object pool
    // objects_per_block: Number of objects per block
    ObjectPool(size_t objects_per_block = ObjectPoolConfig<T>::DEFAULT_OBJECTS_PER_BLOCK)
        : objects_per_block_(objects_per_block),
          // Calculate block size: block header size + object size * object count
          block_size_(sizeof(BlockHeader) + sizeof(T) * objects_per_block),
          head_block_(nullptr),
          free_list_(nullptr) {
        try {
            // Pre-allocate first block
            allocate_block();
        } catch (const std::exception& e) {
            std::cerr << "Exception in ObjectPool constructor: " << e.what() << std::endl;
            throw;
        }
    }

    // Destructor: Release all blocks
    ~ObjectPool() {
        // Release all blocks
        BlockHeader* block = head_block_;
        while (block) {
            BlockHeader* next = block->next;
            deallocate_block(block);
            block = next;
        }
    }

    // Disable copy and move
    ObjectPool(const ObjectPool&) = delete;
    ObjectPool& operator=(const ObjectPool&) = delete;
    ObjectPool(ObjectPool&&) = delete;
    ObjectPool& operator=(ObjectPool&&) = delete;

    // Allocate object
    T* allocate() {
        // Try to get from free list
        FreeNode* node = free_list_.load(std::memory_order_acquire);
        while (node) {
            // Load next node with acquire memory order
            FreeNode* next = node->next.load(std::memory_order_acquire);
            // Compare-exchange weak: lock-free CAS operation
            if (free_list_.compare_exchange_weak(node, next, std::memory_order_acq_rel, std::memory_order_acquire)) {
                // Reinterpret cast: convert FreeNode* to T*
                return reinterpret_cast<T*>(node);
            }
        }

        // Free list is empty, try to allocate in existing blocks
        BlockHeader* block = head_block_.load(std::memory_order_acquire);
        while (block) {
            size_t used = block->used.load(std::memory_order_acquire);
            while (used < block->capacity) {
                if (block->used.compare_exchange_weak(
                        used, used + 1,
                        std::memory_order_acq_rel,
                        std::memory_order_acquire)) {
                    return reinterpret_cast<T*>(block->data + sizeof(T) * used);
                }
            }
            block = block->next.load(std::memory_order_acquire);
        }

        // All blocks are full, allocate new block and retry on head
        allocate_block();
        BlockHeader* head = head_block_.load(std::memory_order_acquire);
        while (true) {
            size_t used = head->used.load(std::memory_order_acquire);
            if (used >= head->capacity) {
                allocate_block();
                head = head_block_.load(std::memory_order_acquire);
                continue;
            }
            if (head->used.compare_exchange_weak(
                    used, used + 1,
                    std::memory_order_acq_rel,
                    std::memory_order_acquire)) {
                return reinterpret_cast<T*>(head->data + sizeof(T) * used);
            }
        }
    }

    // Deallocate object
    void deallocate(T* ptr) {
        // Convert object to free node
        FreeNode* node = reinterpret_cast<FreeNode*>(ptr);
        // Load free list head with acquire memory order
        FreeNode* old_head = free_list_.load(std::memory_order_acquire);
        do {
            // Set new node's next pointer to old head
            node->next.store(old_head, std::memory_order_release);
            // CAS operation: try to set new node as list head
        } while (!free_list_.compare_exchange_weak(old_head, node, std::memory_order_acq_rel, std::memory_order_acquire));
    }

    // Get number of allocated objects
    size_t size() const {
        size_t total = 0;
        BlockHeader* block = head_block_.load(std::memory_order_acquire);
        while (block) {
            total += block->used.load(std::memory_order_acquire);
            block = block->next.load(std::memory_order_acquire);
        }
        return total;
    }

    // Iterate all objects and execute callback
    template <typename Func>
    void for_each(Func func) {
        BlockHeader* block = head_block_.load(std::memory_order_acquire);
        while (block) {
            size_t used = block->used.load(std::memory_order_acquire);
            for (size_t i = 0; i < used; ++i) {
                T* obj = reinterpret_cast<T*>(block->data + sizeof(T) * i);
                func(obj);
            }
            block = block->next.load(std::memory_order_acquire);
        }
    }

    // Access object by index
    T& operator[](size_t index) {
        size_t current_index = 0;
        BlockHeader* block = head_block_.load(std::memory_order_acquire);
        
        // Reverse traversal since blocks are linked in reverse order
        std::vector<BlockHeader*> blocks;
        while (block) {
            blocks.push_back(block);
            block = block->next.load(std::memory_order_acquire);
        }
        
        // Traverse in reverse order (oldest first)
        for (auto it = blocks.rbegin(); it != blocks.rend(); ++it) {
            BlockHeader* b = *it;
            size_t used = b->used.load(std::memory_order_acquire);
            if (index < current_index + used) {
                size_t offset = index - current_index;
                return *reinterpret_cast<T*>(b->data + sizeof(T) * offset);
            }
            current_index += used;
        }
        
        throw std::out_of_range("Index out of range");
    }

    // Const access
    const T& operator[](size_t index) const {
        return const_cast<ObjectPool*>(this)->operator[](index);
    }

private:
    // Allocate new memory block
    void allocate_block() {
        try {
            // Calculate block size
            size_t actual_block_size = block_size_;
            std::cout << "Allocating block with size: " << actual_block_size << " bytes" << std::endl;
            
            // Allocate memory
            void* memory = nullptr;
#ifdef _WIN32
            // Windows: Use VirtualAlloc to allocate virtual memory
            // MEM_COMMIT | MEM_RESERVE: Reserve and commit memory
            // PAGE_READWRITE: Readable and writable
            std::cout << "Calling VirtualAlloc" << std::endl;
            memory = VirtualAlloc(nullptr, actual_block_size, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
            std::cout << "VirtualAlloc returned: " << memory << std::endl;
#else
            // Linux: Use mmap to allocate memory
            // MAP_PRIVATE | MAP_ANONYMOUS: Private, anonymous mapping
            // PROT_READ | PROT_WRITE: Readable and writable
            memory = mmap(nullptr, actual_block_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
#endif

            if (!memory) {
                std::cerr << "Failed to allocate memory" << std::endl;
                throw std::bad_alloc();
            }

            // Initialize block header
            BlockHeader* block = reinterpret_cast<BlockHeader*>(memory);
            block->used.store(0, std::memory_order_release);
            block->capacity = objects_per_block_;

            BlockHeader* old_head = head_block_.load(std::memory_order_acquire);
            do {
                block->next.store(old_head, std::memory_order_release);
            } while (!head_block_.compare_exchange_weak(old_head, block, std::memory_order_acq_rel, std::memory_order_acquire));
            std::cout << "Block allocated successfully" << std::endl;
        } catch (const std::exception& e) {
            std::cerr << "Exception in allocate_block: " << e.what() << std::endl;
            throw;
        }
    }

    // Release memory block
    void deallocate_block(BlockHeader* block) {
#ifdef _WIN32
        // Windows: Use VirtualFree to release memory
        // MEM_RELEASE: Release entire memory block
        VirtualFree(block, 0, MEM_RELEASE);
#else
        // Linux: Use munmap to release memory
        munmap(block, block_size_);
#endif
    }

    size_t objects_per_block_; // Number of objects per block
    size_t block_size_;        // Size of each block
    std::atomic<BlockHeader*> head_block_;  // Head block pointer
    std::atomic<FreeNode*> free_list_; // Free list (atomic pointer)
};

} // namespace core
} // namespace hhb
