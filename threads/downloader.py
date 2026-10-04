import os
import re
import time
import subprocess
import traceback
from pathlib import Path
from PySide6.QtCore import QThread, Signal

from utils.binary_resolver import resolve_yt_dlp_command, resolve_ffmpeg_command, resolve_ffprobe_command, is_ffmpeg_usable
from utils.logger import logger, write_download_debug_log, write_error_log
from utils.parser import build_ytdlp_args

class DownloadThread(QThread):
    progress = Signal(int)
    detail = Signal(str)
    download_completed = Signal(str)

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
        self._final_path = None
        self._output_paths = []
        self._already_downloaded = False
        self._status = "pending"  # "success" / "skipped" / "cancelled" / "failed"

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

    def _report_failure(self, section: str, reason: str, details: dict):
        self._status = "failed"
        values = {
            "reason": reason,
            "url": self.url,
            "download_folder": self.folder,
            "download_folder_exists": Path(self.folder).is_dir(),
            "format": self.cfg.get("format", "mp4"),
            "video_quality": self.cfg.get("video_quality", "Best"),
            "video_fps": self.cfg.get("video_fps", "Any"),
            "audio_quality": self.cfg.get("audio_quality", "0"),
            "cookies_browser": self.cfg.get("cookies_browser", "none"),
            "embed_thumbnail": self.cfg.get("embed_thumbnail", False),
            "embed_subtitles": self.cfg.get("embed_subtitles", False),
            "time_range_start": self.cfg.get("time_range_start"),
            "time_range_end": self.cfg.get("time_range_end"),
        }
        values.update(details)

        app_log_path = ""
        try:
            app_log_path = write_error_log(section, values, prefix=section)
        except Exception:
            logger.exception("Failed to write download failure to application log")

        try:
            debug_log_path = write_download_debug_log(section, values)
            message = f"{reason}\nデバッグログ: {debug_log_path}"
        except Exception:
            logger.exception("Failed to save download debug log")
            if app_log_path:
                message = f"{reason}\nデバッグログを保存できませんでした。通常ログ: {app_log_path}"
            else:
                message = f"{reason}\nデバッグログと通常ログの保存に失敗しました。"

        self.download_completed.emit(message)

    def run(self):
        output_tail = []
        output_line_count = 0
        args = []
        yt_cmd = None
        ffmpeg_cmd = None
        ffprobe_cmd = None
        ffmpeg_ok = False
        ffprobe_ok = False

        try:
            yt_cmd = resolve_yt_dlp_command()
            if yt_cmd is None:
                self._report_failure(
                    "download_prerequisite_error",
                    "yt-dlp が見つかりません。",
                    {"yt_dlp_command": None},
                )
                return

            ffmpeg_cmd = resolve_ffmpeg_command()
            ffprobe_cmd = resolve_ffprobe_command()
            ffmpeg_ok = is_ffmpeg_usable(ffmpeg_cmd) if ffmpeg_cmd else False
            ffprobe_ok = bool(ffprobe_cmd)

            out_format = self.cfg.get("format", "mp4")
            if out_format in ("mp3", "wav", "m4a", "mp4") and not ffmpeg_ok:
                format_names = {
                    "mp3": "MP3",
                    "wav": "WAV",
                    "m4a": "M4A",
                    "mp4": "高画質MP4",
                }
                self._report_failure(
                    "download_prerequisite_error",
                    f"{format_names[out_format]}のダウンロードには ffmpeg が必要です。"
                    "ffmpeg.exe をアプリと同じフォルダに配置してください。",
                    {
                        "yt_dlp_command": yt_cmd,
                        "ffmpeg_command": ffmpeg_cmd,
                        "ffmpeg_usable": ffmpeg_ok,
                    },
                )
                return

            args = build_ytdlp_args(
                yt_cmd,
                self.url,
                self.folder,
                self.cfg,
                ffmpeg_path=ffmpeg_cmd,
                ffprobe_path=ffprobe_cmd,
            )

            if self.cfg.get("embed_thumbnail", False):
                self._snapshot_existing_webps()
                self._run_started_ts = time.time()

            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"

            self.process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                env=env
            )

            while not self._stopped:
                line_bytes = self.process.stdout.readline()
                if not line_bytes:
                    break

                try:
                    line = line_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    try:
                        line = line_bytes.decode("cp932")
                    except UnicodeDecodeError:
                        line = line_bytes.decode("utf-8", errors="replace")

                line = line.strip()
                if not line:
                    continue
                output_tail.append(line)
                output_line_count += 1
                if len(output_tail) > 200:
                    output_tail = output_tail[-200:]
                self._track_thumbnail_webp(line)
                if line.startswith("title:"):
                    self._current_title = line.split("title:", 1)[1].strip()
                    continue

                if line.startswith("FILEPATH:"):
                    raw_path = line.split(":", 1)[1].strip()
                    if raw_path:
                        output_path = Path(raw_path)
                        if not output_path.is_absolute():
                            output_path = Path(self.folder) / output_path
                        output_path = output_path.resolve()
                        self._output_paths.append(str(output_path))
                        self._final_path = str(output_path)

                if line.startswith("[download] Destination:"):
                    raw_name = line.split("Destination:", 1)[1].strip()
                    if raw_name:
                        p = Path(raw_name)
                        if not p.is_absolute():
                            p = Path(self.folder) / p
                        self._final_path = str(p.absolute())

                        stem = p.stem
                        stem = re.sub(r'\.f\d+$', '', stem)
                        if not (stem.startswith("f") and stem[1:].isdigit() and len(stem) <= 5):
                            self._current_title = stem
                if line.startswith("[ffmpeg] Merging formats into"):
                    m = re.search(r'Merging formats into "(.+?)"', line)
                    if m:
                        raw_name = m.group(1)
                        p = Path(raw_name)
                        if not p.is_absolute():
                            p = Path(self.folder) / p
                        self._final_path = str(p.absolute())
                if "has already been downloaded" in line:
                    self._already_downloaded = True
                    m = re.search(r'\[download\]\s+(.+?)\s+has already been downloaded', line)
                    if m:
                        raw_name = m.group(1).strip()
                        p = Path(raw_name)
                        if not p.is_absolute():
                            p = Path(self.folder) / p
                        self._final_path = str(p.absolute())
                        if not self._current_title:
                            self._current_title = p.stem
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
                candidate_paths = self._output_paths[:]
                if (
                    not candidate_paths
                    and self._already_downloaded
                    and self._final_path
                ):
                    candidate_paths.append(self._final_path)
                existing_output_paths = [
                    path for path in candidate_paths
                    if Path(path).is_file() and Path(path).stat().st_size > 0
                ]
                if not existing_output_paths:
                    self._report_failure(
                        "download_no_output",
                        "yt-dlp は正常終了しましたが、動画ファイルを確認できませんでした。",
                        {
                            "yt_dlp_command": yt_cmd,
                            "command": args,
                            "ffmpeg_cmd": ffmpeg_cmd or "",
                            "ffprobe_cmd": ffprobe_cmd or "",
                            "ffmpeg_usable": ffmpeg_ok,
                            "ffprobe_usable": ffprobe_ok,
                            "returncode": self.process.returncode,
                            "reported_output_paths": self._output_paths,
                            "checked_output_paths": candidate_paths,
                            "output_line_count": output_line_count,
                            "output_tail": output_tail,
                        },
                    )
                    return
                self._final_path = existing_output_paths[-1]
                if self.cfg.get("embed_thumbnail", False):
                    self._cleanup_thumbnail_webps()
                    self._cleanup_new_webps()
                self.progress.emit(100)
                if self._already_downloaded:
                    self._status = "skipped"
                    msg = "同名ファイルが存在するため、ダウンロードはキャンセルされました"
                else:
                    self._status = "success"
                    msg = "ダウンロードが完了しました"
                self.download_completed.emit(msg)
            elif self._stopped:
                self._status = "cancelled"
                self.download_completed.emit("ダウンロードはキャンセルされました")
            else:
                self._report_failure(
                    "download_error",
                    "ダウンロードに失敗しました。",
                    {
                        "yt_dlp_command": yt_cmd,
                        "command": args,
                        "ffmpeg_cmd": ffmpeg_cmd or "",
                        "ffprobe_cmd": ffprobe_cmd or "",
                        "ffmpeg_usable": ffmpeg_ok,
                        "ffprobe_usable": ffprobe_ok,
                        "returncode": self.process.returncode if self.process else "unknown",
                        "reported_output_paths": self._output_paths,
                        "output_line_count": output_line_count,
                        "output_tail": output_tail,
                    },
                )

        except Exception as e:
            self._report_failure(
                "download_exception",
                f"ダウンロード実行中にエラーが発生しました: {e}",
                {
                    "yt_dlp_command": yt_cmd,
                    "command": args,
                    "ffmpeg_cmd": ffmpeg_cmd or "",
                    "ffprobe_cmd": ffprobe_cmd or "",
                "ffmpeg_usable": ffmpeg_ok,
                "ffprobe_usable": ffprobe_ok,
                    "error": repr(e),
                    "traceback": traceback.format_exc(),
                    "output_line_count": output_line_count,
                    "output_tail": output_tail,
                },
            )