import os
import re
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

from constants import VERSION, APP_GITHUB_REPO_URL

class ErrorReport:
    _cached_info = None

    def __init__(self, exception=None, title="", details=""):
        self.exception = exception
        self.title = title
        self.details = details
        self.system_info = self._collect_system_info()

    def _collect_system_info(self):
        if ErrorReport._cached_info:
            return ErrorReport._cached_info

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
                total_gb = round(mem.total / (1024**3), 1)
                info["RAM"] = f"{total_gb} GB"
            except Exception:
                pass

        # 3. GPU情報の取得 (Multi-layered chain)
        def get_gpu():
            # 3-1. wmic (標準的な方法)
            try:
                out = subprocess.check_output(["wmic", "path", "win32_VideoController", "get", "name"], 
                                           universal_newlines=True, stderr=subprocess.DEVNULL)
                gpus = [l.strip() for l in out.splitlines() if l.strip() and l.strip().lower() != "name"]
                if gpus: return gpus
            except Exception: pass

            # 3-2. レジストリ探索 (wmicが制限されている環境用)
            try:
                # ディスプレイアダプタのクラスIDを指定して検索
                reg_cmd = ["reg", "query", "HKEY_LOCAL_MACHINE\\SYSTEM\\CurrentControlSet\\Control\\Class\\{4d36e968-e325-11ce-bfc1-08002be10318}", "/s", "/v", "DriverDesc"]
                out_raw = subprocess.check_output(reg_cmd, stderr=subprocess.DEVNULL)
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
                subprocess.run(["dxdiag", "/t", str(temp_file)], timeout=15, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
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
        lines = []
        
        # 詳細
        lines.append("## 詳細")
        lines.append(self.details if self.details else "記述なし")
        lines.append("")
        
        # バージョン
        lines.append("## バージョン")
        lines.append(f"`{VERSION}`")
        lines.append("")
        
        # デバイス情報
        if include_system_info:
            lines.append("## デバイス情報")
            lines.append(f"- **OS**: `{self.system_info.get('OS', '不明')}`")
            lines.append(f"- **CPU**: `{self.system_info.get('CPU', '不明')}`")
            lines.append(f"- **GPU**: `{self.system_info.get('GPU', '不明')}`")
            lines.append(f"- **RAM**: `{self.system_info.get('RAM', '不明')}`")
        
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

    def send_to_webhook(self, url: str) -> bool:
        if not url:
            return False
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
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "Sagami-Youtube-Downloader"
                }
            )
            context = None
            if url.startswith("https:"):
                import ssl
                context = ssl._create_unverified_context() if hasattr(ssl, "_create_unverified_context") else None
                
            with urllib.request.urlopen(req, timeout=10, context=context) as response:
                return response.status < 300
        except Exception:
            return False
    def send_to_api(self, api_url: str, api_key: str = "", discord_webhook_url: str = "") -> bool:
        """自作 API (Cloudflare Workers等) 経由でレポートを送信する"""
        if not api_url:
            return False
        import urllib.request
        import json
        
        # サーバー側で使い分けられるように情報を集約して送る
        main_title = self.title.strip() if self.title else "名称未設定の報告"
        payload = {
            "title": main_title,
            "version": VERSION, # アプリのバージョン
            "markdown": self.to_markdown(include_system_info=True),    # OS情報あり (Discord用)
            "markdown_no_sys": self.to_markdown(include_system_info=False), # OS情報なし (GitHub用)
            "discord_webhook_url": discord_webhook_url.strip() if discord_webhook_url else ""
        }
        
        try:
            headers = {
                "Content-Type": "application/json",
                "User-Agent": f"Sagami-Youtube-Downloader/{VERSION}"
            }
            if api_key:
                headers["X-API-Key"] = api_key # 自作サーバーでの認証用
            
            req = urllib.request.Request(
                api_url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST"
            )
            
            context = None
            if api_url.startswith("https:"):
                import ssl
                context = ssl._create_unverified_context() if hasattr(ssl, "_create_unverified_context") else None
            
            # 302 リダイレクト等を考慮 (GAS/Workers等)
            with urllib.request.urlopen(req, timeout=15, context=context) as response:
                status = response.getcode()
                return status < 400
        except Exception:
            return False
