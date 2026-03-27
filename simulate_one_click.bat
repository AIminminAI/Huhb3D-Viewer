@echo off
echo 模拟one_click_run.bat开始执行...

rem 环境变量隔离
setlocal
echo 环境变量隔离成功...

rem 清理旧的build文件夹
echo 清理旧的build文件夹...
if exist build rmdir /s /q build
echo 清理完成...

rem 寻找Visual Studio
set VCVARS=
echo 开始寻找Visual Studio...

rem 尝试常见的Visual Studio安装路径
if "%VCVARS%"=="" (
    if exist "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" (
        set "VCVARS=C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat"
        echo 找到Visual Studio在C盘64位路径
    )
)

echo 路径检查完成...

if "%VCVARS%"=="" (
    echo 错误：未找到Visual Studio 2022
    goto :error
)

echo 找到vcvarsall.bat：%VCVARS%

rem 创建build文件夹
echo 创建build文件夹...
mkdir build
echo 创建完成...

echo 模拟完成！
exit /b 0

:error
echo 发生错误！
exit /b 1