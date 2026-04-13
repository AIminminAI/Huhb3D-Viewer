#include "command_dispatcher.h"
#include <thread>
#include <iostream>
#include <string>
#include <cstring>
#include <map>

#ifdef _WIN32
    #include <winsock2.h>
    #include <ws2tcpip.h>
    #pragma comment(lib, "ws2_32.lib")
#else
    #include <sys/socket.h>
    #include <netinet/in.h>
    #include <arpa/inet.h>
    #include <unistd.h>
    #define SOCKET int
    #define INVALID_SOCKET -1
    #define SOCKET_ERROR -1
    #define closesocket close
#endif

namespace hhb {
namespace core {

struct JsonParser {
    static std::map<std::string, std::string> parse(const std::string& json) {
        std::map<std::string, std::string> result;
        
        size_t pos = json.find('{');
        if (pos == std::string::npos) return result;
        
        size_t end = json.find('}');
        if (end == std::string::npos) return result;
        
        std::string content = json.substr(pos + 1, end - pos - 1);
        
        size_t current = 0;
        while (current < content.size()) {
            size_t key_start = content.find('"', current);
            if (key_start == std::string::npos) break;
            
            size_t key_end = content.find('"', key_start + 1);
            if (key_end == std::string::npos) break;
            
            std::string key = content.substr(key_start + 1, key_end - key_start - 1);
            
            size_t colon = content.find(':', key_end);
            if (colon == std::string::npos) break;
            
            size_t value_start = content.find_first_not_of(" \t\n\r", colon + 1);
            if (value_start == std::string::npos) break;
            
            size_t value_end;
            if (content[value_start] == '"') {
                value_end = content.find('"', value_start + 1);
                if (value_end == std::string::npos) break;
                std::string value = content.substr(value_start + 1, value_end - value_start - 1);
                result[key] = value;
            } else {
                value_end = content.find_first_of(",}\n\r\t", value_start);
                if (value_end == std::string::npos) value_end = content.size();
                std::string value = content.substr(value_start, value_end - value_start);
                result[key] = value;
            }
            
            current = value_end + 1;
        }
        
        return result;
    }
};

CommandDispatcher::CommandDispatcher() : running(false) {
}

CommandDispatcher::~CommandDispatcher() {
    stop();
}

void CommandDispatcher::start(int port) {
    running = true;
    
    std::thread serverThread([this, port]() {
        #ifdef _WIN32
        WSADATA wsaData;
        if (WSAStartup(MAKEWORD(2, 2), &wsaData) != 0) {
            std::cerr << "WSAStartup failed" << std::endl;
            return;
        }
        #endif
        
        SOCKET serverSocket = socket(AF_INET, SOCK_STREAM, 0);
        if (serverSocket == INVALID_SOCKET) {
            std::cerr << "Failed to create socket" << std::endl;
            #ifdef _WIN32
            WSACleanup();
            #endif
            return;
        }
        
        int reuse = 1;
        setsockopt(serverSocket, SOL_SOCKET, SO_REUSEADDR, (const char*)&reuse, sizeof(reuse));
        
        sockaddr_in serverAddr;
        serverAddr.sin_family = AF_INET;
        serverAddr.sin_addr.s_addr = INADDR_ANY;
        serverAddr.sin_port = htons(port);
        
        if (bind(serverSocket, (struct sockaddr*)&serverAddr, sizeof(serverAddr)) == SOCKET_ERROR) {
            std::cerr << "Failed to bind socket" << std::endl;
            closesocket(serverSocket);
            #ifdef _WIN32
            WSACleanup();
            #endif
            return;
        }
        
        if (listen(serverSocket, 5) == SOCKET_ERROR) {
            std::cerr << "Failed to listen" << std::endl;
            closesocket(serverSocket);
            #ifdef _WIN32
            WSACleanup();
            #endif
            return;
        }
        
        std::cout << "Command dispatcher server started on port " << port << std::endl;
        
        while (running) {
            fd_set readfds;
            FD_ZERO(&readfds);
            FD_SET(serverSocket, &readfds);
            
            struct timeval timeout;
            timeout.tv_sec = 1;
            timeout.tv_usec = 0;
            
            int selectResult = select(0, &readfds, nullptr, nullptr, &timeout);
            if (selectResult == SOCKET_ERROR) {
                continue;
            }
            
            if (selectResult == 0) {
                continue;
            }
            
            SOCKET clientSocket = accept(serverSocket, nullptr, nullptr);
            if (clientSocket == INVALID_SOCKET) {
                continue;
            }
            
            char buffer[8192] = {0};
            int bytesRead = recv(clientSocket, buffer, sizeof(buffer) - 1, 0);
            if (bytesRead > 0) {
                std::string request(buffer, bytesRead);
                
                if (request.find("POST /execute_task") != std::string::npos) {
                    size_t bodyStart = request.find("\r\n\r\n");
                    if (bodyStart != std::string::npos) {
                        std::string body = request.substr(bodyStart + 4);
                        processRequest(body);
                        
                        std::string response = "HTTP/1.1 200 OK\r\n";
                        response += "Content-Type: application/json\r\n";
                        response += "Access-Control-Allow-Origin: *\r\n";
                        response += "Content-Length: 18\r\n";
                        response += "\r\n";
                        response += "{\"status\": \"success\"}";
                        send(clientSocket, response.c_str(), response.size(), 0);
                    } else {
                        std::string response = "HTTP/1.1 400 Bad Request\r\n";
                        response += "Content-Type: application/json\r\n";
                        response += "Content-Length: 42\r\n";
                        response += "\r\n";
                        response += "{\"status\": \"error\", \"message\": \"Invalid request\"}";
                        send(clientSocket, response.c_str(), response.size(), 0);
                    }
                } else if (request.find("OPTIONS") != std::string::npos) {
                    std::string response = "HTTP/1.1 200 OK\r\n";
                    response += "Access-Control-Allow-Origin: *\r\n";
                    response += "Access-Control-Allow-Methods: POST, OPTIONS\r\n";
                    response += "Access-Control-Allow-Headers: Content-Type\r\n";
                    response += "Content-Length: 0\r\n";
                    response += "\r\n";
                    send(clientSocket, response.c_str(), response.size(), 0);
                } else {
                    std::string response = "HTTP/1.1 404 Not Found\r\n";
                    response += "Content-Type: text/plain\r\n";
                    response += "Content-Length: 9\r\n";
                    response += "\r\n";
                    response += "Not Found";
                    send(clientSocket, response.c_str(), response.size(), 0);
                }
            }
            
            closesocket(clientSocket);
        }
        
        closesocket(serverSocket);
        #ifdef _WIN32
        WSACleanup();
        #endif
    });
    
    serverThread.detach();
}

void CommandDispatcher::stop() {
    running = false;
}

bool CommandDispatcher::hasCommand() {
    std::lock_guard<std::mutex> lock(queueMutex);
    return !commandQueue.empty();
}

Command CommandDispatcher::getCommand() {
    std::unique_lock<std::mutex> lock(queueMutex);
    cv.wait(lock, [this]() { return !commandQueue.empty() || !running; });
    
    if (!running && commandQueue.empty()) {
        return Command{"", 0.0, {}};
    }
    
    Command cmd = commandQueue.front();
    commandQueue.pop();
    return cmd;
}

void CommandDispatcher::processRequest(const std::string& json) {
    try {
        auto parsed = JsonParser::parse(json);
        
        auto action_it = parsed.find("action");
        if (action_it == parsed.end()) {
            std::cerr << "Missing 'action' field in request" << std::endl;
            return;
        }
        
        std::string action = action_it->second;
        
        double value = 0.0;
        auto value_it = parsed.find("value");
        if (value_it != parsed.end()) {
            try {
                value = std::stod(value_it->second);
            } catch (...) {
                value = 0.0;
            }
        }
        
        Command cmd;
        cmd.action = action;
        cmd.value = value;
        cmd.params = parsed;
        
        {
            std::lock_guard<std::mutex> lock(queueMutex);
            commandQueue.push(cmd);
            cv.notify_one();
        }
        
        std::cout << "Received command: " << action << " with value: " << value << std::endl;
    } catch (const std::exception& e) {
        std::cerr << "Error processing request: " << e.what() << std::endl;
    }
}

} // namespace core
} // namespace hhb
