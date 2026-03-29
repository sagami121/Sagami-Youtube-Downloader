import traceback
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QScrollArea, QWidget,
    QLabel, QComboBox, QPushButton, QCheckBox, QLineEdit,
    QGridLayout, QFrame, QMessageBox, QListWidget, QPlainTextEdit,
    QAbstractItemView, QListWidgetItem, QTableWidget, QTableWidgetItem,
    QHeaderView, QApplication, QStyle
)
from PySide6.QtCore import Qt, QUrl, QEvent
from PySide6.QtGui import QColor, QPalette, QDesktopServices

from ui.components import FocusClearLineEdit
from constants import VERSION
from core.config_manager import save_config, save_history, load_history, load_config
from core.theme_manager import (
    apply_dialog_theme, get_stylesheet, scan_theme_options, load_theme_profile, get_theme_manager
)
from core.lang_manager import i18n
from utils.logger import write_error_log
from ui.report_dialog import ErrorReportDialog

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
        self.format_combo.addItem("mp4", "mp4")
        self.format_combo.addItem("mp3", "mp3")
        self.format_combo.addItem("wav", "wav")
        self.format_combo.addItem("m4a", "m4a")
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
        
        # 開発者モードトグル
        layout.addSpacing(10)
        self.dev_mode_cb = QCheckBox("開発者モードを有効にする (Enable Developer Mode)")
        self.dev_mode_cb.setChecked(self.cfg.get("developer_mode", False))
        self.dev_mode_cb.toggled.connect(self._toggle_dev_section)
        layout.addWidget(self.dev_mode_cb)

        # エラー報告設定セクション (開発者モード時のみ表示)
        self.dev_section_widget = QWidget()
        dev_layout = QVBoxLayout(self.dev_section_widget)
        dev_layout.setContentsMargins(0, 0, 0, 0)
        dev_layout.setSpacing(5)
        
        dev_layout.addWidget(self._create_section_header("エラー報告設定 (Reporting Settings)"))
        
        webhook_label = QLabel("Discord Webhook URL:")
        webhook_label.setStyleSheet("font-weight: bold;")
        dev_layout.addWidget(webhook_label)
        
        self.webhook_input = QLineEdit()
        self.webhook_input.setPlaceholderText("https://discord.com/api/webhooks/...")
        self.webhook_input.setText(str(self.cfg.get("error_webhook_url", "")))
        dev_layout.addWidget(self.webhook_input)
        
        self.auto_report_cb = QCheckBox("エラー時に自動で報告画面を表示する")
        self.auto_report_cb.setChecked(self.cfg.get("auto_send_reports", False))
        dev_layout.addWidget(self.auto_report_cb)
        
        dev_layout.addSpacing(5)
        api_label = QLabel("カスタム報告 API URL (Workers等):")
        api_label.setStyleSheet("font-weight: bold;")
        dev_layout.addWidget(api_label)
        
        self.api_url_input = QLineEdit()
        self.api_url_input.setPlaceholderText("https://your-worker.workers.dev/api/report")
        self.api_url_input.setText(str(self.cfg.get("error_report_api_url", "")))
        dev_layout.addWidget(self.api_url_input)
        
        key_label = QLabel("API 認証キー (X-API-Key):")
        key_label.setStyleSheet("font-weight: bold;")
        dev_layout.addWidget(key_label)
        
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("your-secret-api-key")
        self.api_key_input.setText(str(self.cfg.get("error_report_api_key", "")))
        dev_layout.addWidget(self.api_key_input)
        
        webhook_desc = QLabel("※URLを入力すると、自作API経由でボット報告が可能になります。")
        webhook_desc.setStyleSheet("color: #8e8e93; font-size: 10px;")
        dev_layout.addWidget(webhook_desc)
        
        layout.addWidget(self.dev_section_widget)
        
        # 初期表示の反映
        self.dev_section_widget.setVisible(self.dev_mode_cb.isChecked())
        
        # バグ報告ボタン
        self.btn_bug_report = QPushButton("不具合を報告する (Send Bug Report)")
        self.btn_bug_report.setStyleSheet("color: #8e8e93; font-size: 11px; border: none; background: transparent; text-decoration: underline;")
        self.btn_bug_report.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_bug_report.clicked.connect(self.manual_report)
        layout.addWidget(self.btn_bug_report)

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

    def manual_report(self):
        dlg = ErrorReportDialog(self, context_info="Manual Report")
        dlg.exec()

    def _toggle_dev_section(self, checked):
        self.dev_section_widget.setVisible(checked)

    def _create_section_header(self, text):
        label = QLabel(text)
        label.setStyleSheet("font-weight: bold; color: #8e8e93; border-bottom: 1px solid #333; margin-top: 10px; padding-bottom: 2px;")
        return label

    def update_theme_info(self):
        theme = self.theme_combo.currentData() or ""
        info = get_theme_manager().load_theme_info(str(theme))
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
        get_theme_manager().refresh_cache()
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
            self.cfg["proxy_url"] = self.proxy_input.text()
            self.cfg["developer_mode"] = self.dev_mode_cb.isChecked()
            self.cfg["error_webhook_url"] = self.webhook_input.text().strip()
            self.cfg["error_report_api_url"] = self.api_url_input.text().strip()
            self.cfg["error_report_api_key"] = self.api_key_input.text().strip()
            self.cfg["auto_send_reports"] = self.auto_report_cb.isChecked()
            save_config(self.cfg)
            
            # 親ウィンドウの設定とスタイルも更新
            self.parent_win.cfg = self.cfg
            self.parent_win.apply_style()
            self.parent_win.apply_language_texts()
            
            self.accept()
        except Exception as e:
            log_path = write_error_log(
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
        self.btn_refresh.setIcon("refresh")
        self.btn_open_folder = QPushButton("フォルダを開く")
        self.btn_open_folder.setIcon("folder_open")
        self.btn_close = QPushButton("閉じる")
        self.btn_close.setIcon("close")
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
        files = []
        for p in self.logs_dir.iterdir():
            if p.is_file() and p.name.startswith("app.log"):
                files.append(p)
        files = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
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
        
        search_text_color = "#ffffff" if "dark" in theme else "#000000"
        self.search_input.setStyleSheet(f"QLineEdit#PlaylistSearch {{ color: {search_text_color}; }}")
        
        try:
            pal = self.search_input.palette()
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

class HistoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ダウンロード履歴")
        self.resize(950, 450)
        self.cfg = load_config()
        self.init_ui()
        self.load_data()

    def init_ui(self):
        layout = QVBoxLayout(self)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["日時", "タイトル", "URL", "アクション"])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(1, 280)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        self.btn_clear = QPushButton("履歴をクリア")
        self.btn_clear.clicked.connect(self.clear_history)
        btn_layout.addWidget(self.btn_clear)
        
        self.btn_close = QPushButton("閉じる")
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_close)
        
        layout.addLayout(btn_layout)
        apply_dialog_theme(self, str(self.cfg.get("theme", "dark")))

    def load_data(self):
        history = load_history()
        self.table.setRowCount(len(history))
        for row, entry in enumerate(reversed(history)):
            ts = entry.get("timestamp", "")
            title = entry.get("title", "")
            url = entry.get("url", "")
            folder = entry.get("folder", "")

            self.table.setItem(row, 0, QTableWidgetItem(ts))
            self.table.setItem(row, 1, QTableWidgetItem(title))
            self.table.setItem(row, 2, QTableWidgetItem(url))

            btn_folder = QPushButton("フォルダを開く")
            btn_folder.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_folder.clicked.connect(lambda checked, f=folder: self.open_folder(f))
            self.table.setCellWidget(row, 3, btn_folder)
            
        self.table.resizeColumnToContents(0)
        self.table.resizeColumnToContents(3)

    def open_folder(self, folder_path: str):
        if not folder_path:
            return
        url = QUrl.fromLocalFile(folder_path)
        QDesktopServices.openUrl(url)

    def clear_history(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("確認")
        msg.setText("すべてのダウンロード履歴を削除しますか？")
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        apply_dialog_theme(msg, str(self.cfg.get("theme", "dark")))
        if msg.exec() == QMessageBox.StandardButton.Yes:
            save_history([])
            self.load_data()
