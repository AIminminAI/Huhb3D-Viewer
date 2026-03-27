#include <iostream>
#include <cstdlib>
#include <string>
#include <fstream>
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <direct.h>
#include "render_manager.h"
#include "stl_parser.h"

bool fileExists(const std::string& name) {
    std::ifstream f(name.c_str());
    return f.good();
}

// 简单的路径提取
std::string getParentPath(const std::string& path) {
    size_t pos = path.find_last_of("\\/");
    return (pos != std::string::npos) ? path.substr(0, pos) : "";
}

int main(int argc, char* argv[]) {
    std::cout << "Starting STL renderer test..." << std::endl;
    
    // 打印当前工作目录
    char cwd[1024];
    if (_getcwd(cwd, sizeof(cwd)) != NULL) {
        std::cout << "Current working directory: " << cwd << std::endl;
    } else {
        std::cerr << "Error getting current working directory" << std::endl;
    }
    
    // 尝试不同的路径寻找STL文件
    std::string stlPath = "Dji+Avata+2+Simple.stl";
    
    if (argc > 1) {
        // 如果有命令行参数（例如拖拽文件），使用该文件
        stlPath = argv[1];
    } else {
        // 检查当前目录
        if (!fileExists(stlPath)) {
            std::cout << "STL file not found in current directory, checking program directory..." << std::endl;
            // 检查程序所在目录
            char exePath[1024];
            GetModuleFileNameA(NULL, exePath, sizeof(exePath));
            std::string exeDir = getParentPath(exePath);
            std::string checkPath = exeDir + "\\" + stlPath;
            std::cout << "Checking program directory: " << checkPath << std::endl;
            
            if (!fileExists(checkPath)) {
                std::cout << "STL file not found in program directory, checking parent directory..." << std::endl;
                // 检查上一级目录
                checkPath = getParentPath(exeDir) + "\\" + stlPath;
                std::cout << "Checking parent directory: " << checkPath << std::endl;
            }
            if (fileExists(checkPath)) {
                stlPath = checkPath;
            }
        }
    }
    
    // 创建RenderManager
    std::cout << "Creating RenderManager..." << std::endl;
    hhb::render::RenderManager renderManager(1280, 720, "Huhb CAD Viewer");
    
    // 初始化RenderManager
    if (!renderManager.initialize()) {
        std::cerr << "Failed to initialize RenderManager" << std::endl;
        return 1;
    }
    
    // 使用RenderManager的loadFile方法，这样会触发自动居中等逻辑
    if (fileExists(stlPath)) {
        renderManager.loadFile(stlPath);
    } else {
        std::cout << "No default STL file found, starting with empty scene." << std::endl;
    }
    
    // 进入渲染循环
    std::cout << "Entering render loop..." << std::endl;
    while (!renderManager.shouldClose()) {
        // 处理输入
        renderManager.processInput();
        
        // 渲染
        renderManager.render();
        
        // 交换缓冲区
        renderManager.swapBuffers();
    }
    
    return 0;
}