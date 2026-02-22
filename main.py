import sys
import subprocess
import re
import json
import os
import shutil
from pathlib import Path
from PyQt6.QtWidgets import *
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRect, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont, QIcon

VERSION = "v1.1"
CONFIG_DIR_NAME = "SagamiYoutubeDownloader"

def get_stylesheet(theme="dark", widget_type="main"):
    """テーマに応じたスタイルシートを返す"""
    if theme == "light":
        if widget_type == "main":
            return """
            QWidget#Main { background-color: #ffffff; }
            QFrame#Card { background-color: #f5f5f7; border-radius: 24px; border: 1px solid #d5d5d7; }
            QLabel { color: #333333; font-size: 11px; font-weight: bold; margin-left: 5px; }
            QLabel#Title { color: #000000; font-size: 24px; font-weight: 200; margin-left: 0px; }
            QLineEdit { border: 1px solid #d5d5d7; padding: 10px 12px; border-radius: 10px; background: #ffffff; color: #000000; font-size: 14px; }
            QPushButton { background-color: #0a84ff; color: white; border-radius: 10px; padding: 10px; font-size: 14px; font-weight: 600; border: none; }
            QPushButton:hover { background-color: #409cff; }
            QPushButton#SecondaryBtn { background-color: #e8e8ea; color: #000000; font-size: 13px; font-weight: normal; }
            #SettingsBtn { background: transparent; color: #636366; font-size: 13px; }
            #ThemeBtn { background-color: #e8e8ea; color: #000000; font-weight: normal; }
            QProgressBar {
                border: 1px solid #c9c9ce;
                background-color: #f1f2f6;
                border-radius: 10px;
                padding: 2px;
                text-align: center;
                color: #0a84ff;
                font-size: 11px;
                font-weight: 700;
            }
            QProgressBar::chunk {
                border-radius: 8px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #42a5ff, stop:1 #0a84ff);
            }
            """
        else:  # settings
            return """
            QDialog { background: #ffffff; }
            QLabel { color: #333333; font-size: 13px; font-weight: bold; }
            QCheckBox { color: #333333; font-size: 13px; }
            QLineEdit { border: 1px solid #d5d5d7; padding: 10px 12px; border-radius: 10px; background: #ffffff; color: #000000; font-family: 'Consolas'; font-size: 14px; }
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
            QLabel { color: #8e8e93; font-size: 11px; font-weight: bold; margin-left: 5px; }
            QLabel#Title { color: #ffffff; font-size: 24px; font-weight: 200; margin-left: 0px; }
            QLineEdit { border: 1px solid #3a3a3c; padding: 10px 12px; border-radius: 10px; background: #2c2c2e; color: #ffffff; font-size: 14px; }
            QPushButton { background-color: #0a84ff; color: white; border-radius: 10px; padding: 10px; font-size: 14px; font-weight: 600; border: none; }
            QPushButton:hover { background-color: #409cff; }
            QPushButton#SecondaryBtn { background-color: #3a3a3c; font-size: 13px; font-weight: normal; }
            #SettingsBtn { background: transparent; color: #636366; font-size: 13px; }
            #ThemeBtn { background-color: #3a3a3c; color: #ffffff; font-weight: normal; }
            QProgressBar {
                border: 1px solid #444449;
                background-color: #1f1f22;
                border-radius: 10px;
                padding: 2px;
                text-align: center;
                color: #8ec8ff;
                font-size: 11px;
                font-weight: 700;
            }
            QProgressBar::chunk {
                border-radius: 8px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #66b8ff, stop:1 #0a84ff);
            }
            """
        else:  # settings
            return """
            QDialog { background: #1c1c1e; }
            QLabel { color: #ffffff; font-size: 13px; font-weight: bold; }
            QCheckBox { color: #ffffff; font-size: 13px; }
            QLineEdit { border: 1px solid #3a3a3c; padding: 10px 12px; border-radius: 10px; background: #2c2c2e; color: #0a84ff; font-family: 'Consolas'; font-size: 14px; }
            QPushButton { background-color: #2c2c2e; color: white; border-radius: 10px; border: 1px solid #3a3a3c; font-size: 13px; padding: 2px; }
            QPushButton:hover { background-color: #3a3a3c; }
            QPushButton:checked { background-color: #0a84ff; border: none; font-weight: bold; }
            #ClearBtn { color: #ff453a; }
            #SaveBtn { background-color: #0a84ff; font-weight: bold; font-size: 15px; border: none; }
            """

CONFIG_DIR_NAME = "SagamiYoutubeDownloader"

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
        # EXEとして実行されている場合
        app_dir = Path(sys.executable).parent
    else:
        # Pythonスクリプトとして実行されている場合
        app_dir = Path(__file__).parent
    
    return app_dir / "config.json"


def load_config():
    default_path = os.path.join(os.path.expanduser("~"), "Downloads")
    cfg_path = get_config_path()
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            if "path" not in cfg:
                cfg["path"] = default_path
            if "theme" not in cfg:
                cfg["theme"] = "dark"
            if "embed_thumbnail" not in cfg:
                cfg["embed_thumbnail"] = False
            return cfg
    except (FileNotFoundError, json.JSONDecodeError):
        return {"format": "mp4", "template": "%(title)s", "path": default_path, "theme": "dark", "embed_thumbnail": False}


def save_config(cfg):
    cfg_path = get_config_path()
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)

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

    def run(self):
        template = self.cfg.get("template", "%(title)s")
        args = ["yt-dlp", self.url, "-P", self.folder, "-o", f"{template}.%(ext)s", "--newline", "--restrict-filenames"]

        if self.cfg.get("format") == "mp3":
            args += ["-x", "--audio-format", "mp3"]
        else:
            args += ["-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]",
                     "--merge-output-format", "mp4",
                     "--postprocessor-args", "ffmpeg:-c:a aac -ac 2"]
            
            # MP4の場合、サムネイル埋め込みオプションを追加
            if self.cfg.get("embed_thumbnail", False):
                args += ["--write-thumbnail", "--embed-thumbnail"]

        try:
            self.process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            for line in iter(self.process.stdout.readline, ''):
                if self._stopped:
                    break
                line = line.strip()
                if "[download]" in line:
                    m = re.search(r'(\d{1,3}(?:\.\d+)?)%', line)
                    if m:
                        try:
                            pct = int(float(m.group(1)))
                        except Exception:
                            continue
                        if pct <= 100:
                            self.progress.emit(pct)

            self.process.wait()
            if not self._stopped and self.process.returncode == 0:
                self.progress.emit(100)
                self.finished.emit("ダウンロードが完了しました")
            elif self._stopped:
                self.finished.emit("ダウンロードはキャンセルされました")
            else:
                self.finished.emit("エラーが発生しました")

        except Exception as e:
            self.finished.emit(f"実行エラー: {e}")

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
        self.fmt_group = QHBoxLayout()
        self.btn_mp4 = QPushButton("Video (mp4)")
        self.btn_mp3 = QPushButton("Audio (mp3)")
        for b in [self.btn_mp4, self.btn_mp3]:
            b.setCheckable(True)
            b.setMinimumHeight(45)
            self.fmt_group.addWidget(b)
        
        if self.cfg.get("format") == "mp3":
            self.btn_mp3.setChecked(True)
        else:
            self.btn_mp4.setChecked(True)
            
        self.btn_mp4.clicked.connect(lambda: self.toggle_format("mp4"))
        self.btn_mp3.clicked.connect(lambda: self.toggle_format("mp3"))
        layout.addLayout(self.fmt_group)

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

    def toggle_format(self, fmt):
        if fmt == "mp4":
            self.btn_mp4.setChecked(True)
            self.btn_mp3.setChecked(False)
        else:
            self.btn_mp3.setChecked(True)
            self.btn_mp4.setChecked(False)

    def add_tag(self, code):
        current = self.template_display.text()
        new_text = (current + " " + code) if current else code
        self.template_display.setText(new_text)

    def save(self):
        self.cfg["format"] = "mp3" if self.btn_mp3.isChecked() else "mp4"
        self.cfg["template"] = self.template_display.text() or "%(title)s"
        self.cfg["path"] = self.parent_win.path_display.text()
        self.cfg["embed_thumbnail"] = self.chk_thumbnail.isChecked()
        save_config(self.cfg)
        self.accept()


class Main(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("Main")
        self.setWindowTitle("Sagami Youtube Downloader")
        self.resize(800, 620)
        self.setMinimumSize(600, 520)
        self.cfg = load_config()
        self.is_animating = False  # アニメーション中かどうかを追跡

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # テーマ切り替えボタンを一番上に配置
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(20, 10, 20, 10)
        top_bar.addStretch()
        self.btn_theme = QPushButton("🌙 ダークモード" if self.cfg.get("theme", "dark") == "dark" else "☀️ ライトモード")
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
        center_layout.addStretch()

        card = QFrame()
        card.setObjectName("Card")
        card.setFixedWidth(520)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(40, 45, 40, 45)
        card_layout.setSpacing(18)

        title = QLabel("Sagami YouTube Downloader")
        title.setObjectName("Title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title)

        # URL入力
        card_layout.addWidget(QLabel("動画URL"))
        url_layout = QHBoxLayout()
        self.url = QLineEdit()
        self.url.setPlaceholderText("ここにリンクを貼り付け...")
        self.btn_paste = QPushButton("ペースト")
        self.btn_paste.setFixedWidth(90)
        self.btn_paste.setMinimumHeight(45)
        self.btn_paste.setObjectName("SecondaryBtn")
        self.btn_paste.clicked.connect(self.paste_url)
        url_layout.addWidget(self.url)
        url_layout.addWidget(self.btn_paste)
        card_layout.addLayout(url_layout)

        # 保存先
        card_layout.addWidget(QLabel("保存先フォルダ"))
        path_layout = QHBoxLayout()
        self.path_display = QLineEdit()
        self.path_display.setText(self.cfg.get("path"))
        self.path_display.setReadOnly(True)
        
        self.btn_browse = QPushButton("選択")
        self.btn_browse.setFixedWidth(80)
        self.btn_browse.setMinimumHeight(45)
        self.btn_browse.setObjectName("SecondaryBtn")
        self.btn_browse.clicked.connect(self.browse_folder)
        
        path_layout.addWidget(self.path_display)
        path_layout.addWidget(self.btn_browse)
        card_layout.addLayout(path_layout)

        # ダウンロードボタン
        self.btn_dl = QPushButton("ダウンロードを開始")
        self.btn_dl.setMinimumHeight(55)
        self.btn_dl.clicked.connect(self.start)
        card_layout.addWidget(self.btn_dl)

        # 進捗バー
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(18)
        card_layout.addWidget(self.progress_bar)

        # 詳細設定
        self.btn_settings = QPushButton("詳細設定を表示")
        self.btn_settings.setObjectName("SettingsBtn")
        self.btn_settings.clicked.connect(lambda: Settings(self).exec())
        card_layout.addWidget(self.btn_settings, alignment=Qt.AlignmentFlag.AlignCenter)

        center_layout.addWidget(card)
        center_layout.addStretch()
        main_layout.addLayout(center_layout)
        
        main_layout.addStretch()
        self.apply_style()

    def apply_style(self):
        self.setStyleSheet(get_stylesheet(self.cfg.get("theme", "dark"), "main"))

    def paste_url(self):
        self.url.setText(QApplication.clipboard().text())

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "保存先フォルダを選択", self.path_display.text())
        if folder:
            self.path_display.setText(folder)
            self.cfg["path"] = folder
            save_config(self.cfg)

    def start(self):
        # Toggle: if a download is running, cancel it
        if hasattr(self, 't') and self.t.isRunning():
            self.cancel_download()
            return

        url = self.url.text().strip()
        if not url:
            return

        # Check that yt-dlp is available
        if shutil.which("yt-dlp") is None:
            QMessageBox.warning(self, "エラー", "yt-dlp が見つかりません。yt-dlp をインストールしてください。")
            return

        self.btn_dl.setEnabled(True)
        self.btn_dl.setText("ダウンロード中... 0%")
        self.t = DownloadThread(url, self.path_display.text(), load_config())
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
            self.progress_bar.setVisible(False)
        except Exception:
            pass

    def done(self, msg):
        self.btn_dl.setEnabled(True)
        self.btn_dl.setText("ダウンロードを開始")
        self.progress_bar.setVisible(False)
        self.progress_bar.setValue(0)
        QMessageBox.information(self, "通知", msg)

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
        self.theme_anim.valueChanged.connect(lambda v: self.update_theme_color(v, new_theme))
        self.theme_anim.finished.connect(lambda: self.finalize_theme(new_theme))
        self.theme_anim.start()

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
            QLabel {{ color: {label_color}; font-size: 11px; font-weight: bold; margin-left: 5px; }}
            QLabel#Title {{ color: {title_color}; font-size: 24px; font-weight: 200; margin-left: 0px; }}
            QLineEdit {{ border: 1px solid {input_border}; padding: 10px 12px; border-radius: 10px; background: {input_bg}; color: {input_text}; font-size: 14px; }}
            QPushButton {{ background-color: #0a84ff; color: white; border-radius: 10px; padding: 10px; font-size: 14px; font-weight: 600; border: none; }}
            QPushButton:hover {{ background-color: #409cff; }}
            QPushButton#SecondaryBtn {{ background-color: {btn_bg}; color: {btn_text}; font-size: 13px; font-weight: normal; }}
            #SettingsBtn {{ background: transparent; color: #636366; font-size: 13px; }}
            #ThemeBtn {{ background-color: {btn_bg}; color: {btn_text}; font-weight: normal; }}
            QProgressBar {{
                border: 1px solid {input_border};
                background-color: {input_bg};
                border-radius: 10px;
                padding: 2px;
                text-align: center;
                color: {title_color};
                font-size: 11px;
                font-weight: 700;
            }}
            QProgressBar::chunk {{
                border-radius: 8px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #42a5ff, stop:1 #0a84ff);
            }}
        """
        self.setStyleSheet(stylesheet)

    def finalize_theme(self, new_theme):
        """テーマを確定"""
        self.cfg["theme"] = new_theme
        save_config(self.cfg)
        
        # ボタンテキストを更新
        self.btn_theme.setText("🌙 ダークモード" if new_theme == "dark" else "☀️ ライトモード")
        
        # 完全なスタイルを再適用
        self.apply_style()
        
        # アニメーション中フラグを解除
        self.is_animating = False
        self.btn_theme.setEnabled(True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Main()
    w.show()
    sys.exit(app.exec())
