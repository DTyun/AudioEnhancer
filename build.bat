@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [1/3] 创建虚拟环境并安装依赖...
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -m venv .venv
) else (
    python -m venv .venv
)
if errorlevel 1 (
    echo 创建虚拟环境失败，请检查 Python 路径
    pause
    exit /b 1
)

.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo 安装依赖失败
    pause
    exit /b 1
)

echo [2/3] 打包为单文件 exe...
.venv\Scripts\python.exe -m PyInstaller ^
    --clean ^
    --noconfirm ^
    AudioEnhancer.spec

if errorlevel 1 (
    echo 打包失败
    pause
    exit /b 1
)

copy /y "dist\AudioEnhancer.exe" "AudioEnhancer.exe" >nul
if errorlevel 1 (
    echo 打包成功，但复制到项目根目录失败；请使用 dist\AudioEnhancer.exe
    pause
    exit /b 1
)

echo [3/3] 完成！exe 位于 dist\AudioEnhancer.exe 和项目根目录
pause
