@echo off
setlocal

cd /d "%~dp0"

set "OUTPUT_DIR=nuitka_dist"
set "PACKAGE_DIR=%OUTPUT_DIR%\Sagami Youtube Downloader"
set "ICON_FILE=Sagami Youtube Downloader.ico"
set "NUITKA_CACHE_DIR=%CD%\.nuitka-cache"
if not exist "%NUITKA_CACHE_DIR%" mkdir "%NUITKA_CACHE_DIR%"

if not exist "main.py" (
  echo [ERROR] main.py not found.
  exit /b 1
)
if not exist "update.py" (
  echo [ERROR] update.py not found.
  exit /b 1
)
if not exist "yt-dlp.exe" (
  echo [ERROR] yt-dlp.exe not found.
  exit /b 1
)
if not exist "config.json" (
  echo [ERROR] config.json not found.
  exit /b 1
)
if not exist "%ICON_FILE%" (
  echo [ERROR] %ICON_FILE% not found.
  exit /b 1
)

echo [START] Build main app
python -m nuitka --standalone --disable-cache=all --enable-plugin=pyqt6 --windows-console-mode=disable --windows-icon-from-ico="%ICON_FILE%" --output-dir="%OUTPUT_DIR%" --output-filename="Sagami Youtube Downloader.exe" --include-data-file="%ICON_FILE%=Sagami Youtube Downloader.ico" --include-data-file=yt-dlp.exe=yt-dlp.exe --include-data-file=config.json=config.json main.py
if errorlevel 1 (
  echo [ERROR] Build main app failed.
  exit /b 1
)
echo [DONE] Build main app

echo [START] Build updater
python -m nuitka --standalone --disable-cache=all --windows-console-mode=disable --windows-icon-from-ico="%ICON_FILE%" --output-dir="%OUTPUT_DIR%" --output-filename="Sagami Youtube Updater.exe" update.py
if errorlevel 1 (
  echo [ERROR] Build updater failed.
  exit /b 1
)
echo [DONE] Build updater

echo [START] Package output
if not exist "%PACKAGE_DIR%" mkdir "%PACKAGE_DIR%"
xcopy /E /I /Y "%OUTPUT_DIR%\main.dist\*" "%PACKAGE_DIR%\" >nul
if errorlevel 1 (
  echo [ERROR] Copy from main.dist failed.
  exit /b 1
)
copy /Y "%OUTPUT_DIR%\update.dist\Sagami Youtube Updater.exe" "%PACKAGE_DIR%\" >nul
if errorlevel 1 (
  echo [ERROR] Copy updater exe failed.
  exit /b 1
)
copy /Y "%ICON_FILE%" "%PACKAGE_DIR%\%ICON_FILE%" >nul
if errorlevel 1 (
  echo [ERROR] Copy icon failed.
  exit /b 1
)
echo [DONE] Package output

echo.
echo Build completed: %PACKAGE_DIR%
echo.
pause
exit /b 0
