#pragma once

#include <coroutine> // 必须包含，用于协程 handle 和 traits
#include <expected> // 必须包含，用于 std::expected 和 std::unexpected
#include <string>
#include <utility>
#include "object_pool.h"
#include "stl_parser.h"

namespace hhb {
namespace core {

// Coroutine task type
template <typename T>
struct ParserTask {
    struct promise_type {
        std::expected<T, std::string> result;

        ParserTask<T> get_return_object() {
            return ParserTask<T>{std::coroutine_handle<promise_type>::from_promise(*this)};
        }

        std::suspend_never initial_suspend() noexcept {
            return {};
        }

        std::suspend_never final_suspend() noexcept {
            return {};
        }

        void return_value(std::expected<T, std::string> value) {
            result = std::move(value);
        }

        void unhandled_exception() {
            result = std::unexpected("Exception occurred");
        }
    };

    std::coroutine_handle<promise_type> handle;

    ~ParserTask() {
        if (handle) {
            handle.destroy();
        }
    }

    std::expected<T, std::string> get() {
        return handle.promise().result;
    }

    // Awaiter interface for co_await
    bool await_ready() const noexcept {
        return false; // Always suspend
    }

    void await_suspend(std::coroutine_handle<> h) const noexcept {
        // No special handling needed for this simple case
    }

    std::expected<T, std::string> await_resume() {
        return handle.promise().result;
    }
};

// Coroutine-based STL parser class
class StlParserCoroutine {
public:
    StlParserCoroutine() = default;
    ~StlParserCoroutine() = default;

    // Parse ASCII STL file (coroutine version)
    ParserTask<size_t> parse_ascii(const std::string& filename, ObjectPool<Triangle>& pool);

private:
    // Asynchronously read file line
    ParserTask<std::string> read_line(std::ifstream& file);
};

} // namespace core
} // namespace hhb