import json
import sys
from pathlib import Path

from core.config_manager import get_config_manager
from utils.logger import logger

class LangManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self._lang_cache = {}
            self.initialized = True

    def get_app_dir(self):
        if getattr(sys, "frozen", False):
            return Path(sys.executable).parent
        # This file is in core/lang_manager.py, so app_dir is parent of core
        return Path(__file__).parent.parent.resolve()

    def load_language_dict(self, lang_code: str) -> dict:
        code = (lang_code or "ja").strip().lower()
        if code in self._lang_cache:
            return self._lang_cache[code]

        app_dir = self.get_app_dir()
        lang_dir = app_dir / "language"
        lang_file = lang_dir / f"{code}.json"
        fallback_file = lang_dir / "ja.json"

        data = {}
        try:
            if lang_file.exists():
                data = json.loads(lang_file.read_text(encoding="utf-8-sig"))
            elif fallback_file.exists():
                data = json.loads(fallback_file.read_text(encoding="utf-8-sig"))
        except Exception as e:
            logger.error(f"Failed to load language dict {code}: {e}", exc_info=True)
            data = {}

        if not isinstance(data, dict):
            data = {}
        self._lang_cache[code] = data
        return data

    def i18n(self, key: str, default: str) -> str:
        cfg = get_config_manager().cfg
        lang_code = str(cfg.get("language", "ja"))
        data = self.load_language_dict(lang_code)
        value = data.get(key, default)
        return str(value) if value is not None else default

# アクセス用
def get_lang_manager():
    return LangManager()

def load_language_dict(lang_code: str) -> dict:
    return get_lang_manager().load_language_dict(lang_code)

def i18n(cfg: dict, key: str, default: str) -> str:
    lang_code = str((cfg or {}).get("language", "ja"))
    data = get_lang_manager().load_language_dict(lang_code)
    value = data.get(key, default)
    return str(value) if value is not None else default
