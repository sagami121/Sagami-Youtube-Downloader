import os
import re
import subprocess
import urllib.request
import json
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QPixmap, QImage

from utils.binary_resolver import resolve_yt_dlp_command


class ThumbnailFetchThread(QThread):
    """URLからサムネイル画像とタイトルをバックグラウンドで取得するスレッド"""
    fetched = Signal(str, QPixmap)  # (title, pixmap)
    failed = Signal()

    def __init__(self, url: str, cfg: dict = None):
        super().__init__()
        self.url = url
        self.cfg = cfg or {}
        self._stopped = False
        self.process = None

    def run(self):
        if self._stopped:
            self.failed.emit()
            return

        yt_cmd = resolve_yt_dlp_command()
        if yt_cmd is None:
            self.failed.emit()
            return

        # yt-dlpでJSON形式で情報を取得
        args = yt_cmd + [
            "-J", "--flat-playlist", "--no-warnings",
            self.url
        ]

        cookies_browser = self.cfg.get("cookies_browser", "none")
        if cookies_browser and cookies_browser != "none":
            args += ["--cookies-from-browser", cookies_browser]

        proxy_url = str(self.cfg.get("proxy_url", "") or "").strip()
        if proxy_url:
            args += ["--proxy", proxy_url]

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        try:
            self.process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,  # 文字化け防止のためバイナリで取得
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                env=env,
            )
            
            stdout_bytes, stderr_bytes = self.process.communicate(timeout=20)
            
            if self._stopped or self.process.returncode != 0:
                self.failed.emit()
                return
            
            # ハイブリッドデコード
            try:
                stdout_text = stdout_bytes.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    stdout_text = stdout_bytes.decode("cp932")
                except UnicodeDecodeError:
                    stdout_text = stdout_bytes.decode("utf-8", errors="replace")
                    
        except (subprocess.TimeoutExpired, Exception):
            if self.process:
                try:
                    self.process.terminate()
                except Exception:
                    pass
            self.failed.emit()
            return

        try:
            data = json.loads(stdout_text)
            # タイトルの取得 (優先度: タイトルがあれば使用)
            # 再生リストやチャンネルの場合は playlist_title や channel なども考慮
            title = data.get("title") or data.get("playlist_title") or data.get("uploader") or data.get("fulltitle") or "Unknown"
            
            # サムネイルの抽出
            thumbnail_url = data.get("thumbnail")
            
            # 複数のサムネイルから最適なものを選択
            thumbnails = data.get("thumbnails", [])
            if thumbnails:
                # 配列の末尾が最も高画質・最適な場合が多い (yt-dlpの仕様)
                # 特にチャンネルアイコンの場合、最後にアイコンが含まれる傾向にある
                thumbnail_url = thumbnails[-1].get("url")
                
        except Exception:
            self.failed.emit()
            return

        if not title or not thumbnail_url:
            self.failed.emit()
            return

        # サムネイル画像をダウンロード
        pixmap = self._download_thumbnail(thumbnail_url)
        if self._stopped or pixmap is None or pixmap.isNull():
            self.failed.emit()
            return

        self.fetched.emit(title, pixmap)

    def _download_thumbnail(self, url: str) -> QPixmap | None:
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0"
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
            image = QImage()
            if image.loadFromData(data):
                return QPixmap.fromImage(image)
        except Exception:
            pass
        return None

    def stop(self):
        self._stopped = True
        if self.process:
            try:
                self.process.terminate()
            except Exception:
                pass
