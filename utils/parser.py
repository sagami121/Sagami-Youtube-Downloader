import os
import re
from pathlib import Path

def build_ytdlp_args(yt_cmd: list, url: str, folder: str, cfg: dict, ffmpeg_path: str = None, ffprobe_path: str = None) -> list:
    """
    Build yt-dlp command-line arguments based on user config.
    
    Args:
        yt_cmd: The base yt-dlp command list.
        url: The YouTube URL.
        folder: Download destination folder.
        cfg: Configuration dictionary.
        ffmpeg_path: Path to ffmpeg executable (optional).
        ffprobe_path: Path to ffprobe executable (optional).
        
    Returns:
        A list of command-line arguments.
    """
    ffmpeg_ok = bool(ffmpeg_path)
    ffprobe_ok = bool(ffprobe_path)
    template = str(cfg.get("template", "%(title)s")).strip()

    args = yt_cmd + [
        "-P", folder, "-o", f"{template}.%(ext)s",
        "--newline",
        "--print", "title:%(title)s",
        "--print", "after_move:FILEPATH:%(filepath)s",
        "--progress-template", "download:%(progress._percent_str)s|%(progress.eta)s|%(info.title)s",
        "--no-overwrites",
        "--no-post-overwrites"
    ]

    # Playlist settings
    playlist_items = str(cfg.get("playlist_items", "") or "").strip()
    if playlist_items:
        args += ["--playlist-items", playlist_items]
    
    order_mode = str(cfg.get("playlist_order_mode", "default"))
    if order_mode == "latest":
        args += ["--playlist-reverse"]
    elif order_mode == "popular":
        args += ["--playlist-sorting", "view_count"]
    elif order_mode == "oldest":
        args += ["--playlist-reverse"]
    elif cfg.get("playlist_reverse", False) and not playlist_items:
        args += ["--playlist-reverse"]
        
    if cfg.get("disable_playlist_thumbnail", False):
        args += ["-o", "pl_thumbnail:"]
        
    if ffmpeg_ok:
        args += ["--ffmpeg-location", str(Path(ffmpeg_path))]

    # Cookies
    cookies_browser = cfg.get("cookies_browser", "none")
    if cookies_browser and cookies_browser != "none":
        args += ["--cookies-from-browser", cookies_browser]

    # Format selection logic
    out_format = cfg.get("format", "mp4")
    if out_format == "mp3":
        audio_quality = str(cfg.get("audio_quality", "0")).strip()
        if not re.fullmatch(r"\d+(?:\.\d+)?", audio_quality):
            audio_quality = "0"
        args += ["-x", "--audio-format", "mp3", "--audio-quality", audio_quality]
    elif out_format == "wav":
        args += ["-x", "--audio-format", "wav"]
    elif out_format == "m4a":
        args += ["-x", "--audio-format", "m4a"]
    else:
        # MP4 (Video)
        quality = cfg.get("video_quality", "Best")
        fps = cfg.get("video_fps", "Any")

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
        
        if cfg.get("embed_thumbnail", False) and ffprobe_ok:
            args += ["--write-thumbnail", "--embed-thumbnail"]
        
        if cfg.get("embed_subtitles", False):
            args += ["--embed-subs"]

    # Download sections (Trimming)
    start_sec = cfg.get("time_range_start")
    end_sec = cfg.get("time_range_end")
    if start_sec is not None and end_sec is not None:
        args += ["--download-sections", f"*{start_sec}-{end_sec}", "--force-keyframes-at-cuts"]

    args.append(url)
    return args