import os
import re
import platform
import subprocess
import traceback
from pathlib import Path

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
            "CPU": "取得失敗",
            "GPU": "取得失敗"
        }
        
        def run_pwsh(cmd):
            try:
                # PowerShellを使用して情報を取得 (wmicより確実)
                process = subprocess.Popen(["powershell", "-Command", cmd], 
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                                         text=False, shell=True)
                out, _ = process.communicate(timeout=5)
                # Windowsの日本語環境(cp932)とUTF-8の両方を試す
                for enc in ["cp932", "utf-8", "utf-16"]:
                    try:
                        res = out.decode(enc).strip()
                        if res: return res
                    except Exception: continue
                return ""
            except Exception:
                return ""

        # CPU情報の取得
        cpu_res = run_pwsh("(Get-CimInstance Win32_Processor).Name")
        if cpu_res: info["CPU"] = cpu_res
            
        # GPU情報の取得
        gpu_raw = run_pwsh("(Get-CimInstance Win32_VideoController).Name")
        if gpu_raw:
            # 複数行(複数のGPU)がある場合に対応
            gpu_list = [l.strip() for l in gpu_raw.splitlines() if l.strip()]
            
            # 優先順位付け: 物理GPU(Intel, NVIDIA, AMD, Radeon)を優先
            real_keywords = ["intel", "nvidia", "amd", "radeon", "geforce", "arc"]
            virtual_keywords = ["virtual", "mirror", "basic", "parsec", "microsoft remote"]
            
            def gpu_priority(name):
                name_low = name.lower()
                # 仮想デバイスは最下位(2)
                if any(k in name_low for k in virtual_keywords): return 2
                # 物理ハードウェアは最上位(0)
                if any(k in name_low for k in real_keywords): return 0
                # その他は中間(1)
                return 1
                
            gpu_list.sort(key=gpu_priority)
            
            # 物理GPU(優先度0)が見つかった場合、仮想デバイス(優先度2)をすべて除外する
            has_real_gpu = any(gpu_priority(g) == 0 for g in gpu_list)
            if has_real_gpu:
                gpu_list = [g for g in gpu_list if gpu_priority(g) != 2]
                
            info["GPU"] = ", ".join(gpu_list)
            
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
        if self.details:
            lines.append("## 詳細")
            lines.append(self.details)
            lines.append("")
            
        if include_system_info:
            lines.append("## デバイス情報")
            lines.append(f"- **OS**: `{self.system_info.get('OS', '不明')}`")
            lines.append(f"- **CPU**: `{self.system_info.get('CPU', '不明')}`")
            lines.append(f"- **GPU**: `{self.system_info.get('GPU', '不明')}`")
        
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
        summary = f"【不具合報告】{main_title} (Ver {VERSION})"
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
        payload = {
            "title": self.title or "名称未設定の報告",
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
