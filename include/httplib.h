#ifndef CPPHTTPLIB_HTTPLIB_H
#define CPPHTTPLIB_HTTPLIB_H

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <winhttp.h>
#pragma comment(lib, "winhttp.lib")
#else
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <netdb.h>
#include <unistd.h>
#endif

#include <string>
#include <map>
#include <vector>
#include <memory>
#include <functional>
#include <sstream>
#include <iostream>
#include <cstring>

namespace httplib {

struct Response {
    int status = 0;
    std::string body;
    std::map<std::string, std::string> headers;
};

typedef std::map<std::string, std::string> Headers;

class Client {
public:
    Client(const std::string& url, int port = 0) : base_url_(url), port_(port) {
        timeout_sec_ = 30;
    }

    void set_timeout_sec(int timeout) { timeout_sec_ = timeout; }

    std::shared_ptr<Response> Post(const std::string& path, const Headers& headers,
                                   const std::string& body, const std::string& content_type) {
        std::string full_url = base_url_;
        if (!path.empty() && path[0] != '/') full_url += "/";
        full_url += path;
        return http_request("POST", full_url, headers, body, content_type);
    }

    std::shared_ptr<Response> Get(const std::string& path, const Headers& headers = Headers()) {
        std::string full_url = base_url_;
        if (!path.empty() && path[0] != '/') full_url += "/";
        full_url += path;
        return http_request("GET", full_url, headers, "", "");
    }

    std::string get_last_error() const { return last_error_; }

private:
    std::string base_url_;
    int port_;
    int timeout_sec_;
    std::string last_error_;

    struct UrlParts {
        std::string scheme;
        std::string host;
        int port;
        std::string path;
    };

    static UrlParts parse_url(const std::string& url) {
        UrlParts parts;
        parts.port = 443;
        parts.scheme = "https";

        size_t pos = 0;
        size_t scheme_end = url.find("://");
        if (scheme_end != std::string::npos) {
            parts.scheme = url.substr(0, scheme_end);
            pos = scheme_end + 3;
        }

        if (parts.scheme == "http") parts.port = 80;

        size_t path_start = url.find('/', pos);
        size_t port_colon = std::string::npos;

        if (path_start != std::string::npos) {
            std::string authority = url.substr(pos, path_start - pos);
            port_colon = authority.rfind(':');
            if (port_colon != std::string::npos) {
                parts.host = authority.substr(0, port_colon);
                parts.port = std::stoi(authority.substr(port_colon + 1));
            } else {
                parts.host = authority;
            }
            parts.path = url.substr(path_start);
        } else {
            std::string authority = url.substr(pos);
            port_colon = authority.rfind(':');
            if (port_colon != std::string::npos) {
                parts.host = authority.substr(0, port_colon);
                parts.port = std::stoi(authority.substr(port_colon + 1));
            } else {
                parts.host = authority;
            }
            parts.path = "/";
        }

        return parts;
    }

    std::shared_ptr<Response> http_request(const std::string& method, const std::string& url,
                                           const Headers& headers, const std::string& body,
                                           const std::string& content_type) {
        auto res = std::make_shared<Response>();
        last_error_.clear();

#ifdef _WIN32
        UrlParts parts = parse_url(url);

        HINTERNET hSession = WinHttpOpen(L"HuhbCAD-AI-Agent/1.0",
            WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
            WINHTTP_NO_PROXY_NAME,
            WINHTTP_NO_PROXY_BYPASS, 0);
        if (!hSession) {
            last_error_ = "WinHttpOpen failed";
            return res;
        }

        DWORD timeout_ms = timeout_sec_ * 1000;
        WinHttpSetOption(hSession, WINHTTP_OPTION_CONNECT_TIMEOUT, &timeout_ms, sizeof(timeout_ms));
        WinHttpSetOption(hSession, WINHTTP_OPTION_RECEIVE_TIMEOUT, &timeout_ms, sizeof(timeout_ms));
        WinHttpSetOption(hSession, WINHTTP_OPTION_SEND_TIMEOUT, &timeout_ms, sizeof(timeout_ms));

        std::wstring whost(parts.host.begin(), parts.host.end());
        HINTERNET hConnect = WinHttpConnect(hSession, whost.c_str(),
            static_cast<INTERNET_PORT>(parts.port), 0);
        if (!hConnect) {
            last_error_ = "WinHttpConnect failed for host: " + parts.host;
            WinHttpCloseHandle(hSession);
            return res;
        }

        std::wstring wpath(parts.path.begin(), parts.path.end());
        DWORD dwFlags = (parts.scheme == "https") ? WINHTTP_FLAG_SECURE : 0;
        HINTERNET hRequest = WinHttpOpenRequest(hConnect,
            (method == "POST") ? L"POST" : L"GET",
            wpath.c_str(), NULL, WINHTTP_NO_REFERER,
            WINHTTP_DEFAULT_ACCEPT_TYPES, dwFlags);
        if (!hRequest) {
            last_error_ = "WinHttpOpenRequest failed";
            WinHttpCloseHandle(hConnect);
            WinHttpCloseHandle(hSession);
            return res;
        }

        if (parts.scheme == "https") {
            DWORD security_flags = SECURITY_FLAG_IGNORE_UNKNOWN_CA |
                                   SECURITY_FLAG_IGNORE_CERT_DATE_INVALID |
                                   SECURITY_FLAG_IGNORE_CERT_CN_INVALID |
                                   SECURITY_FLAG_IGNORE_CERT_WRONG_USAGE;
            WinHttpSetOption(hRequest, WINHTTP_OPTION_SECURITY_FLAGS, &security_flags, sizeof(security_flags));
        }

        std::wstring header_str;
        for (const auto& h : headers) {
            std::string line = h.first + ": " + h.second + "\r\n";
            header_str += std::wstring(line.begin(), line.end());
        }
        if (!content_type.empty()) {
            std::string ct = "Content-Type: " + content_type + "\r\n";
            header_str += std::wstring(ct.begin(), ct.end());
        }
        if (!header_str.empty()) {
            WinHttpAddRequestHeaders(hRequest, header_str.c_str(),
                static_cast<DWORD>(header_str.length()), WINHTTP_ADDREQ_FLAG_ADD);
        }

        BOOL bResults = WinHttpSendRequest(hRequest,
            WINHTTP_NO_ADDITIONAL_HEADERS, 0,
            body.empty() ? WINHTTP_NO_REQUEST_DATA : (LPVOID)body.c_str(),
            body.empty() ? 0 : static_cast<DWORD>(body.length()),
            body.empty() ? 0 : static_cast<DWORD>(body.length()), 0);

        if (!bResults) {
            DWORD err = GetLastError();
            last_error_ = "WinHttpSendRequest failed, error: " + std::to_string(err);
            WinHttpCloseHandle(hRequest);
            WinHttpCloseHandle(hConnect);
            WinHttpCloseHandle(hSession);
            return res;
        }

        bResults = WinHttpReceiveResponse(hRequest, NULL);
        if (!bResults) {
            last_error_ = "WinHttpReceiveResponse failed";
            WinHttpCloseHandle(hRequest);
            WinHttpCloseHandle(hConnect);
            WinHttpCloseHandle(hSession);
            return res;
        }

        DWORD status_code = 0;
        DWORD status_code_size = sizeof(status_code);
        WinHttpQueryHeaders(hRequest, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
            WINHTTP_HEADER_NAME_BY_INDEX, &status_code, &status_code_size, WINHTTP_NO_HEADER_INDEX);
        res->status = static_cast<int>(status_code);

        DWORD available_data = 0;
        std::string response_body;
        do {
            available_data = 0;
            if (!WinHttpQueryDataAvailable(hRequest, &available_data)) break;
            if (available_data == 0) break;
            std::vector<char> buffer(available_data + 1);
            DWORD bytes_read = 0;
            if (WinHttpReadData(hRequest, buffer.data(), available_data, &bytes_read)) {
                response_body.append(buffer.data(), bytes_read);
            }
        } while (available_data > 0);

        res->body = response_body;

        WinHttpCloseHandle(hRequest);
        WinHttpCloseHandle(hConnect);
        WinHttpCloseHandle(hSession);
#else
        // Linux fallback: simple socket HTTP
        UrlParts parts = parse_url(url);
        struct hostent* he = gethostbyname(parts.host.c_str());
        if (!he) { last_error_ = "DNS resolution failed"; return res; }

        int sockfd = socket(AF_INET, SOCK_STREAM, 0);
        struct sockaddr_in addr;
        memset(&addr, 0, sizeof(addr));
        addr.sin_family = AF_INET;
        addr.sin_port = htons(parts.port);
        memcpy(&addr.sin_addr, he->h_addr_list[0], he->h_length);

        if (connect(sockfd, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
            last_error_ = "Connection failed";
            close(sockfd);
            return res;
        }

        std::stringstream req;
        req << method << " " << parts.path << " HTTP/1.1\r\n";
        req << "Host: " << parts.host << "\r\n";
        for (const auto& h : headers) req << h.first << ": " << h.second << "\r\n";
        if (!content_type.empty()) req << "Content-Type: " << content_type << "\r\n";
        req << "Content-Length: " << body.length() << "\r\n";
        req << "Connection: close\r\n\r\n";
        req << body;

        std::string req_str = req.str();
        send(sockfd, req_str.c_str(), req_str.length(), 0);

        char buf[4096];
        std::string response_str;
        ssize_t n;
        while ((n = recv(sockfd, buf, sizeof(buf) - 1, 0)) > 0) {
            buf[n] = '\0';
            response_str += buf;
        }
        close(sockfd);

        size_t body_start = response_str.find("\r\n\r\n");
        if (body_start != std::string::npos) {
            res->body = response_str.substr(body_start + 4);
        }
        size_t status_pos = response_str.find(' ');
        if (status_pos != std::string::npos) {
            res->status = std::stoi(response_str.substr(status_pos + 1, 3));
        }
#endif
        return res;
    }
};

} // namespace httplib

#endif // CPPHTTPLIB_HTTPLIB_H
