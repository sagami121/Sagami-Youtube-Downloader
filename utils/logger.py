import logging
from logging.handlers import RotatingFileHandler
import os
import sys
from pathlib import Path

from constants import get_runtime_app_dir, get_config_path

def setup_logger():
    # logging を出力する場所を決定
    # まずは app_dir 内の logs フォルダを試す、書き込めなければ APPDATA 側の logs を使う
    app_dir = get_runtime_app_dir()
    log_dir = app_dir / "logs"
    
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "app.log"
        # 書き込みテスト
        with open(log_file, "a") as _:
            pass
    except Exception:
        # 書き込み権限がない場合などは APPDATA (config.jsonの親) に逃がす
        try:
            cfg_base = get_config_path().parent
            log_dir = cfg_base / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            # それすら失敗したらカレントディレクトリ
            log_dir = Path.cwd() / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            
    log_file = log_dir / "app.log"
    
    logger = logging.getLogger("SagamiDL")
    logger.setLevel(logging.INFO)
    
    # 既存のハンドラーがある場合は重複を避けるためにそのまま利用
    if not logger.handlers:
        # 基本的に 5MB でローテート、5ファイルまで保持
        handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
        formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] [%(funcName)s:%(lineno)d] %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        # エラー出力へも並行して吐く
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
    return logger, str(log_file)

logger, log_file_path = setup_logger()

def get_log_dir() -> Path:
    """現在のロガーが出力しているログディレクトリを返す"""
    return Path(log_file_path).parent

def write_error_log(section: str, values: dict, prefix: str = "error") -> str:
    """互換性のためのエラー出力関数。今後は logger.error を推奨"""
    lines = [f"[{section}]"]
    for key, value in values.items():
        text = str(value).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")
        lines.append(f"{key}={text}")
    payload = "\n".join(lines)
    
    logger.error(f"====== {prefix.upper()} ======\n{payload}\n========================")
    
    # UIにログパスを返す仕様の後方互換維持
    return log_file_path
