import traceback
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QScrollArea, QFrame, QWidget, QApplication, QLineEdit,
    QMessageBox
)
from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtGui import QDesktopServices

from core.error_reporter import ErrorReport
from core.theme_manager import apply_dialog_theme
from core.config_manager import load_config

class ErrorReportDialog(QDialog):
    def __init__(self, parent=None, exception=None, context_info=""):
        super().__init__(parent)
        self.cfg = load_config()
        self.report = ErrorReport(exception)
        self.context_info = context_info
        
        apply_dialog_theme(self, str(self.cfg.get("theme", "dark")))
        
        # 開き方によるタイトルの切り替え
        if self.context_info == "Manual Report":
            self.setWindowTitle("不具合報告")
        else:
            self.setWindowTitle("エラーが発生しました")
            
        self.resize(650, 520)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        head = QLabel("アプリでエラーが発生しました。")
        head.setWordWrap(True)
        head.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(head)

        desc = QLabel("以下に示す情報は匿名化されており、個人を特定する情報は含まれません。内容を確認して、よろしければ GitHub で報告してください。")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #8e8e93;")
        layout.addWidget(desc)

        # 入力項目
        layout.addWidget(QLabel("タイトル"))
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("例: 設定画面が開かない")
        self.title_input.setMinimumHeight(32)
        self.title_input.textChanged.connect(self.update_preview)
        layout.addWidget(self.title_input)

        layout.addWidget(QLabel("詳細"))
        self.details_input = QPlainTextEdit()
        self.details_input.setPlaceholderText("例: 詳細設定ボタンを押すと、エラーが出てアプリが固まってしまいます...")
        self.details_input.textChanged.connect(self.update_preview)
        layout.addWidget(self.details_input, 1)

        # プレビュー
        layout.addWidget(QLabel("送信内容 (詳細) のプレビュー:"))
        self.preview_area = QPlainTextEdit()
        self.preview_area.setReadOnly(True)
        self.preview_area.setPlainText(self.report.to_markdown())
        self.preview_area.setMaximumHeight(100)
        self.preview_area.setStyleSheet("font-family: 'Consolas', 'Monaco', monospace; font-size: 11px;")
        layout.addWidget(self.preview_area)

        # ボタン
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_github = QPushButton("GitHub でissueを開く")
        self.btn_github.setMinimumHeight(40)
        self.btn_github.clicked.connect(self.submit_to_github)

        self.btn_direct = None
        self.btn_api = None
        webhook_url = str(self.cfg.get("error_webhook_url", "")).strip()
        api_url = str(self.cfg.get("error_report_api_url", "")).strip()

        if api_url:
            self.btn_api = QPushButton("ワンクリックでボット報告")
            self.btn_api.setObjectName("SaveBtn") # 目立つ色にする
            self.btn_api.setMinimumHeight(40)
            self.btn_api.clicked.connect(self.submit_to_api)
            btn_layout.addWidget(self.btn_api, 2)
            
            if webhook_url:
                self.btn_direct = QPushButton("Discordへ直接送信")
                self.btn_direct.setMinimumHeight(40)
                self.btn_direct.clicked.connect(self.submit_to_webhook)
                btn_layout.addWidget(self.btn_direct, 1)
            
            btn_layout.addWidget(self.btn_github, 1)
            
        elif webhook_url:
            self.btn_direct = QPushButton("今すぐ報告を送信")
            self.btn_direct.setObjectName("SaveBtn")
            self.btn_direct.setMinimumHeight(40)
            self.btn_direct.clicked.connect(self.submit_to_webhook)
            btn_layout.addWidget(self.btn_direct, 2)
            btn_layout.addWidget(self.btn_github, 1)
        else:
            self.btn_github.setObjectName("SaveBtn")
            btn_layout.addWidget(self.btn_github, 2)

        self.btn_copy = QPushButton("クリップボードにコピー")
        self.btn_copy.setMinimumHeight(40)
        self.btn_copy.clicked.connect(self.copy_to_clipboard)

        self.btn_cancel = QPushButton("キャンセル")
        self.btn_cancel.setMinimumHeight(40)
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(self.btn_copy, 1)
        btn_layout.addWidget(self.btn_cancel, 1)
        layout.addLayout(btn_layout)

    def update_preview(self):
        self.report.title = self.title_input.text()
        self.report.details = self.details_input.toPlainText()
        self.preview_area.setPlainText(self.report.to_markdown())

    def submit_to_webhook(self):
        webhook_url = str(self.cfg.get("error_webhook_url", "")).strip()
        if not webhook_url:
            return
            
        self.btn_direct.setEnabled(False)
        self.btn_direct.setText("送信中...")
        self.report.title = self.title_input.text()
        self.report.details = self.details_input.toPlainText()
        
        success = self.report.send_to_webhook(webhook_url)
        
        if success:
            self.btn_direct.setText("送信完了！")
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "成功", "エラー報告を送信しました。ご協力ありがとうございます！")
            self.accept()
        else:
            self.btn_direct.setEnabled(True)
            self.btn_direct.setText("送信失敗 (再試行)")
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "失敗", "送信に失敗しました。ネットワーク状況を確認するか、GitHub経由でお試しください。")

    def submit_to_api(self):
        url = str(self.cfg.get("error_report_api_url", "")).strip()
        key = str(self.cfg.get("error_report_api_key", "")).strip()
        if not url:
            return
            
        self.btn_api.setEnabled(False)
        self.btn_api.setText("送信中...")
        self.report.title = self.title_input.text()
        self.report.details = self.details_input.toPlainText()
        
        # Webhook URL も引数として渡す
        webhook_url = str(self.cfg.get("error_webhook_url", "")).strip()
        success = self.report.send_to_api(url, key, webhook_url)
        
        if success:
            self.btn_api.setText("報告完了！")
            QMessageBox.information(self, "成功", "独自 API 経由でのボット報告が完了しました！")
            self.accept()
        else:
            self.btn_api.setEnabled(True)
            self.btn_api.setText("送信失敗 (再試行)")
            QMessageBox.warning(self, "失敗", "API への接続に失敗しました。URL や認証キーを確認してください。")

    def submit_to_github(self):
        self.report.title = self.title_input.text()
        self.report.details = self.details_input.toPlainText()
        url = self.report.get_github_issue_url()
        QDesktopServices.openUrl(QUrl(url))
        self.accept()

    def copy_to_clipboard(self):
        self.report.title = self.title_input.text()
        self.report.details = self.details_input.toPlainText()
        clipboard = QApplication.clipboard()
        clipboard.setText(self.report.to_markdown())
        self.btn_copy.setText("コピーしました！")
        QTimer.singleShot(2000, lambda: self.btn_copy.setText("クリップボードにコピー"))
