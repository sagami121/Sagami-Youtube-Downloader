import sys
import subprocess
import re
import json
import os
from PyQt6.QtWidgets import *
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRect, QPropertyAnimation
from PyQt6.QtGui import QFont

CONFIG_FILE = "config.json"

def load_config():
    default_path = os.path.join(os.path.expanduser("~"), "Downloads")
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            if "path" not in cfg:
                cfg["path"] = default_path
            return cfg
    except:
        return {"format": "mp4", "template": "%(title)s", "path": default_path}

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)

class DownloadThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)

    def __init__(self, url, folder, cfg):
        super().__init__()
        self.url = url
        self.folder = folder
        self.cfg = cfg

    def run(self):
        template = self.cfg.get("template", "%(title)s")
        args = ["yt-dlp", self.url, "-P", self.folder, "-o", f"{template}.%(ext)s", "--newline"]

        if self.cfg.get("format") == "mp3":
            args += ["-x", "--audio-format", "mp3"]
        else:
            args += ["-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]",
                     "--merge-output-format", "mp4",
                     "--postprocessor-args", "ffmpeg:-c:a aac -ac 2"]

        try:
            process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            for line in iter(process.stdout.readline, ''):
                line = line.strip()
                if "[download]" in line:
                    m = re.search(r'(\d{1,3}(?:\.\d+)?)%', line)
                    if m:
                        pct = int(float(m.group(1)))
                        if pct <= 100:
                            self.progress.emit(pct)

            process.wait()
            if process.returncode == 0:
                self.finished.emit("ダウンロードが完了しました")
            else:
                self.finished.emit("エラーが発生しました")

        except Exception as e:
            self.finished.emit(f"実行エラー: {e}")

class Settings(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent_win = parent
        self.setWindowTitle("出力設定")
        self.setFixedWidth(420)
        self.cfg = load_config()
        
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

        layout.addWidget(QLabel("現在のファイル名構成"))
        self.template_display = QLineEdit()
        self.template_display.setText(self.cfg.get("template", "%(title)s"))
        layout.addWidget(self.template_display)

        layout.addWidget(QLabel("ファイル名の設定"))
        tag_layout = QGridLayout()
        tags = [
            ("タイトル", "%(title)s"), ("動画ID", "[%(id)s]"), 
            ("投稿者", "[%(uploader)s]"), ("投稿日", "[%(upload_date)s]"),
            ("画質", "[%(height)sp]"), ("クリア", "clear")
        ]

        for i, (label, code) in enumerate(tags):
            btn = QPushButton(label)
            btn.setMinimumHeight(40) 
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
        self.apply_style()

    def apply_style(self):
        self.setStyleSheet("""
            QDialog { background: #1c1c1e; }
            QLabel { color: #ffffff; font-size: 13px; font-weight: bold; }
            QLineEdit { border: 1px solid #3a3a3c; padding: 10px 12px; border-radius: 10px; background: #2c2c2e; color: #0a84ff; font-family: 'Consolas'; font-size: 14px; }
            QPushButton { background-color: #2c2c2e; color: white; border-radius: 10px; border: 1px solid #3a3a3c; font-size: 13px; padding: 2px; }
            QPushButton:hover { background-color: #3a3a3c; }
            QPushButton:checked { background-color: #0a84ff; border: none; font-weight: bold; }
            #ClearBtn { color: #ff453a; }
            #SaveBtn { background-color: #0a84ff; font-weight: bold; font-size: 15px; border: none; }
        """)

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

        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("Card")
        card.setFixedWidth(520)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(40, 45, 40, 45)
        card_layout.setSpacing(18)

        title = QLabel("Sagami YouTube Downloader")
        title.setStyleSheet("font-size: 24px; font-weight: 200; color: #ffffff;")
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
        self.path_display.setStyleSheet("color: #ffffff; font-size: 12px; background: #252527;")
        
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

        # 詳細設定
        self.btn_settings = QPushButton("詳細設定を表示")
        self.btn_settings.setObjectName("SettingsBtn")
        self.btn_settings.clicked.connect(lambda: Settings(self).exec())
        card_layout.addWidget(self.btn_settings, alignment=Qt.AlignmentFlag.AlignCenter)

        main_layout.addWidget(card)
        self.apply_style()

    def apply_style(self):
        self.setStyleSheet("""
            QWidget#Main { background-color: #000000; }
            QFrame#Card { background-color: #1c1c1e; border-radius: 24px; border: 1px solid #2c2c2e; }
            QLabel { color: #8e8e93; font-size: 11px; font-weight: bold; margin-left: 5px; }
            QLineEdit { border: 1px solid #3a3a3c; padding: 10px 12px; border-radius: 10px; background: #2c2c2e; color: #ffffff; font-size: 14px; }
            QPushButton { background-color: #0a84ff; color: white; border-radius: 10px; padding: 10px; font-size: 14px; font-weight: 600; border: none; }
            QPushButton:hover { background-color: #409cff; }
            QPushButton#SecondaryBtn { background-color: #3a3a3c; font-size: 13px; font-weight: normal; }
            #SettingsBtn { background: transparent; color: #636366; font-size: 13px; }
        """)

    def paste_url(self):
        self.url.setText(QApplication.clipboard().text())

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "保存先フォルダを選択", self.path_display.text())
        if folder:
            self.path_display.setText(folder)
            self.cfg["path"] = folder
            save_config(self.cfg)

    def start(self):
        url = self.url.text().strip()
        if not url: return
        self.btn_dl.setEnabled(False)
        self.btn_dl.setText("ダウンロード中...")
        self.t = DownloadThread(url, self.path_display.text(), load_config())
        self.t.finished.connect(self.done)
        self.t.start()

    def done(self, msg):
        self.btn_dl.setEnabled(True)
        self.btn_dl.setText("ダウンロードを開始")
        QMessageBox.information(self, "通知", msg)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Main()
    w.show()
    sys.exit(app.exec())