#pragma once

#include <string>
#include <type_traits>

// 绠€鍖栫増鐨?simdjson 澶存枃浠讹紝瀹為檯椤圭洰涓簲璇ヤ娇鐢ㄥ畬鏁寸殑 simdjson 搴?

namespace simdjson {

class simdjson_error {
public:
    simdjson_error(const char* message) : message_(message) {}
    const char* what() const { return message_; }
private:
    const char* message_;
};

namespace dom {

class element {
public:
    element() = default;
    
    template<typename T>
    bool is() const {
        return true;
    }
    
    template<typename T>
    T get() const {
        if constexpr (std::is_same_v<T, std::string>) {
            return "test";
        } else if constexpr (std::is_same_v<T, double>) {
            return 0.0;
        } else if constexpr (std::is_same_v<T, uint64_t>) {
            return 0;
        } else {
            return T{};
        }
    }
    
    std::string get_string() const {
        return "test";
    }
    
    double get_double() const {
        return 0.0;
    }
    
    uint64_t get_uint64() const {
        return 0;
    }
    
    bool contains(const char*) const {
        return true;
    }
    
    element operator[](const char*) const {
        return element();
    }
    
    element get_object() const {
        return element();
    }
};

class parser {
public:
    element parse(const std::string&) {
        return element();
    }
};

} // namespace dom

} // namespace simdjson
