@echo off
chcp 65001 >nul
echo ==========================================
echo    创建服务器启动快捷方式
echo ==========================================
echo.

REM 获取当前目录
set "CURRENT_DIR=%~dp0"
set "TARGET_PATH=%CURRENT_DIR%start_server.bat"
set "ICON_PATH=%CURRENT_DIR%backend\static\favicon.ico"

REM 创建快捷方式到桌面
echo [信息] 正在创建桌面快捷方式...

powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%USERPROFILE%\Desktop\ESP32-CAM服务器.lnk'); $Shortcut.TargetPath = '%TARGET_PATH%'; $Shortcut.WorkingDirectory = '%CURRENT_DIR%'; $Shortcut.Description = '启动ESP32-CAM照片上传服务器'; $Shortcut.Save()"

if errorlevel 1 (
    echo [错误] 创建快捷方式失败
    pause
    exit /b 1
)

echo [成功] 快捷方式已创建到桌面: ESP32-CAM服务器.lnk
echo.
echo 使用方法:
echo   1. 双击桌面上的"ESP32-CAM服务器"快捷方式
echo   2. 等待服务器启动
echo   3. 在浏览器中访问 http://127.0.0.1:5000
echo.
pause
