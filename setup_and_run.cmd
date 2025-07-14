@echo off
chcp 65001 >nul

:: ============================================================================
:: 权限自提升模块 - 自动请求管理员权限
:: ============================================================================
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

:: ============================================================================
:: 主要逻辑开始
:: ============================================================================
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
py -%PYTHON_VERSION% -m pip install -r %REQUIREMENTS_FILE% >nul
if %errorlevel% neq 0 (
    echo.
    echo *** 错误: 依赖库安装失败！请检查网络或 requirements.txt 文件。 ***
    goto end
)
echo 依赖库安装完成！

:: 4. 启动主程序并自动打开浏览器
echo.
echo === 步骤 4: 正在启动应用程序 %MAIN_SCRIPT%... ===
echo.

:: 第一步：在一个新的命令窗口中启动 Flask 服务器。
start "Flask Server" py -%PYTHON_VERSION% %MAIN_SCRIPT%

:: 第二步：等待 5 秒钟，给服务器足够的时间来启动。
echo 正在等待服务器启动 (5秒)...
timeout /t 5 /nobreak >nul

:: 第三步：现在再打开浏览器。
echo 正在打开浏览器访问 %APP_URL% ...
start "" %APP_URL%

echo.
echo 操作完成！Flask 服务器正在一个新窗口中运行。
echo 您可以关闭这个脚本窗口，服务器将继续运行。
echo 要停止服务器，请关闭标题为 "Flask Server" 的那个新窗口。

:end
echo.
pause