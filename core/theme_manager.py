import os
import re
import json
from pathlib import Path
from PySide6.QtWidgets import QWidget, QDialog, QApplication
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPalette

from constants import get_runtime_app_dir
from utils.logger import logger

class ThemeManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self._theme_css_cache = {}
            self._theme_profile_cache = {}
            self._theme_info_cache = {}
            self._theme_options_cache = None
            self._theme_json_cache = {}
            self.initialized = True

    def refresh_cache(self):
        self._theme_css_cache.clear()
        self._theme_profile_cache.clear()
        self._theme_info_cache.clear()
        self._theme_options_cache = None
        self._theme_json_cache.clear()

    def _theme_base_dirs(self):
        app_dir = get_runtime_app_dir()
        current_dir = Path(__file__).parent.parent.resolve()
        bases = [app_dir / "theme", current_dir / "theme"]
        return [b for b in bases if b.exists()]

    def resolve_theme_assets(self, theme: str):
        bases = self._theme_base_dirs()
        css_path = None
        json_path = None
        if theme in ("dark", "light"):
            for base in bases:
                candidate = base / "default" / f"default_{theme}.css"
                if candidate.exists():
                    css_path = candidate
                    json_path = base / "default" / "default.json"
                    break
        elif "_" in theme:
            prefix = theme.split("_", 1)[0]
            for base in bases:
                candidate = base / prefix / f"{theme}.css"
                if candidate.exists():
                    css_path = candidate
                    json_path = base / prefix / f"{prefix}.json"
                    break
        if css_path is None:
            for base in bases:
                try:
                    found = next(base.rglob(f"{theme}.css"))
                    css_path = found
                    json_path = found.parent / f"{found.parent.name}.json"
                    break
                except StopIteration:
                    continue
        return css_path, json_path

    def _read_json_cached(self, path: Path):
        key = str(path)
        if key in self._theme_json_cache:
            return self._theme_json_cache[key]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = None
        self._theme_json_cache[key] = data
        return data

    def get_stylesheet(self, theme="dark", widget_type="main"):
        theme_file, _json_path = self.resolve_theme_assets(str(theme))

        cache_key = f"{theme}:{widget_type}:{theme_file}"
        if cache_key in self._theme_css_cache:
            return self._theme_css_cache[cache_key]

        if theme_file and theme_file.exists():
            try:
                text = theme_file.read_text(encoding="utf-8")
                self._theme_css_cache[cache_key] = text
                return text
            except Exception as e:
                logger.error(f"Failed to read stylesheet {theme_file}: {e}")

        # ファイルが見つからない、またはエラー時の最小限のフォールバック
        if "light" in theme:
            fallback = "QWidget#Main { background-color: #ffffff; } QLabel { color: #333333; }"
        else:
            fallback = "QWidget#Main { background-color: #000000; } QLabel { color: #ffffff; }"
        self._theme_css_cache[cache_key] = fallback
        return fallback

    def parse_theme_metadata(self, theme="dark", widget_type="main"):
        theme_file, _json_path = self.resolve_theme_assets(str(theme))
        
        cache_key = f"{theme}:{widget_type}:meta"
        if cache_key in self._theme_profile_cache:
            cached = self._theme_profile_cache[cache_key]
            return dict(cached) if isinstance(cached, dict) else {}

        colors = {}
        if theme_file and theme_file.exists():
            try:
                content = theme_file.read_text(encoding="utf-8")
                match = re.search(r"METADATA\s*(.*?)\s*END_METADATA", content, re.DOTALL)
                if match:
                    for line in match.group(1).strip().splitlines():
                        if ":" in line:
                            k, v = line.split(":", 1)
                            colors[k.strip()] = v.strip()
            except Exception:
                pass
        self._theme_profile_cache[cache_key] = dict(colors)
        return colors

    def load_theme_profile(self, theme: str):
        if theme in self._theme_profile_cache:
            colors, props = self._theme_profile_cache[theme]
            return dict(colors), dict(props)
        _css_path, json_path = self.resolve_theme_assets(str(theme))
        if json_path and json_path.exists():
            try:
                data = self._read_json_cached(json_path)
                if isinstance(data, dict):
                    profile = data.get(theme) or data.get("default")
                    if isinstance(profile, dict):
                        colors = profile.get("colors") or {}
                        props = profile.get("props") or {}
                        colors = colors if isinstance(colors, dict) else {}
                        props = props if isinstance(props, dict) else {}
                        self._theme_profile_cache[theme] = (dict(colors), dict(props))
                        return dict(colors), dict(props)
            except Exception:
                pass
        self._theme_profile_cache[theme] = ({}, {})
        return {}, {}

    def load_theme_info(self, theme: str):
        if theme in self._theme_info_cache:
            return dict(self._theme_info_cache[theme])
        app_dir = get_runtime_app_dir()
        base = app_dir / "theme"
        if not base.exists():
            base = Path(__file__).parent.parent.resolve() / "theme"
        if not base.exists():
            return {}
        for json_path in base.rglob("*.json"):
            try:
                data = self._read_json_cached(json_path)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            if theme in data and isinstance(data.get("info"), dict):
                info = data.get("info") or {}
                if isinstance(info, dict):
                    self._theme_info_cache[theme] = dict(info)
                    return dict(info)
        self._theme_info_cache[theme] = {}
        return {}

    def scan_theme_options(self):
        if self._theme_options_cache is not None:
            return list(self._theme_options_cache)
        bases = self._theme_base_dirs()
        themes = []
        for base in bases:
            for css_path in base.rglob("*.css"):
                name = css_path.stem
                if css_path.parent.name == "default" and name.startswith("default_"):
                    theme_name = name.replace("default_", "", 1)
                else:
                    theme_name = name
                if theme_name not in themes:
                    themes.append(theme_name)
        if not themes:
            themes = ["dark", "light"]
        self._theme_options_cache = list(themes)
        return list(themes)

    def warm_theme_cache(self, theme: str):
        try:
            self.get_stylesheet(theme, "main")
            self.get_stylesheet(theme, "settings")
            self.load_theme_profile(theme)
        except Exception:
            pass

def get_theme_manager():
    return ThemeManager()

# 後方互換用の関数ラッパー群
def get_stylesheet(theme="dark", widget_type="main"):
    return get_theme_manager().get_stylesheet(theme, widget_type)

def load_theme_profile(theme: str):
    return get_theme_manager().load_theme_profile(theme)

def load_theme_info(theme: str):
    return get_theme_manager().load_theme_info(theme)

def scan_theme_options():
    return get_theme_manager().scan_theme_options()

def apply_titlebar_theme(widget: QWidget, theme: str):
    if os.name != "nt" or widget is None:
        return
    try:
        import ctypes
        hwnd = int(widget.winId())
        use_dark = 1 if "dark" in str(theme) else 0
        value = ctypes.c_int(use_dark)
        # Try Windows 10/11 attribute IDs
        for attr in (20, 19):
            try:
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd,
                    attr,
                    ctypes.byref(value),
                    ctypes.sizeof(value),
                )
            except Exception:
                continue
    except Exception:
        pass

def apply_dialog_theme(dialog: QDialog, theme: str):
    try:
        dialog.setStyleSheet(get_stylesheet(theme, "main"))
        dialog.setAutoFillBackground(True)
        dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        colors, _props = load_theme_profile(theme)
        bg = colors.get("bg")
        if not bg:
            bg = "#000000" if "dark" in theme else "#ffffff"
        base = colors.get("input_bg") or colors.get("card") or bg
        text = colors.get("input_text") or ("#ffffff" if "dark" in theme else "#000000")
        pal = dialog.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(bg))
        pal.setColor(QPalette.ColorRole.Base, QColor(base))
        pal.setColor(QPalette.ColorRole.Text, QColor(text))
        dialog.setPalette(pal)
        apply_titlebar_theme(dialog, theme)
        QTimer.singleShot(0, lambda: apply_titlebar_theme(dialog, theme))
    except Exception:
        pass

def apply_app_theme(app: QApplication, theme: str):
    if app is None:
        return
    try:
        app.setStyleSheet(get_stylesheet(theme, "main"))
        colors, _props = load_theme_profile(theme)
        bg = colors.get("bg")
        if not bg:
            bg = "#000000" if "dark" in theme else "#ffffff"
        base = colors.get("input_bg") or colors.get("card") or bg
        text = colors.get("input_text") or ("#ffffff" if "dark" in theme else "#000000")
        pal = app.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(bg))
        pal.setColor(QPalette.ColorRole.Base, QColor(base))
        pal.setColor(QPalette.ColorRole.Text, QColor(text))
        app.setPalette(pal)
    except Exception:
        pass

def lerp_color(start_color, end_color, progress):
    try:
        start_rgb = tuple(int(start_color[i:i+2], 16) for i in (1, 3, 5))
        end_rgb = tuple(int(end_color[i:i+2], 16) for i in (1, 3, 5))
        
        interpolated = tuple(int(s + (e - s) * progress) for s, e in zip(start_rgb, end_rgb))
        
        return '#{:02x}{:02x}{:02x}'.format(*interpolated)
    except Exception:
        return end_color
