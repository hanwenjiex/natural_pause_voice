@echo off
chcp 65001 > nul
echo ========================================
echo   网络波动模拟器 - 打包脚本
echo ========================================
echo.

REM 安装依赖
echo [1/3] 安装 Python 依赖...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo 安装依赖失败，请检查网络或 pip 配置
    pause
    exit /b 1
)

echo.
echo [2/3] 使用 PyInstaller 打包 exe...
pyinstaller --onefile --noconsole ^
    --name "网络波动模拟器" ^
    --add-data "README.md;." ^
    main.py

if %errorlevel% neq 0 (
    echo 打包失败
    pause
    exit /b 1
)

echo.
echo [3/3] 打包完成！
echo 输出文件: dist\网络波动模拟器.exe
echo.
echo 双击 dist\网络波动模拟器.exe 即可运行
echo 发送给朋友时只需要这一个 exe 文件
echo.

pause
