@echo off

echo 测试脚本开始执行...
pause

rem 环境变量隔离
setlocal

echo 测试setlocal命令...
pause

rem 测试if语句
set TESTVAR=
echo 测试if语句前...
pause

if "%TESTVAR%"=="" (
    echo TESTVAR为空
) else (
    echo TESTVAR不为空
)
pause

echo 测试goto命令...
pause
goto :test_label

:test_label
echo 跳转到标签成功！
pause

echo 测试完成！
pause
exit /b 0