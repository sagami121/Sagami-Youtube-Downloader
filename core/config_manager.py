import os
import json
from pathlib import Path

from constants import get_config_path, get_history_path
from utils.logger import logger

class ConfigManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.cfg = self._load_config()
            self.history = self._load_history()
            self.initialized = True

    def _load_dotenv(self):
        """プロジェクトルートの .env および環境別設定ファイルを読み込む"""
        # 読み込む順番 (後ろほど優先順位が高い)
        env_files = [".env", ".env.Production_environment"]
        env_vars = {}
        
        for filename in env_files:
            env_path = os.path.join(os.getcwd(), filename)
            if os.path.exists(env_path):
                try:
                    with open(env_path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line or line.startswith("#"):
                                continue
                            if "=" in line:
                                parts = line.split("=", 1)
                                key = parts[0].strip()
                                val = parts[1].strip().strip("'").strip('"')
                                env_vars[key] = val
                except Exception as e:
                    logger.error(f"Error loading {filename}: {e}")
        return env_vars

    def _load_config(self):
        default_path = ""
        downloads_path = os.path.join(os.path.expanduser("~"), "Downloads")
        cfg_path = get_config_path()
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                if "path" not in cfg:
                    cfg["path"] = default_path
                elif str(cfg.get("path", "")).strip() == downloads_path:
                    cfg["path"] = default_path
                if "theme" not in cfg:
                    cfg["theme"] = "dark"
                if "language" not in cfg:
                    cfg["language"] = "ja"
                if "embed_thumbnail" not in cfg:
                    cfg["embed_thumbnail"] = False
                if "video_quality" not in cfg:
                    cfg["video_quality"] = "Best"
                if "video_fps" not in cfg:
                    cfg["video_fps"] = "Any"
                if "audio_quality" not in cfg:
                    cfg["audio_quality"] = "0"
                if "time_range_input" not in cfg:
                    cfg["time_range_input"] = ""
                if "app_update_source_url" not in cfg:
                    cfg["app_update_source_url"] = ""
                if "cookies_browser" not in cfg:
                    cfg["cookies_browser"] = "none"
                if "proxy_url" not in cfg:
                    cfg["proxy_url"] = ""
                if "embed_subtitles" not in cfg:
                    cfg["embed_subtitles"] = False
                if "error_webhook_url" not in cfg:
                    cfg["error_webhook_url"] = ""
                if "developer_mode" not in cfg:
                    cfg["developer_mode"] = False
                if "error_report_api_url" not in cfg:
                    cfg["error_report_api_url"] = ""
                if "error_report_api_key" not in cfg:
                    cfg["error_report_api_key"] = ""
                
                # .env によるオーバーライド (開発者設定)
                dot_env = self._load_dotenv()
                if "ERROR_REPORT_API_URL" in dot_env:
                    cfg["error_report_api_url"] = dot_env["ERROR_REPORT_API_URL"]
                if "ERROR_REPORT_API_KEY" in dot_env:
                    cfg["error_report_api_key"] = dot_env["ERROR_REPORT_API_KEY"]
                if "ERROR_WEBHOOK_URL" in dot_env:
                    cfg["error_webhook_url"] = dot_env["ERROR_WEBHOOK_URL"]
                
                return cfg
        except (FileNotFoundError, json.JSONDecodeError):
            defaults = {
                "format": "mp4",
                "template": "%(title)s",
                "path": default_path,
                "theme": "dark",
                "language": "ja",
                "embed_thumbnail": False,
                "video_quality": "Best",
                "video_fps": "Any",
                "audio_quality": "0",
                "time_range_input": "",
                "app_update_source_url": "",
                "cookies_browser": "none",
                "proxy_url": "",
                "embed_subtitles": False,
                "error_webhook_url": "",
                "auto_send_reports": False,
                "developer_mode": False,
                "error_report_api_url": "",
                "error_report_api_key": "",
            }
            self._save_config_file(defaults)
            return defaults

    def _save_config_file(self, cfg):
        cfg_path = get_config_path()
        try:
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Failed to save config: {e}", exc_info=True)

    def save_config(self):
        self._save_config_file(self.cfg)

    def _load_history(self) -> list:
        path = get_history_path()
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"Failed to load history: {e}", exc_info=True)
            return []

    def save_history(self, history: list = None):
        if history is not None:
            self.history = history
        path = get_history_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.history, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Failed to save history: {e}", exc_info=True)

# ユーティリティ関数（後方互換用）
def get_config_manager():
    return ConfigManager()

def load_config():
    return get_config_manager().cfg

def save_config(cfg):
    cm = get_config_manager()
    cm.cfg = cfg
    cm.save_config()

def load_history() -> list:
    return get_config_manager().history

def save_history(history: list):
    get_config_manager().save_history(history)
