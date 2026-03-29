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

        # メッセージの切り替え
        if self.context_info == "Manual Report":
            msg = "不具合の報告や、改善のご提案をお聞かせください。"
            sub_msg = "お送りいただいた内容は匿名化され、開発の参考にさせていただきます。よろしければ送信をお願いします。"
        else:
            msg = "アプリでエラーが発生しました。"
            sub_msg = "以下に示す情報は匿名化されており、個人を特定する情報は含まれません。(デバイス情報は公開されません）"

        head = QLabel(msg)
        head.setWordWrap(True)
        head.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(head)

        desc = QLabel(sub_msg)
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #8e8e93;")
        layout.addWidget(desc)

        # テーマに応じた入力欄のスタイル
        is_light = str(self.cfg.get("theme", "dark")) == "light"
        input_style = f"""
            QLineEdit, QPlainTextEdit {{
                background-color: {"#ffffff" if is_light else "#2c2c2e"};
                color: {"#000000" if is_light else "#ffffff"};
                border: 1px solid {"#d1d1d6" if is_light else "#3a3a3c"};
                border-radius: 6px;
                padding: 6px;
            }}
        """

        # 入力項目
        layout.addWidget(QLabel("タイトル"))
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("例: 設定画面が開かない")
        self.title_input.setMinimumHeight(32)
        self.title_input.setStyleSheet(input_style)
        self.title_input.textChanged.connect(self.update_preview)
        layout.addWidget(self.title_input)

        layout.addWidget(QLabel("詳細"))
        self.details_input = QPlainTextEdit()
        self.details_input.setPlaceholderText("例: 詳細設定ボタンを押すと、エラーが出てアプリが固まってしまいます...")
        self.details_input.setStyleSheet(input_style)
        self.details_input.textChanged.connect(self.update_preview)
        layout.addWidget(self.details_input, 1)

        # プレビュー
        layout.addWidget(QLabel("送信内容 (詳細) のプレビュー:"))
        self.preview_area = QPlainTextEdit()
        self.preview_area.setReadOnly(True)
        self.preview_area.setPlainText(self.report.to_markdown())
        self.preview_area.setMinimumHeight(140)
        self.preview_area.setMaximumHeight(250)
        self.preview_area.setStyleSheet("font-family: 'Consolas', 'Monaco', monospace; font-size: 11px; color: #8e8e93; border: 1px solid #333; border-radius: 4px;")
        layout.addWidget(self.preview_area)

        # ボタン
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_direct = None
        self.btn_api = None
        webhook_url = str(self.cfg.get("error_webhook_url", "")).strip()
        api_url = str(self.cfg.get("error_report_api_url", "")).strip()

        if api_url:
            self.btn_api = QPushButton("送信する")
            self.btn_api.setObjectName("SaveBtn") 
            self.btn_api.setMinimumHeight(40)
            self.btn_api.clicked.connect(self.submit_to_api)
            btn_layout.addWidget(self.btn_api, 2)
            
            if webhook_url:
                self.btn_direct = QPushButton("Discordへ直接送信")
                self.btn_direct.setMinimumHeight(40)
                self.btn_direct.clicked.connect(self.submit_to_webhook)
                btn_layout.addWidget(self.btn_direct, 1)
            
            # GitHub ボタンは削除
            
        elif webhook_url:
            self.btn_direct = QPushButton("送信する")
            self.btn_direct.setObjectName("SaveBtn")
            self.btn_direct.setMinimumHeight(40)
            self.btn_direct.clicked.connect(self.submit_to_webhook)
            btn_layout.addWidget(self.btn_direct, 2)
        else:
            # 報告先がない場合はコピーボタンを強調
            pass

        self.btn_cancel = QPushButton("キャンセル")
        self.btn_cancel.setMinimumHeight(40)
        self.btn_cancel.clicked.connect(self.reject)

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
            self.btn_direct.setText("送信完了")
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "成功", "エラー報告を送信しました。ご協力ありがとうございます！")
            self.accept()
        else:
            self.btn_direct.setEnabled(True)
            self.btn_direct.setText("送信失敗 (再試行)")
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "失敗", "送信に失敗しました。ネットワーク状況を確認してください。")

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
            self.btn_api.setText("報告完了")
            QMessageBox.information(self, "成功", "エラー報告を送信しました。ご協力ありがとうございます！")
            self.accept()
        else:
            self.btn_api.setEnabled(True)
            self.btn_api.setText("送信失敗 (再試行)")
            QMessageBox.warning(self, "失敗", "送信に失敗しました。ネットワーク状況を確認してください。")

