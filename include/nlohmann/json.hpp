#ifndef NLOHMANN_JSON_HPP
#define NLOHMANN_JSON_HPP

#include <string>
#include <map>
#include <vector>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <initializer_list>
#include <cmath>

namespace nlohmann {

class json {
public:
    enum class value_t { null, string, number_integer, number_float, boolean, array, object };

    json() : type_(value_t::null) {}
    json(std::nullptr_t) : type_(value_t::null) {}
    json(const std::string& s) : type_(value_t::string), str_val_(s) {}
    json(const char* s) : type_(value_t::string), str_val_(s) {}
    json(double d) : type_(value_t::number_float), float_val_(d), int_val_(0) {}
    json(int i) : type_(value_t::number_integer), int_val_(i), float_val_(0.0) {}
    json(bool b) : type_(value_t::boolean), bool_val_(b), int_val_(0), float_val_(0.0) {}

    json(std::initializer_list<json> init) {
        if (init.size() > 0 && init.begin()->is_pair()) {
            type_ = value_t::object;
            for (const auto& el : init) {
                obj_val_[el.pair_key_] = el.pair_val_;
            }
        } else {
            type_ = value_t::array;
            for (const auto& el : init) {
                arr_val_.push_back(el);
            }
        }
    }

    static json object(std::initializer_list<std::pair<std::string, json>> init) {
        json j;
        j.type_ = value_t::object;
        for (const auto& p : init) {
            j.obj_val_[p.first] = p.second;
        }
        return j;
    }

    static json array() {
        json j;
        j.type_ = value_t::array;
        return j;
    }

    static json parse(const std::string& s) {
        size_t pos = 0;
        return parse_value(s, pos);
    }

    bool is_null() const { return type_ == value_t::null; }
    bool is_string() const { return type_ == value_t::string; }
    bool is_number() const { return type_ == value_t::number_integer || type_ == value_t::number_float; }
    bool is_boolean() const { return type_ == value_t::boolean; }
    bool is_array() const { return type_ == value_t::array; }
    bool is_object() const { return type_ == value_t::object; }

    json& operator[](const std::string& key) {
        if (type_ != value_t::object) {
            type_ = value_t::object;
            obj_val_.clear();
        }
        return obj_val_[key];
    }

    const json& operator[](const std::string& key) const {
        static json null_json;
        auto it = obj_val_.find(key);
        return it != obj_val_.end() ? it->second : null_json;
    }

    json& operator[](size_t idx) {
        if (type_ != value_t::array) {
            type_ = value_t::array;
        }
        if (idx >= arr_val_.size()) {
            arr_val_.resize(idx + 1);
        }
        return arr_val_[idx];
    }

    const json& operator[](size_t idx) const {
        static json null_json;
        return idx < arr_val_.size() ? arr_val_[idx] : null_json;
    }

    void push_back(const json& val) {
        if (type_ != value_t::array) {
            type_ = value_t::array;
        }
        arr_val_.push_back(val);
    }

    size_t size() const {
        if (type_ == value_t::array) return arr_val_.size();
        if (type_ == value_t::object) return obj_val_.size();
        return 0;
    }

    bool empty() const {
        if (type_ == value_t::array) return arr_val_.empty();
        if (type_ == value_t::object) return obj_val_.empty();
        return type_ == value_t::null;
    }

    bool contains(const std::string& key) const {
        return type_ == value_t::object && obj_val_.find(key) != obj_val_.end();
    }

    std::string as_string() const {
        if (type_ == value_t::string) return str_val_;
        if (type_ == value_t::number_integer) return std::to_string(int_val_);
        if (type_ == value_t::number_float) return std::to_string(float_val_);
        if (type_ == value_t::boolean) return bool_val_ ? "true" : "false";
        return "";
    }

    int as_int() const {
        if (type_ == value_t::number_integer) return int_val_;
        if (type_ == value_t::number_float) return static_cast<int>(float_val_);
        if (type_ == value_t::string) { try { return std::stoi(str_val_); } catch (...) { return 0; } }
        return 0;
    }

    double as_double() const {
        if (type_ == value_t::number_float) return float_val_;
        if (type_ == value_t::number_integer) return static_cast<double>(int_val_);
        if (type_ == value_t::string) { try { return std::stod(str_val_); } catch (...) { return 0.0; } }
        return 0.0;
    }

    bool as_bool() const {
        if (type_ == value_t::boolean) return bool_val_;
        if (type_ == value_t::number_integer) return int_val_ != 0;
        if (type_ == value_t::string) return str_val_ == "true";
        return false;
    }

    std::string dump(int indent = -1) const {
        std::ostringstream oss;
        serialize(oss, indent > 0 ? indent : 0, 0);
        return oss.str();
    }

    typedef std::map<std::string, json>::iterator iterator;
    typedef std::map<std::string, json>::const_iterator const_iterator;

    iterator begin() { return obj_val_.begin(); }
    iterator end() { return obj_val_.end(); }
    const_iterator begin() const { return obj_val_.begin(); }
    const_iterator end() const { return obj_val_.end(); }

    std::vector<json>::iterator arr_begin() { return arr_val_.begin(); }
    std::vector<json>::iterator arr_end() { return arr_val_.end(); }

private:
    value_t type_ = value_t::null;
    std::string str_val_;
    int int_val_ = 0;
    double float_val_ = 0.0;
    bool bool_val_ = false;
    std::vector<json> arr_val_;
    std::map<std::string, json> obj_val_;

    std::string pair_key_;
    json pair_val_;
    bool is_pair_ = false;

    json(bool is_pair, const std::string& key, const json& val)
        : type_(value_t::null), is_pair_(is_pair), pair_key_(key), pair_val_(val) {}

    bool is_pair() const { return is_pair_; }

    void serialize(std::ostringstream& oss, int indent, int level) const {
        std::string pad(indent * level, ' ');
        std::string pad1(indent * (level + 1), ' ');

        switch (type_) {
        case value_t::null:
            oss << "null"; break;
        case value_t::string:
            oss << '"';
            for (char c : str_val_) {
                switch (c) {
                case '"': oss << "\\\""; break;
                case '\\': oss << "\\\\"; break;
                case '\n': oss << "\\n"; break;
                case '\r': oss << "\\r"; break;
                case '\t': oss << "\\t"; break;
                default: oss << c; break;
                }
            }
            oss << '"';
            break;
        case value_t::number_integer:
            oss << int_val_; break;
        case value_t::number_float:
            if (std::isfinite(float_val_)) {
                char buf[64];
                std::snprintf(buf, sizeof(buf), "%.6g", float_val_);
                oss << buf;
            } else {
                oss << "null";
            }
            break;
        case value_t::boolean:
            oss << (bool_val_ ? "true" : "false"); break;
        case value_t::array:
            oss << '[';
            if (indent > 0) oss << '\n';
            for (size_t i = 0; i < arr_val_.size(); ++i) {
                if (indent > 0) oss << pad1;
                arr_val_[i].serialize(oss, indent, level + 1);
                if (i + 1 < arr_val_.size()) oss << ',';
                if (indent > 0) oss << '\n';
            }
            if (indent > 0) oss << pad;
            oss << ']';
            break;
        case value_t::object:
            oss << '{';
            if (indent > 0) oss << '\n';
            {
                bool first = true;
                for (const auto& kv : obj_val_) {
                    if (!first) oss << ',';
                    if (indent > 0) oss << '\n' << pad1;
                    else if (!first) oss << ' ';
                    oss << '"';
                    for (char c : kv.first) {
                        if (c == '"') oss << "\\\"";
                        else if (c == '\\') oss << "\\\\";
                        else oss << c;
                    }
                    oss << "\":";
                    if (indent > 0) oss << ' ';
                    kv.second.serialize(oss, indent, level + 1);
                    first = false;
                }
            }
            if (indent > 0) oss << '\n' << pad;
            oss << '}';
            break;
        }
    }

    static void skip_ws(const std::string& s, size_t& pos) {
        while (pos < s.size() && (s[pos] == ' ' || s[pos] == '\t' || s[pos] == '\n' || s[pos] == '\r'))
            ++pos;
    }

    static json parse_value(const std::string& s, size_t& pos) {
        skip_ws(s, pos);
        if (pos >= s.size()) return json();

        char c = s[pos];
        if (c == '"') return parse_string(s, pos);
        if (c == '{') return parse_object(s, pos);
        if (c == '[') return parse_array(s, pos);
        if (c == 't' || c == 'f') return parse_bool(s, pos);
        if (c == 'n') return parse_null(s, pos);
        if (c == '-' || (c >= '0' && c <= '9')) return parse_number(s, pos);
        return json();
    }

    static json parse_string(const std::string& s, size_t& pos) {
        ++pos;
        std::string result;
        while (pos < s.size() && s[pos] != '"') {
            if (s[pos] == '\\' && pos + 1 < s.size()) {
                ++pos;
                switch (s[pos]) {
                case '"': result += '"'; break;
                case '\\': result += '\\'; break;
                case 'n': result += '\n'; break;
                case 'r': result += '\r'; break;
                case 't': result += '\t'; break;
                case 'u': {
                    result += "\\u";
                    for (int i = 0; i < 4 && pos + 1 < s.size(); ++i) {
                        ++pos;
                        result += s[pos];
                    }
                    break;
                }
                default: result += s[pos]; break;
                }
            } else {
                result += s[pos];
            }
            ++pos;
        }
        if (pos < s.size()) ++pos;
        return json(result);
    }

    static json parse_number(const std::string& s, size_t& pos) {
        size_t start = pos;
        bool is_float = false;
        if (s[pos] == '-') ++pos;
        while (pos < s.size() && s[pos] >= '0' && s[pos] <= '9') ++pos;
        if (pos < s.size() && s[pos] == '.') { is_float = true; ++pos; while (pos < s.size() && s[pos] >= '0' && s[pos] <= '9') ++pos; }
        if (pos < s.size() && (s[pos] == 'e' || s[pos] == 'E')) { is_float = true; ++pos; if (pos < s.size() && (s[pos] == '+' || s[pos] == '-')) ++pos; while (pos < s.size() && s[pos] >= '0' && s[pos] <= '9') ++pos; }
        std::string num_str = s.substr(start, pos - start);
        if (is_float) return json(std::stod(num_str));
        return json(std::stoi(num_str));
    }

    static json parse_bool(const std::string& s, size_t& pos) {
        if (s.substr(pos, 4) == "true") { pos += 4; return json(true); }
        if (s.substr(pos, 5) == "false") { pos += 5; return json(false); }
        return json();
    }

    static json parse_null(const std::string& s, size_t& pos) {
        if (s.substr(pos, 4) == "null") { pos += 4; }
        return json();
    }

    static json parse_array(const std::string& s, size_t& pos) {
        json arr;
        arr.type_ = value_t::array;
        ++pos;
        skip_ws(s, pos);
        if (pos < s.size() && s[pos] == ']') { ++pos; return arr; }
        while (pos < s.size()) {
            arr.arr_val_.push_back(parse_value(s, pos));
            skip_ws(s, pos);
            if (pos < s.size() && s[pos] == ',') { ++pos; skip_ws(s, pos); }
            else break;
        }
        if (pos < s.size() && s[pos] == ']') ++pos;
        return arr;
    }

    static json parse_object(const std::string& s, size_t& pos) {
        json obj;
        obj.type_ = value_t::object;
        ++pos;
        skip_ws(s, pos);
        if (pos < s.size() && s[pos] == '}') { ++pos; return obj; }
        while (pos < s.size()) {
            skip_ws(s, pos);
            std::string key = parse_string(s, pos).str_val_;
            skip_ws(s, pos);
            if (pos < s.size() && s[pos] == ':') ++pos;
            skip_ws(s, pos);
            obj.obj_val_[key] = parse_value(s, pos);
            skip_ws(s, pos);
            if (pos < s.size() && s[pos] == ',') { ++pos; skip_ws(s, pos); }
            else break;
        }
        if (pos < s.size() && s[pos] == '}') ++pos;
        return obj;
    }
};

} // namespace nlohmann

#endif // NLOHMANN_JSON_HPP
