import os
import re
import time
import subprocess
import traceback
from pathlib import Path
from PySide6.QtCore import QThread, Signal

from utils.binary_resolver import resolve_yt_dlp_command, resolve_ffmpeg_command, resolve_ffprobe_command, is_ffmpeg_usable
from utils.logger import write_error_log

class DownloadThread(QThread):
    progress = Signal(int)
    detail = Signal(str)
    finished = Signal(str)

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
            audio_quality = str(self.cfg.get("audio_quality", "0")).strip()
            if not re.fullmatch(r"\d+(?:\.\d+)?", audio_quality):
                audio_quality = "0"
            args += ["-x", "--audio-format", "mp3", "--audio-quality", audio_quality]
        elif out_format == "wav":
            if not ffmpeg_ok:
                self.finished.emit("WAV変換には ffmpeg が必要です。ffmpeg.exe をアプリと同じフォルダに配置してください。")
                return
            args += ["-x", "--audio-format", "wav"]
        elif out_format == "m4a":
            if not ffmpeg_ok:
                self.finished.emit("M4A変換には ffmpeg が必要です。ffmpeg.exe をアプリと同じフォルダに配置してください。")
                return
            args += ["-x", "--audio-format", "m4a"]
        else:
            if not ffmpeg_ok:
                self.finished.emit("高画質MP4の結合には ffmpeg が必要です。ffmpeg.exe をアプリと同じフォルダに配置してください。")
                return
            quality = self.cfg.get("video_quality", "Best")
            fps = self.cfg.get("video_fps", "Any")

            video_selector = "bv*"
            if quality and quality != "Best":
                h = quality.replace("p", "")
                if h.isdigit():
                    video_selector += f"[height<={h}]"
            if fps and fps != "Any" and str(fps).isdigit():
                video_selector += f"[fps<={fps}]"

            format_selector = f"{video_selector}+ba[acodec*=mp4a]/{video_selector}+ba[ext=m4a]/{video_selector}+ba/b[ext=mp4]/b"

            args += ["-f", format_selector,
                     "--format-sort", "res,fps,vcodec:avc",
                     "--merge-output-format", "mp4"]
            
            if self.cfg.get("embed_thumbnail", False) and ffprobe_ok:
                args += ["--write-thumbnail", "--embed-thumbnail"]
            
            if self.cfg.get("embed_subtitles", False):
                args += ["--embed-subs"]

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
                        stem = Path(raw_name).stem
                        stem = re.sub(r'\.f\d+$', '', stem)
                        if not (stem.startswith("f") and stem[1:].isdigit() and len(stem) <= 5):
                            self._current_title = stem
                if line.startswith("download:"):
                    parts = line.split(":", 1)[1].split("|", 2)
                    if len(parts) >= 3:
                        eta = parts[1].strip() or "?"
                        t = parts[2].strip()
                        if t and t != "NA":
                            self._current_title = t
                        title = self._current_title
                        self.detail.emit(f"残り: {eta} / {title}")
                    elif len(parts) >= 1:
                        pct_text = parts[0].strip()
                        self.detail.emit(f"進捗: {pct_text}")
                elif line.startswith("[download]"):
                    m_eta = re.search(r"ETA\s+([0-9:]+)", line)
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
                log_path = write_error_log(
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
            log_path = write_error_log(
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
