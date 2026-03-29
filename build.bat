@echo off
echo ========================================
echo  BINMUN Profile Manager - Build Script
echo ========================================
echo.

set CONDA_PATH=C:\ProgramData\miniconda3
set ENV_NAME=binmun_build
set APP_DIR=%~dp0
set CHROME_SRC=%APPDATA%\GPMLoginGlobal\Browsers\ChromiumCore_v144
set DIST_DIR=%APP_DIR%dist\binmun

:: Activate conda
call "%CONDA_PATH%\Scripts\activate.bat"

:: Create env if not exists
conda info --envs | findstr /C:"%ENV_NAME%" >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] Creating environment '%ENV_NAME%'...
    call conda create -n %ENV_NAME% python=3.11 -y
)

:: Activate env
echo [*] Activating '%ENV_NAME%'...
call conda activate %ENV_NAME%
echo [*] Python: & python --version

:: Install dependencies
echo [*] Installing dependencies...
pip install PyQt6 pyinstaller --quiet

:: Build exe
echo.
echo [*] Building exe...
cd /d "%APP_DIR%"

pyinstaller ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name "BINMUN_ProfileManager" ^
    --distpath "%DIST_DIR%" ^
    --add-data "gpm_profile_launcher.py;." ^
    --hidden-import PyQt6.QtWidgets ^
    --hidden-import PyQt6.QtCore ^
    --hidden-import PyQt6.QtGui ^
    --collect-all PyQt6.QtWidgets ^
    --collect-all PyQt6.QtCore ^
    --collect-all PyQt6.QtGui ^
    --collect-all PyQt6.sip ^
    --exclude-module PyQt6.QtQml ^
    --exclude-module PyQt6.QtQuick ^
    --exclude-module PyQt6.QtWebEngine ^
    --exclude-module PyQt6.QtWebEngineCore ^
    --exclude-module PyQt6.QtWebEngineWidgets ^
    --exclude-module PyQt6.Qt3DCore ^
    --exclude-module PyQt6.Qt3DRender ^
    --exclude-module PyQt6.QtMultimedia ^
    --exclude-module PyQt6.QtBluetooth ^
    --exclude-module PyQt6.QtNfc ^
    gpm_manager.py

if %errorlevel% neq 0 (
    echo [ERROR] Build failed!
    pause
    exit /b 1
)

:: Copy Chrome with correct folder structure
echo.
echo [*] Copying ChromiumCore browser...
set CHROME_DEST=%DIST_DIR%\GPMLoginData\Browsers\ChromiumCore_v144
if exist "%CHROME_SRC%" (
    if exist "%CHROME_DEST%" rmdir /s /q "%CHROME_DEST%"
    xcopy "%CHROME_SRC%" "%CHROME_DEST%\" /E /I /Q /Y >nul
    :: Create dummy MUNLoginGlobal.exe (chrome.dll checks for it via ..\..)
    echo. > "%DIST_DIR%\GPMLoginData\GPMLoginGlobal.exe"
    echo [*] Chrome copied to GPMLoginData\Browsers\ChromiumCore_v144\
) else (
    echo [WARN] ChromiumCore not found at %CHROME_SRC%
)

echo.
echo ========================================
echo  Build complete!
echo.
echo  %DIST_DIR%\
echo    BINMUN_ProfileManager.exe
echo    GPMLoginData\
echo      GPMLoginGlobal.exe  (dummy)
echo      Browsers\ChromiumCore_v144\
echo        chrome.exe
echo ========================================
pause
