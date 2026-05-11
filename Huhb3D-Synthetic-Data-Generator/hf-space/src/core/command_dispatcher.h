#ifndef COMMAND_DISPATCHER_H
#define COMMAND_DISPATCHER_H

#include <string>
#include <queue>
#include <mutex>
#include <condition_variable>
#include <functional>
#include <map>

namespace hhb {
namespace core {

struct Command {
    std::string action;
    double value;
    std::map<std::string, std::string> params;
};

class CommandDispatcher {
public:
    CommandDispatcher();
    ~CommandDispatcher();
    
    void start(int port = 8080);
    void stop();
    
    bool hasCommand();
    Command getCommand();
    
private:
    std::queue<Command> commandQueue;
    std::mutex queueMutex;
    std::condition_variable cv;
    bool running;
    
    void processRequest(const std::string& json);
};

} // namespace core
} // namespace hhb

#endif // COMMAND_DISPATCHER_H
