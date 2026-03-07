import sys
import subprocess
import re
import json
import os
import shutil
import time
import urllib.request
import urllib.error
import urllib.parse
import ssl
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import *
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRect, QPropertyAnimation, QEasingCurve, QTimer, QUrl, qInstallMessageHandler
from PyQt6.QtGui import QFont, QIcon, QDesktopServices

VERSION = "1.2.1"
CONFIG_DIR_NAME = "SagamiYoutubeDownloader"
APP_GITHUB_REPO_URL = "https://github.com/sagami121/Sagami-Youtube-Downloader"
APP_DISPLAY_NAME = "Sagami youtube Downloader"

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

def get_stylesheet(theme="dark", widget_type="main"):
    """テーマに応じたスタイルシートを返す"""
    if theme == "light":
        if widget_type == "main":
            return """
            QWidget#Main { background-color: #ffffff; }
            QFrame#Card { background-color: #f5f5f7; border-radius: 24px; border: 1px solid #d5d5d7; }
            QLabel { color: #333333; font-size: 11px; font-weight: bold; margin: 0px; margin-left: 2px; }
            QLabel#Title { color: #000000; font-size: 24px; font-weight: 200; margin-left: 0px; }
            QLineEdit, QComboBox { border: 1px solid #d5d5d7; padding: 10px 12px; border-radius: 10px; background: #ffffff; color: #000000; font-size: 14px; }
            QLineEdit#PathDisplay { color: #111111; font-size: 15px; font-weight: 500; }
            QLineEdit:focus, QComboBox:focus { border: 1px solid #d5d5d7; border-bottom: 2px solid #0a84ff; }
            QComboBox::drop-down { border: none; width: 22px; }
            QPushButton { background-color: #0a84ff; color: white; border-radius: 10px; padding: 10px; font-size: 14px; font-weight: 600; border: none; }
            QPushButton:hover { background-color: #409cff; }
            QPushButton#SecondaryBtn { background-color: #e8e8ea; color: #000000; font-size: 13px; font-weight: normal; }
            QLabel#YtDlpStatusLabel { color: #34c759; font-size: 12px; font-weight: 600; margin-right: 4px; }
            QLabel#AppStatusLabel { color: #34c759; font-size: 12px; font-weight: 600; margin-right: 4px; }
            #SettingsBtn { background: transparent; color: #000000; font-size: 13px; }
            #ThemeBtn { background-color: #e8e8ea; color: #000000; font-weight: normal; }
            QProgressBar {
                border: none;
                background-color: #e8e8ea;
                border-radius: 4px;
                text-align: center;
                color: #333333;
                font-size: 11px;
                font-weight: 600;
            }
            QProgressBar::chunk {
                border-radius: 4px;
                background: #0a84ff;
            }
            """
        else:  # settings
            return """
            QDialog { background: #ffffff; }
            QLabel { color: #333333; font-size: 13px; font-weight: bold; }
            QCheckBox { color: #333333; font-size: 13px; }
            QLineEdit { border: 1px solid #d5d5d7; padding: 10px 12px; border-radius: 10px; background: #ffffff; color: #000000; font-family: 'Consolas'; font-size: 14px; }
            QLineEdit:focus { border: 1px solid #d5d5d7; border-bottom: 2px solid #0a84ff; }
            QPushButton { background-color: #e8e8ea; color: #000000; border-radius: 10px; border: none; font-size: 13px; padding: 2px; }
            QPushButton:hover { background-color: #d5d5d7; }
            QPushButton:checked { background-color: #0a84ff; color: white; border: none; font-weight: bold; }
            #ClearBtn { color: #ff3b30; }
            #SaveBtn { background-color: #0a84ff; color: white; font-weight: bold; font-size: 15px; border: none; }
            """
    else:  # dark
        if widget_type == "main":
            return """
            QWidget#Main { background-color: #000000; }
            QFrame#Card { background-color: #1c1c1e; border-radius: 24px; border: 1px solid #2c2c2e; }
            QLabel { color: #8e8e93; font-size: 11px; font-weight: bold; margin: 0px; margin-left: 2px; }
            QLabel#Title { color: #ffffff; font-size: 24px; font-weight: 200; margin-left: 0px; }
            QLineEdit, QComboBox { border: 1px solid #3a3a3c; padding: 10px 12px; border-radius: 10px; background: #2c2c2e; color: #ffffff; font-size: 14px; }
            QLineEdit#PathDisplay { color: #f2f2f7; font-size: 15px; font-weight: 500; }
            QLineEdit:focus, QComboBox:focus { border: 1px solid #3a3a3c; border-bottom: 2px solid #0a84ff; }
            QComboBox::drop-down { border: none; width: 22px; }
            QPushButton { background-color: #0a84ff; color: white; border-radius: 10px; padding: 10px; font-size: 14px; font-weight: 600; border: none; }
            QPushButton:hover { background-color: #409cff; }
            QPushButton#SecondaryBtn { background-color: #3a3a3c; font-size: 13px; font-weight: normal; }
            QLabel#AppStatusLabel { color: #34c759; font-size: 12px; font-weight: 600; margin-right: 4px; }
            #SettingsBtn { background: transparent; color: #ffffff; font-size: 13px; }
            #ThemeBtn { background-color: #3a3a3c; color: #ffffff; font-weight: normal; }
            QProgressBar {
                border: none;
                background-color: #2c2c2e;
                border-radius: 4px;
                text-align: center;
                color: #ffffff;
                font-size: 11px;
                font-weight: 600;
            }
            QProgressBar::chunk {
                border-radius: 4px;
                background: #0a84ff;
            }
            """
        else:  # settings
            return """
            QDialog { background: #1c1c1e; }
            QLabel { color: #ffffff; font-size: 13px; font-weight: bold; }
            QCheckBox { color: #ffffff; font-size: 13px; }
            QLineEdit { border: 1px solid #3a3a3c; padding: 10px 12px; border-radius: 10px; background: #2c2c2e; color: #0a84ff; font-family: 'Consolas'; font-size: 14px; }
            QLineEdit:focus { border: 1px solid #3a3a3c; border-bottom: 2px solid #0a84ff; }
            QPushButton { background-color: #2c2c2e; color: white; border-radius: 10px; border: 1px solid #3a3a3c; font-size: 13px; padding: 2px; }
            QPushButton:hover { background-color: #3a3a3c; }
            QPushButton:checked { background-color: #0a84ff; border: none; font-weight: bold; }
            #ClearBtn { color: #ff453a; }
            #SaveBtn { background-color: #0a84ff; font-weight: bold; font-size: 15px; border: none; }
            """

def lerp_color(start_color, end_color, progress):
    """16進数カラーコードを線形補間"""
    # 16進数から RGB に解析
    start_rgb = tuple(int(start_color[i:i+2], 16) for i in (1, 3, 5))
    end_rgb = tuple(int(end_color[i:i+2], 16) for i in (1, 3, 5))
    
    # 補間
    interpolated = tuple(int(s + (e - s) * progress) for s, e in zip(start_rgb, end_rgb))
    
    # RGB から16進数文字列に変換
    return '#{:02x}{:02x}{:02x}'.format(*interpolated)

def get_config_path() -> Path:
    if getattr(sys, 'frozen', False):
        # EXEとして実行されている場合はユーザー領域に保存
        base_dir = Path(os.getenv("APPDATA") or (Path.home() / "AppData" / "Roaming"))
        cfg_dir = base_dir / CONFIG_DIR_NAME
        cfg_dir.mkdir(parents=True, exist_ok=True)
        return cfg_dir / "config.json"
    else:
        # Pythonスクリプトとして実行されている場合
        app_dir = Path(__file__).parent
    
    return app_dir / "config.json"

def resolve_yt_dlp_command():
    app_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    candidates = [app_dir / "yt-dlp.exe", app_dir / "yt-dlp"]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return [str(candidate)]
    if shutil.which("yt-dlp"):
        return ["yt-dlp"]
    return None

def resolve_aria2c_command():
    app_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    candidates = [app_dir / "aria2c.exe", app_dir / "aria2c"]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    return shutil.which("aria2c")

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
        app_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
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
            return cfg
    except (FileNotFoundError, json.JSONDecodeError):
        defaults = {
            "format": "mp4",
            "template": "%(title)s",
            "path": default_path,
            "theme": "dark",
            "embed_thumbnail": False,
            "video_quality": "Best",
            "video_fps": "Any",
            "audio_quality": "0",
            "time_range_input": "",
            "app_update_source_url": "",
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
    app_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    logs_dir = app_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = logs_dir / f"{prefix}_{ts}.txt"

    lines = [f"[{section}]"]
    for key, value in values.items():
        text = str(value).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")
        lines.append(f"{key}={text}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)

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

        args = yt_cmd + [
            self.url, "-P", self.folder, "-o", f"{template}.%(ext)s",
            "--newline",
            "--progress-template", "download:%(progress._percent_str)s"
        ]

        out_format = self.cfg.get("format", "mp4")
        if out_format == "mp3":
            # MP3は指定音質で抽出
            audio_quality = str(self.cfg.get("audio_quality", "0")).strip()
            if not re.fullmatch(r"\d+(?:\.\d+)?", audio_quality):
                audio_quality = "0"
            args += ["-x", "--audio-format", "mp3", "--audio-quality", audio_quality]
        elif out_format == "wav":
            # WAVは再エンコード時の品質指定を使わず抽出
            args += ["-x", "--audio-format", "wav"]
        elif out_format == "m4a":
            # M4Aは可能な限り再エンコードせず抽出
            args += ["-x", "--audio-format", "m4a"]
        else:
            quality = self.cfg.get("video_quality", "Best")
            fps = self.cfg.get("video_fps", "Any")

            video_selector = "bv*[ext=mp4]"
            if quality and quality != "Best":
                h = quality.replace("p", "")
                if h.isdigit():
                    video_selector += f"[height<={h}]"
            if fps and fps != "Any" and str(fps).isdigit():
                video_selector += f"[fps<={fps}]"

            format_selector = f"{video_selector}+ba[ext=m4a]/{video_selector}+ba/{video_selector}/b[ext=mp4]/b"

            args += ["-f", format_selector,
                     "--merge-output-format", "mp4"]
            
            # MP4の場合、サムネイル埋め込みオプションを追加
            if self.cfg.get("embed_thumbnail", False):
                args += ["--write-thumbnail", "--embed-thumbnail"]

        start_sec = self.cfg.get("time_range_start")
        end_sec = self.cfg.get("time_range_end")
        if start_sec is not None and end_sec is not None:
            args += ["--download-sections", f"*{start_sec}-{end_sec}", "--force-keyframes-at-cuts"]

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

            if process.returncode != 0 and self._is_pypi_update_hint(output):
                pip_ok, pip_output = self._run_pip_update()
                output = (output or "") + "\n\n[pip fallback]\n" + (pip_output or "")
                if pip_ok:
                    process_returncode = 0
                else:
                    process_returncode = process.returncode
            else:
                process_returncode = process.returncode

            after_version = self._get_version(yt_cmd)
            if process_returncode == 0:
                state = "updated"
                if before_version != "不明" and after_version != "不明" and before_version == after_version:
                    state = "up_to_date"
                self.finished.emit(True, state, before_version, after_version, output or "更新チェックが完了しました。")
            else:
                self.finished.emit(False, "failed", before_version, after_version, output or "yt-dlp の更新に失敗しました。")
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

    def _is_known_update_host(self, url: str) -> bool:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
        trusted_suffixes = (
            "github.com",
            "githubusercontent.com",
            "githubassets.com",
        )
        return any(host == suffix or host.endswith("." + suffix) for suffix in trusted_suffixes)

    def _urlopen_with_ssl_fallback(self, req, url: str, timeout: int = 10):
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except ssl.SSLCertVerificationError as first_error:
            certifi_ctx = None
            try:
                import certifi
                certifi_ctx = ssl.create_default_context(cafile=certifi.where())
            except Exception:
                certifi_ctx = None

            if certifi_ctx is not None:
                try:
                    return urllib.request.urlopen(req, timeout=timeout, context=certifi_ctx)
                except ssl.SSLCertVerificationError:
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

    def _load_release(self):
        if not self.source_url:
            raise ValueError("更新元URLが未設定です。")

        # 1) GitHub Releases がある場合はこちらを優先
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
        self.setWindowTitle("出力設定")
        self.setFixedSize(420, 560)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        self.cfg = load_config()
        
        # ダイアログを親ウィンドウの中央に配置するように設定
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)

        layout.addWidget(QLabel("保存ファイル名の構成を選択してください"))
        
        layout.addWidget(QLabel("出力形式"))
        self.format_combo = QComboBox()
        self.format_combo.addItem("Video (mp4)", "mp4")
        self.format_combo.addItem("Audio (mp3)", "mp3")
        self.format_combo.addItem("Audio (wav)", "wav")
        self.format_combo.addItem("Audio (m4a)", "m4a")
        self.format_combo.setMinimumHeight(45)
        fmt_idx = self.format_combo.findData(str(self.cfg.get("format", "mp4")))
        self.format_combo.setCurrentIndex(fmt_idx if fmt_idx >= 0 else 0)
        layout.addWidget(self.format_combo)

        # サムネイル埋め込み設定
        layout.addWidget(QLabel("その他の設定"))
        thumbnail_layout = QHBoxLayout()
        self.chk_thumbnail = QCheckBox("MP4に動画のサムネイルを埋め込む")
        self.chk_thumbnail.setChecked(self.cfg.get("embed_thumbnail", False))
        thumbnail_layout.addWidget(self.chk_thumbnail)
        layout.addLayout(thumbnail_layout)

        layout.addWidget(QLabel("現在のファイル名構成"))
        self.template_display = QLineEdit()
        self.template_display.setText(self.cfg.get("template", "%(title)s"))
        layout.addWidget(self.template_display)

        layout.addWidget(QLabel("ファイル名の設定"))
        tag_layout = QGridLayout()
        tag_layout.setContentsMargins(0, 0, 0, 0)
        tag_layout.setHorizontalSpacing(14)
        tag_layout.setVerticalSpacing(10)
        tags = [
            ("タイトル", "%(title)s"), ("動画ID", "[%(id)s]"), 
            ("投稿者", "[%(uploader)s]"), ("投稿日", "[%(upload_date)s]"),
            ("画質", "[%(height)sp]"), ("クリア", "clear")
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
        layout.addLayout(tag_layout)

        layout.addSpacing(10)
        save_btn = QPushButton("設定を保存")
        save_btn.setObjectName("SaveBtn")
        save_btn.setMinimumHeight(50)
        save_btn.clicked.connect(self.save)
        layout.addWidget(save_btn)
        
        # バージョン情報
        layout.addSpacing(15)
        version_label = QLabel(f"Version: {VERSION}")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setStyleSheet("color: #8e8e93; font-size: 10px;")
        layout.addWidget(version_label)
        
        self.apply_style()

    def apply_style(self):
        self.setStyleSheet(get_stylesheet(self.parent_win.cfg.get("theme", "dark"), "settings"))

    def add_tag(self, code):
        current = self.template_display.text()
        new_text = (current + " " + code) if current else code
        self.template_display.setText(new_text)

    def save(self):
        self.cfg["format"] = self.format_combo.currentData() or "mp4"
        self.cfg["template"] = self.template_display.text() or "%(title)s"
        self.cfg["path"] = self.parent_win.path_display.text()
        self.cfg["embed_thumbnail"] = self.chk_thumbnail.isChecked()
        save_config(self.cfg)
        self.accept()


class LogViewerDialog(QDialog):
    def __init__(self, parent, logs_dir: Path):
        super().__init__(parent)
        self.logs_dir = logs_dir
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


class Main(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("Main")
        self.setWindowTitle("Sagami Youtube Downloader")
        self.resize(920, 700)
        self.setMinimumSize(720, 600)
        self.cfg = load_config()
        self.is_animating = False  # アニメーション中かどうかを追跡

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # テーマ切り替えボタンを一番上に配置
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(20, 10, 20, 10)
        top_bar.addStretch()
        self.btn_theme = QPushButton("ダークモード" if self.cfg.get("theme", "dark") == "dark" else "ライトモード")
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
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 26, 28, 24)
        card_layout.setSpacing(5)

        title = QLabel("Sagami YouTube Downloader")
        title.setObjectName("Title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title)

        # URL入力
        card_layout.addWidget(QLabel("動画URL"))
        url_layout = QHBoxLayout()
        url_layout.setSpacing(8)
        self.url = FocusClearLineEdit()
        self.url.setPlaceholderText("ここにリンクを貼り付け...")
        self.url.setFixedHeight(40)
        self.btn_paste = QPushButton("ペースト")
        self.btn_paste.setFixedWidth(90)
        self.btn_paste.setMinimumHeight(38)
        self.btn_paste.setObjectName("SecondaryBtn")
        self.btn_paste.clicked.connect(self.paste_url)
        url_layout.addWidget(self.url)
        url_layout.addWidget(self.btn_paste)
        card_layout.addLayout(url_layout)

        card_layout.addWidget(QLabel("時間指定"))
        self.time_range = FocusClearLineEdit()
        self.time_range.setPlaceholderText("例: 0:00~0:15")
        self.time_range.setText(self.cfg.get("time_range_input", ""))
        self.time_range.setFixedHeight(40)
        card_layout.addWidget(self.time_range)

        # 保存先
        card_layout.addWidget(QLabel("保存先フォルダ"))
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
        self.btn_browse.clicked.connect(self.browse_folder)
        
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
        self.quality_combo.setCurrentText(self.cfg.get("video_quality", "Best"))

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

        self.quality_combo.currentTextChanged.connect(self.on_video_quality_changed)
        self.fps_combo.currentIndexChanged.connect(self.on_video_fps_changed)
        self.audio_quality_combo.currentIndexChanged.connect(self.on_audio_quality_changed)
        self.update_mp4_option_state()

        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(8)

        self.btn_dl = QPushButton("ダウンロードを開始")
        self.btn_dl.setMinimumHeight(46)
        self.btn_dl.clicked.connect(self.start)
        actions_layout.addWidget(self.btn_dl, 1)

        self.btn_update_ytdlp = QPushButton("yt-dlp を更新")
        self.btn_update_ytdlp.setObjectName("SecondaryBtn")
        self.btn_update_ytdlp.setMinimumHeight(46)
        self.btn_update_ytdlp.clicked.connect(self.update_ytdlp)
        self.btn_update_ytdlp.setVisible(False)

        self.btn_check_app_update = QPushButton("アプリ更新を確認")
        self.btn_check_app_update.setObjectName("SecondaryBtn")
        self.btn_check_app_update.setMinimumHeight(46)
        self.btn_check_app_update.clicked.connect(self.check_app_update_manually)
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

        # 進捗バー
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(18)
        card_layout.addWidget(self.progress_bar)

        # 詳細設定
        foot_actions = QHBoxLayout()
        foot_actions.addStretch()
        self.btn_settings = QPushButton("詳細設定")
        self.btn_settings.setObjectName("SettingsBtn")
        self.btn_settings.clicked.connect(self.open_settings)
        foot_actions.addWidget(self.btn_settings)
        foot_actions.addStretch()
        card_layout.addLayout(foot_actions)

        center_layout.addWidget(card)
        center_layout.addStretch()
        main_layout.addLayout(center_layout)
        main_layout.addStretch()

        self.apply_style()
        QTimer.singleShot(700, self.check_app_update_on_startup)
        QTimer.singleShot(1200, self.check_ytdlp_on_startup)

    def apply_style(self):
        self.setStyleSheet(get_stylesheet(self.cfg.get("theme", "dark"), "main"))

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
        dlg = Settings(self)
        if dlg.exec():
            self.cfg = load_config()
            self.update_mp4_option_state()

    def paste_url(self):
        self.url.setText(QApplication.clipboard().text())

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
        self.media_quality_label.setText("画質設定" if is_mp4 else "音質設定")

        self.quality_combo.setVisible(is_mp4)
        self.fps_combo.setVisible(is_mp4)
        self.quality_combo.setEnabled(is_mp4)
        self.fps_combo.setEnabled(is_mp4)

        self.audio_quality_combo.setVisible(not is_mp4)
        self.audio_quality_combo.setEnabled(not is_mp4)

        if is_mp4:
            self.quality_combo.setCurrentText(self.cfg.get("video_quality", "Best"))
            fps_idx = self.fps_combo.findData(str(self.cfg.get("video_fps", "Any")))
            self.fps_combo.setCurrentIndex(fps_idx if fps_idx >= 0 else 0)
        else:
            aq_idx = self.audio_quality_combo.findData(str(self.cfg.get("audio_quality", "0")))
            self.audio_quality_combo.setCurrentIndex(aq_idx if aq_idx >= 0 else 0)

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
        if hasattr(self, "updater") and self.updater.isRunning():
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
            self.set_ytdlp_status("不明", "failed")
            return
        if hasattr(self, "startup_updater") and self.startup_updater.isRunning():
            return

        self.ytdlp_status_label.setText("yt-dlp - 確認中...")
        self.startup_updater = YtDlpUpdateThread()
        self.startup_updater.finished.connect(self.on_startup_ytdlp_updated)
        self.startup_updater.start()

    def check_app_update_on_startup(self):
        self.start_app_update_check(interactive=True, suppress_latest_popup=True)

    def check_app_update_manually(self):
        self.start_app_update_check(interactive=True, suppress_latest_popup=False)

    def start_app_update_check(self, interactive: bool, suppress_latest_popup: bool = False):
        if hasattr(self, "app_updater") and self.app_updater.isRunning():
            return

        source_url = str(self.cfg.get("app_update_source_url", "") or APP_GITHUB_REPO_URL).strip()
        if not source_url:
            self.app_status_label.setText(f"{APP_DISPLAY_NAME} - {VERSION} 更新元URL未設定")
            if interactive:
                self._show_info("アプリ更新", "GitHubリポジトリURLが未設定です。\nconfig.json の app_update_source_url にURLを設定してください。")
            return

        self.btn_check_app_update.setEnabled(False)
        self.btn_check_app_update.setText("確認中...")
        self.app_status_label.setText(f"{APP_DISPLAY_NAME} - {VERSION} 確認中...")
        self.app_updater = AppUpdateThread(source_url)
        self.app_updater.finished.connect(
            lambda ok, state, current, latest, page_url, notes, published_at, installer_url:
            self.on_app_update_finished(ok, state, current, latest, page_url, notes, published_at, installer_url, interactive, suppress_latest_popup)
        )
        self.app_updater.start()

    def _launch_background_update(self, installer_url: str, release_page_url: str):
        app_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
        updater_exe_path = app_dir / "Sagami Youtube Updater.exe"
        updater_path = app_dir / "update.py"

        try:
            launch_path = sys.executable if getattr(sys, "frozen", False) else str((app_dir / "main.py").resolve())
            if getattr(sys, "frozen", False):
                if not updater_exe_path.exists():
                    self._show_warning("更新", f"Updater が見つかりません: {updater_exe_path}")
                    if release_page_url:
                        QDesktopServices.openUrl(QUrl(release_page_url))
                    return
                cmd = [
                    str(updater_exe_path),
                    "--installer-url", installer_url,
                    "--current-pid", str(os.getpid()),
                    "--launch-path", launch_path,
                ]
            else:
                if not updater_path.exists():
                    self._show_warning("更新", f"update.py が見つかりません: {updater_path}")
                    if release_page_url:
                        QDesktopServices.openUrl(QUrl(release_page_url))
                    return
                python_cmd = sys.executable
                cmd = [
                    python_cmd, str(updater_path),
                    "--installer-url", installer_url,
                    "--current-pid", str(os.getpid()),
                    "--launch-path", launch_path,
                ]

            subprocess.Popen(
                cmd,
                cwd=str(app_dir),
                creationflags=(subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS) if os.name == "nt" else 0
            )
            self._show_info("更新", "バックグラウンドで更新を開始しました。\nこのアプリは終了します。")
            QApplication.quit()
        except Exception as e:
            log_path = write_ini_log(
                "update_launch_error",
                {"error": repr(e), "installer_url": installer_url, "updater_path": str(updater_path)},
                prefix="update_launch_error",
            )
            self._show_warning("更新", f"自動更新の起動に失敗しました。\nログ: {log_path}")
            if release_page_url:
                QDesktopServices.openUrl(QUrl(release_page_url))

    def on_app_update_finished(self, ok: bool, state: str, current_version: str, latest_version: str, release_page_url: str, notes: str, published_at: str, installer_url: str, interactive: bool, suppress_latest_popup: bool):
        self.btn_check_app_update.setEnabled(True)
        self.btn_check_app_update.setText("アプリ更新を確認")
        version_display = latest_version or current_version

        if not ok:
            self.app_status_label.setText(f"{APP_DISPLAY_NAME} - {version_display} 確認失敗")
            if interactive:
                reason = (notes or "").strip() or "不明なエラー"
                self._show_warning("更新", f"更新確認に失敗しました。\n\n理由: {reason}")
            return

        if state == "update_available":
            self.app_status_label.setText(f"{APP_DISPLAY_NAME} - {current_version}→{latest_version} 更新あり")
            notes_text = notes or "更新内容は取得できませんでした。"
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setWindowTitle("更新")
            msg.setMinimumWidth(460)
            msg.setText(f"更新通知\nアプリ更新があります。\n現在: {current_version}\n最新: {latest_version}")
            msg.setInformativeText(f"更新内容:\n{notes_text}")
            self._apply_messagebox_theme(msg)
            auto_btn = None
            open_btn = None
            if installer_url:
                auto_btn = msg.addButton("自動更新", QMessageBox.ButtonRole.AcceptRole)
            if release_page_url:
                open_btn = msg.addButton("ページを開く", QMessageBox.ButtonRole.AcceptRole)
            msg.addButton("閉じる", QMessageBox.ButtonRole.RejectRole)
            msg.exec()
            clicked = msg.clickedButton()
            if auto_btn is not None and clicked == auto_btn:
                self._launch_background_update(installer_url, release_page_url)
            elif open_btn is not None and clicked == open_btn:
                QDesktopServices.openUrl(QUrl(release_page_url))
            return

        self.app_status_label.setText(f"{APP_DISPLAY_NAME} - {current_version} 最新版です")
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

        version = (version or "不明").strip()
        if state == "up_to_date":
            self.ytdlp_status_label.setText(f"yt-dlp - {version} 最新版です")
        elif state == "updated":
            self.ytdlp_status_label.setText(f"yt-dlp - {version} 更新しました")
        else:
            self.ytdlp_status_label.setText(f"yt-dlp - {version} 確認失敗")

        self.ytdlp_status_label.setVisible(True)
    def on_startup_ytdlp_updated(self, ok: bool, state: str, before_version: str, after_version: str, output: str):
        status_version = after_version if after_version != "不明" else before_version
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
        self.ytdlp_status_label.setText(f"yt-dlp - {status_version} 確認失敗 (ログ: {Path(log_path).name})")

    def on_ytdlp_updated(self, ok: bool, state: str, before_version: str, after_version: str, output: str):
        self.btn_update_ytdlp.setEnabled(True)
        self.btn_update_ytdlp.setText("yt-dlp を更新")
        body = tail_text(output)
        status_version = after_version if after_version != "不明" else before_version
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
        if hasattr(self, 't') and self.t.isRunning():
            self.cancel_download()
            return

        url = self.url.text().strip()
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
        download_folder = self.path_display.text().strip() or os.path.join(os.path.expanduser("~"), "Downloads")
        self.t = DownloadThread(url, download_folder, cfg)
        self.t.progress.connect(self.update_progress)
        self.t.finished.connect(self.done)
        self.t.start()
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

    def update_progress(self, pct: int):
        try:
            self.btn_dl.setText(f"ダウンロード中... {pct}%")
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(pct)
        except Exception:
            pass

    def cancel_download(self):
        if not hasattr(self, 't'):
            return
        try:
            self.t._stopped = True
            if hasattr(self.t, 'process') and self.t.process:
                self.t.process.terminate()
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
        self._show_info("通知", msg)

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
        
        # アニメーション中フラグを設定
        self.is_animating = True
        self.btn_theme.setEnabled(False)
        
        current_theme = self.cfg.get("theme", "dark")
        new_theme = "light" if current_theme == "dark" else "dark"
        
        # 既存のアニメーションがあれば停止
        if hasattr(self, 'theme_anim'):
            try:
                self.theme_anim.stop()
            except:
                pass
        
        # アニメーション用の値を0.0→1.0で変更
        self.theme_anim = QPropertyAnimation(self, b"animProgress")
        self.theme_anim.setDuration(600)
        self.theme_anim.setStartValue(0.0)
        self.theme_anim.setEndValue(1.0)
        self.theme_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.theme_anim.valueChanged.connect(lambda v: self._on_theme_anim_value_changed(v, new_theme))
        self.theme_anim.finished.connect(lambda: self._on_theme_anim_finished(new_theme))
        self.theme_anim.start()

    def _on_theme_anim_value_changed(self, value, new_theme):
        try:
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
        
        # 現在のテーマと目標のテーマから、元の色と目標の色を決定
        if new_theme == "light":
            # ダーク → ライト
            start_colors = dark_colors
            end_colors = light_colors
        else:
            # ライト → ダーク
            start_colors = light_colors
            end_colors = dark_colors
        
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
        
        # 完全なスタイルシートを適用
        stylesheet = f"""
            QWidget#Main {{ background-color: {bg_color}; }}
            QFrame#Card {{ background-color: {card_color}; border-radius: 24px; border: 1px solid {input_border}; }}
            QLabel {{ color: {label_color}; font-size: 11px; font-weight: bold; margin: 0px; margin-left: 2px; }}
            QLabel#Title {{ color: {title_color}; font-size: 24px; font-weight: 200; margin-left: 0px; }}
            QLineEdit, QComboBox {{ border: 1px solid {input_border}; padding: 10px 12px; border-radius: 10px; background: {input_bg}; color: {input_text}; font-size: 14px; }}
            QLineEdit#PathDisplay {{ color: {input_text}; font-size: 15px; font-weight: 500; }}
            QLineEdit:focus, QComboBox:focus {{ border: 1px solid {input_border}; border-bottom: 2px solid #0a84ff; }}
            QComboBox::drop-down {{ border: none; width: 22px; }}
            QPushButton {{ background-color: #0a84ff; color: white; border-radius: 10px; padding: 10px; font-size: 14px; font-weight: 600; border: none; }}
            QPushButton:hover {{ background-color: #409cff; }}
            QPushButton#SecondaryBtn {{ background-color: {btn_bg}; color: {btn_text}; font-size: 13px; font-weight: normal; }}
            QLabel#YtDlpStatusLabel {{ color: #34c759; font-size: 12px; font-weight: 600; margin-right: 4px; }}
            QLabel#AppStatusLabel {{ color: #34c759; font-size: 12px; font-weight: 600; margin-right: 4px; }}
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
                background: #0a84ff;
            }}
        """
        self.setStyleSheet(stylesheet)

    def finalize_theme(self, new_theme):
        """テーマを確定"""
        self.cfg["theme"] = new_theme
        save_config(self.cfg)
        
        # ボタンテキストを更新
        self.btn_theme.setText("ダークモード" if new_theme == "dark" else "ライトモード")
        
        # 完全なスタイルを再適用
        self.apply_style()
        
        # アニメーション中フラグを解除
        self.is_animating = False
        self.btn_theme.setEnabled(True)

if __name__ == "__main__":
    qInstallMessageHandler(qt_message_filter)
    app = QApplication(sys.argv)
    w = Main()
    w.show()
    sys.exit(app.exec())
