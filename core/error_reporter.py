import os
import re
import json
import platform
import subprocess
import traceback
from pathlib import Path

try:
    import psutil
    import cpuinfo
except ImportError:
    psutil = None
    cpuinfo = None

from constants import VERSION, APP_GITHUB_REPO_URL, get_config_path

# subprocessでコンソールウィンドウを非表示にするためのフラグ
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

def _get_device_cache_path() -> Path:
    """デバイス情報キャッシュファイルのパスを返す"""
    return get_config_path().parent / "device_info_cache.json"

def _load_device_cache() -> dict | None:
    """キャッシュファイルからデバイス情報を読み込む。無ければNone"""
    try:
        cache_path = _get_device_cache_path()
        if cache_path.exists():
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 必要なキーが揃っているか確認
            if all(k in data for k in ("OS", "CPU", "GPU", "RAM")):
                return data
    except Exception:
        pass
    return None

def _save_device_cache(info: dict):
    """デバイス情報をキャッシュファイルに保存する"""
    try:
        cache_path = _get_device_cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

class ErrorReport:
    _cached_info = None

    def __init__(self, exception=None, title="", details="", cfg=None):
        self.exception = exception
        self.title = title
        self.details = details
        self.cfg = cfg or {}
        self.system_info = self._collect_system_info()

    def _collect_system_info(self):
        if ErrorReport._cached_info:
            return ErrorReport._cached_info

        # まずファイルキャッシュから読み込みを試みる（wmic等を起動しない）
        cached = _load_device_cache()
        if cached:
            ErrorReport._cached_info = cached
            return cached

        info = {
            "OS": f"{platform.system()} {platform.release()} ({platform.machine()})",
            "CPU": "情報の取得に失敗",
            "GPU": "情報の取得に失敗",
            "RAM": "不明"
        }
        
        # 1. CPU情報の取得 (py-cpuinfoを使用)
        if cpuinfo:
            try:
                c_info = cpuinfo.get_cpu_info()
                cpu_name = c_info.get('brand_raw') or c_info.get('brand')
                if cpu_name:
                    info["CPU"] = str(cpu_name)
            except Exception:
                pass
        
        # 2. メモリ情報の取得 (psutilを使用)
        if psutil:
            try:
                mem = psutil.virtual_memory()
                raw_gb = mem.total / (1024**3)
                # 標準的な物理RAM容量に切り上げ (psutilはOS利用可能量を返すため少し小さい)
                standard_sizes = [1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128, 256, 512]
                total_gb = round(raw_gb)
                for size in standard_sizes:
                    if raw_gb <= size:
                        total_gb = size
                        break
                info["RAM"] = f"{total_gb} GB"
            except Exception:
                pass

        # 3. GPU情報の取得 (Multi-layered chain)
        def get_gpu():
            # 3-1. wmic (標準的な方法) — CREATE_NO_WINDOW でコンソール非表示
            try:
                out = subprocess.check_output(
                    ["wmic", "path", "win32_VideoController", "get", "name"], 
                    universal_newlines=True, stderr=subprocess.DEVNULL,
                    creationflags=_NO_WINDOW)
                gpus = [l.strip() for l in out.splitlines() if l.strip() and l.strip().lower() != "name"]
                if gpus: return gpus
            except Exception: pass

            # 3-2. レジストリ探索 (wmicが制限されている環境用)
            try:
                # ディスプレイアダプタのクラスIDを指定して検索
                reg_cmd = ["reg", "query", "HKEY_LOCAL_MACHINE\\SYSTEM\\CurrentControlSet\\Control\\Class\\{4d36e968-e325-11ce-bfc1-08002be10318}", "/s", "/v", "DriverDesc"]
                out_raw = subprocess.check_output(reg_cmd, stderr=subprocess.DEVNULL,
                                                  creationflags=_NO_WINDOW)
                # エンコーディングの判定
                out_text = ""
                for enc in ["cp932", "utf-8", "utf-16"]:
                    try:
                        out_text = out_raw.decode(enc)
                        break
                    except Exception: continue
                
                if out_text:
                    # DriverDescの後ろの情報を抽出
                    gpus = []
                    for line in out_text.splitlines():
                        if "DriverDesc" in line:
                            parts = line.split("REG_SZ")
                            if len(parts) > 1:
                                desc = parts[1].strip()
                                if desc and desc not in gpus:
                                    gpus.append(desc)
                    if gpus: return gpus
            except Exception: pass

            # 3-3. dxdiag (最終手段)
            try:
                # 診断に時間がかかるため、バックグラウンドで一時ファイルに出力して解析
                temp_file = Path(os.environ.get("TEMP", ".")) / "gpu_check.txt"
                subprocess.run(["dxdiag", "/t", str(temp_file)], timeout=15,
                               stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               creationflags=_NO_WINDOW)
                if temp_file.exists():
                    with open(temp_file, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        match = re.search(r"Card name: (.+)", content)
                        if match: 
                            gpu = match.group(1).strip()
                            try: temp_file.unlink() # 掃除
                            except: pass
                            return [gpu]
            except Exception: pass
            
            return []

        gpus = get_gpu()
        if gpus:
            # 優先順位付けと仮想デバイスの除外 (既存ロジック転用)
            real_keywords = ["intel", "nvidia", "amd", "radeon", "geforce", "arc", "rtx", "gtx"]
            virtual_keywords = ["virtual", "mirror", "basic", "parsec", "remote", "citrix"]
            
            def gpu_priority(name):
                nl = name.lower()
                if any(k in nl for k in virtual_keywords): return 2
                if any(k in nl for k in real_keywords): return 0
                return 1
                
            gpus.sort(key=gpu_priority)
            has_real = any(gpu_priority(g) == 0 for g in gpus)
            if has_real:
                gpus = [g for g in gpus if gpu_priority(g) != 2]
                
            info["GPU"] = ", ".join(gpus)

        ErrorReport._cached_info = info
        # ファイルに永続化 → 次回起動時はwmic等を起動しない
        _save_device_cache(info)
        return info



    def _anonymize(self, text: str) -> str:
        if not text:
            return ""
        
        # 1. ユーザー名のパス部分を丸ごとマスク (C:\Users\Name)
        # 大文字小文字を区別せず、パスコンポーネントとしてマッチさせる
        res = text
        user_profile = os.environ.get("USERPROFILE")
        if user_profile:
            username = os.path.basename(user_profile)
            if username:
                # \b (単語の境界) を使うことで、sagam は置換し、sagami は置換しないようにする
                pattern = re.compile(rf"\b{re.escape(username)}\b", re.IGNORECASE)
                res = pattern.sub("<USER>", res)
        
        # 2. それでも漏れる場合の汎用的な C:\Users パターンのマスク
        res = re.sub(r"([Cc]:\\Users\\)([^\\]+)", r"\1<USER>", res)
        
        # 3. URLのマスク
        res = re.sub(r"(https?://(?:www\.)?youtube\.com/watch\?v=)[^&\s]+", r"\1<VIDEO_ID>", res)
        res = re.sub(r"(https?://(?:www\.)?youtu\.be/)[^?\s]+", r"\1<VIDEO_ID>", res)
        
        return res

    def to_markdown(self, include_system_info=True) -> str:
        from core.lang_manager import i18n
        lbl_details = i18n(self.cfg, "report.md_details", "詳細")
        lbl_none = i18n(self.cfg, "report.md_none", "記述なし")
        lbl_version = i18n(self.cfg, "report.md_version", "バージョン")
        lbl_device = i18n(self.cfg, "report.md_device", "デバイス情報")
        lbl_unknown = i18n(self.cfg, "common.unknown", "不明")
        lbl_fail = i18n(self.cfg, "report.md_fetch_fail", "情報の取得に失敗")
        
        lines = []
        
        # 詳細
        lines.append(f"## {lbl_details}")
        lines.append(self.details if self.details else lbl_none)
        lines.append("")
        
        # バージョン
        lines.append(f"## {lbl_version}")
        lines.append(f"`{VERSION}`")
        lines.append("")
        
        # デバイス情報
        if include_system_info:
            lines.append(f"## {lbl_device}")
            lines.append(f"- **OS**: `{self.system_info.get('OS', lbl_unknown)}`")
            
            cpu = self.system_info.get('CPU', lbl_unknown)
            cpu = lbl_fail if cpu == "情報の取得に失敗" else cpu
            lines.append(f"- **CPU**: `{cpu}`")
            
            gpu = self.system_info.get('GPU', lbl_unknown)
            gpu = lbl_fail if gpu == "情報の取得に失敗" else gpu
            lines.append(f"- **GPU**: `{gpu}`")
            
            ram = self.system_info.get('RAM', lbl_unknown)
            ram = lbl_unknown if ram == "不明" else ram
            lines.append(f"- **RAM**: `{ram}`")
        
        return "\n".join(lines)

    def get_github_issue_url(self) -> str:
        import urllib.parse
        base_url = APP_GITHUB_REPO_URL.rstrip("/") + "/issues/new"
        
        # タイトルをそのまま使用
        main_title = self.title.strip() if self.title else "名称未設定の報告"
        title = f"【不具合報告】{main_title}"
            
        body = self.to_markdown(include_system_info=False)
        params = {
            "title": title,
            "body": body,
            "labels": "bug,report-jp"
        }
        return base_url + "?" + urllib.parse.urlencode(params)

    def _log_network_error(self, context: str, error: str, response_body: str = ""):
        """詳細なネットワークエラーログを出力する"""
        try:
            import datetime
            from constants import get_runtime_app_dir
            log_dir = get_runtime_app_dir() / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "network_debug.log"
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[{now}] [{context}] Error: {error}\n")
                if response_body:
                    body_preview = response_body[:500] + ("..." if len(response_body) > 500 else "")
                    f.write(f"  Response: {body_preview}\n")
        except Exception:
            pass


    def _get_ssl_context(self, url: str):
        """SSLコンテキストを取得する (検証エラー回避用)"""
        if url.startswith("https:"):
            import ssl
            try:
                # ユーザーの環境によっては証明書エラーが出ることがあるため、便宜上検証をスキップするオプションも考慮
                return ssl._create_unverified_context()
            except AttributeError:
                return None
        return None

    def send_to_webhook(self, url: str) -> tuple[bool, str]:
        if not url:
            return False, "URLが空です"
        import urllib.request
        import json
        
        # タイトル生成
        main_title = self.title.strip() if self.title else "名称未設定の報告"
        summary = f"【不具合報告】{main_title}"
        content = self.to_markdown()
        
        # Discord Embed 制限 (4096文字) に対応
        if len(content) > 3800:
            content = content[:3800] + "\n\n... (以下省略)"
            
        payload = {
            "username": "Sagami youtube Downloader",
            "embeds": [
                {
                    "title": summary,
                    "description": content,
                    "color": 15158332, # 鮮やかな赤
                }
            ]
        }
        
        try:
            headers = {
                "User-Agent": "Sagami-Youtube-Downloader"
            }
            
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
                
            req = urllib.request.Request(url, data=data, headers=headers)
            
            context = None
            if url.startswith("https:"):
                import ssl
                context = ssl._create_unverified_context() if hasattr(ssl, "_create_unverified_context") else None
                
            with urllib.request.urlopen(req, timeout=40, context=context) as response:
                if response.status < 300:
                    return True, "Success"
                return False, f"HTTP Error {response.status}"
        except Exception as e:
            err_msg = str(e)
            try:
                if hasattr(e, 'read'):
                    err_msg += f" | Response: {e.read().decode('utf-8', errors='ignore')}"
            except: pass
            self._log_network_error("send_to_webhook", err_msg)
            return False, err_msg
    def send_to_api(self, api_url: str, api_key: str = "", discord_webhook_url: str = "") -> tuple[bool, str]:
        """自作 API (Cloudflare Workers等) 経由でレポートを送信する"""
        if not api_url:
            return False, "API URLが空です"
        import urllib.request
        import json
        
        # サーバー側で使い分けられるように情報を集約して送る
        main_title = self.title.strip() if self.title else "名称未設定の報告"
        payload = {
            "title": main_title,
            "version": VERSION,
            "markdown": self.to_markdown(include_system_info=True),
            "markdown_no_sys": self.to_markdown(include_system_info=False),
            "discord_webhook_url": discord_webhook_url.strip() if discord_webhook_url else ""
        }
        
        try:
            headers = {
                "User-Agent": f"Sagami-Youtube-Downloader/{VERSION}"
            }
            if api_key:
                headers["X-API-Key"] = api_key 
            
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
            
            req = urllib.request.Request(api_url, data=data, headers=headers, method="POST")
            
            context = self._get_ssl_context(api_url)
            
            with urllib.request.urlopen(req, timeout=45, context=context) as response:
                status = response.getcode()
                res_body = response.read().decode('utf-8', errors='ignore')
                
                # レスポンスが成功(2xx)でも中身がエラーの場合を考慮
                try:
                    res_json = json.loads(res_body)
                    if not res_json.get("success", True):
                        self._log_network_error("send_to_api", "Worker returned success:false", res_body)
                        return False, f"Worker Error: {res_json.get('error', 'Unknown error')}"
                except:
                    pass

                if status >= 400:
                    self._log_network_error("send_to_api", f"Server returned {status}", res_body)
                    return False, f"API Error {status}: {res_body}"
                
                return True, "Success"
        except Exception as e:
            err_msg = str(e)
            # Responseオブジェクトが含まれている場合はその内容も取得を試みる
            if hasattr(e, 'read'):
                try:
                    res_content = e.read().decode('utf-8', errors='ignore')
                    err_msg += f" | Body: {res_content}"
                    self._log_network_error("send_to_api", f"Exception with body: {str(e)}", res_content)
                except: pass
            else:
                self._log_network_error("send_to_api", err_msg)
            return False, err_msg
