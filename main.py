import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from PySide6.QtCore import qInstallMessageHandler, QTimer

from constants import get_runtime_app_dir
from utils.system import qt_message_filter, resolve_app_icon_path
from core.config_manager import load_config
from core.theme_manager import apply_app_theme, get_theme_manager
from ui.main_window import Main

def main():
    # Qtの内部メッセージをフィルタリング
    qInstallMessageHandler(qt_message_filter)
    
    app = QApplication(sys.argv)
    
    try:
        # 起動時の設定とテーマの読み込み
        startup_cfg = load_config()
        startup_theme = str(startup_cfg.get("theme", "dark"))
        
        # テーマキャッシュの事前読み込みと適用
        tm = get_theme_manager()
        tm.warm_theme_cache(startup_theme)
        apply_app_theme(app, startup_theme)
    except Exception:
        # 設定読み込み失敗時はデフォルトで続行
        pass
        
    # アイコンの設定
    app_dir = get_runtime_app_dir()
    icon_path = resolve_app_icon_path(app_dir)
    if icon_path:
        app.setWindowIcon(QIcon(str(icon_path)))
        
    # メインウィンドウの起動
    window = Main()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
