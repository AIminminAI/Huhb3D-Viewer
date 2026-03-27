# 设置Visual Studio环境变量
& "D:\Huhb\SoftwareSetUp\Visual Studio\18\Community\VC\Auxiliary\Build\vcvarsall.bat" x64

# 运行CMake命令
cmake -B build -S . -G "NMake Makefiles" -DCMAKE_BUILD_TYPE=Release

# 构建项目
cmake --build build