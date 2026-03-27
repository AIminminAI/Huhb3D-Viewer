@echo off
echo 测试脚本开始执行...

rem 环境变量隔离
setlocal
echo 测试setlocal成功...

rem 清理文件夹
echo 测试清理文件夹...
if exist test_build rmdir /s /q test_build
echo 清理文件夹成功...

rem 设置变量
set VCVARS=
echo 设置变量成功...

rem 简单if语句
if "%VCVARS%"=="" (
    echo VCVARS为空
) else (
    echo VCVARS不为空
)
echo 简单if语句测试成功...

rem 嵌套if语句
if "%VCVARS%"=="" (
    if exist "C:\Windows" (
        echo C盘Windows文件夹存在
    ) else (
        echo C盘Windows文件夹不存在
    )
)
echo 嵌套if语句测试成功...

rem goto命令
echo 测试goto命令...
goto :test_label

:test_label
echo 跳转到标签成功！

echo 所有测试完成！
exit /b 0