@echo off
echo ========================================
echo  BINMUN Profile Manager - Nuitka Build
echo ========================================
echo.

set CONDA_PATH=C:\ProgramData\miniconda3
set ENV_NAME=binmun_build
set APP_DIR=%~dp0
set CHROME_SRC=%APPDATA%\GPMLoginGlobal\Browsers\ChromiumCore_v144
set DIST_DIR=%APP_DIR%dist\binmun
set BUILD_DIR=%APP_DIR%build_nuitka
set ICON_PNG=%APP_DIR%assets\binmun_logo.png
set ICON_ICO=%APP_DIR%assets\binmun_logo.ico

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
pip install nuitka PyQt6 pillow firebase-admin huggingface_hub --quiet

:: === Convert PNG → ICO ===
echo.
echo [*] Converting icon PNG to ICO...
python -c "from PIL import Image; img=Image.open(r'%ICON_PNG%'); img.save(r'%ICON_ICO%', sizes=[(16,16),(32,32),(48,48),(256,256)])"
if %errorlevel% neq 0 (
    echo [ERROR] Icon conversion failed!
    pause
    exit /b 1
)
echo [*] Icon saved to assets\binmun_logo.ico

:: === Kill running exe before cleanup ===
echo.
echo [*] Killing running BINMUN_ProfileManager...
taskkill /F /IM BINMUN_ProfileManager.exe >nul 2>&1
timeout /t 2 /nobreak >nul

:: === Cleanup old exe only (keep build_nuitka/ for incremental recompile) ===
echo [*] Cleaning old exe...
if exist "%DIST_DIR%\BINMUN_ProfileManager.exe" (
    del /f /q "%DIST_DIR%\BINMUN_ProfileManager.exe"
    if exist "%DIST_DIR%\BINMUN_ProfileManager.exe" (
        echo [ERROR] Cannot delete exe - still locked!
        pause
        exit /b 1
    )
    echo [*] Deleted old exe.
)
:: To force a full clean build, uncomment below:
:: if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"

:: === Nuitka build ===
echo.
echo [*] Building exe with Nuitka...
cd /d "%APP_DIR%"

python -m nuitka ^
    --onefile ^
    --enable-plugin=pyqt6 ^
    --windows-disable-console ^
    --output-filename=BINMUN_ProfileManager.exe ^
    --output-dir="%BUILD_DIR%" ^
    --include-data-files=gpm_profile_launcher.py=gpm_profile_launcher.py ^
    --include-data-files=lib/profile_sync.py=lib/profile_sync.py ^
    --windows-icon-from-ico="%ICON_ICO%" ^
    --assume-yes-for-downloads ^
    gpm_manager.py

if %errorlevel% neq 0 (
    echo [ERROR] Nuitka build failed!
    pause
    exit /b 1
)

:: Move exe to dist\binmun
if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"
move "%BUILD_DIR%\BINMUN_ProfileManager.exe" "%DIST_DIR%\" >nul

:: Copy assets (icon, etc.) so exe can find them at runtime
echo [*] Copying assets...
if not exist "%DIST_DIR%\assets" mkdir "%DIST_DIR%\assets"
xcopy "%APP_DIR%assets\*" "%DIST_DIR%\assets\" /E /I /Q /Y >nul

:: Copy Firebase service account
echo [*] Copying Firebase credentials...
if not exist "%DIST_DIR%\auth_files" mkdir "%DIST_DIR%\auth_files"
if exist "%APP_DIR%auth_files\firebase.json" (
    copy /Y "%APP_DIR%auth_files\firebase.json" "%DIST_DIR%\auth_files\" >nul
    echo [*] firebase.json copied to auth_files\
) else (
    echo [WARN] auth_files\firebase.json not found
)

:: Copy Chrome with correct folder structure
echo.
echo [*] Copying ChromiumCore browser...
set CHROME_DEST=%DIST_DIR%\GPMLoginData\Browsers\ChromiumCore_v144
if exist "%CHROME_SRC%" (
    if exist "%CHROME_DEST%" rmdir /s /q "%CHROME_DEST%"
    xcopy "%CHROME_SRC%" "%CHROME_DEST%\" /E /I /Q /Y >nul
    :: Create dummy GPMLoginGlobal.exe (chrome.dll checks for it via ..\..)
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
echo    auth_files\firebase.json
echo    GPMLoginData\
echo      GPMLoginGlobal.exe  (dummy)
echo      Browsers\ChromiumCore_v144\
echo        chrome.exe
echo ========================================
pause
