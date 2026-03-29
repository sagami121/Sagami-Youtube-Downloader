import os
import sys
from pathlib import Path

VERSION = "1.6.4"
CONFIG_DIR_NAME = "SagamiYoutubeDownloader"
APP_GITHUB_REPO_URL = "https://github.com/sagami121/Sagami-Youtube-Downloader"
APP_DISPLAY_NAME = "Sagami youtube Downloader"

YT_DLP_WIN_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
FFMPEG_WIN_ZIP_URL = "https://github.com/ffbinaries/ffbinaries-prebuilt/releases/download/v4.4.1/ffmpeg-4.4.1-win-64.zip"
FFPROBE_WIN_ZIP_URL = "https://github.com/ffbinaries/ffbinaries-prebuilt/releases/download/v4.4.1/ffprobe-4.4.1-win-64.zip"

def is_packaged_executable() -> bool:
    if getattr(sys, "frozen", False):
        return True
    if "__compiled__" in globals():
        return True
    if hasattr(sys, "_MEIPASS"):
        return True
    return False

def get_runtime_app_dir() -> Path:
    if is_packaged_executable():
        return Path(sys.executable).parent
    return Path(__file__).parent.resolve()

def get_config_path() -> Path:
    if is_packaged_executable():
        base_dir = Path(os.getenv("APPDATA") or (Path.home() / "AppData" / "Roaming"))
        cfg_dir = base_dir / CONFIG_DIR_NAME
        cfg_dir.mkdir(parents=True, exist_ok=True)
        return cfg_dir / "config.json"
    else:
        return get_runtime_app_dir() / "config.json"

def get_history_path() -> Path:
    return get_config_path().parent / "history.json"
