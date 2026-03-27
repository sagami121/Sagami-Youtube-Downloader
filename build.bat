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
if not exist "main_legacy.py" (
  echo [ERROR] main_legacy.py not found.
  exit /b 1
)
if not exist "yt-dlp.exe" (
  echo [ERROR] yt-dlp.exe not found.
  exit /b 1
)
if not exist "ffmpeg.exe" (
  echo [ERROR] ffmpeg.exe not found.
  exit /b 1
)
if not exist "ffprobe.exe" (
  echo [ERROR] ffprobe.exe not found.
  exit /b 1
)
if not exist "language\ja.json" (
  echo [ERROR] language\ja.json not found.
  exit /b 1
)
if not exist "language\en.json" (
  echo [ERROR] language\en.json not found.
  exit /b 1
)
if not exist "language\ko.json" (
  echo [ERROR] language\ko.json not found.
  exit /b 1
)
if not exist "language\zh.json" (
  echo [ERROR] language\zh.json not found.
  exit /b 1
)
if not exist "theme" (
  echo [ERROR] theme folder not found.
  exit /b 1
)
if not exist "%ICON_FILE%" (
  echo [ERROR] %ICON_FILE% not found.
  exit /b 1
)

echo [START] Build main app
py -3.13 -m nuitka --standalone --disable-cache=all --assume-yes-for-downloads --enable-plugin=pyside6 --windows-console-mode=disable --windows-icon-from-ico="%ICON_FILE%" --output-dir="%OUTPUT_DIR%" --output-filename="Sagami Youtube Downloader.exe" --include-data-file="%ICON_FILE%=Sagami Youtube Downloader.ico" --include-data-file=yt-dlp.exe=yt-dlp.exe --include-data-file=ffmpeg.exe=ffmpeg.exe --include-data-file=ffprobe.exe=ffprobe.exe --include-data-dir=language=language --include-data-dir=theme=theme main.py
if errorlevel 1 (
  echo [ERROR] Build main app failed.
  exit /b 1
)
echo [DONE] Build main app

echo [START] Build legacy app
py -3.8 -m nuitka --standalone --disable-cache=all --assume-yes-for-downloads --enable-plugin=pyqt5 --windows-console-mode=disable --windows-icon-from-ico="%ICON_FILE%" --output-dir="%OUTPUT_DIR%" --output-filename="Sagami Youtube Downloader Legacy.exe" --include-data-file="%ICON_FILE%=Sagami Youtube Downloader.ico" --include-data-file=yt-dlp.exe=yt-dlp.exe --include-data-file=ffmpeg.exe=ffmpeg.exe --include-data-file=ffprobe.exe=ffprobe.exe --include-data-dir=language=language --include-data-dir=theme=theme main_legacy.py
if errorlevel 1 (
  echo [ERROR] Build legacy app failed.
  exit /b 1
)
echo [DONE] Build legacy app

echo [START] Package output
if not exist "%PACKAGE_DIR%" mkdir "%PACKAGE_DIR%"
if not exist "%PACKAGE_DIR%\legacy" mkdir "%PACKAGE_DIR%\legacy"

@REM main.distの中身をパッケージディレクトリにコピー
xcopy /E /I /Y "%OUTPUT_DIR%\main.dist\*" "%PACKAGE_DIR%\" >nul
if errorlevel 1 (
  echo [ERROR] Copy from main.dist failed.
  exit /b 1
)

@REM main_legacy.distの中身をパッケージディレクトリにコピー
xcopy /E /I /Y "%OUTPUT_DIR%\main_legacy.dist\*" "%PACKAGE_DIR%\legacy\" >nul
if errorlevel 1 (
  echo [ERROR] Copy from main_legacy.dist failed.
  exit /b 1
)

@REM アイコンファイルのコピー
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
