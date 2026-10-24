#pragma once

#include <string>
#include <unordered_set>
#include <unordered_map>
#include <utility>

// Syntax/ambiguity check only: the Credential Provider still validates the
// authorization fields independently. No login decision is made here.
class FaceKidsJsonEnvelopeGuard final {
    class Parser {
        const std::string& s_;
        size_t pos_ = 0;
        unsigned depth_ = 0;
        std::unordered_map<std::string, std::pair<size_t, size_t>> topLevelFields_;

        void whitespace() {
            while (pos_ < s_.size() && (s_[pos_] == ' ' || s_[pos_] == '\t' ||
                                        s_[pos_] == '\r' || s_[pos_] == '\n')) ++pos_;
        }
        bool consume(char ch) {
            whitespace();
            if (pos_ >= s_.size() || s_[pos_] != ch) return false;
            ++pos_;
            return true;
        }
        bool literal(const char* text) {
            size_t n = 0;
            while (text[n]) ++n;
            if (s_.compare(pos_, n, text, n) != 0) return false;
            pos_ += n;
            return true;
        }
        bool stringValue(std::string* key = nullptr) {
            if (!consume('"')) return false;
            const size_t start = pos_;
            while (pos_ < s_.size()) {
                unsigned char c = static_cast<unsigned char>(s_[pos_++]);
                if (c == '"') {
                    if (key) *key = s_.substr(start, pos_ - start - 1);
                    return true;
                }
                if (c < 0x20) return false;
                if (c == '\\') {
                    // The server emits literal ASCII JSON keys; escaped keys can
                    // alias authorization fields and must fail closed.
                    if (key) return false;
                    if (pos_ == s_.size()) return false;
                    char escaped = s_[pos_++];
                    if (escaped == 'u') {
                        for (int n = 0; n < 4; ++n) {
                            if (pos_ >= s_.size()) return false;
                            char h = s_[pos_++];
                            if (!((h >= '0' && h <= '9') ||
                                  (h >= 'a' && h <= 'f') ||
                                  (h >= 'A' && h <= 'F'))) return false;
                        }
                    } else if (escaped != '"' && escaped != '\\' && escaped != '/' &&
                               escaped != 'b' && escaped != 'f' && escaped != 'n' &&
                               escaped != 'r' && escaped != 't') {
                        return false;
                    }
                }
            }
            return false;
        }
        bool digits() {
            size_t start = pos_;
            while (pos_ < s_.size() && s_[pos_] >= '0' && s_[pos_] <= '9') ++pos_;
            return pos_ != start;
        }
        bool number() {
            if (pos_ < s_.size() && s_[pos_] == '-') ++pos_;
            if (pos_ < s_.size() && s_[pos_] == '0') {
                ++pos_;
                if (pos_ < s_.size() && s_[pos_] >= '0' && s_[pos_] <= '9') return false;
            } else if (!digits()) return false;
            if (pos_ < s_.size() && s_[pos_] == '.') {
                ++pos_;
                if (!digits()) return false;
            }
            if (pos_ < s_.size() && (s_[pos_] == 'e' || s_[pos_] == 'E')) {
                ++pos_;
                if (pos_ < s_.size() && (s_[pos_] == '+' || s_[pos_] == '-')) ++pos_;
                if (!digits()) return false;
            }
            return true;
        }
        bool value() {
            whitespace();
            if (pos_ == s_.size()) return false;
            switch (s_[pos_]) {
                case '{': return object();
                case '[': return array();
                case '"': return stringValue();
                case 't': return literal("true");
                case 'f': return literal("false");
                case 'n': return literal("null");
                default: return number();
            }
        }
        bool object() {
            if (++depth_ > 16 || !consume('{')) return false;
            std::unordered_set<std::string> keys;
            if (consume('}')) { --depth_; return true; }
            while (true) {
                std::string key;
                if (!stringValue(&key) || !keys.insert(key).second || !consume(':'))
                    return false;
                whitespace();
                if (depth_ == 1) {
                    const bool needsText = key == "status" || key == "user" ||
                                           key == "protocol_marker" || key == "child_name";
                    const bool needsNumber = key == "child_id" || key == "remaining" ||
                                             key == "timestamp";
                    if (pos_ == s_.size() ||
                        (needsText && s_[pos_] != '"') ||
                        (needsNumber && s_[pos_] != '-' &&
                         !(s_[pos_] >= '0' && s_[pos_] <= '9'))) return false;
                }
                const size_t fieldStart = pos_;
                if (!value()) return false;
                if (depth_ == 1) topLevelFields_.emplace(key, std::make_pair(fieldStart, pos_));
                if (consume('}')) { --depth_; return true; }
                if (!consume(',')) return false;
            }
        }
        bool array() {
            if (++depth_ > 16 || !consume('[')) return false;
            if (consume(']')) { --depth_; return true; }
            while (true) {
                if (!value()) return false;
                if (consume(']')) { --depth_; return true; }
                if (!consume(',')) return false;
            }
        }
    public:
        explicit Parser(const std::string& s) : s_(s) {}
        bool validObject() {
            if (s_.size() > 2047 || !object()) return false;
            whitespace();
            return pos_ == s_.size();
        }
        std::string topLevelValue(const std::string& key) const {
            auto it = topLevelFields_.find(key);
            if (it == topLevelFields_.end()) return "";
            size_t first = it->second.first, last = it->second.second;
            if (first < last && s_[first] == '"') return s_.substr(first + 1, last - first - 2);
            return s_.substr(first, last - first);
        }
    };
public:
    static bool IsValidObject(const std::string& json) {
        return Parser(json).validObject();
    }
    // Only actual top-level JSON fields are returned; never search for key text
    // inside strings or nested objects. Invalid/ambiguous JSON is rejected.
    static std::string TopLevelValue(const std::string& json, const std::string& key) {
        Parser parsed(json);
        if (!parsed.validObject()) return "";
        return parsed.topLevelValue(key);
    }
};
