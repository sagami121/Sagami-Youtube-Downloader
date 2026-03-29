import os
import sys
from pathlib import Path

def _ensure_executable(path: Path):
    if os.name != "nt" and path.exists() and not os.access(path, os.X_OK):
        try:
            import stat
            st = os.stat(path)
            os.chmod(path, st.st_mode | stat.S_IEXEC)
        except Exception:
            pass

def resolve_app_icon_path(app_dir: Path):
    candidates = [
        app_dir / "Sagami Youtube Downloader.ico"
    ]
    for icon_path in candidates:
        if icon_path.exists():
            return icon_path
    return None

def qt_message_filter(_msg_type, _context, message):
    text = str(message or "")
    if "QFont::setPointSize: Point size <= 0" in text:
        return
    if "DirectWrite:" in text or "OpenType support missing" in text:
        return
    try:
        err = getattr(sys, "stderr", None)
        if err and hasattr(err, "write"):
            err.write(text + "\n")
    except Exception:
        pass
