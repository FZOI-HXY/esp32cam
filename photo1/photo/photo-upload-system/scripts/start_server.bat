@echo off
chcp 65001 >nul
echo ==========================================
echo    ESP32-CAM 照片上传服务器启动脚本
echo ==========================================
echo.

REM 切换到backend目录
cd /d "%~dp0\..\backend"

REM 检查Python是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到Python，请确保Python已安装并添加到环境变量
    pause
    exit /b 1
)

echo [信息] Python版本:
python --version
echo.

REM 检查依赖是否安装
echo [信息] 检查依赖...
python -c "import flask, requests" >nul 2>&1
if errorlevel 1 (
    echo [警告] 部分依赖未安装，正在安装...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败
        pause
        exit /b 1
    )
)

echo [信息] 依赖检查完成
echo.

REM 数据目录由 app.py 启动时自动创建（data/uploads, data/captures, data/album）

REM 启动服务器
echo [信息] 启动服务器...
echo [信息] 服务器将在 http://0.0.0.0:5000 运行
echo [信息] 按Ctrl+C停止服务器
echo.
echo ==========================================
echo.

python app.py

REM 如果服务器异常退出
echo.
echo [警告] 服务器已停止
pause
