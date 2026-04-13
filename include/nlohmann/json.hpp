#ifndef NLOHMANN_JSON_HPP
#define NLOHMANN_JSON_HPP

#include <string>
#include <map>
#include <vector>
#include <iostream>
#include <sstream>

namespace nlohmann {

class json {
public:
    json() : type_(Type::Null) {}
    
    json(const std::string& s) : type_(Type::String), string_value_(s) {}
    
    json(double d) : type_(Type::Number), number_value_(d) {}
    
    json(int i) : type_(Type::Number), number_value_(i) {}
    
    json(bool b) : type_(Type::Boolean), bool_value_(b) {}
    
    json(std::initializer_list<std::pair<std::string, json>> init) 
        : type_(Type::Object) {
        for (const auto& pair : init) {
            object_value_[pair.first] = pair.second;
        }
    }
    
    json& operator[](const std::string& key) {
        if (type_ != Type::Object) {
            type_ = Type::Object;
            object_value_.clear();
        }
        return object_value_[key];
    }
    
    std::string dump() const {
        std::ostringstream oss;
        serialize(oss);
        return oss.str();
    }
    
private:
    enum class Type {
        Null,
        String,
        Number,
        Boolean,
        Object
    };
    
    Type type_;
    std::string string_value_;
    double number_value_;
    bool bool_value_;
    std::map<std::string, json> object_value_;
    
    void serialize(std::ostringstream& oss) const {
        switch (type_) {
            case Type::Null:
                oss << "null";
                break;
            case Type::String:
                oss << '"' << string_value_ << '"';
                break;
            case Type::Number:
                oss << number_value_;
                break;
            case Type::Boolean:
                oss << (bool_value_ ? "true" : "false");
                break;
            case Type::Object:
                oss << '{';
                bool first = true;
                for (const auto& pair : object_value_) {
                    if (!first) oss << ",";
                    oss << '"' << pair.first << '"' << ":";
                    pair.second.serialize(oss);
                    first = false;
                }
                oss << '}';
                break;
        }
    }
};

} // namespace nlohmann

#endif // NLOHMANN_JSON_HPP