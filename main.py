import sys
import subprocess
import re
import json
import os
import shutil
import time
import traceback
import urllib.request
import urllib.error
import urllib.parse
import ssl
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import *
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRect, QPropertyAnimation, QEasingCurve, QTimer, QUrl, qInstallMessageHandler, QEvent
from PyQt6.QtGui import QFont, QIcon, QDesktopServices, QColor, QPalette

VERSION = "1.6.1"
CONFIG_DIR_NAME = "SagamiYoutubeDownloader"
APP_GITHUB_REPO_URL = "https://github.com/sagami121/Sagami-Youtube-Downloader"
APP_DISPLAY_NAME = "Sagami youtube Downloader"

def is_packaged_executable() -> bool:
    """パッケージ化（EXE/App/Bin）されているか判定"""
    if getattr(sys, "frozen", False):
        return True
    if "__compiled__" in globals():
        return True
    if hasattr(sys, "_MEIPASS"):
        return True
    return False

def get_runtime_app_dir() -> Path:
    """実行ファイルまたはスクリプトの配置ディレクトリを取得"""
    if is_packaged_executable():
        # macOS .app の場合は Contents/MacOS に実行ファイルがあるため、その親の親がリソースディレクトリになる場合があるが、
        # PyInstaller/Nuitkaの標準的な動作に合わせる
        return Path(sys.executable).parent
    return Path(__file__).parent

def get_runtime_launch_target(app_dir: Path) -> Path:
    """自分自身の実行パスを取得（再起動用など）"""
    if not is_packaged_executable():
        return (app_dir / "main.py").resolve()
    return Path(sys.executable).resolve()

def resolve_app_icon_path():
    """OSに合わせたアイコンパスを解決"""
    app_dir = get_runtime_app_dir()
    # Windows用ico, または汎用png
    candidates = [
        app_dir / "Sagami Youtube Downloader.ico",
        app_dir / "icon.png",
        app_dir / "assets" / "icon.png"
    ]
    for icon_path in candidates:
        if icon_path.exists():
            return icon_path
    return None

def qt_message_filter(_msg_type, _context, message):
    text = str(message or "")
    if "QFont::setPointSize: Point size <= 0" in text:
        return
    try:
        err = getattr(sys, "stderr", None)
        if err and hasattr(err, "write"):
            err.write(text + "\n")
    except Exception:
        # Never crash app from Qt log handler.
        pass

def _theme_base_dirs():
    app_dir = get_runtime_app_dir()
    bases = [app_dir / "theme", Path(__file__).parent / "theme"]
    return [b for b in bases if b.exists()]

def resolve_theme_assets(theme: str):
    """テーマ名からCSS/JSONパスを解決"""
    bases = _theme_base_dirs()
    css_path = None
    json_path = None
    if theme in ("dark", "light"):
        for base in bases:
            candidate = base / "default" / f"default_{theme}.css"
            if candidate.exists():
                css_path = candidate
                json_path = base / "default" / "default.json"
                break
    elif "_" in theme:
        prefix = theme.split("_", 1)[0]
        for base in bases:
            candidate = base / prefix / f"{theme}.css"
            if candidate.exists():
                css_path = candidate
                json_path = base / prefix / f"{prefix}.json"
                break
    if css_path is None:
        for base in bases:
            try:
                found = next(base.rglob(f"{theme}.css"))
                css_path = found
                json_path = found.parent / f"{found.parent.name}.json"
                break
            except StopIteration:
                continue
    return css_path, json_path

def get_stylesheet(theme="dark", widget_type="main"):
    """テーマに応じたスタイルシートを返す"""
    theme_file, _json_path = resolve_theme_assets(str(theme))

    cache_key = f"{theme}:{widget_type}:{theme_file}"
    if cache_key in _THEME_CSS_CACHE:
        return _THEME_CSS_CACHE[cache_key]

    if theme_file and theme_file.exists():
        try:
            text = theme_file.read_text(encoding="utf-8")
            _THEME_CSS_CACHE[cache_key] = text
            return text
        except Exception:
            pass

    # ファイルが見つからない、またはエラー時の最小限のフォールバック
    if "light" in theme:
        fallback = "QWidget#Main { background-color: #ffffff; } QLabel { color: #333333; }"
    else:
        fallback = "QWidget#Main { background-color: #000000; } QLabel { color: #ffffff; }"
    _THEME_CSS_CACHE[cache_key] = fallback
    return fallback

def parse_theme_metadata(theme="dark", widget_type="main"):
    """CSSファイル内のMETADATAセクションから配色情報を取得"""
    theme_file, _json_path = resolve_theme_assets(str(theme))
    
    cache_key = f"{theme}:{widget_type}:meta"
    if cache_key in _THEME_PROFILE_CACHE:
        cached = _THEME_PROFILE_CACHE[cache_key]
        return dict(cached) if isinstance(cached, dict) else {}

    colors = {}
    if theme_file and theme_file.exists():
        try:
            content = theme_file.read_text(encoding="utf-8")
            match = re.search(r"METADATA\s*(.*?)\s*END_METADATA", content, re.DOTALL)
            if match:
                for line in match.group(1).strip().splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        colors[k.strip()] = v.strip()
        except Exception:
            pass
    _THEME_PROFILE_CACHE[cache_key] = dict(colors)
    return colors

def load_theme_profile(theme: str):
    """テーマJSONから colors/props を取得（あれば）"""
    if theme in _THEME_PROFILE_CACHE:
        colors, props = _THEME_PROFILE_CACHE[theme]
        return dict(colors), dict(props)
    _css_path, json_path = resolve_theme_assets(str(theme))
    if json_path and json_path.exists():
        try:
            data = _read_json_cached(json_path)
            if isinstance(data, dict):
                profile = data.get(theme) or data.get("default")
                if isinstance(profile, dict):
                    colors = profile.get("colors") or {}
                    props = profile.get("props") or {}
                    colors = colors if isinstance(colors, dict) else {}
                    props = props if isinstance(props, dict) else {}
                    _THEME_PROFILE_CACHE[theme] = (dict(colors), dict(props))
                    return dict(colors), dict(props)
        except Exception:
            pass
    _THEME_PROFILE_CACHE[theme] = ({}, {})
    return {}, {}

def load_theme_info(theme: str):
    """テーマ情報（info）を取得"""
    if theme in _THEME_INFO_CACHE:
        return dict(_THEME_INFO_CACHE[theme])
    app_dir = get_runtime_app_dir()
    base = app_dir / "theme"
    if not base.exists():
        base = Path(__file__).parent / "theme"
    if not base.exists():
        return {}
    for json_path in base.rglob("*.json"):
        try:
            data = _read_json_cached(json_path)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        if theme in data and isinstance(data.get("info"), dict):
            info = data.get("info") or {}
            if isinstance(info, dict):
                _THEME_INFO_CACHE[theme] = dict(info)
                return dict(info)
    _THEME_INFO_CACHE[theme] = {}
    return {}

def apply_dialog_theme(dialog: QDialog, theme: str):
    """ダイアログにテーマを適用（白フラッシュ対策）"""
    try:
        dialog.setStyleSheet(get_stylesheet(theme, "main"))
        dialog.setAutoFillBackground(True)
        dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        colors, _props = load_theme_profile(theme)
        bg = colors.get("bg")
        if not bg:
            bg = "#000000" if "dark" in theme else "#ffffff"
        base = colors.get("input_bg") or colors.get("card") or bg
        text = colors.get("input_text") or ("#ffffff" if "dark" in theme else "#000000")
        pal = dialog.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(bg))
        pal.setColor(QPalette.ColorRole.Base, QColor(base))
        pal.setColor(QPalette.ColorRole.Text, QColor(text))
        dialog.setPalette(pal)
        apply_titlebar_theme(dialog, theme)
        QTimer.singleShot(0, lambda: apply_titlebar_theme(dialog, theme))
    except Exception:
        pass

def apply_app_theme(app: QApplication, theme: str):
    """アプリ全体にテーマを適用（初回の白フラッシュ対策）"""
    if app is None:
        return
    try:
        app.setStyleSheet(get_stylesheet(theme, "main"))
        colors, _props = load_theme_profile(theme)
        bg = colors.get("bg")
        if not bg:
            bg = "#000000" if "dark" in theme else "#ffffff"
        base = colors.get("input_bg") or colors.get("card") or bg
        text = colors.get("input_text") or ("#ffffff" if "dark" in theme else "#000000")
        pal = app.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(bg))
        pal.setColor(QPalette.ColorRole.Base, QColor(base))
        pal.setColor(QPalette.ColorRole.Text, QColor(text))
        app.setPalette(pal)
    except Exception:
        pass

def apply_titlebar_theme(widget: QWidget, theme: str):
    """Windowsのタイトルバーをテーマに合わせる"""
    if os.name != "nt" or widget is None:
        return
    try:
        import ctypes
        hwnd = int(widget.winId())
        use_dark = 1 if "dark" in str(theme) else 0
        value = ctypes.c_int(use_dark)
        # Try Windows 10/11 attribute IDs
        for attr in (20, 19):
            try:
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd,
                    attr,
                    ctypes.byref(value),
                    ctypes.sizeof(value),
                )
            except Exception:
                continue
    except Exception:
        pass

def warm_theme_cache(theme: str):
    """テーマのCSS/JSONを先読みしてキャッシュ（初回の白フラッシュ対策）"""
    try:
        get_stylesheet(theme, "main")
        get_stylesheet(theme, "settings")
        load_theme_profile(theme)
    except Exception:
        pass

def scan_theme_options():
    """themeフォルダから利用可能なテーマ一覧を収集"""
    global _THEME_OPTIONS_CACHE
    if _THEME_OPTIONS_CACHE is not None:
        return list(_THEME_OPTIONS_CACHE)
    bases = _theme_base_dirs()
    themes = []
    for base in bases:
        for css_path in base.rglob("*.css"):
            name = css_path.stem
            if css_path.parent.name == "default" and name.startswith("default_"):
                theme_name = name.replace("default_", "", 1)
            else:
                theme_name = name
            if theme_name not in themes:
                themes.append(theme_name)
    # フォールバック
    if not themes:
        themes = ["dark", "light"]
    _THEME_OPTIONS_CACHE = list(themes)
    return list(themes)

def lerp_color(start_color, end_color, progress):
    """16進数カラーコードを線形補間"""
    try:
        # 16進数から RGB に解析
        start_rgb = tuple(int(start_color[i:i+2], 16) for i in (1, 3, 5))
        end_rgb = tuple(int(end_color[i:i+2], 16) for i in (1, 3, 5))
        
        # 補間
        interpolated = tuple(int(s + (e - s) * progress) for s, e in zip(start_rgb, end_rgb))
        
        # RGB から16進数文字列に変換
        return '#{:02x}{:02x}{:02x}'.format(*interpolated)
    except Exception:
        return end_color

def get_config_path() -> Path:
    if is_packaged_executable():
        # パッケージ化されている場合はOSごとの標準的なユーザー領域に保存
        if os.name == "nt":
            base_dir = Path(os.getenv("APPDATA") or (Path.home() / "AppData" / "Roaming"))
        elif sys.platform == "darwin":
            base_dir = Path.home() / "Library" / "Application Support"
        else:
            # Linux (XDG)
            base_dir = Path(os.getenv("XDG_CONFIG_HOME") or (Path.home() / ".config"))
        
        cfg_dir = base_dir / CONFIG_DIR_NAME
        cfg_dir.mkdir(parents=True, exist_ok=True)
        return cfg_dir / "config.json"
    else:
        # Pythonスクリプトとして実行されている場合
        app_dir = Path(__file__).parent
    
    return app_dir / "config.json"

def resolve_yt_dlp_command():
    app_dir = get_runtime_app_dir()
    candidates = [app_dir / "yt-dlp.exe", app_dir / "yt-dlp"]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return [str(candidate)]
    if shutil.which("yt-dlp"):
        return ["yt-dlp"]
    return None

def resolve_aria2c_command():
    app_dir = get_runtime_app_dir()
    candidates = [app_dir / "aria2c.exe", app_dir / "aria2c"]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    return shutil.which("aria2c")

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

def parse_timecode_to_seconds(value: str):
    text = (value or "").strip()
    if not text:
        return None

    if text.isdigit():
        return int(text)

    parts = text.split(":")
    if len(parts) not in (2, 3):
        return None
    if not all(p.isdigit() for p in parts):
        return None

    if len(parts) == 2:
        mm, ss = map(int, parts)
        if ss >= 60:
            return None
        return mm * 60 + ss

    hh, mm, ss = map(int, parts)
    if mm >= 60 or ss >= 60:
        return None
    return hh * 3600 + mm * 60 + ss

def parse_time_range(value: str):
    raw = (value or "").strip()
    if not raw:
        return None, None, None

    normalized = raw.replace(" ", "").replace("～", "~").replace("〜", "~").replace("－", "~").replace("-", "~")
    if "~" not in normalized:
        return None, None, "時間指定は `開始~終了` で入力してください。(例: 0:00~0:15)"

    start_raw, end_raw = normalized.split("~", 1)
    start_sec = parse_timecode_to_seconds(start_raw)
    end_sec = parse_timecode_to_seconds(end_raw)
    if start_sec is None or end_sec is None:
        return None, None, "時間の形式が不正です。`秒` / `mm:ss` / `hh:mm:ss` を使ってください。"
    if start_sec >= end_sec:
        return None, None, "開始時間は終了時間より前にしてください。"

    return str(start_sec), str(end_sec), None

def tail_text(text: str, max_lines: int = 8):
    lines = [line for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return ""
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    return "\n".join(lines)

def version_key(version: str):
    text = (version or "").strip().lower()
    if text.startswith("v"):
        text = text[1:]
    nums = [int(x) for x in re.findall(r"\d+", text)]
    nums = (nums + [0, 0, 0])[:3]
    pre_rank = 0
    pre_num = 0
    if "alpha" in text:
        pre_rank = -3
    elif "beta" in text:
        pre_rank = -2
    elif "rc" in text:
        pre_rank = -1
    match = re.search(r"(alpha|beta|rc)\s*(\d+)?", text)
    if match and match.group(2):
        pre_num = int(match.group(2))
    return (*nums, pre_rank, pre_num)

def is_newer_version(latest: str, current: str) -> bool:
    return version_key(latest) > version_key(current)

def extract_latest_changelog_entry(changelog_text: str) -> str:
    lines = (changelog_text or "").splitlines()
    block = []
    started = False
    for line in lines:
        if line.strip():
            started = True
            block.append(line.rstrip())
        elif started:
            break
    return "\n".join(block).strip()

def read_changelog_latest_entry() -> str:
    try:
        app_dir = get_runtime_app_dir()
        changelog_path = app_dir / "changelog.txt"
        if not changelog_path.exists():
            return ""
        text = changelog_path.read_text(encoding="utf-8")
        return extract_latest_changelog_entry(text)
    except Exception:
        return ""

def format_release_date(iso_text: str) -> str:
    text = (iso_text or "").strip()
    if not text:
        return ""
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
    if not match:
        return ""
    return f"{match.group(1)}.{match.group(2)}.{match.group(3)}"

_LANG_CACHE = {}
_THEME_CSS_CACHE = {}
_THEME_PROFILE_CACHE = {}
_THEME_INFO_CACHE = {}
_THEME_OPTIONS_CACHE = None
_THEME_JSON_CACHE = {}

def load_language_dict(lang_code: str) -> dict:
    code = (lang_code or "ja").strip().lower()
    if code in _LANG_CACHE:
        return _LANG_CACHE[code]

    app_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    lang_dir = app_dir / "language"
    lang_file = lang_dir / f"{code}.json"
    fallback_file = lang_dir / "ja.json"

    data = {}
    try:
        if lang_file.exists():
            data = json.loads(lang_file.read_text(encoding="utf-8-sig"))
        elif fallback_file.exists():
            data = json.loads(fallback_file.read_text(encoding="utf-8-sig"))
    except Exception:
        data = {}

    if not isinstance(data, dict):
        data = {}
    _LANG_CACHE[code] = data
    return data

def i18n(cfg: dict, key: str, default: str) -> str:
    lang_code = str((cfg or {}).get("language", "ja"))
    data = load_language_dict(lang_code)
    value = data.get(key, default)
    return str(value) if value is not None else default

def _read_json_cached(path: Path):
    key = str(path)
    if key in _THEME_JSON_CACHE:
        return _THEME_JSON_CACHE[key]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = None
    _THEME_JSON_CACHE[key] = data
    return data


def load_config():
    default_path = ""
    downloads_path = os.path.join(os.path.expanduser("~"), "Downloads")
    cfg_path = get_config_path()
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            if "path" not in cfg:
                cfg["path"] = default_path
            elif str(cfg.get("path", "")).strip() == downloads_path:
                cfg["path"] = default_path
            if "theme" not in cfg:
                cfg["theme"] = "dark"
            if "language" not in cfg:
                cfg["language"] = "ja"
            if "embed_thumbnail" not in cfg:
                cfg["embed_thumbnail"] = False
            if "video_quality" not in cfg:
                cfg["video_quality"] = "Best"
            if "video_fps" not in cfg:
                cfg["video_fps"] = "Any"
            if "audio_quality" not in cfg:
                cfg["audio_quality"] = "0"
            if "time_range_input" not in cfg:
                cfg["time_range_input"] = ""
            if "app_update_source_url" not in cfg:
                cfg["app_update_source_url"] = ""
            if "cookies_browser" not in cfg:
                cfg["cookies_browser"] = "none"
            if "proxy_url" not in cfg:
                cfg["proxy_url"] = ""
            if "embed_subtitles" not in cfg:
                cfg["embed_subtitles"] = False
            return cfg
    except (FileNotFoundError, json.JSONDecodeError):
        defaults = {
            "format": "mp4",
            "template": "%(title)s",
            "path": default_path,
            "theme": "dark",
            "language": "ja",
            "embed_thumbnail": False,
            "video_quality": "Best",
            "video_fps": "Any",
            "audio_quality": "0",
            "time_range_input": "",
            "app_update_source_url": "",
            "cookies_browser": "none",
            "proxy_url": "",
            "embed_subtitles": False,
        }
        try:
            save_config(defaults)
        except Exception:
            pass
        return defaults


def save_config(cfg):
    cfg_path = get_config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)

def write_ini_log(section: str, values: dict, prefix: str = "error") -> str:
    lines = [f"[{section}]"]
    for key, value in values.items():
        text = str(value).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")
        lines.append(f"{key}={text}")
    payload = "\n".join(lines) + "\n"

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    app_dir = get_runtime_app_dir()
    candidates = [app_dir / "logs"]
    try:
        cfg_base = get_config_path().parent
        candidates.append(cfg_base / "logs")
    except Exception:
        pass

    for logs_dir in candidates:
        try:
            logs_dir.mkdir(parents=True, exist_ok=True)
            path = logs_dir / f"{prefix}_{ts}.txt"
            path.write_text(payload, encoding="utf-8")
            return str(path)
        except Exception:
            continue

    return ""

class DownloadThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)

    def __init__(self, url, folder, cfg):
        super().__init__()
        self.url = url
        self.folder = folder
        self.cfg = cfg
        self.process = None
        self._stopped = False
        self._thumbnail_webps = set()
        self._existing_webps = set()
        self._run_started_ts = None
        self._current_title = ""

    def _track_thumbnail_webp(self, line: str):
        if not self.cfg.get("embed_thumbnail", False):
            return

        markers = [
            "Destination: ",
            "Writing video thumbnail to: ",
            "Thumbnail is already present: ",
        ]
        for marker in markers:
            if marker in line:
                raw_path = line.split(marker, 1)[1].strip()
                if raw_path.lower().endswith(".webp"):
                    p = Path(raw_path)
                    if not p.is_absolute():
                        p = Path(self.folder) / p
                    self._thumbnail_webps.add(p)
                return

        m = re.search(r'^\[download\]\s(.+?\.webp)\s+has already been downloaded$', line, re.IGNORECASE)
        if m:
            p = Path(m.group(1).strip())
            if not p.is_absolute():
                p = Path(self.folder) / p
            self._thumbnail_webps.add(p)

    def _cleanup_thumbnail_webps(self):
        for p in self._thumbnail_webps:
            try:
                if p.exists() and p.is_file():
                    p.unlink()
            except Exception:
                pass

    def _snapshot_existing_webps(self):
        root = Path(self.folder)
        if not root.exists() or not root.is_dir():
            return
        try:
            self._existing_webps = {p.resolve() for p in root.rglob("*.webp") if p.is_file()}
        except Exception:
            self._existing_webps = set()

    def _cleanup_new_webps(self):
        root = Path(self.folder)
        if not root.exists() or not root.is_dir():
            return

        try:
            current_webps = [p.resolve() for p in root.rglob("*.webp") if p.is_file()]
        except Exception:
            return

        for p in current_webps:
            if p in self._existing_webps:
                continue
            try:
                p.unlink()
            except Exception:
                pass

    def run(self):
        template = self.cfg.get("template", "%(title)s")
        yt_cmd = resolve_yt_dlp_command()
        if yt_cmd is None:
            self.finished.emit("yt-dlp が見つかりません。")
            return
        ffmpeg_cmd = resolve_ffmpeg_command()
        ffprobe_cmd = resolve_ffprobe_command()
        ffmpeg_ok = is_ffmpeg_usable(ffmpeg_cmd) if ffmpeg_cmd else False
        ffprobe_ok = bool(ffprobe_cmd)

        args = yt_cmd + [
            "-P", self.folder, "-o", f"{template}.%(ext)s",
            "--newline",
            "--progress-template", "download:%(progress._percent_str)s|%(progress.eta)s|%(info.title)s"
        ]
        playlist_items = str(self.cfg.get("playlist_items", "") or "").strip()
        if playlist_items:
            args += ["--playlist-items", playlist_items]
        order_mode = str(self.cfg.get("playlist_order_mode", "default"))
        if order_mode == "latest":
            args += ["--playlist-reverse"]
        elif order_mode == "popular":
            args += ["--playlist-sorting", "view_count"]
        elif order_mode == "oldest":
            args += ["--playlist-reverse"]
        elif self.cfg.get("playlist_reverse", False) and not playlist_items:
            args += ["--playlist-reverse"]
        if self.cfg.get("disable_playlist_thumbnail", False):
            args += ["-o", "pl_thumbnail:"]
        if ffmpeg_ok:
            args += ["--ffmpeg-location", str(Path(ffmpeg_cmd).parent)]

        # Cookies setting
        cookies_browser = self.cfg.get("cookies_browser", "none")
        if cookies_browser and cookies_browser != "none":
            args += ["--cookies-from-browser", cookies_browser]

        out_format = self.cfg.get("format", "mp4")
        if out_format == "mp3":
            if not ffmpeg_ok:
                self.finished.emit("MP3変換には ffmpeg が必要です。ffmpeg.exe をアプリと同じフォルダに配置してください。")
                return
            # MP3は指定音質で抽出
            audio_quality = str(self.cfg.get("audio_quality", "0")).strip()
            if not re.fullmatch(r"\d+(?:\.\d+)?", audio_quality):
                audio_quality = "0"
            args += ["-x", "--audio-format", "mp3", "--audio-quality", audio_quality]
        elif out_format == "wav":
            if not ffmpeg_ok:
                self.finished.emit("WAV変換には ffmpeg が必要です。ffmpeg.exe をアプリと同じフォルダに配置してください。")
                return
            # WAVは再エンコード時の品質指定を使わず抽出
            args += ["-x", "--audio-format", "wav"]
        elif out_format == "m4a":
            if not ffmpeg_ok:
                self.finished.emit("M4A変換には ffmpeg が必要です。ffmpeg.exe をアプリと同じフォルダに配置してください。")
                return
            # M4Aは可能な限り再エンコードせず抽出
            args += ["-x", "--audio-format", "m4a"]
        else:
            if not ffmpeg_ok:
                self.finished.emit("高画質MP4の結合には ffmpeg が必要です。ffmpeg.exe をアプリと同じフォルダに配置してください。")
                return
            quality = self.cfg.get("video_quality", "Best")
            fps = self.cfg.get("video_fps", "Any")

            # Prefer highest available video stream first; remux to mp4 at merge stage.
            video_selector = "bv*"
            if quality and quality != "Best":
                h = quality.replace("p", "")
                if h.isdigit():
                    video_selector += f"[height<={h}]"
            if fps and fps != "Any" and str(fps).isdigit():
                video_selector += f"[fps<={fps}]"

            # Prefer AAC-compatible audio first to avoid Opus in MP4 outputs.
            format_selector = f"{video_selector}+ba[acodec*=mp4a]/{video_selector}+ba[ext=m4a]/{video_selector}+ba/b[ext=mp4]/b"

            args += ["-f", format_selector,
                     "--format-sort", "res,fps,vcodec:avc",
                     "--merge-output-format", "mp4"]
            
            # MP4の場合、サムネイル埋め込みオプションを追加
            if self.cfg.get("embed_thumbnail", False) and ffprobe_ok:
                args += ["--write-thumbnail", "--embed-thumbnail"]

        start_sec = self.cfg.get("time_range_start")
        end_sec = self.cfg.get("time_range_end")
        if start_sec is not None and end_sec is not None:
            args += ["--download-sections", f"*{start_sec}-{end_sec}", "--force-keyframes-at-cuts"]

        args.append(self.url)

        try:
            output_tail = []
            if self.cfg.get("embed_thumbnail", False):
                self._snapshot_existing_webps()
                self._run_started_ts = time.time()

            self.process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            for line in iter(self.process.stdout.readline, ''):
                if self._stopped:
                    break
                line = line.strip()
                if line:
                    output_tail.append(line)
                    if len(output_tail) > 60:
                        output_tail = output_tail[-60:]
                self._track_thumbnail_webp(line)
                if line.startswith("[download] Destination:"):
                    raw_name = line.split("Destination:", 1)[1].strip()
                    if raw_name:
                        self._current_title = Path(raw_name).stem
                if line.startswith("download:"):
                    parts = line.split(":", 1)[1].split("|")
                    if len(parts) >= 3:
                        eta = parts[1].strip() or "?"
                        title = parts[2].strip() or self._current_title
                        self.detail.emit(f"残り: {eta} / {title}")
                    elif len(parts) >= 1:
                        pct_text = parts[0].strip()
                        self.detail.emit(f"進捗: {pct_text}")
                elif line.startswith("[download]"):
                    m_eta = re.search(r"ETA\\s+([0-9:]+)", line)
                    if m_eta:
                        eta = m_eta.group(1)
                        title = self._current_title or ""
                        self.detail.emit(f"残り: {eta} / {title}" if title else f"残り: {eta}")

                m = re.search(r'(\d{1,3}(?:\.\d+)?)%', line)
                if m:
                    try:
                        pct = int(float(m.group(1)))
                    except Exception:
                        continue
                    if 0 <= pct <= 100:
                        self.progress.emit(pct)

            self.process.wait()
            if not self._stopped and self.process.returncode == 0:
                if self.cfg.get("embed_thumbnail", False):
                    self._cleanup_thumbnail_webps()
                    self._cleanup_new_webps()
                self.progress.emit(100)
                self.finished.emit("ダウンロードが完了しました")
            elif self._stopped:
                self.finished.emit("ダウンロードはキャンセルされました")
            else:
                log_path = write_ini_log(
                    "download_error",
                    {
                        "url": self.url,
                        "folder": self.folder,
                        "ffmpeg_cmd": ffmpeg_cmd or "",
                        "ffprobe_cmd": ffprobe_cmd or "",
                        "ffmpeg_usable": ffmpeg_ok,
                        "ffprobe_usable": ffprobe_ok,
                        "returncode": self.process.returncode if self.process else "unknown",
                        "command": " ".join(args),
                        "output_tail": "\n".join(output_tail),
                    },
                    prefix="download_error",
                )
                self.finished.emit(f"エラーが発生しました。\nログ: {log_path}")

        except Exception as e:
            log_path = write_ini_log(
                "download_exception",
                {
                    "url": self.url,
                    "folder": self.folder,
                    "ffmpeg_cmd": ffmpeg_cmd or "",
                    "ffprobe_cmd": ffprobe_cmd or "",
                    "ffmpeg_usable": ffmpeg_ok if "ffmpeg_ok" in locals() else False,
                    "ffprobe_usable": ffprobe_ok if "ffprobe_ok" in locals() else False,
                    "error": repr(e),
                    "command": " ".join(args) if "args" in locals() else "",
                },
                prefix="download_exception",
            )
            self.finished.emit(f"実行エラー: {e}\nログ: {log_path}")

class YtDlpUpdateThread(QThread):
    finished = pyqtSignal(bool, str, str, str, str)

    def _create_flags(self) -> int:
        return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    def _get_version(self, yt_cmd):
        try:
            process = subprocess.run(
                yt_cmd + ["--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if process.returncode == 0:
                ver = (process.stdout or "").strip()
                if ver:
                    return ver.splitlines()[-1].strip()
        except Exception:
            pass
        return "不明"

    def _is_pypi_update_hint(self, text: str) -> bool:
        body = (text or "").lower()
        return (
            "you installed yt-dlp with pip" in body
            or "wheel from pypi" in body
            or "use that to update" in body
        )

    def _run_pip_update(self):
        candidates = []
        if sys.executable:
            candidates.append([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"])
        candidates.append(["python", "-m", "pip", "install", "-U", "yt-dlp"])
        if os.name == "nt":
            candidates.append(["py", "-m", "pip", "install", "-U", "yt-dlp"])

        logs = []
        for cmd in candidates:
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=self._create_flags(),
                )
                out, _ = proc.communicate()
                logs.append(f"$ {' '.join(cmd)}\n{(out or '').strip()}")
                if proc.returncode == 0:
                    return True, "\n\n".join(logs)
            except Exception as e:
                logs.append(f"$ {' '.join(cmd)}\n実行エラー: {e}")

        return False, "\n\n".join(logs)

    def run(self):
        yt_cmd = resolve_yt_dlp_command()
        if yt_cmd is None:
            self.finished.emit(False, "failed", "不明", "不明", "yt-dlp が見つかりません。")
            return

        try:
            before_version = self._get_version(yt_cmd)

            # パッケージ版（PyInstaller等）
            if getattr(sys, "frozen", False):

                exe_path = Path(yt_cmd[0])

                # OSごとのダウンロードURL
                if os.name == "nt":
                    url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
                elif sys.platform == "darwin":
                    url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos"
                else:
                    url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"

                tmp = exe_path.with_suffix(".new")

                import urllib.request
                urllib.request.urlretrieve(url, tmp)

                # Linux / macOS 実行権限
                if os.name != "nt":
                    os.chmod(tmp, 0o755)

                exe_path.unlink(missing_ok=True)
                tmp.rename(exe_path)

                output = "GitHubからyt-dlpを更新しました"
                process_returncode = 0

            else:
                # Python版
                process = subprocess.Popen(
                    yt_cmd + ["-U"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=self._create_flags()
                )

                output, _ = process.communicate()
                process_returncode = process.returncode

                if process_returncode != 0 and self._is_pypi_update_hint(output):
                    pip_ok, pip_output = self._run_pip_update()
                    output = (output or "") + "\n\n[pip fallback]\n" + (pip_output or "")
                    if pip_ok:
                        process_returncode = 0

            after_version = self._get_version(yt_cmd)

            if process_returncode == 0:
                state = "updated"
                if before_version == after_version:
                    state = "up_to_date"

                self.finished.emit(True, state, before_version, after_version, output)
            else:
                self.finished.emit(False, "failed", before_version, after_version, output)
        except Exception as e:
            self.finished.emit(False, "failed", "不明", "不明", f"yt-dlp 更新エラー: {e}")


class YtDlpCheckThread(QThread):
    finished = pyqtSignal(bool, str, str, str, str)

    def _create_flags(self) -> int:
        return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    def _get_version(self, yt_cmd):
        try:
            process = subprocess.run(
                yt_cmd + ["--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=self._create_flags()
            )
            if process.returncode == 0:
                ver = (process.stdout or "").strip()
                if ver:
                    return ver.splitlines()[-1].strip()
        except Exception:
            pass
        return "不明"

    def _fetch_latest_version(self):
        latest_url = "https://github.com/yt-dlp/yt-dlp/releases/latest"
        req = urllib.request.Request(latest_url, headers={"User-Agent": "Sagami-Youtube-Downloader"})
        with urllib.request.urlopen(req, timeout=10) as response:
            final_url = response.geturl()
        parsed = urllib.parse.urlparse(final_url)
        parts = (parsed.path or "").strip("/").split("/")
        if len(parts) >= 4 and parts[-2] == "tag":
            return parts[-1]
        return ""

    def run(self):
        yt_cmd = resolve_yt_dlp_command()
        if yt_cmd is None:
            self.finished.emit(False, "failed", "不明", "不明", "yt-dlp が見つかりません。")
            return

        try:
            current_version = self._get_version(yt_cmd)
            latest_version = self._fetch_latest_version()
            if not latest_version:
                self.finished.emit(False, "failed", current_version, current_version, "最新バージョンの取得に失敗しました。")
                return

            if current_version and current_version != "不明" and is_newer_version(latest_version, current_version):
                self.finished.emit(True, "update_available", current_version, latest_version, "")
                return

            self.finished.emit(True, "up_to_date", current_version, latest_version, "")
        except Exception as e:
            self.finished.emit(False, "failed", "不明", "不明", str(e))

        except Exception as e:
            self.finished.emit(False, "failed", "不明", "不明", f"yt-dlp 更新エラー: {e}")

class AppUpdateThread(QThread):
    finished = pyqtSignal(bool, str, str, str, str, str, str, str)

    def __init__(self, source_url: str):
        super().__init__()
        self.source_url = (source_url or "").strip()

    def _github_latest_release_api(self, url: str) -> str:
        text = (url or "").strip()
        if text.endswith("/"):
            text = text[:-1]
        match = re.match(r"^https?://github\.com/([^/]+)/([^/]+)$", text)
        if not match:
            raise ValueError("GitHubリポジトリURLの形式が不正です。")
        owner = match.group(1)
        repo = match.group(2)
        return f"https://api.github.com/repos/{owner}/{repo}/releases/latest"

    def _github_tags_api(self, url: str) -> str:
        text = (url or "").strip()
        if text.endswith("/"):
            text = text[:-1]
        match = re.match(r"^https?://github\.com/([^/]+)/([^/]+)$", text)
        if not match:
            raise ValueError("GitHubリポジトリURLの形式が不正です。")
        owner = match.group(1)
        repo = match.group(2)
        return f"https://api.github.com/repos/{owner}/{repo}/tags"

    def _http_get_json(self, url: str):
        req = urllib.request.Request(url, headers={"User-Agent": "Sagami-Youtube-Downloader"})
        with self._urlopen_with_ssl_fallback(req, url, timeout=10) as response:
            payload = response.read().decode("utf-8")
        return json.loads(payload)

    def _http_get_text(self, url: str):
        req = urllib.request.Request(url, headers={"User-Agent": "Sagami-Youtube-Downloader"})
        with self._urlopen_with_ssl_fallback(req, url, timeout=10) as response:
            payload = response.read().decode("utf-8", errors="replace")
            final_url = response.geturl()
        return payload, final_url

    def _is_known_update_host(self, url: str) -> bool:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
        trusted_suffixes = (
            "github.com",
            "githubusercontent.com",
            "githubassets.com",
        )
        return any(host == suffix or host.endswith("." + suffix) for suffix in trusted_suffixes)

    def _urlopen_with_ssl_fallback(self, req, url: str, timeout: int = 10):
        def _is_ssl_verify_error(exc: Exception) -> bool:
            if isinstance(exc, ssl.SSLCertVerificationError):
                return True
            if isinstance(exc, urllib.error.URLError):
                reason = getattr(exc, "reason", None)
                return isinstance(reason, ssl.SSLCertVerificationError)
            return False

        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except Exception as first_error:
            if not _is_ssl_verify_error(first_error):
                raise
            certifi_ctx = None
            try:
                import certifi
                certifi_ctx = ssl.create_default_context(cafile=certifi.where())
            except Exception:
                certifi_ctx = None

            if certifi_ctx is not None:
                try:
                    return urllib.request.urlopen(req, timeout=timeout, context=certifi_ctx)
                except Exception as second_error:
                    if not _is_ssl_verify_error(second_error):
                        raise
                    pass

            if self._is_known_update_host(url):
                insecure_ctx = ssl._create_unverified_context()
                return urllib.request.urlopen(req, timeout=timeout, context=insecure_ctx)
            raise first_error

    def _pick_installer_asset_url(self, release_data: dict) -> str:
        assets = release_data.get("assets") or []
        if not isinstance(assets, list):
            return ""
        urls = []
        for item in assets:
            name = str(item.get("name", "")).lower()
            url = str(item.get("browser_download_url", "")).strip()
            if not url:
                continue
            if name.endswith(".exe") or name.endswith(".msi"):
                urls.append((name, url))
        if not urls:
            return ""
        preferred = [u for u in urls if ("setup" in u[0] or "installer" in u[0])]
        return (preferred[0] if preferred else urls[0])[1]

    def _github_release_latest_page(self, url: str) -> str:
        text = (url or "").strip()
        if text.endswith("/"):
            text = text[:-1]
        match = re.match(r"^https?://github\.com/([^/]+)/([^/]+)$", text)
        if not match:
            raise ValueError("GitHubリポジトリURLの形式が不正です。")
        owner = match.group(1)
        repo = match.group(2)
        return f"https://github.com/{owner}/{repo}/releases/latest"

    def _extract_version_from_release_url(self, url: str) -> str:
        if not url:
            return ""
        parsed = urllib.parse.urlparse(url)
        parts = (parsed.path or "").strip("/").split("/")
        if len(parts) >= 4 and parts[-2] == "tag":
            return parts[-1]
        return ""

    def _pick_installer_from_html(self, html: str, base_url: str) -> str:
        if not html:
            return ""
        hrefs = re.findall(r'href="([^"]+)"', html, flags=re.IGNORECASE)
        urls = []
        for href in hrefs:
            if not href:
                continue
            if href.startswith("/"):
                full = "https://github.com" + href
            else:
                full = href
            if not full.startswith("http"):
                continue
            low = full.lower()
            if not (low.endswith(".exe") or low.endswith(".msi")):
                continue
            if "/releases/download/" not in low:
                continue
            name = low.split("/")[-1]
            urls.append((name, full))
        if not urls:
            return ""
        preferred = [u for u in urls if ("setup" in u[0] or "installer" in u[0])]
        return (preferred[0] if preferred else urls[0])[1]

    def _load_release(self):
        if not self.source_url:
            raise ValueError("更新元URLが未設定です。")
        try:
            data = self._http_get_json(self._github_latest_release_api(self.source_url))
            latest_version = str(data.get("tag_name", "")).strip()
            release_page_url = str(data.get("html_url", "")).strip()
            installer_url = self._pick_installer_asset_url(data)
            notes = str(data.get("body", "")).strip()
            published_at = str(data.get("published_at", "")).strip()
            if latest_version:
                return latest_version, release_page_url, notes, published_at, installer_url
        except urllib.error.HTTPError as e:
            # 404 は「Release未作成」の可能性が高いので tags へフォールバック
            if getattr(e, "code", None) in (403, 429):
                try:
                    latest_page = self._github_release_latest_page(self.source_url)
                    html, final_url = self._http_get_text(latest_page)
                    latest_version = self._extract_version_from_release_url(final_url)
                    release_page_url = final_url or latest_page
                    installer_url = self._pick_installer_from_html(html, release_page_url)
                    notes = "GitHub API の制限のため、HTMLから取得しました。"
                    if latest_version:
                        return latest_version, release_page_url, notes, "", installer_url
                except Exception:
                    raise
            if getattr(e, "code", None) != 404:
                raise

        # 2) Release未作成時は tags の先頭を最新として扱う
        tags = self._http_get_json(self._github_tags_api(self.source_url))
        if not isinstance(tags, list) or not tags:
            raise ValueError("GitHub からタグ情報を取得できませんでした。")
        latest_version = str(tags[0].get("name", "")).strip()
        if not latest_version:
            raise ValueError("GitHub タグ名を取得できませんでした。")
        release_page_url = self.source_url.rstrip("/") + "/releases"
        notes = "GitHub Release が未作成のため、タグを基準に更新判定しました。"
        return latest_version, release_page_url, notes, "", ""

    def run(self):
        try:
            latest_version, release_page_url, notes, published_at, installer_url = self._load_release()

            if not latest_version:
                self.finished.emit(False, "failed", "", "", "", "", "", "GitHub release の tag_name がありません。")
                return

            state = "update_available" if is_newer_version(latest_version, VERSION) else "up_to_date"
            self.finished.emit(True, state, VERSION, latest_version, release_page_url, notes, published_at, installer_url)
        except Exception as e:
            reason = str(e).strip() or repr(e)
            self.finished.emit(False, "failed", VERSION, "", "", reason, "", "")

class FocusClearLineEdit(QLineEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_LineEditClearButton)
        self._clear_action = self.addAction(icon, QLineEdit.ActionPosition.TrailingPosition)
        self._clear_action.triggered.connect(self.clear)
        self._clear_action.setVisible(False)
        self.textChanged.connect(self._update_clear_action)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._update_clear_action()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._update_clear_action()

    def _update_clear_action(self):
        self._clear_action.setVisible(self.hasFocus() and bool(self.text()))

class Settings(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent_win = parent
        self.cfg = load_config()
        apply_dialog_theme(self, str(self.cfg.get("theme", "dark")))
        self.setWindowTitle(i18n(self.cfg, "settings.window_title", "出力設定"))
        self.resize(500, 700)
        self.setMinimumSize(460, 600)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        main_vbox = QVBoxLayout(self)
        main_vbox.setContentsMargins(0, 0, 0, 0)
        main_vbox.setSpacing(0)

        # Scroll Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        scroll_content = QWidget()
        scroll_content.setObjectName("SettingsContent")
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(14)

        # Language
        layout.addWidget(QLabel(i18n(self.cfg, "settings.language_label", "言語 / Language")))
        self.lang_combo = QComboBox()
        self.lang_combo.addItem(i18n(self.cfg, "settings.lang_ja", "日本語"), "ja")
        self.lang_combo.addItem(i18n(self.cfg, "settings.lang_en", "English"), "en")
        self.lang_combo.addItem(i18n(self.cfg, "settings.lang_ko", "한국어"), "ko")
        self.lang_combo.addItem(i18n(self.cfg, "settings.lang_zh", "中文(简体)"), "zh")
        lang_idx = self.lang_combo.findData(str(self.cfg.get("language", "ja")))
        self.lang_combo.setCurrentIndex(lang_idx if lang_idx >= 0 else 0)
        self.lang_combo.setMinimumHeight(40)
        layout.addWidget(self.lang_combo)

        # Theme
        layout.addSpacing(4)
        layout.addWidget(QLabel(i18n(self.cfg, "settings.theme_label", "テーマ")))
        self.theme_combo = QComboBox()
        self._all_theme_options = list(scan_theme_options())
        for theme_name in self._all_theme_options:
            label = theme_name.replace("_", " ").title()
            self.theme_combo.addItem(label, theme_name)
        theme_idx = self.theme_combo.findData(str(self.cfg.get("theme", "dark")))
        self.theme_combo.setCurrentIndex(theme_idx if theme_idx >= 0 else 0)
        self.theme_combo.setMinimumHeight(40)
        layout.addWidget(self.theme_combo)

        info_row = QHBoxLayout()
        info_row.addWidget(QLabel(i18n(self.cfg, "settings.theme_info_label", "テーマ情報")))
        self.btn_theme_info = QPushButton(i18n(self.cfg, "settings.theme_info_show", "表示"))
        self.btn_theme_info.setMinimumHeight(32)
        self.btn_theme_info.clicked.connect(self.show_theme_info)
        self.btn_theme_refresh = QPushButton(i18n(self.cfg, "settings.theme_refresh", "テーマを更新"))
        self.btn_theme_refresh.setMinimumHeight(32)
        self.btn_theme_refresh.clicked.connect(self.refresh_theme_list)
        info_row.addStretch()
        info_row.addWidget(self.btn_theme_info)
        info_row.addWidget(self.btn_theme_refresh)
        layout.addLayout(info_row)
        self.theme_combo.currentIndexChanged.connect(self.update_theme_info)
        self.update_theme_info()

        # Output Format
        layout.addSpacing(4)
        layout.addWidget(QLabel(i18n(self.cfg, "settings.output_format", "出力形式")))
        self.format_combo = QComboBox()
        self.format_combo.addItem("Video (mp4)", "mp4")
        self.format_combo.addItem("Audio (mp3)", "mp3")
        self.format_combo.addItem("Audio (wav)", "wav")
        self.format_combo.addItem("Audio (m4a)", "m4a")
        self.format_combo.setMinimumHeight(40)
        fmt_idx = self.format_combo.findData(str(self.cfg.get("format", "mp4")))
        self.format_combo.setCurrentIndex(fmt_idx if fmt_idx >= 0 else 0)
        layout.addWidget(self.format_combo)

        # Other Settings
        layout.addSpacing(4)
        layout.addWidget(QLabel(i18n(self.cfg, "settings.other", "その他の設定")))
        self.chk_thumbnail = QCheckBox(i18n(self.cfg, "settings.embed_thumbnail", "MP4に動画のサムネイルを埋め込む"))
        self.chk_thumbnail.setChecked(self.cfg.get("embed_thumbnail", False))
        layout.addWidget(self.chk_thumbnail)

        self.chk_subtitles = QCheckBox(i18n(self.cfg, "settings.embed_subtitles", "字幕を埋め込む (利用可能な場合)"))
        self.chk_subtitles.setChecked(self.cfg.get("embed_subtitles", False))
        layout.addWidget(self.chk_subtitles)

        # Proxy Settings
        layout.addSpacing(4)
        layout.addWidget(QLabel(i18n(self.cfg, "settings.proxy", "プロキシ設定 (Proxy URL)")))
        self.proxy_input = QLineEdit()
        self.proxy_input.setPlaceholderText("http://user:pass@host:port")
        self.proxy_input.setText(self.cfg.get("proxy_url", ""))
        layout.addWidget(self.proxy_input)

        # Filename Template
        layout.addSpacing(4)
        layout.addWidget(QLabel(i18n(self.cfg, "settings.current_template", "現在のファイル名構成")))
        self.template_display = QLineEdit()
        self.template_display.setText(self.cfg.get("template", "%(title)s"))
        layout.addWidget(self.template_display)

        # Filename Tags Grid
        layout.addWidget(QLabel(i18n(self.cfg, "settings.filename_tags", "ファイル名のタグ設定")))
        tag_container = QWidget()
        tag_layout = QGridLayout(tag_container)
        tag_layout.setContentsMargins(0, 0, 0, 0)
        tag_layout.setHorizontalSpacing(10)
        tag_layout.setVerticalSpacing(10)
        tags = [
            (i18n(self.cfg, "settings.tag_title", "タイトル"), "%(title)s"),
            (i18n(self.cfg, "settings.tag_id", "動画ID"), "[%(id)s]"),
            (i18n(self.cfg, "settings.tag_uploader", "投稿者"), "[%(uploader)s]"),
            (i18n(self.cfg, "settings.tag_date", "投稿日"), "[%(upload_date)s]"),
            (i18n(self.cfg, "settings.tag_quality", "画質"), "[%(height)sp]"),
            (i18n(self.cfg, "settings.tag_clear", "クリア"), "clear"),
        ]

        for i, (label, code) in enumerate(tags):
            btn = QPushButton(label)
            btn.setMinimumHeight(36)
            if code == "clear":
                btn.clicked.connect(lambda: self.template_display.clear())
                btn.setObjectName("ClearBtn")
            else:
                btn.clicked.connect(lambda _, c=code: self.add_tag(c))
            tag_layout.addWidget(btn, i // 3, i % 3)
        layout.addWidget(tag_container)

        # Browser for cookies
        layout.addSpacing(8)
        layout.addWidget(QLabel(i18n(self.cfg, "settings.cookies_browser", "Cookiesを取得するブラウザ")))
        self.cookies_combo = QComboBox()
        self.cookies_combo.addItem(i18n(self.cfg, "settings.cookies_none", "使用しない (None)"), "none")
        self.cookies_combo.addItem("Chrome", "chrome")
        self.cookies_combo.addItem("Edge", "edge")
        self.cookies_combo.addItem("Firefox", "firefox")
        self.cookies_combo.addItem("Opera", "opera")
        self.cookies_combo.addItem("Vivaldi", "vivaldi")
        self.cookies_combo.addItem("Brave", "brave")
        self.cookies_combo.setMinimumHeight(40)
        c_idx = self.cookies_combo.findData(str(self.cfg.get("cookies_browser", "none")))
        self.cookies_combo.setCurrentIndex(c_idx if c_idx >= 0 else 0)
        layout.addWidget(self.cookies_combo)

        layout.addSpacing(10)
        save_btn = QPushButton(i18n(self.cfg, "settings.save", "設定を保存"))
        save_btn.setObjectName("SaveBtn")
        save_btn.setMinimumHeight(48)
        save_btn.clicked.connect(self.save)
        layout.addWidget(save_btn)

        layout.addSpacing(6)
        version_label = QLabel(f"Version: {VERSION}")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setStyleSheet("color: #8e8e93; font-size: 10px;")
        layout.addWidget(version_label)

        scroll.setWidget(scroll_content)
        main_vbox.addWidget(scroll)

        self.apply_style()

    def apply_style(self):
        theme = self.parent_win.cfg.get("theme", "dark")
        self.setStyleSheet(get_stylesheet(theme, "settings"))

    def add_tag(self, code):
        current = self.template_display.text()
        new_text = (current + " " + code) if current else code
        self.template_display.setText(new_text)

    def update_theme_info(self):
        theme = self.theme_combo.currentData() or ""
        info = load_theme_info(str(theme))
        self._theme_info_cache = info if isinstance(info, dict) else {}

    def show_theme_info(self):
        info = getattr(self, "_theme_info_cache", {}) or {}
        if not info:
            QMessageBox.information(self, "テーマ情報", "このテーマの情報はありません。")
            return
        parts = []
        if info.get("theme_name"):
            parts.append(f"テーマ: {info.get('theme_name')}")
        if info.get("author"):
            parts.append(f"作者: {info.get('author')}")
        if info.get("description"):
            parts.append(str(info.get("description")))
        QMessageBox.information(self, "テーマ情報", "\n".join(parts))

    def refresh_theme_list(self):
        try:
            global _THEME_OPTIONS_CACHE, _THEME_CSS_CACHE, _THEME_PROFILE_CACHE, _THEME_INFO_CACHE, _THEME_JSON_CACHE
            _THEME_OPTIONS_CACHE = None
            _THEME_CSS_CACHE.clear()
            _THEME_PROFILE_CACHE.clear()
            _THEME_INFO_CACHE.clear()
            _THEME_JSON_CACHE.clear()
        except Exception:
            pass
        current = self.theme_combo.currentData() or self.cfg.get("theme", "dark")
        self._all_theme_options = list(scan_theme_options())
        self.theme_combo.blockSignals(True)
        self.theme_combo.clear()
        for theme_name in self._all_theme_options:
            label = theme_name.replace("_", " ").title()
            self.theme_combo.addItem(label, theme_name)
        theme_idx = self.theme_combo.findData(str(current))
        self.theme_combo.setCurrentIndex(theme_idx if theme_idx >= 0 else 0)
        self.theme_combo.blockSignals(False)
        self.update_theme_info()


    def save(self):
        try:
            self.cfg["language"] = self.lang_combo.currentData() or "ja"
            self.cfg["theme"] = self.theme_combo.currentData() or "dark"
            self.cfg["format"] = self.format_combo.currentData() or "mp4"
            self.cfg["template"] = self.template_display.text() or "%(title)s"
            self.cfg["path"] = self.parent_win.path_display.text()
            self.cfg["embed_thumbnail"] = self.chk_thumbnail.isChecked()
            self.cfg["embed_subtitles"] = self.chk_subtitles.isChecked()
            self.cfg["cookies_browser"] = self.cookies_combo.currentData() or "none"
            save_config(self.cfg)
            
            # 親ウィンドウの設定とスタイルも更新
            self.parent_win.cfg = self.cfg
            self.parent_win.apply_style()
            self.parent_win.apply_language_texts()
            
            self.accept()
        except Exception as e:
            log_path = write_ini_log(
                "settings_save_exception",
                {"error": repr(e), "traceback": traceback.format_exc()},
                prefix="settings_save_exception",
            )
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("エラー")
            suffix = f"\nログ: {log_path}" if log_path else ""
            msg.setText(f"設定の保存に失敗しました。{suffix}")
            msg.exec()


class LogViewerDialog(QDialog):
    def __init__(self, parent, logs_dir: Path):
        super().__init__(parent)
        self.logs_dir = logs_dir
        theme = "dark"
        if parent and hasattr(parent, "cfg"):
            theme = str(getattr(parent, "cfg", {}).get("theme", "dark"))
        apply_dialog_theme(self, theme)
        self.setWindowTitle("ログビュー")
        self.resize(760, 520)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.list_logs = QListWidget()
        self.list_logs.setMinimumHeight(180)
        self.list_logs.currentItemChanged.connect(self.on_log_selected)
        layout.addWidget(self.list_logs)

        self.text_log = QPlainTextEdit()
        self.text_log.setReadOnly(True)
        layout.addWidget(self.text_log, 1)

        actions = QHBoxLayout()
        actions.addStretch()
        self.btn_refresh = QPushButton("再読み込み")
        self.btn_open_folder = QPushButton("フォルダを開く")
        self.btn_close = QPushButton("閉じる")
        self.btn_refresh.clicked.connect(self.refresh_logs)
        self.btn_open_folder.clicked.connect(self.open_logs_folder)
        self.btn_close.clicked.connect(self.close)
        actions.addWidget(self.btn_refresh)
        actions.addWidget(self.btn_open_folder)
        actions.addWidget(self.btn_close)
        layout.addLayout(actions)

        self.refresh_logs()

    def refresh_logs(self):
        self.list_logs.clear()
        self.text_log.clear()
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        files = sorted(self.logs_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
        for p in files:
            item = QListWidgetItem(p.name)
            item.setData(Qt.ItemDataRole.UserRole, str(p))
            self.list_logs.addItem(item)
        if self.list_logs.count() > 0:
            self.list_logs.setCurrentRow(0)
        else:
            self.text_log.setPlainText("ログがありません。")

    def on_log_selected(self, current, _previous):
        if current is None:
            self.text_log.clear()
            return
        path = Path(current.data(Qt.ItemDataRole.UserRole))
        try:
            self.text_log.setPlainText(path.read_text(encoding="utf-8"))
        except Exception as e:
            self.text_log.setPlainText(f"ログの読み込みに失敗しました。\n{e}")

    def open_logs_folder(self):
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.logs_dir)))


class PlaylistSelectDialog(QDialog):
    def __init__(self, parent, entries, source_label: str = "プレイリスト", source_name: str = ""):
        super().__init__(parent)
        theme = "dark"
        if parent and hasattr(parent, "cfg"):
            theme = str(getattr(parent, "cfg", {}).get("theme", "dark"))
        apply_dialog_theme(self, theme)
        self.setWindowTitle("動画選択")
        self.resize(620, 520)
        self.result_mode = "cancel"
        self.selected_indices = []
        self.order_mode = "default"
        self.search_text = ""
        self._entries = list(entries or [])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        if source_label == "チャンネル" and source_name:
            head = f"動画を検出しました。チャンネル名　{source_name}"
        elif source_name:
            head = f"{source_label}「{source_name}」を検出しました。（{len(entries)}件）"
        else:
            head = f"{source_label}を検出しました。（{len(entries)}件）"
        label = QLabel(f"{head}\nダウンロードする動画を選択してください。")
        label.setWordWrap(True)
        layout.addWidget(label)

        order_row = QHBoxLayout()
        order_row.addWidget(QLabel("並び順"))
        self.order_combo = QComboBox()
        self.order_combo.addItem("最新順")
        self.order_combo.addItem("人気順")
        self.order_combo.addItem("古い順")
        self.order_combo.setMinimumHeight(32)
        self.order_combo.currentIndexChanged.connect(self._apply_order)
        order_row.addWidget(self.order_combo, 1)
        layout.addLayout(order_row)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("検索"))
        self.search_input = QLineEdit()
        self.search_input.setObjectName("PlaylistSearch")
        self.search_input.setPlaceholderText("タイトルで検索...")
        
        # テーマに合わせてテキスト色を調整しつつ、プレースホルダーの色を灰色に設定
        # Qtのスタイルシートではプレースホルダーの色を直接指定できないためPaletteを使用
        search_text_color = "#ffffff" if "dark" in theme else "#000000"
        self.search_input.setStyleSheet(f"QLineEdit#PlaylistSearch {{ color: {search_text_color}; }}")
        
        try:
            pal = self.search_input.palette()
            # PlaceholderText役割を使用して灰色に設定
            pal.setColor(QPalette.ColorRole.PlaceholderText, QColor("#8e8e93"))
            self.search_input.setPalette(pal)
        except Exception:
            pass
        self.search_input.textChanged.connect(self._on_search_changed)
        search_row.addWidget(self.search_input, 1)
        layout.addLayout(search_row)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.list_widget.viewport().installEventFilter(self)
        layout.addWidget(self.list_widget, 1)
        self._apply_order()

        actions = QHBoxLayout()
        self.btn_select_all = QPushButton("全部選択")
        self.btn_clear_all = QPushButton("全解除")
        self.btn_download_all = QPushButton("全部ダウンロード")
        self.btn_download_selected = QPushButton("選択のみダウンロード")
        self.btn_cancel = QPushButton("キャンセル")

        self.btn_select_all.clicked.connect(self.select_all)
        self.btn_clear_all.clicked.connect(self.clear_all)
        self.btn_download_all.clicked.connect(self.download_all)
        self.btn_download_selected.clicked.connect(self.download_selected)
        self.btn_cancel.clicked.connect(self.reject)

        actions.addWidget(self.btn_select_all)
        actions.addWidget(self.btn_clear_all)
        actions.addStretch()
        actions.addWidget(self.btn_download_all)
        actions.addWidget(self.btn_download_selected)
        actions.addWidget(self.btn_cancel)
        layout.addLayout(actions)
        self._apply_startup_palette()

    def _apply_startup_palette(self):
        theme = ""
        if self.parent() and hasattr(self.parent(), "cfg"):
            theme = str(getattr(self.parent(), "cfg", {}).get("theme", "dark"))
        if not theme:
            theme = "dark"
        colors, _props = load_theme_profile(theme)
        bg = colors.get("bg")
        if not bg:
            bg = "#000000" if "dark" in theme else "#ffffff"
        try:
            pal = self.palette()
            pal.setColor(QPalette.ColorRole.Window, QColor(bg))
            self.setPalette(pal)
        except Exception:
            pass

    def select_all(self):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.CheckState.Checked)

    def clear_all(self):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.CheckState.Unchecked)

    def download_all(self):
        self.result_mode = "all"
        self.accept()

    def download_selected(self):
        indices = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                idx = item.data(Qt.ItemDataRole.UserRole)
                if idx is not None:
                    indices.append(int(idx))
        self.selected_indices = indices
        self.result_mode = "selected"
        self.accept()

    def toggle_item_check(self, item):
        if item is None:
            return
        state = item.checkState()
        item.setCheckState(Qt.CheckState.Unchecked if state == Qt.CheckState.Checked else Qt.CheckState.Checked)

    def eventFilter(self, obj, event):
        if obj is self.list_widget.viewport() and event.type() == QEvent.Type.MouseButtonPress:
            item = self.list_widget.itemAt(event.pos())
            if item is not None:
                self.toggle_item_check(item)
                return True
        return super().eventFilter(obj, event)

    def _on_search_changed(self, text: str):
        self.search_text = (text or "").strip().lower()
        self._apply_order()

    def _apply_order(self):
        self.list_widget.clear()
        index = self.order_combo.currentIndex()
        if index == 0:
            self.order_mode = "latest"
        elif index == 1:
            self.order_mode = "popular"
        else:
            self.order_mode = "oldest"
        items = list(self._entries)
        if self.search_text:
            items = [e for e in items if self.search_text in str(e.get("title", "")).lower()]

        has_date = any(self._date_sort_key(e) > 0 for e in items)
        if self.order_mode == "latest":
            if has_date:
                items.sort(key=self._date_sort_key, reverse=True)
            else:
                items.sort(key=lambda e: int(e.get("order_index") or e.get("index") or 0))
        elif self.order_mode == "popular":
            items.sort(key=lambda e: int(e.get("view_count") or 0), reverse=True)
        elif self.order_mode == "oldest":
            if has_date:
                items.sort(key=self._date_sort_key, reverse=False)
            else:
                items.sort(key=lambda e: int(e.get("order_index") or e.get("index") or 0), reverse=True)
        for entry in items:
            idx = entry.get("index")
            title = entry.get("title") or "(タイトル未取得)"
            text = f"{idx}. {title}"
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, idx)
            self.list_widget.addItem(item)

    def _date_sort_key(self, entry):
        ts = entry.get("timestamp") or 0
        if ts:
            return int(ts)
        ud = str(entry.get("upload_date") or "")
        if ud.isdigit():
            return int(ud)
        return 0


class Main(QWidget):
    def is_english(self) -> bool:
        return str(self.cfg.get("language", "ja")).lower().startswith("en")

    def t(self, key: str, default: str) -> str:
        return i18n(self.cfg, key, default)

    def _safe_call(self, action: str, func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            log_path = write_ini_log(
                "ui_action_exception",
                {
                    "action": action,
                    "error": repr(e),
                    "traceback": traceback.format_exc(),
                },
                prefix="ui_action_exception",
            )
            try:
                suffix = f"\nログ: {log_path}" if log_path else ""
                self._show_warning("エラー", f"操作中にエラーが発生しました。\n{action}{suffix}")
            except Exception:
                pass
            return None

    def theme_button_text(self, theme_name: str) -> str:
        return theme_name.replace("_", " ").title()

    def apply_language_texts(self):
        self.btn_theme.setText(self.theme_button_text(self.cfg.get("theme", "dark")))
        self.lbl_url.setText(self.t("main.video_url", "Video URL"))
        self.lbl_time.setText(self.t("main.time_range", "Time Range"))
        self.lbl_folder.setText(self.t("main.output_folder", "Output Folder"))
        self.url.setPlaceholderText(self.t("main.url_placeholder", "Paste link here..."))
        self.time_range.setPlaceholderText(self.t("main.time_placeholder", "e.g. 0:00~0:15"))
        self.btn_paste.setText(self.t("main.paste", "Paste"))
        self.btn_browse.setText(self.t("main.browse", "Browse"))
        self.btn_dl.setText(self.t("main.start_download", "Start Download"))
        self.btn_update_ytdlp.setText(self.t("main.update_ytdlp", "Update yt-dlp"))
        self.btn_check_app_update.setText(self.t("main.check_app_update", "Check App Update"))
        self.btn_settings.setText(self.t("main.settings", "Settings"))
        self.media_quality_label.setText(self.t("main.video_quality", "Video Quality"))
        self.set_ytdlp_status(self.ytdlp_version, self.ytdlp_state)
        self.set_app_status(self.app_state, self.app_current_version, self.app_latest_version)

    def set_app_status(self, state: str, current_version: str = "", latest_version: str = ""):
        self.app_state = state or "pending"
        if current_version:
            self.app_current_version = current_version
        if latest_version:
            self.app_latest_version = latest_version
        if not hasattr(self, "app_status_label"):
            return

        if self.app_state == "checking":
            text = self.t("status.app_checking", "{app} - {version} Checking...").format(app=APP_DISPLAY_NAME, version=VERSION)
        elif self.app_state == "failed":
            ver = self.app_latest_version or self.app_current_version or VERSION
            text = self.t("status.app_failed", "{app} - {version} Check failed").format(app=APP_DISPLAY_NAME, version=ver)
        elif self.app_state == "update_available":
            text = self.t("status.app_update_available", "{app} - {current}->{latest} Update available").format(
                app=APP_DISPLAY_NAME,
                current=self.app_current_version or VERSION,
                latest=self.app_latest_version or self.app_current_version or VERSION,
            )
        elif self.app_state == "source_not_set":
            text = self.t("status.app_source_not_set", "{app} - Update source URL not set").format(app=APP_DISPLAY_NAME)
        elif self.app_state == "up_to_date":
            ver = self.app_current_version or VERSION
            text = self.t("status.app_up_to_date", "{app} - {version} Up to date").format(app=APP_DISPLAY_NAME, version=ver)
        else:
            text = self.t("status.app_pending", "{app} - {version} Pending check").format(app=APP_DISPLAY_NAME, version=VERSION)
        self.app_status_label.setText(text)

    def _pick_known_version(self, after_version: str, before_version: str) -> str:
        unknown_values = {"", "不明", "unknown", self.t("common.unknown", "Unknown").lower()}
        a = (after_version or "").strip()
        b = (before_version or "").strip()
        if a and a.lower() not in unknown_values:
            return a
        if b and b.lower() not in unknown_values:
            return b
        return self.t("common.unknown", "Unknown")

    def __init__(self):
        super().__init__()
        self.setObjectName("Main")
        self.setWindowTitle("Sagami Youtube Downloader")
        self.setAutoFillBackground(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        icon_path = resolve_app_icon_path()
        if icon_path:
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(920, 700)
        self.setMinimumSize(720, 600)
        self.cfg = load_config()
        self._apply_startup_palette()
        self.is_animating = False  # アニメーション中かどうかを追跡
        self.download_thread = None
        self.updater = None
        self.startup_updater = None
        self.app_updater = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # テーマ切り替えボタンを一番上に配置
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(20, 10, 20, 10)
        top_bar.addStretch()
        self.btn_theme = QPushButton(self.theme_button_text(self.cfg.get("theme", "dark")))
        self.btn_theme.setObjectName("ThemeBtn")
        self.btn_theme.setFixedWidth(150)
        self.btn_theme.setMinimumHeight(35)
        self.btn_theme.clicked.connect(self.toggle_theme)
        top_bar.addWidget(self.btn_theme)
        main_layout.addLayout(top_bar)

        # スペーサー
        main_layout.addStretch()

        # カードを中央に配置するレイアウト
        center_layout = QHBoxLayout()
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.addStretch()

        card = QFrame()
        card.setObjectName("Card")
        card.setFixedWidth(520)
        self.card = card
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 26, 28, 24)
        card_layout.setSpacing(5)

        title = QLabel("Sagami YouTube Downloader")
        title.setObjectName("Title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title)

        # URL入力
        self.lbl_url = QLabel("動画URL")
        card_layout.addWidget(self.lbl_url)
        url_layout = QHBoxLayout()
        url_layout.setSpacing(8)
        self.url = FocusClearLineEdit()
        self.url.setPlaceholderText("ここにリンクを貼り付け...")
        self.url.setFixedHeight(40)
        self.btn_paste = QPushButton("ペースト")
        self.btn_paste.setFixedWidth(90)
        self.btn_paste.setMinimumHeight(38)
        self.btn_paste.setObjectName("SecondaryBtn")
        self.btn_paste.clicked.connect(lambda: self._safe_call("paste_url", self.paste_url))
        url_layout.addWidget(self.url)
        url_layout.addWidget(self.btn_paste)
        card_layout.addLayout(url_layout)

        self.lbl_time = QLabel("時間指定")
        card_layout.addWidget(self.lbl_time)
        self.time_range = FocusClearLineEdit()
        self.time_range.setPlaceholderText("例: 0:00~0:15")
        self.time_range.setText(self.cfg.get("time_range_input", ""))
        self.time_range.setFixedHeight(40)
        card_layout.addWidget(self.time_range)

        # 保存先
        self.lbl_folder = QLabel("保存先フォルダ")
        card_layout.addWidget(self.lbl_folder)
        path_layout = QHBoxLayout()
        path_layout.setSpacing(8)
        self.path_display = FocusClearLineEdit()
        self.path_display.setObjectName("PathDisplay")
        self.path_display.setText(self.cfg.get("path"))
        self.path_display.setReadOnly(False)
        self.path_display.setFixedHeight(40)
        self.path_display.editingFinished.connect(self.on_path_edited)
        
        self.btn_browse = QPushButton("選択")
        self.btn_browse.setFixedWidth(80)
        self.btn_browse.setMinimumHeight(38)
        self.btn_browse.setObjectName("SecondaryBtn")
        self.btn_browse.clicked.connect(lambda: self._safe_call("browse_folder", self.browse_folder))
        
        path_layout.addWidget(self.path_display)
        path_layout.addWidget(self.btn_browse)
        card_layout.addLayout(path_layout)

        # 画質/音質設定
        self.media_quality_label = QLabel("画質設定")
        card_layout.addWidget(self.media_quality_label)
        mp4_opts_layout = QHBoxLayout()
        mp4_opts_layout.setSpacing(8)

        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Best", "2160p", "1440p", "1080p", "720p", "480p", "360p"])
        self.quality_combo.setMinimumHeight(34)
        q_text = str(self.cfg.get("video_quality", "Best"))
        q_idx = self.quality_combo.findText(q_text)
        self.quality_combo.setCurrentIndex(q_idx if q_idx >= 0 else self.quality_combo.findText("Best"))

        self.fps_combo = QComboBox()
        self.fps_combo.addItem("Any", "Any")
        self.fps_combo.addItem("60 fps", "60")
        self.fps_combo.addItem("30 fps", "30")
        self.fps_combo.addItem("24 fps", "24")
        self.fps_combo.setMinimumHeight(34)
        fps_idx = self.fps_combo.findData(str(self.cfg.get("video_fps", "Any")))
        self.fps_combo.setCurrentIndex(fps_idx if fps_idx >= 0 else 0)

        self.audio_quality_combo = QComboBox()
        self.audio_quality_combo.addItem("最高 (0) - 320kbps", "0")
        self.audio_quality_combo.addItem("高 (2) - 256kbps", "2")
        self.audio_quality_combo.addItem("標準 (5) - 160kbps", "5")
        self.audio_quality_combo.addItem("低 (7) - 128kbps", "7")
        self.audio_quality_combo.setMinimumHeight(34)
        aq_idx = self.audio_quality_combo.findData(str(self.cfg.get("audio_quality", "0")))
        self.audio_quality_combo.setCurrentIndex(aq_idx if aq_idx >= 0 else 0)

        mp4_opts_layout.addWidget(self.quality_combo)
        mp4_opts_layout.addWidget(self.fps_combo)
        mp4_opts_layout.addWidget(self.audio_quality_combo)
        card_layout.addLayout(mp4_opts_layout)

        self.quality_combo.currentTextChanged.connect(lambda value: self._safe_call("on_video_quality_changed", self.on_video_quality_changed, value))
        self.fps_combo.currentIndexChanged.connect(lambda *_: self._safe_call("on_video_fps_changed", self.on_video_fps_changed))
        self.audio_quality_combo.currentIndexChanged.connect(lambda *_: self._safe_call("on_audio_quality_changed", self.on_audio_quality_changed))
        self.update_mp4_option_state()

        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(8)

        self.btn_dl = QPushButton("ダウンロードを開始")
        self.btn_dl.setMinimumHeight(46)
        self.btn_dl.clicked.connect(lambda: self._safe_call("start_download", self.start))
        actions_layout.addWidget(self.btn_dl, 1)

        self.btn_update_ytdlp = QPushButton("yt-dlp を更新")
        self.btn_update_ytdlp.setObjectName("SecondaryBtn")
        self.btn_update_ytdlp.setMinimumHeight(46)
        self.btn_update_ytdlp.clicked.connect(lambda: self._safe_call("update_ytdlp", self.update_ytdlp))
        self.btn_update_ytdlp.setVisible(False)

        self.btn_check_app_update = QPushButton("アプリ更新を確認")
        self.btn_check_app_update.setObjectName("SecondaryBtn")
        self.btn_check_app_update.setMinimumHeight(46)
        self.btn_check_app_update.clicked.connect(lambda: self._safe_call("check_app_update_manually", self.check_app_update_manually))
        self.btn_check_app_update.setVisible(False)
        actions_layout.addWidget(self.btn_check_app_update)

        card_layout.addLayout(actions_layout)

        self.ytdlp_status_label = QLabel("yt-dlp - 確認待ち")
        self.ytdlp_status_label.setObjectName("YtDlpStatusLabel")
        self.ytdlp_status_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        card_layout.addWidget(self.ytdlp_status_label)

        self.app_status_label = QLabel(f"{APP_DISPLAY_NAME} - {VERSION} 確認待ち")
        self.app_status_label.setObjectName("AppStatusLabel")
        self.app_status_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        card_layout.addWidget(self.app_status_label)
        self.ytdlp_state = "pending"
        self.ytdlp_version = self.t("common.unknown", "Unknown")
        self.app_state = "pending"
        self.app_current_version = VERSION
        self.app_latest_version = VERSION

        # 進捗バー
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(18)
        card_layout.addWidget(self.progress_bar)

        self.progress_detail_label = QLabel("")
        self.progress_detail_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.progress_detail_label.setWordWrap(True)
        self.progress_detail_label.setVisible(True)
        card_layout.addWidget(self.progress_detail_label)

        # 詳細設定
        foot_actions = QHBoxLayout()
        foot_actions.addStretch()
        self.btn_settings = QPushButton("詳細設定")
        self.btn_settings.setObjectName("SettingsBtn")
        self.btn_settings.clicked.connect(lambda: self._safe_call("open_settings", self.open_settings))
        foot_actions.addWidget(self.btn_settings)
        foot_actions.addStretch()
        card_layout.addLayout(foot_actions)

        center_layout.addWidget(card)
        center_layout.addStretch()
        main_layout.addLayout(center_layout)
        main_layout.addStretch()

        self.setAcceptDrops(True)
        self.apply_language_texts()
        self.apply_style()
        QTimer.singleShot(0, lambda: apply_titlebar_theme(self, self.cfg.get("theme", "dark")))
        QTimer.singleShot(700, self.check_app_update_on_startup)
        QTimer.singleShot(1200, self.check_ytdlp_on_startup)

    def showEvent(self, event):
        super().showEvent(event)
        try:
            apply_titlebar_theme(self, self.cfg.get("theme", "dark"))
        except Exception:
            pass

    def _apply_startup_palette(self):
        theme = str(self.cfg.get("theme", "dark"))
        colors, _props = load_theme_profile(theme)
        bg = colors.get("bg")
        if not bg:
            bg = "#000000" if "dark" in theme else "#ffffff"
        try:
            pal = self.palette()
            pal.setColor(QPalette.ColorRole.Window, QColor(bg))
            self.setPalette(pal)
        except Exception:
            pass

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        url_text = ""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                url_text = urls[0].toString()
        elif event.mimeData().hasText():
            url_text = event.mimeData().text()
        
        if url_text:
            raw = url_text.strip()
            if raw.lower().startswith("ttps://"):
                raw = "h" + raw
            elif raw.lower().startswith("ps://"):
                raw = "htt" + raw
            self.url.setText(raw)
            self.url.setCursorPosition(0)

    def apply_style(self):
        theme = self.cfg.get("theme", "dark")
        self.setStyleSheet(get_stylesheet(theme, "main"))
        app = QApplication.instance()
        if app is not None:
            apply_app_theme(app, theme)
        apply_titlebar_theme(self, theme)

    def _messagebox_stylesheet(self) -> str:
        theme = self.cfg.get("theme", "dark")
        if theme == "light":
            return """
                QMessageBox { background-color: #ffffff; }
                QMessageBox QLabel { color: #222222; font-size: 13px; font-weight: 400; padding-top: 2px; padding-bottom: 2px; }
            """
        return """
            QMessageBox { background-color: #1c1c1e; }
            QMessageBox QLabel { color: #f2f2f7; font-size: 13px; font-weight: 400; padding-top: 2px; padding-bottom: 2px; }
        """

    def _apply_messagebox_theme(self, box: QMessageBox):
        box.setStyleSheet(self._messagebox_stylesheet())
        try:
            title_label = box.findChild(QLabel, "qt_msgbox_label")
            if title_label:
                title_label.setWordWrap(True)
                title_label.setContentsMargins(0, 2, 0, 2)
            info_label = box.findChild(QLabel, "qt_msgbox_informativelabel")
            if info_label:
                info_label.setWordWrap(True)
                info_label.setContentsMargins(0, 2, 0, 2)
            box.setMinimumWidth(max(box.minimumWidth(), 430))
        except Exception:
            pass

    def _show_info(self, title: str, text: str):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle(title)
        box.setText(text)
        self._apply_messagebox_theme(box)
        box.exec()

    def _show_warning(self, title: str, text: str):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(title)
        box.setText(text)
        self._apply_messagebox_theme(box)
        box.exec()

    def open_settings(self):
        prev_lang = str(self.cfg.get("language", "ja"))
        dlg = Settings(self)
        if dlg.exec():
            self.cfg = load_config()
            self.update_mp4_option_state()
            self.apply_language_texts()
            if str(self.cfg.get("language", "ja")) != prev_lang:
                self._show_info("Language", "Language setting updated.")

    def paste_url(self):
        raw = (QApplication.clipboard().text() or "").strip()
        if raw.lower().startswith("ttps://"):
            raw = "h" + raw
        elif raw.lower().startswith("ps://"):
            raw = "htt" + raw
        self.url.setText(raw)
        self.url.setCursorPosition(0)

    def on_video_quality_changed(self, value):
        self.cfg["video_quality"] = value
        save_config(self.cfg)

    def on_video_fps_changed(self, *_):
        self.cfg["video_fps"] = self.fps_combo.currentData() or "Any"
        save_config(self.cfg)

    def on_audio_quality_changed(self, *_):
        self.cfg["audio_quality"] = self.audio_quality_combo.currentData() or "0"
        save_config(self.cfg)

    def update_mp4_option_state(self):
        is_mp4 = self.cfg.get("format", "mp4") == "mp4"
        self.media_quality_label.setText(self.t("main.video_quality", "Video Quality") if is_mp4 else self.t("main.audio_quality", "Audio Quality"))

        self.quality_combo.setVisible(is_mp4)
        self.fps_combo.setVisible(is_mp4)
        self.quality_combo.setEnabled(is_mp4)
        self.fps_combo.setEnabled(is_mp4)

        self.audio_quality_combo.setVisible(not is_mp4)
        self.audio_quality_combo.setEnabled(not is_mp4)

        if is_mp4:
            q_text = str(self.cfg.get("video_quality", "Best"))
            q_idx = self.quality_combo.findText(q_text)
            self.quality_combo.setCurrentIndex(q_idx if q_idx >= 0 else self.quality_combo.findText("Best"))
            fps_idx = self.fps_combo.findData(str(self.cfg.get("video_fps", "Any")))
            self.fps_combo.setCurrentIndex(fps_idx if fps_idx >= 0 else 0)
        else:
            aq_idx = self.audio_quality_combo.findData(str(self.cfg.get("audio_quality", "0")))
            self.audio_quality_combo.setCurrentIndex(aq_idx if aq_idx >= 0 else 0)

    def _looks_like_playlist_url(self, url: str) -> bool:
        text = (url or "").lower()
        if "list=" in text:
            return True
        if "/playlist" in text:
            return True
        if "music.youtube.com/playlist" in text:
            return True
        return False

    def _looks_like_channel_url(self, url: str) -> bool:
        text = (url or "").lower()
        if "youtube.com/channel/" in text:
            return True
        if "youtube.com/@" in text:
            return True
        if "youtube.com/user/" in text:
            return True
        return False

    def _normalize_channel_videos_url(self, url: str) -> str:
        raw = (url or "").strip()
        if not raw:
            return raw
        parsed = urllib.parse.urlparse(raw)
        path = parsed.path or ""
        lower_path = path.lower()
        if any(token in lower_path for token in ["/videos", "/streams", "/live", "/shorts"]):
            return raw
        if path.endswith("/"):
            path = path + "videos"
        else:
            path = path + "/videos"
        return urllib.parse.urlunparse(parsed._replace(path=path))

    def _fetch_playlist_entries(self, url: str, limit: int = 4000, order_mode: str = "default", is_channel: bool = False):
        yt_cmd = resolve_yt_dlp_command()
        if yt_cmd is None:
            return None, "yt-dlp が見つかりません。", {}

        flat_limit = max(1, int(limit))
        args = yt_cmd + ["--flat-playlist", "-J", "--playlist-end", str(flat_limit)]
        if order_mode == "latest":
            args += ["--playlist-reverse"]
        elif order_mode == "popular":
            args += ["--playlist-sorting", "view_count"]
        elif order_mode == "oldest":
            args += ["--playlist-reverse"]
        args.append(url)

        cookies_browser = self.cfg.get("cookies_browser", "none")
        if cookies_browser and cookies_browser != "none":
            args += ["--cookies-from-browser", cookies_browser]

        proxy_url = str(self.cfg.get("proxy_url", "") or "").strip()
        if proxy_url:
            args += ["--proxy", proxy_url]

        label = "チャンネル" if is_channel else "プレイリスト"

        try:
            proc = subprocess.run(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except Exception as e:
            return None, f"{label}取得に失敗しました。\n{e}", {}

        if proc.returncode != 0:
            err_tail = tail_text(proc.stderr or "")
            if err_tail:
                return None, f"{label}の取得に失敗しました。\n{err_tail}", {}
            return None, f"{label}の取得に失敗しました。", {}

        try:
            stdout_text = proc.stdout or ""
            data = json.loads(stdout_text)
        except Exception:
            # In case warnings got mixed into stdout, try extracting JSON block.
            stdout_text = proc.stdout or ""
            start = stdout_text.find("{")
            end = stdout_text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    data = json.loads(stdout_text[start:end + 1])
                except Exception:
                    data = None
            else:
                data = None
            if not data:
                err_tail = tail_text(proc.stderr or "")
                if err_tail:
                    return None, f"{label}情報の解析に失敗しました。\n{err_tail}", {}
                return None, f"{label}情報の解析に失敗しました。", {}

        entries = data.get("entries") or []
        meta = {}
        if isinstance(data, dict):
            channel_name = data.get("channel") or data.get("uploader") or data.get("title") or ""
            if channel_name:
                meta["channel_name"] = str(channel_name)
        if not entries:
            return None, None, meta

        items = []
        idx_counter = 1
        for entry in entries:
            if not entry:
                idx_counter += 1
                continue
            idx = entry.get("playlist_index") or entry.get("index") or idx_counter
            title = entry.get("title") or entry.get("fulltitle") or entry.get("id") or "(タイトル未取得)"
            upload_date = entry.get("upload_date")
            timestamp = entry.get("timestamp")
            view_count = entry.get("view_count")
            items.append({
                "index": int(idx),
                "order_index": int(idx),
                "title": str(title),
                "upload_date": str(upload_date) if upload_date is not None else "",
                "timestamp": int(timestamp) if str(timestamp).isdigit() else 0,
                "view_count": int(view_count) if str(view_count).isdigit() else 0,
            })
            idx_counter += 1

        return items, None, meta

    def browse_folder(self):
        start_dir = self.path_display.text().strip() or os.path.join(os.path.expanduser("~"), "Downloads")
        folder = QFileDialog.getExistingDirectory(self, "保存先フォルダを選択", start_dir)
        if folder:
            self.path_display.setText(folder)
            self.cfg["path"] = folder
            save_config(self.cfg)

    def on_path_edited(self):
        path = self.path_display.text().strip()
        self.cfg["path"] = path
        save_config(self.cfg)

    def update_ytdlp(self):
        if self.updater is not None and self.updater.isRunning():
            return

        if resolve_yt_dlp_command() is None:
            self._show_warning("エラー", "yt-dlp が見つかりません。")
            return

        self.btn_update_ytdlp.setEnabled(False)
        self.btn_update_ytdlp.setText("更新中...")
        self.updater = YtDlpUpdateThread()
        self.updater.finished.connect(self.on_ytdlp_updated)
        self.updater.start()

    def check_ytdlp_on_startup(self):
        if resolve_yt_dlp_command() is None:
            self.set_ytdlp_status("", "not_found")
            return
        if self.startup_updater is not None and self.startup_updater.isRunning():
            return

        self.startup_updater = YtDlpCheckThread()
        self.startup_updater.finished.connect(self.on_startup_ytdlp_checked)
        self.startup_updater.start()

    def check_app_update_on_startup(self):
        self.start_app_update_check(interactive=True, suppress_latest_popup=True)

    def check_app_update_manually(self):
        self.start_app_update_check(interactive=True, suppress_latest_popup=False)

    def start_app_update_check(self, interactive: bool, suppress_latest_popup: bool = False):
        if self.app_updater is not None and self.app_updater.isRunning():
            return

        source_url = str(self.cfg.get("app_update_source_url", "") or APP_GITHUB_REPO_URL).strip()
        if not source_url:
            self.set_app_status("source_not_set", VERSION, VERSION)
            if interactive:
                self._show_info("アプリ更新", "GitHubリポジトリURLが未設定です。\nconfig.json の app_update_source_url にURLを設定してください。")
            return

        self.btn_check_app_update.setEnabled(False)
        self.btn_check_app_update.setText("確認中...")
        self.set_app_status("checking", VERSION, VERSION)
        self.app_updater = AppUpdateThread(source_url)
        self.app_updater.finished.connect(
            lambda ok, state, current, latest, page_url, notes, published_at, installer_url:
            self.on_app_update_finished(ok, state, current, latest, page_url, notes, published_at, installer_url, interactive, suppress_latest_popup)
        )
        self.app_updater.start()

    def on_app_update_finished(self, ok: bool, state: str, current_version: str, latest_version: str, release_page_url: str, notes: str, published_at: str, installer_url: str, interactive: bool, suppress_latest_popup: bool):
        self.btn_check_app_update.setEnabled(True)
        self.btn_check_app_update.setText("アプリ更新を確認")
        version_display = latest_version or current_version

        if not ok:
            self.set_app_status("failed", version_display, version_display)
            if interactive:
                reason = (notes or "").strip() or "不明なエラー"
                self._show_warning("更新", f"更新確認に失敗しました。\n\n理由: {reason}")
            return

        if state == "update_available":
            self.set_app_status("update_available", current_version, latest_version)
            notes_text = notes or "更新内容は取得できませんでした。"
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setWindowTitle("更新")
            msg.setMinimumWidth(460)
            msg.setText(f"更新通知\nアプリ更新があります。\n現在: {current_version}\n最新: {latest_version}")
            msg.setInformativeText(f"更新内容:\n{notes_text}")
            self._apply_messagebox_theme(msg)
            
            # --- 「自動更新」ボタンの作成(auto_btn)を削除 ---
            open_btn = None
            if release_page_url:
                open_btn = msg.addButton("ページを開く", QMessageBox.ButtonRole.AcceptRole)
            
            msg.addButton("閉じる", QMessageBox.ButtonRole.RejectRole)
            msg.exec()
            
            clicked = msg.clickedButton()
            if open_btn is not None and clicked == open_btn:
                QDesktopServices.openUrl(QUrl(release_page_url))
            return

        self.set_app_status("up_to_date", current_version, current_version)
        if interactive and not suppress_latest_popup:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setWindowTitle("更新")
            msg.setMinimumWidth(420)
            msg.setText(f"更新通知\n{current_version} は最新です。")
            self._apply_messagebox_theme(msg)
            msg.exec()

    def set_ytdlp_status(self, version: str, state: str):
        if not hasattr(self, "ytdlp_status_label"):
            return

        version = (version or "").strip()
        self.ytdlp_version = version or self.t("common.unknown", "Unknown")
        self.ytdlp_state = state or "pending"
        if state == "pending":
            self.ytdlp_status_label.setText(self.t("status.ytdlp_pending", "yt-dlp - Pending check"))
        elif state == "checking":
            self.ytdlp_status_label.setText(self.t("status.ytdlp_checking", "yt-dlp - Checking..."))
        elif state == "not_found":
            self.ytdlp_status_label.setText(self.t("status.ytdlp_not_found", "yt-dlp - Not found"))
        elif state == "update_available":
            current = self.ytdlp_version or self.t("common.unknown", "Unknown")
            self.ytdlp_status_label.setText(self.t("status.ytdlp_update_available", "yt-dlp - {current}->{latest} Update available").format(current=current, latest=version))
        elif state == "up_to_date":
            if not version:
                version = self.t("common.unknown", "Unknown")
            self.ytdlp_status_label.setText(self.t("status.ytdlp_up_to_date", "yt-dlp - {version} Up to date").format(version=version))
        elif state == "updated":
            if not version:
                version = self.t("common.unknown", "Unknown")
            self.ytdlp_status_label.setText(self.t("status.ytdlp_updated", "yt-dlp - {version} Updated").format(version=version))
        else:
            if not version:
                version = self.t("common.unknown", "Unknown")
            self.ytdlp_status_label.setText(self.t("status.ytdlp_failed", "yt-dlp - {version} Check failed").format(version=version))

        self.ytdlp_status_label.setVisible(True)
    def on_startup_ytdlp_updated(self, ok: bool, state: str, before_version: str, after_version: str, output: str):
        status_version = self._pick_known_version(after_version, before_version)
        self.set_ytdlp_status(status_version, state if ok else "failed")
        if ok:
            return
        log_path = write_ini_log(
            "ytdlp_update_startup_failed",
            {
                "before_version": before_version,
                "after_version": after_version,
                "state": state,
                "output_tail": tail_text(output),
            },
            prefix="ytdlp_update_startup_failed",
        )
        self.ytdlp_status_label.setText(self.t("status.ytdlp_failed_with_log", "yt-dlp - {version} Check failed (log: {log})").format(version=status_version, log=Path(log_path).name))

    def on_startup_ytdlp_checked(self, ok: bool, state: str, current_version: str, latest_version: str, _output: str):
        if not ok:
            return
        if state == "update_available":
            self.ytdlp_version = current_version or self.t("common.unknown", "Unknown")
            self.set_ytdlp_status(latest_version or current_version, "update_available")
        elif state == "up_to_date":
            self.set_ytdlp_status(current_version or latest_version, "up_to_date")

    def on_ytdlp_updated(self, ok: bool, state: str, before_version: str, after_version: str, output: str):
        self.btn_update_ytdlp.setEnabled(True)
        self.btn_update_ytdlp.setText("yt-dlp を更新")
        body = tail_text(output)
        status_version = self._pick_known_version(after_version, before_version)
        self.set_ytdlp_status(status_version, state if ok else "failed")
        if ok and state == "up_to_date":
            message = "yt-dlp は最新です。"
        elif ok:
            message = "yt-dlp を更新しました。"
        else:
            message = "yt-dlp の更新に失敗しました。"

        message += f"\n\n更新前バージョン: {before_version}\n更新後バージョン: {after_version}"
        if body:
            message = f"{message}\n\n{body}"
        if ok:
            self._show_info("yt-dlp 更新", message)
        else:
            self._show_warning("yt-dlp 更新", message)

    def start(self):
        # Toggle: if a download is running, cancel it
        if self.download_thread is not None and self.download_thread.isRunning():
            self.cancel_download()
            return

        url = self.url.text().strip()
        if url.lower().startswith("ttps://"):
            url = "h" + url
            self.url.setText(url)
        elif url.lower().startswith("ps://"):
            url = "htt" + url
            self.url.setText(url)
        if not url:
            self._show_warning("入力エラー", "YouTube URLを入力してください。")
            return

        # Check that yt-dlp is available
        if resolve_yt_dlp_command() is None:
            self._show_warning("エラー", "yt-dlp が見つかりません。yt-dlp をインストールしてください。")
            return

        start_sec, end_sec, time_error = parse_time_range(self.time_range.text())
        if time_error:
            self._show_warning("時間指定エラー", time_error)
            return

        playlist_items = ""
        playlist_reverse = False
        playlist_order_mode = "default"
        is_playlist_url = self._looks_like_playlist_url(url)
        is_channel_url = self._looks_like_channel_url(url)
        if is_channel_url:
            url = self._normalize_channel_videos_url(url)
        if is_playlist_url or is_channel_url:
            entries, error, meta = self._fetch_playlist_entries(url, limit=4000, order_mode=playlist_order_mode)
            if error:
                self._show_warning("プレイリスト", error)
                return
            elif entries:
                source_label = "チャンネル" if is_channel_url and not is_playlist_url else "プレイリスト"
                source_name = ""
                if is_channel_url and not is_playlist_url:
                    source_name = str((meta or {}).get("channel_name", "") or "")
                dlg = PlaylistSelectDialog(self, entries, source_label=source_label, source_name=source_name)
                if dlg.exec() != QDialog.DialogCode.Accepted:
                    return
                if dlg.result_mode == "selected":
                    if not dlg.selected_indices:
                        self._show_warning("プレイリスト", "動画が選択されていません。")
                        return
                    seen = set()
                    ordered = []
                    for idx in dlg.selected_indices:
                        if idx in seen:
                            continue
                        seen.add(idx)
                        ordered.append(idx)
                    playlist_items = ",".join(str(i) for i in ordered)
                    playlist_reverse = False
                    playlist_order_mode = dlg.order_mode
                elif dlg.result_mode == "all":
                    playlist_items = ""
                    playlist_reverse = (dlg.order_mode == "oldest")
                    playlist_order_mode = dlg.order_mode
                else:
                    return

        self.btn_dl.setEnabled(True)
        self.btn_dl.setText("ダウンロード中... 0%")
        self.btn_update_ytdlp.setEnabled(False)
        cfg = load_config()
        cfg["video_quality"] = self.quality_combo.currentText()
        cfg["video_fps"] = self.fps_combo.currentData() or "Any"
        cfg["audio_quality"] = self.audio_quality_combo.currentData() or "0"
        cfg["time_range_input"] = self.time_range.text().strip()
        cfg["time_range_start"] = start_sec
        cfg["time_range_end"] = end_sec
        save_config(cfg)
        cfg["disable_playlist_thumbnail"] = bool(is_playlist_url or is_channel_url)
        cfg["playlist_reverse"] = bool(playlist_reverse)
        cfg["playlist_order_mode"] = str(playlist_order_mode)
        if playlist_items:
            cfg["playlist_items"] = playlist_items
        else:
            cfg.pop("playlist_items", None)
        download_folder = self.path_display.text().strip() or os.path.join(os.path.expanduser("~"), "Downloads")
        self.download_thread = DownloadThread(url, download_folder, cfg)
        self.download_thread.progress.connect(self.update_progress)
        self.download_thread.detail.connect(self.update_progress_detail)
        self.download_thread.finished.connect(self.done)
        self.download_thread.finished.connect(self.on_download_thread_finished)
        self.download_thread.start()
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_detail_enabled = True
        self.progress_detail_label.setVisible(True)

    def update_progress(self, pct: int):
        try:
            self.btn_dl.setText(f"ダウンロード中... {pct}%")
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(pct)
        except Exception:
            pass

    def update_progress_detail(self, text: str):
        if not hasattr(self, "progress_detail_label"):
            return
        if text:
            self.progress_detail_label.setText(text)

    def cancel_download(self):
        if self.download_thread is None:
            return
        try:
            self.download_thread._stopped = True
            if hasattr(self.download_thread, 'process') and self.download_thread.process:
                self.download_thread.process.terminate()
            self.btn_dl.setText("キャンセル中...")
            self.btn_update_ytdlp.setEnabled(True)
            self.progress_bar.setVisible(False)
        except Exception:
            pass

    def done(self, msg):
        self.btn_dl.setEnabled(True)
        self.btn_dl.setText("ダウンロードを開始")
        self.btn_update_ytdlp.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.progress_bar.setValue(0)
        if hasattr(self, "progress_detail_label"):
            self.progress_detail_label.setText("")
        self.progress_detail_enabled = True
        self._show_info("通知", msg)

    def on_download_thread_finished(self):
        if self.download_thread is None:
            return
        if self.download_thread.isRunning():
            self.download_thread.wait(3000)
        self.download_thread = None
        self.progress_detail_enabled = True

    def _stop_thread(self, thread, terminate_process: bool = False, wait_ms: int = 5000) -> bool:
        if thread is None:
            return True
        try:
            if not thread.isRunning():
                return True
        except Exception:
            return True

        try:
            thread.requestInterruption()
        except Exception:
            pass
        if terminate_process:
            try:
                if hasattr(thread, "process") and thread.process:
                    thread.process.terminate()
            except Exception:
                pass
        try:
            thread.quit()
        except Exception:
            pass
        try:
            return thread.wait(wait_ms)
        except Exception:
            return False

    def closeEvent(self, event):
        ok_download = self._stop_thread(self.download_thread, terminate_process=True, wait_ms=7000)
        ok_updater = self._stop_thread(self.updater, wait_ms=4000)
        ok_startup = self._stop_thread(self.startup_updater, wait_ms=4000)
        ok_app = self._stop_thread(self.app_updater, wait_ms=4000)

        if not (ok_download and ok_updater and ok_startup and ok_app):
            self._show_warning("終了待機", "バックグラウンド処理の終了待機中です。少し待ってから再度閉じてください。")
            event.ignore()
            return
        event.accept()

    def _handle_theme_error(self, phase: str, error: Exception):
        try:
            write_ini_log(
                "theme_error",
                {
                    "phase": phase,
                    "error": repr(error),
                    "theme": self.cfg.get("theme", "dark"),
                },
                prefix="theme_error",
            )
        except Exception:
            pass
        self.is_animating = False
        self.btn_theme.setEnabled(True)
        self.apply_style()

    def toggle_theme(self):
        """テーマを切り替える（アニメーション付き）"""
        # アニメーション中なら処理をスキップ
        if self.is_animating:
            return
        try:
            self.setWindowOpacity(1.0)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        except Exception:
            pass
        
        # アニメーション中フラグを設定
        self.is_animating = True
        self.btn_theme.setEnabled(False)
        
        current_theme = str(self.cfg.get("theme", "dark"))
        if current_theme.endswith("_dark"):
            base = current_theme.rsplit("_", 1)[0]
            new_theme = f"{base}_light"
        elif current_theme.endswith("_light"):
            base = current_theme.rsplit("_", 1)[0]
            new_theme = f"{base}_dark"
        elif current_theme == "dark":
            new_theme = "light"
        elif current_theme == "light":
            new_theme = "dark"
        else:
            new_theme = "light"
        # テーマを確定してからカードだけ軽く動かす（色の混在を防止）
        self.finalize_theme(new_theme, keep_animating=True)
        self._start_theme_card_anim()

    def _start_theme_card_anim(self):
        try:
            rect = self.card.geometry()
        except Exception:
            self._end_theme_card_anim()
            return
        shrink = QRect(rect.x() + 4, rect.y() + 4, max(0, rect.width() - 8), max(0, rect.height() - 8))
        self.theme_anim = QPropertyAnimation(self.card, b"geometry")
        self.theme_anim.setDuration(180)
        self.theme_anim.setStartValue(shrink)
        self.theme_anim.setEndValue(rect)
        self.theme_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self.theme_anim.finished.connect(self._end_theme_card_anim)
        self.theme_anim.start()

    def _end_theme_card_anim(self):
        self.is_animating = False
        self.btn_theme.setEnabled(True)

    def _on_theme_anim_value_changed(self, value, new_theme):
        try:
            try:
                self.setWindowOpacity(1.0)
                self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            except Exception:
                pass
            self.update_theme_color(float(value), new_theme)
        except Exception as e:
            self._handle_theme_error("valueChanged", e)

    def _on_theme_anim_finished(self, new_theme):
        try:
            self.finalize_theme(new_theme)
        except Exception as e:
            self._handle_theme_error("finished", e)

    def update_theme_color(self, progress, new_theme):
        """背景色をアニメーションで更新"""
        # テーマの色定義
        dark_colors = {
            "bg": "#000000",
            "card": "#1c1c1e",
            "label": "#8e8e93",
            "title": "#ffffff",
            "input_bg": "#2c2c2e",
            "input_text": "#ffffff",
            "input_border": "#3a3a3c",
            "btn_bg": "#3a3a3c",
            "btn_text": "#ffffff",
        }
        
        light_colors = {
            "bg": "#ffffff",
            "card": "#f5f5f7",
            "label": "#333333",
            "title": "#000000",
            "input_bg": "#ffffff",
            "input_text": "#000000",
            "input_border": "#d5d5d7",
            "btn_bg": "#e8e8ea",
            "btn_text": "#000000",
        }

        neon_light_colors = {
            "bg": "#f3f3f3",
            "card": "#ffffff",
            "label": "#1f1f1f",
            "title": "#1f1f1f",
            "input_bg": "#ffffff",
            "input_text": "#1f1f1f",
            "input_border": "#bdbdbd",
            "btn_bg": "#e7e7e7",
            "btn_text": "#1f1f1f",
        }

        neon_dark_colors = {
            "bg": "#1f1f1f",
            "card": "#2b2b2b",
            "label": "#d6d6d6",
            "title": "#ffffff",
            "input_bg": "#2b2b2b",
            "input_text": "#ffffff",
            "input_border": "#3a3a3a",
            "btn_bg": "#3a3a3a",
            "btn_text": "#ffffff",
        }

        theme_props = {
            "dark": {
                "primary_btn": "#0a84ff",
                "primary_btn_hover": "#409cff",
                "focus_border": "#0a84ff",
                "status_green": "#34c759",
                "card_radius": 24,
                "input_radius": 10,
                "btn_radius": 10,
                "label_size": 11,
                "label_weight": 700,
                "title_size": 24,
                "title_weight": 200,
                "input_padding": "8px 12px 8px 12px",
                "button_padding": "10px",
            },
            "light": {
                "primary_btn": "#0a84ff",
                "primary_btn_hover": "#409cff",
                "focus_border": "#0a84ff",
                "status_green": "#34c759",
                "card_radius": 24,
                "input_radius": 10,
                "btn_radius": 10,
                "label_size": 11,
                "label_weight": 700,
                "title_size": 24,
                "title_weight": 200,
                "input_padding": "8px 12px 8px 12px",
                "button_padding": "10px",
            },
            "neon_light": {
                "primary_btn": "#0078d4",
                "primary_btn_hover": "#1a86d9",
                "focus_border": "#5e9bff",
                "status_green": "#1a7f37",
                "card_radius": 16,
                "input_radius": 6,
                "btn_radius": 6,
                "label_size": 11,
                "label_weight": 700,
                "title_size": 22,
                "title_weight": 600,
                "input_padding": "8px 12px 8px 12px",
                "button_padding": "10px",
            },
            "neon_dark": {
                "primary_btn": "#0078d4",
                "primary_btn_hover": "#1a86d9",
                "focus_border": "#60a5ff",
                "status_green": "#22c55e",
                "card_radius": 16,
                "input_radius": 6,
                "btn_radius": 6,
                "label_size": 11,
                "label_weight": 700,
                "title_size": 22,
                "title_weight": 600,
                "input_padding": "8px 12px 8px 12px",
                "button_padding": "10px",
            },
        }

        theme_colors = {
            "dark": dark_colors,
            "light": light_colors,
            "neon_light": neon_light_colors,
            "neon_dark": neon_dark_colors,
        }

        # 現在のテーマと目標のテーマから、元の色と目標の色を決定
        start_theme = getattr(self, "_theme_anim_from", None) or self.cfg.get("theme", "dark")
        end_theme = getattr(self, "_theme_anim_to", None) or new_theme
        start_colors = theme_colors.get(start_theme, dark_colors).copy()
        end_colors = theme_colors.get(end_theme, light_colors).copy()

        # JSON優先でテーマ情報を取得
        json_start_colors, json_start_props = load_theme_profile(start_theme)
        json_end_colors, json_end_props = load_theme_profile(end_theme)

        for key in ("bg", "card", "label", "title", "input_bg", "input_text", "input_border", "btn_bg", "btn_text"):
            if key in json_start_colors:
                start_colors[key] = json_start_colors[key]
            if key in json_end_colors:
                end_colors[key] = json_end_colors[key]

        # JSONが無い場合はCSSのMETADATAをフォールバック
        if not json_start_colors:
            meta_start = parse_theme_metadata(start_theme)
            for key in ("bg", "card", "label", "title", "input_bg", "input_text", "input_border", "btn_bg", "btn_text"):
                if key in meta_start:
                    start_colors[key] = meta_start[key]
        if not json_end_colors:
            meta_end = parse_theme_metadata(end_theme)
            for key in ("bg", "card", "label", "title", "input_bg", "input_text", "input_border", "btn_bg", "btn_text"):
                if key in meta_end:
                    end_colors[key] = meta_end[key]
        start_props = theme_props.get(start_theme, theme_props["dark"]).copy()
        end_props = theme_props.get(end_theme, theme_props["light"]).copy()
        if json_start_props:
            start_props.update(json_start_props)
        if json_end_props:
            end_props.update(json_end_props)
        
        # 進度に応じて色を補間
        bg_color = lerp_color(start_colors["bg"], end_colors["bg"], progress)
        card_color = lerp_color(start_colors["card"], end_colors["card"], progress)
        label_color = lerp_color(start_colors["label"], end_colors["label"], progress)
        title_color = lerp_color(start_colors["title"], end_colors["title"], progress)
        input_bg = lerp_color(start_colors["input_bg"], end_colors["input_bg"], progress)
        input_text = lerp_color(start_colors["input_text"], end_colors["input_text"], progress)
        input_border = lerp_color(start_colors["input_border"], end_colors["input_border"], progress)
        btn_bg = lerp_color(start_colors["btn_bg"], end_colors["btn_bg"], progress)
        btn_text = lerp_color(start_colors["btn_text"], end_colors["btn_text"], progress)
        
        # テーマ固有プロパティも補間
        primary_btn = lerp_color(start_props["primary_btn"], end_props["primary_btn"], progress)
        primary_btn_hover = lerp_color(start_props["primary_btn_hover"], end_props["primary_btn_hover"], progress)
        focus_border = lerp_color(start_props["focus_border"], end_props["focus_border"], progress)
        status_green = lerp_color(start_props["status_green"], end_props["status_green"], progress)
        card_radius = int(round(start_props["card_radius"] + (end_props["card_radius"] - start_props["card_radius"]) * progress))
        input_radius = int(round(start_props["input_radius"] + (end_props["input_radius"] - start_props["input_radius"]) * progress))
        btn_radius = int(round(start_props["btn_radius"] + (end_props["btn_radius"] - start_props["btn_radius"]) * progress))
        label_size = end_props["label_size"]
        label_weight = end_props["label_weight"]
        title_size = end_props["title_size"]
        title_weight = end_props["title_weight"]
        input_padding = end_props["input_padding"]
        button_padding = end_props["button_padding"]

        # 完全なスタイルシートを適用
        stylesheet = f"""
            QWidget#Main {{ background-color: {bg_color}; }}
            QFrame#Card {{ background-color: {card_color}; border-radius: {card_radius}px; border: 1px solid {input_border}; }}
            QLabel {{ color: {label_color}; font-size: {label_size}px; font-weight: {label_weight}; margin: 0px; margin-left: 2px; }}
            QLabel#Title {{ color: {title_color}; font-size: {title_size}px; font-weight: {title_weight}; margin-left: 0px; }}
            QLineEdit, QComboBox {{ border: 1px solid {input_border}; border-bottom: 2px solid {input_border}; padding: {input_padding}; border-radius: {input_radius}px; background: {input_bg}; background-clip: padding; color: {input_text}; font-size: 14px; }}
            QLineEdit#PathDisplay {{ color: {input_text}; font-size: 15px; font-weight: 500; }}
            QLineEdit:focus, QComboBox:focus {{ border: 1px solid {input_border}; border-bottom: 2px solid {focus_border}; }}
            QComboBox::drop-down {{ border: none; width: 22px; }}
            QPushButton {{ background-color: {primary_btn}; color: white; border-radius: {btn_radius}px; padding: {button_padding}; font-size: 14px; font-weight: 600; border: none; }}
            QPushButton:hover {{ background-color: {primary_btn_hover}; }}
            QPushButton#SecondaryBtn {{ background-color: {btn_bg}; color: {btn_text}; font-size: 13px; font-weight: normal; }}
            QLabel#YtDlpStatusLabel {{ color: {status_green}; font-size: 12px; font-weight: 600; margin-right: 4px; }}
            QLabel#AppStatusLabel {{ color: {status_green}; font-size: 12px; font-weight: 600; margin-right: 4px; }}
            #SettingsBtn {{ background: transparent; color: {btn_text}; font-size: 13px; }}
            #ThemeBtn {{ background-color: {btn_bg}; color: {btn_text}; font-weight: normal; }}
            QProgressBar {{
                border: none;
                background-color: {input_bg};
                border-radius: 4px;
                text-align: center;
                color: {title_color};
                font-size: 11px;
                font-weight: 600;
            }}
            QProgressBar::chunk {{
                border-radius: 4px;
                background: {primary_btn};
            }}
        """
        self.setStyleSheet(stylesheet)

    def finalize_theme(self, new_theme, keep_animating: bool = False):
        """テーマを確定"""
        self.cfg["theme"] = new_theme
        save_config(self.cfg)
        
        # ボタンテキストを更新
        self.btn_theme.setText(self.theme_button_text(new_theme))
        
        # 完全なスタイルを再適用
        self.apply_style()
        self.apply_language_texts()
        try:
            self.setWindowOpacity(1.0)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            self._apply_startup_palette()
        except Exception:
            pass
        
        # アニメーション中フラグを解除
        if not keep_animating:
            self.is_animating = False
            self.btn_theme.setEnabled(True)

if __name__ == "__main__":
    qInstallMessageHandler(qt_message_filter)
    app = QApplication(sys.argv)
    try:
        startup_cfg = load_config()
        startup_theme = str(startup_cfg.get("theme", "dark"))
        warm_theme_cache(startup_theme)
        apply_app_theme(app, startup_theme)
    except Exception:
        pass
    icon_path = resolve_app_icon_path()
    if icon_path:
        app.setWindowIcon(QIcon(str(icon_path)))
    w = Main()
    w.show()
    sys.exit(app.exec())
