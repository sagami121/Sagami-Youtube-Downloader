import os
import sys
import re
import json
import time
import subprocess
import traceback
from datetime import datetime
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QProgressBar, QFileDialog, QMessageBox, QFrame, QSizePolicy,
    QApplication, QMenu, QComboBox
)
from PySide6.QtCore import Qt, QUrl, QTimer, QThread
from PySide6.QtGui import QIcon, QAction, QDesktopServices, QCursor, QFontDatabase, QColor, QPalette

from constants import (
    VERSION, APP_GITHUB_REPO_URL, APP_DISPLAY_NAME, get_runtime_app_dir
)
from utils.logger import logger, get_log_dir, write_error_log
from utils.system import resolve_app_icon_path, qt_message_filter
from utils.formatting import parse_time_range
from utils.binary_resolver import resolve_yt_dlp_command

from core.config_manager import load_config, save_config, save_history, load_history
from core.theme_manager import (
    apply_app_theme, apply_dialog_theme, get_stylesheet, 
    load_theme_profile, lerp_color, apply_titlebar_theme
)
from core.lang_manager import i18n

from ui.components import FocusClearLineEdit
from ui.dialogs import Settings, LogViewerDialog, PlaylistSelectDialog, HistoryDialog
from ui.report_dialog import ErrorReportDialog
from threads.downloader import DownloadThread
from threads.updaters import (
    YtDlpUpdateThread, YtDlpCheckThread, AppUpdateThread, BinariesEnsureThread
)

class Main(QWidget):
    def is_english(self) -> bool:
        return str(self.cfg.get("language", "ja")).lower().startswith("en")

    def t(self, key: str, default: str) -> str:
        return i18n(self.cfg, key, default)

    def _safe_call(self, action: str, func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            log_path = write_error_log(
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
                
                # エラー報告ダイアログの提案
                msg_box = QMessageBox(self)
                msg_box.setIcon(QMessageBox.Icon.Warning)
                msg_box.setWindowTitle("エラー")
                msg_box.setText(f"操作中にエラーが発生しました。\n{action}{suffix}")
                msg_box.setInformativeText("このエラーを開発者に報告しますか？")
                
                report_btn = msg_box.addButton("エラーを報告する", QMessageBox.ButtonRole.ActionRole)
                msg_box.addButton("閉じる", QMessageBox.ButtonRole.RejectRole)
                
                self._apply_messagebox_theme(msg_box)
                msg_box.exec()
                
                if msg_box.clickedButton() == report_btn:
                    dlg = ErrorReportDialog(self, exception=e, context_info=action)
                    dlg.exec()
                    
            except Exception:
                pass
            return None

    def theme_button_text(self, theme_name: str) -> str:
        return theme_name.replace("_", " ").title()

    def apply_language_texts(self):
        self.btn_theme.setText(self.theme_button_text(self.cfg.get("theme", "dark")))
        self.btn_mini.setText("M" if self.is_mini_mode else "Mini")
        self.lbl_url.setText(self.t("main.video_url", "Video URL"))
        self.lbl_time.setText(self.t("main.time_range", "Time Range"))
        self.lbl_folder.setText(self.t("main.output_folder", "Output Folder"))
        self.url.setPlaceholderText(self.t("main.url_placeholder", "Paste link here..."))
        self.time_range.setPlaceholderText(self.t("main.time_placeholder", "e.g. 0:00~0:15"))
        self.btn_paste.setText(self.t("main.paste", "Paste"))
        self.btn_browse.setText(self.t("main.browse", "Browse"))
        self.btn_dl.setText(self.t("main.start_download", "Start Download"))
        self.btn_settings.setText(self.t("main.settings", "Settings"))
        self.btn_update_ytdlp.setText(self.t("main.update_ytdlp", "Update yt-dlp"))
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
        icon_path = resolve_app_icon_path(get_runtime_app_dir())
        if icon_path:
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(920, 700)
        self.setMinimumSize(720, 600)
        self.cfg = load_config()
        self._apply_startup_palette()
        self.is_mini_mode = False
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
        
        self.btn_mini = QPushButton("Mini")
        self.btn_mini.setObjectName("SecondaryBtn")
        self.btn_mini.setFixedWidth(80)
        self.btn_mini.setMinimumHeight(35)
        self.btn_mini.clicked.connect(self.toggle_mini_mode)
        top_bar.addWidget(self.btn_mini)

        self.btn_history = QPushButton("履歴")
        self.btn_history.setObjectName("SecondaryBtn")
        self.btn_history.setFixedWidth(80)
        self.btn_history.setMinimumHeight(35)
        self.btn_history.clicked.connect(self.show_history)
        top_bar.addWidget(self.btn_history)

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
        actions_layout.addWidget(self.btn_update_ytdlp)

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

        self.apply_language_texts()
        self.apply_style()
        QTimer.singleShot(0, lambda: apply_titlebar_theme(self, self.cfg.get("theme", "dark")))
        QTimer.singleShot(700, self.check_app_update_on_startup)
        QTimer.singleShot(1200, self.check_ytdlp_on_startup)
        QTimer.singleShot(1500, self.preload_error_report_info)

    def preload_error_report_info(self):
        """バックグラウンドでシステム情報を取得してキャッシュする"""
        try:
            from core.error_reporter import ErrorReport
            from PySide6.QtCore import QThread
            class PreloadThread(QThread):
                def run(self):
                    ErrorReport() # インスタンス化するだけでキャッシュが作成される
            self.report_preload_thread = PreloadThread()
            self.report_preload_thread.start()
        except Exception:
            pass

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

    def update_ytdlp(self, auto=False):
        if self.updater is not None and self.updater.isRunning():
            return

        if resolve_yt_dlp_command() is None:
            if not auto:
                self._show_warning("エラー", "yt-dlp が見つかりません。")
            return

        self.updater = YtDlpUpdateThread()
        # auto引数を引き継ぐためにlambdaを使用
        self.updater.finished.connect(
            lambda ok, state, before, after, output: self.on_ytdlp_updated(ok, state, before, after, output, auto=auto)
        )
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

        self.set_app_status("checking", VERSION, VERSION)
        self.app_updater = AppUpdateThread(source_url)
        self.app_updater.finished.connect(
            lambda ok, state, current, latest, page_url, notes, published_at, installer_url:
            self.on_app_update_finished(ok, state, current, latest, page_url, notes, published_at, installer_url, interactive, suppress_latest_popup)
        )
        self.app_updater.start()

    def on_app_update_finished(self, ok: bool, state: str, current_version: str, latest_version: str, release_page_url: str, notes: str, published_at: str, installer_url: str, interactive: bool, suppress_latest_popup: bool):
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
        self.ytdlp_state = state or "pending"
        
        # 状態に応じて表示テキストを決定
        if state == "pending":
            self.ytdlp_status_label.setText(self.t("status.ytdlp_pending", "yt-dlp - Pending check"))
        elif state == "checking":
            self.ytdlp_status_label.setText(self.t("status.ytdlp_checking", "yt-dlp - Checking..."))
        elif state == "not_found":
            self.ytdlp_status_label.setText(self.t("status.ytdlp_not_found", "yt-dlp - Not found"))
        elif state == "update_available":
            # version は最新バージョンを指す
            current = self.ytdlp_version or self.t("common.unknown", "Unknown")
            self.ytdlp_status_label.setText(self.t("status.ytdlp_update_available", "yt-dlp - {current}->{latest} Update available").format(current=current, latest=version))
        elif state == "up_to_date":
            # 更新がない場合は渡されたバージョンを現在のバージョンとして保持
            self.ytdlp_version = version or self.t("common.unknown", "Unknown")
            self.ytdlp_status_label.setText(self.t("status.ytdlp_up_to_date", "yt-dlp - {version} Up to date").format(version=self.ytdlp_version))
        elif state == "updated":
            # 更新成功時は渡されたバージョン（新バージョン）に更新
            self.ytdlp_version = version or self.t("common.unknown", "Unknown")
            self.ytdlp_status_label.setText(self.t("status.ytdlp_updated", "yt-dlp - {version} Updated").format(version=self.ytdlp_version))
        else:
            # 失敗時は渡されたバージョンがあれば表示、なければ既存のものを表示
            ver = version or self.ytdlp_version or self.t("common.unknown", "Unknown")
            self.ytdlp_status_label.setText(self.t("status.ytdlp_failed", "yt-dlp - {version} Check failed").format(version=ver))

        self.ytdlp_status_label.setVisible(True)
    def on_startup_ytdlp_updated(self, ok: bool, state: str, before_version: str, after_version: str, output: str):
        status_version = self._pick_known_version(after_version, before_version)
        self.set_ytdlp_status(status_version, state if ok else "failed")
        if ok:
            return
        log_path = write_error_log(
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
            # 更新が見つかった場合は自動で更新を開始
            QTimer.singleShot(500, lambda: self.update_ytdlp(auto=True))
        elif state == "up_to_date":
            self.set_ytdlp_status(current_version or latest_version, "up_to_date")

    def on_ytdlp_updated(self, ok: bool, state: str, before_version: str, after_version: str, output: str, auto=False):
        self.btn_update_ytdlp.setEnabled(True)
        self.btn_update_ytdlp.setText("yt-dlp を更新")
        body = tail_text(output)
        status_version = self._pick_known_version(after_version, before_version)
        self.set_ytdlp_status(status_version, state if ok else "failed")
        
        # 自動更新（auto=True）かつ成功（ok=True）の場合は通知を出さない
        if auto and ok:
            return

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

    def check_app_update_on_startup(self):
        self.start_app_update_check(interactive=True, suppress_latest_popup=True)

    def start_app_update_check(self, interactive: bool, suppress_latest_popup: bool = False):
        if self.app_updater is not None and self.app_updater.isRunning():
            return

        source_url = str(self.cfg.get("app_update_source_url", "") or APP_GITHUB_REPO_URL).strip()
        if not source_url:
            self.set_app_status("source_not_set", VERSION, VERSION)
            if interactive:
                self._show_info("アプリ更新", "GitHubリポジトリURLが未設定です。\nconfig.json の app_update_source_url にURLを設定してください。")
            return

        self.set_app_status("checking", VERSION, VERSION)
        self.app_updater = AppUpdateThread(source_url)
        self.app_updater.finished.connect(
            lambda ok, state, current, latest, page_url, notes, published_at, installer_url:
            self.on_app_update_finished(ok, state, current, latest, page_url, notes, published_at, installer_url, interactive, suppress_latest_popup)
        )
        self.app_updater.start()

    def on_app_update_finished(self, ok: bool, state: str, current_version: str, latest_version: str, release_page_url: str, notes: str, published_at: str, installer_url: str, interactive: bool, suppress_latest_popup: bool):
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

        if "完了" in msg and self.download_thread:
            history = load_history()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            entry = {
                "timestamp": now,
                "url": self.download_thread.url,
                "title": self.download_thread._current_title or self.download_thread.url,
                "folder": self.download_thread.folder
            }
            history.append(entry)
            history = history[-1000:]
            save_history(history)

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
            write_error_log(
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

    def show_history(self):
        dlg = HistoryDialog(self)
        dlg.exec()

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

        start_theme = getattr(self, "_theme_anim_from", None) or self.cfg.get("theme", "dark")
        end_theme = getattr(self, "_theme_anim_to", None) or new_theme
        start_colors = theme_colors.get(start_theme, dark_colors).copy()
        end_colors = theme_colors.get(end_theme, light_colors).copy()

        json_start_colors, json_start_props = load_theme_profile(start_theme)
        json_end_colors, json_end_props = load_theme_profile(end_theme)

        for key in ("bg", "card", "label", "title", "input_bg", "input_text", "input_border", "btn_bg", "btn_text"):
            if key in json_start_colors:
                start_colors[key] = json_start_colors[key]
            if key in json_end_colors:
                end_colors[key] = json_end_colors[key]

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

    def toggle_mini_mode(self):
        self.is_mini_mode = not self.is_mini_mode
        self.btn_mini.setText("M" if self.is_mini_mode else "Mini")
        
        is_normal = not self.is_mini_mode
        
        try:
            # --- 1. ウィンドウフラグの設定 (最前面表示の切替) ---
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self.is_mini_mode)
            
            # --- 2. サイズ制約の更新 ---
            if self.is_mini_mode:
                # ミニモード: 小さく固定
                self.setMinimumSize(420, 280)
                self.setMaximumSize(550, 400)
                self.resize(450, 320)
                self.card.setFixedWidth(410)
                self.card.layout().setSpacing(10)
                self.card.layout().setContentsMargins(20, 20, 20, 15)
            else:
                # 通常モード: 制約を広げる
                self.setMinimumSize(720, 600)
                self.setMaximumSize(16777215, 16777215) 
                self.resize(920, 700)
                self.card.setFixedWidth(520)
                self.card.layout().setSpacing(5)
                self.card.layout().setContentsMargins(28, 26, 28, 24)

            # --- 3. 要素の表示/非表示を制御 ---
            title = self.card.findChild(QLabel, "Title")
            if title: title.setVisible(is_normal)
            
            self.lbl_url.setVisible(is_normal)
            self.lbl_time.setVisible(is_normal)
            self.time_range.setVisible(is_normal)
            self.lbl_folder.setVisible(is_normal)
            self.path_display.setVisible(is_normal)
            self.btn_browse.setVisible(is_normal)
            self.media_quality_label.setVisible(is_normal)
            
            # 画質コンボの状態（MP4かそれ以外か）
            is_mp4 = self.cfg.get("format", "mp4") == "mp4"
            self.quality_combo.setVisible(is_normal and is_mp4)
            self.fps_combo.setVisible(is_normal and is_mp4)
            self.audio_quality_combo.setVisible(is_normal and not is_mp4)
            
            self.btn_settings.setVisible(is_normal)
            self.btn_theme.setVisible(is_normal)
            self.app_status_label.setVisible(is_normal)
            
            # 常に表示するメイン要素
            self.url.setVisible(True)
            self.btn_paste.setVisible(True)
            self.btn_dl.setVisible(True)
            self.ytdlp_status_label.setVisible(True)
            
            # --- 4. ウィンドウの再表示とリサイズ強制 ---
            self.show()
            # フラグ変更後のサイズ適用を確実にするため、少し遅らせて実行
            QTimer.singleShot(50, lambda: self.resize(450, 320) if self.is_mini_mode else self.resize(920, 700))
                
        except Exception as e:
            print(f"Mini mode toggle error: {e}")

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

