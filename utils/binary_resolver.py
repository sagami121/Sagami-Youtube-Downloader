import os
import shutil
import subprocess
import importlib.util
from pathlib import Path
import urllib.request
import urllib.error
import urllib.parse
import ssl
import zipfile

from constants import (
    YT_DLP_WIN_URL, FFMPEG_WIN_ZIP_URL, FFPROBE_WIN_ZIP_URL,
    get_runtime_app_dir, is_packaged_executable
)

def _safe_download_file(url: str, dest_path: Path, timeout: int = 30):
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    context = ssl.create_default_context()
    with urllib.request.urlopen(req, context=context, timeout=timeout) as resp:
        with open(dest_path, "wb") as f:
            shutil.copyfileobj(resp, f)

def _extract_exe_from_zip(zip_path: Path, exe_name: str, dest_dir: Path):
    with zipfile.ZipFile(zip_path) as zf:
        member = None
        for name in zf.namelist():
            if Path(name).name.lower() == exe_name.lower():
                member = name
                break
        if not member:
            raise FileNotFoundError(f"{exe_name} not found in archive")
        extracted = Path(zf.extract(member, dest_dir))
    final_path = dest_dir / exe_name
    if extracted.resolve() != final_path.resolve():
        if final_path.exists():
            final_path.unlink()
        shutil.move(str(extracted), str(final_path))

def ensure_windows_binaries(status_cb=None):
    if os.name != "nt" or not is_packaged_executable():
        return True, "skipped"
    app_dir = get_runtime_app_dir()
    missing = []
    yt_path = app_dir / "yt-dlp.exe"
    ffmpeg_path = app_dir / "ffmpeg.exe"
    ffprobe_path = app_dir / "ffprobe.exe"
    if not yt_path.exists():
        missing.append("yt-dlp.exe")
    if not ffmpeg_path.exists():
        missing.append("ffmpeg.exe")
    if not ffprobe_path.exists():
        missing.append("ffprobe.exe")
    if not missing:
        return True, "already_present"

    try:
        if status_cb:
            status_cb("Checking required binaries...")
        if "yt-dlp.exe" in missing:
            if status_cb:
                status_cb("Downloading yt-dlp...")
            _safe_download_file(YT_DLP_WIN_URL, yt_path)
        if "ffmpeg.exe" in missing:
            if status_cb:
                status_cb("Downloading ffmpeg...")
            zip_path = app_dir / "ffmpeg.zip"
            _safe_download_file(FFMPEG_WIN_ZIP_URL, zip_path)
            _extract_exe_from_zip(zip_path, "ffmpeg.exe", app_dir)
            zip_path.unlink(missing_ok=True)
        if "ffprobe.exe" in missing:
            if status_cb:
                status_cb("Downloading ffprobe...")
            zip_path = app_dir / "ffprobe.zip"
            _safe_download_file(FFPROBE_WIN_ZIP_URL, zip_path)
            _extract_exe_from_zip(zip_path, "ffprobe.exe", app_dir)
            zip_path.unlink(missing_ok=True)
        return True, "downloaded"
    except Exception as e:
        return False, str(e)

def resolve_yt_dlp_command():
    app_dir = get_runtime_app_dir()
    candidates = [app_dir / "yt-dlp.exe", app_dir / "yt-dlp"]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return [str(candidate)]
    if importlib.util.find_spec("yt_dlp") is not None:
        return [sys.executable, "-m", "yt_dlp"]
    if shutil.which("yt-dlp"):
        return ["yt-dlp"]
    return None

def resolve_ffmpeg_command():
    app_dir = get_runtime_app_dir()
    candidates = [
        app_dir / "ffmpeg.exe",
        app_dir / "ffmpeg",
        app_dir / "ffmpeg" / "bin" / "ffmpeg.exe",
        app_dir / "ffmpeg" / "bin" / "ffmpeg",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    return shutil.which("ffmpeg")

def resolve_ffprobe_command():
    app_dir = get_runtime_app_dir()
    candidates = [
        app_dir / "ffprobe.exe",
        app_dir / "ffprobe",
        app_dir / "ffmpeg" / "bin" / "ffprobe.exe",
        app_dir / "ffmpeg" / "bin" / "ffprobe",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    return shutil.which("ffprobe")

def is_ffmpeg_usable(ffmpeg_cmd: str) -> bool:
    if not ffmpeg_cmd:
        return False
    try:
        proc = subprocess.run(
            [ffmpeg_cmd, "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return proc.returncode == 0
    except Exception:
        return False
