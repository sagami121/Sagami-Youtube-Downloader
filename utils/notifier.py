"""
ダウンロード完了時のデスクトップ通知ユーティリティ。
PySide6の QSystemTrayIcon を使用してクロスプラットフォーム対応。
"""
import os
import sys
from pathlib import Path
from PySide6.QtWidgets import QSystemTrayIcon, QApplication
from PySide6.QtGui import QIcon

from constants import get_runtime_app_dir
from utils.system import resolve_app_icon_path


_tray_icon: QSystemTrayIcon | None = None
_pending_filepath: str | None = None


def _on_tray_clicked():
    """通知クリック時の動作（バックアップ用）"""
    global _pending_filepath
    if _pending_filepath and os.path.exists(_pending_filepath):
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(_pending_filepath))


def _get_tray_icon() -> QSystemTrayIcon | None:
    """シングルトンでシステムトレイアイコンを取得/作成する"""
    global _tray_icon
    if _tray_icon is not None:
        return _tray_icon

    app = QApplication.instance()
    if app is None:
        return None

    if not QSystemTrayIcon.isSystemTrayAvailable():
        return None

    _tray_icon = QSystemTrayIcon(app)
    _tray_icon.messageClicked.connect(_on_tray_clicked)
    
    # アプリアイコンを設定
    icon_path = resolve_app_icon_path(get_runtime_app_dir())
    if icon_path:
        _tray_icon.setIcon(QIcon(str(icon_path)))
    else:
        # フォールバック: アプリのウィンドウアイコンを使用
        if app.windowIcon() and not app.windowIcon().isNull():
            _tray_icon.setIcon(app.windowIcon())
    
    return _tray_icon


def send_notification(title: str, message: str, icon_type: QSystemTrayIcon.MessageIcon = QSystemTrayIcon.MessageIcon.Information, duration_ms: int = 5000, filepath: str | None = None):
    """
    デスクトップ通知（トースト）を送信する。
    
    Args:
        title: 通知のタイトル
        message: 通知の本文
        icon_type: アイコンの種類 (Information, Warning, Critical, NoIcon)
        duration_ms: 表示時間（ミリ秒）
        filepath: クリック時に開くファイルのパス
    """
    global _pending_filepath
    _pending_filepath = filepath

    tray = _get_tray_icon()
    if tray is None:
        return

    # トレイアイコンを一時的に表示して通知を送信
    was_visible = tray.isVisible()
    if not was_visible:
        tray.show()

    if not was_visible:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(150, lambda: tray.showMessage(title, message, icon_type, duration_ms))
    else:
        tray.showMessage(title, message, icon_type, duration_ms)


def notify_download_complete(heading: str, body: str, success: bool = True, filepath: str | None = None):
    """
    ダウンロード完了通知を送信する。
    
    Args:
        heading: 通知のタイトル（翻訳済み）
        body: 通知の本文（翻訳済み）
        success: 成功したかどうか
        filepath: ダウンロードされたファイルのパス
    """
    icon = QSystemTrayIcon.MessageIcon.Information if success else QSystemTrayIcon.MessageIcon.Warning
    send_notification(heading, body, icon, filepath=filepath)
