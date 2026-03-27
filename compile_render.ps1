# 运行vcvarsall.bat来设置环境变量
& "D:\Huhb\SoftwareSetUp\Visual Studio\18\Community\VC\Auxiliary\Build\vcvarsall.bat" x64

# 运行编译命令
& "D:\Huhb\SoftwareSetUp\Visual Studio\18\Community\VC\Tools\MSVC\14.50.35717\bin\Hostx64\x64\cl.exe" /nologo /TP /Iinclude src\render\test_render.cpp src\render\render_manager.cpp src\render\glad.c src\render\glfw3.c /link /out:test_render.exe opengl32.lib