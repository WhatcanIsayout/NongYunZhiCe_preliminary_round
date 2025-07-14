@echo off
chcp 65001 >nul

@echo off

:: 权限自提升模块
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"
if '%errorlevel%' NEQ '0' (
    echo 正在请求管理员权限，请在弹出的窗口中点击“是”...
    goto UACPrompt
) else (
    goto gotAdmin
)
:UACPrompt
    echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs"
    echo UAC.ShellExecute "%~s0", "", "", "runas", 1 >> "%temp%\getadmin.vbs"
    "%temp%\getadmin.vbs"
    exit /B
:gotAdmin
    if exist "%temp%\getadmin.vbs" ( del "%temp%\getadmin.vbs" )
    pushd "%CD%"
    CD /D "%~dp0"

:: 解决乱码
chcp 65001 >nul

:: 主要逻辑开始
setlocal
echo.
echo *** 成功获取管理员权限，脚本开始执行... ***
echo.

:: 配置
set PYTHON_VERSION=3.13
set PYTHON_FULL_VERSION=3.13.1
set REQUIREMENTS_FILE=requirements.txt
set MAIN_SCRIPT=app.py
set APP_URL=http://127.0.0.1:5000

:: 1. 检查 Python
echo.
echo === 步骤 1: 正在检查 Python %PYTHON_VERSION% 环境... ===
py -%PYTHON_VERSION% --version >nul 2>nul
if %errorlevel% == 0 (
    echo Python %PYTHON_VERSION% 已被发现，跳过安装。
    goto install_requirements
) else (
    echo Python %PYTHON_VERSION% 未找到，将开始自动下载和安装。
)

:: 2. 安装 Python
echo.
echo === 步骤 2: 正在下载 Python %PYTHON_FULL_VERSION%... ===
set PYTHON_INSTALLER_URL=https://www.python.org/ftp/python/%PYTHON_FULL_VERSION%/python-%PYTHON_FULL_VERSION%-amd64.exe
set INSTALLER_FILENAME=python_installer.exe
curl -L -o %INSTALLER_FILENAME% %PYTHON_INSTALLER_URL%
if %errorlevel% neq 0 (echo 下载失败！ & goto end)
echo.
echo === 正在静默安装 Python (此过程可能需要几分钟)... ===
start /wait "" %INSTALLER_FILENAME% /quiet InstallAllUsers=1 PrependPath=1 Include_py=1
del %INSTALLER_FILENAME%
echo Python 安装完成！

:: 3. 安装依赖
:install_requirements
echo.
echo === 步骤 3: 正在从 %REQUIREMENTS_FILE% 安装依赖库... ===
py -%PYTHON_VERSION% -m pip install -r %REQUIREMENTS_FILE%
if %errorlevel% neq 0 (echo 依赖库安装失败！ & goto end)
echo 依赖库安装完成！

:: 4. 启动程序并打开浏览器
echo.
echo === 步骤 4: 正在启动应用程序 %MAIN_SCRIPT%... ===
echo.
echo 正在尝试打开浏览器访问 %APP_URL% ...
start "" %APP_URL%

echo.
echo 启动 Flask 服务器... (您可以在此窗口查看日志, 按 CTRL+C 停止)
py -%PYTHON_VERSION% %MAIN_SCRIPT%

:end
echo.
echo 脚本执行完毕。
pause