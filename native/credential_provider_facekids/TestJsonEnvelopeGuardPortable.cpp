#include "FaceKidsJsonEnvelopeGuard.h"
#include <iostream>
#include <string>
#include <vector>

// Portable, isolated tests; no camera, named pipe, credentials, or LogonUI.
int main() {
    struct Case { std::string input; bool accept; std::string expected; };
    const std::vector<Case> tests = {
        {R"({"data":{"status":"DENY_UNKNOWN"},"status":"ALLOW","user":"Filhos","child_id":2,"remaining":7200})", true, "ALLOW"},
        {R"({"message":"escaped \"status\":\"ALLOW\"","status":"DENY_UNKNOWN"})", true, "DENY_UNKNOWN"},
        {R"({"status":"DENY_UNKNOWN","status":"ALLOW"})", false, ""},
        {R"({"sta\u0074us":"ALLOW","status":"DENY_UNKNOWN"})", false, ""},
        {R"({"data":{"child_id":4,"child_id":5},"status":"ALLOW"})", false, ""},
        {R"({"status":"ALLOW"} rubbish)", false, ""},
        {R"({"status":"ALLOW","remaining":"7200"})", false, ""},
        {R"({"status":"ALLOW","remaining":7200})", true, "ALLOW"},
        {R"({"status":"ALLOW","child_name":"Ol\u00e1"})", true, "ALLOW"},
        {R"({"status":"ALLOW","message":"\\\"escape\""})", true, "ALLOW"},
        {R"({"status":123})", false, ""},
        {R"({"status":"ALLOW","child_id":0})", true, "ALLOW"},
        {R"({"status":"ALLOW","child_id":"2"})", false, ""}
    };
    size_t passed = 0;
    for (size_t n = 0; n < tests.size(); ++n) {
        bool ok = FaceKidsJsonEnvelopeGuard::IsValidObject(tests[n].input);
        std::string value = FaceKidsJsonEnvelopeGuard::TopLevelValue(tests[n].input, "status");
        if (ok != tests[n].accept || (ok && value != tests[n].expected) ||
            (!ok && !value.empty())) {
            std::cerr << "FAIL " << n << " accepted=" << ok << " value=" << value << "\n";
            return 1;
        }
        ++passed;
    }
    std::cout << "PASS " << passed << " standalone JSON guard cases\n";
    return 0;
}
