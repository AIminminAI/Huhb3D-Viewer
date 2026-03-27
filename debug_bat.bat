@echo off

echo 测试脚本开始执行...
pause

rem 测试1: 环境变量隔离
setlocal
echo 测试setlocal成功...
pause

rem 测试2: 清理文件夹
echo 测试清理文件夹...
pause
if exist test_build rmdir /s /q test_build
echo 清理文件夹成功...
pause

rem 测试3: 设置变量
set VCVARS=
echo 设置变量成功...
pause

rem 测试4: 简单if语句
if "%VCVARS%"=="" (
    echo VCVARS为空
) else (
    echo VCVARS不为空
)
echo 简单if语句测试成功...
pause

rem 测试5: 嵌套if语句
if "%VCVARS%"=="" (
    if exist "C:\Windows" (
        echo C盘Windows文件夹存在
    ) else (
        echo C盘Windows文件夹不存在
    )
)
echo 嵌套if语句测试成功...
pause

rem 测试6: goto命令
echo 测试goto命令...
pause
goto :test_label

:test_label
echo 跳转到标签成功！
pause

echo 所有测试完成！
pause
exit /b 0