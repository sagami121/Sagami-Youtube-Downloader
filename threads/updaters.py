import os
import sys
import subprocess
import shutil
import urllib.request
import urllib.error
import urllib.parse
import ssl
import json
import re
import tempfile
from pathlib import Path
from PySide6.QtCore import QThread, Signal

from constants import VERSION
from utils.system import _ensure_executable
from utils.formatting import is_newer_version
from utils.binary_resolver import resolve_yt_dlp_command, ensure_windows_binaries, get_user_bin_dir


# ---------------------------------------------------------------------------
# 共通ミックスイン
# ---------------------------------------------------------------------------

class _YtDlpMixin:
    """YtDlpUpdateThread / YtDlpCheckThread で共有するヘルパー"""

    def _create_flags(self) -> int:
        return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    def _get_version(self, yt_cmd: list) -> str:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        try:
            process = subprocess.run(
                yt_cmd + ["--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=self._create_flags(),
                env=env,
            )
            if process.returncode == 0:
                ver = (process.stdout or "").strip()
                if ver:
                    return ver.splitlines()[-1].strip()
        except Exception:
            pass
        return "不明"


# ---------------------------------------------------------------------------
# YtDlpUpdateThread
# ---------------------------------------------------------------------------

class YtDlpUpdateThread(_YtDlpMixin, QThread):
    # (ok, state, before_version, after_version, output)
    completed = Signal(bool, str, str, str, str)

    def _is_pypi_update_hint(self, text: str) -> bool:
        body = (text or "").lower()
        return (
            "you installed yt-dlp with pip" in body
            or "wheel from pypi" in body
            or "use that to update" in body
        )

    def _run_pip_update(self):
        candidates = []
        if sys.executable:
            candidates.append([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"])
        candidates.append(["python", "-m", "pip", "install", "-U", "yt-dlp"])
        if os.name == "nt":
            candidates.append(["py", "-m", "pip", "install", "-U", "yt-dlp"])

        logs = []
        for cmd in candidates:
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=self._create_flags(),
                )
                out, _ = proc.communicate()
                logs.append(f"$ {' '.join(cmd)}\n{(out or '').strip()}")
                if proc.returncode == 0:
                    return True, "\n\n".join(logs)
            except Exception as e:
                logs.append(f"$ {' '.join(cmd)}\n実行エラー: {e}")

        return False, "\n\n".join(logs)

    def _update_packaged(self, yt_cmd: list, before_version: str):
        """
        パッケージ版の更新処理。
        管理者権限不要な APPDATA フォルダにダウンロードして差し替える。
        """
        if sys.platform == "win32":
            url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
            exe_name = "yt-dlp.exe"
        elif sys.platform == "darwin":
            url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos"
            exe_name = "yt-dlp"
        else:
            url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
            exe_name = "yt-dlp"

        # 書き込み先は常に APPDATA（管理者権限不要）
        user_bin_dir = get_user_bin_dir()
        user_bin_dir.mkdir(parents=True, exist_ok=True)
        dest_path = user_bin_dir / exe_name

        # 同じフォルダの一時ファイルにダウンロードしてからアトミックに移動
        fd, tmp_str = tempfile.mkstemp(suffix=".tmp", dir=user_bin_dir)
        os.close(fd)
        tmp_path = Path(tmp_str)

        try:
            context = (
                ssl._create_unverified_context()
                if hasattr(ssl, "_create_unverified_context")
                else None
            )
            with urllib.request.urlopen(url, context=context, timeout=60) as resp, \
                    open(tmp_path, "wb") as out_file:
                out_file.write(resp.read())

            if dest_path.exists():
                dest_path.unlink()
            shutil.move(str(tmp_path), str(dest_path))

        except Exception:
            raise
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass

        if os.name != "nt":
            _ensure_executable(dest_path)

        output = f"GitHubからバイナリを更新しました\n保存先: {dest_path}"
        return output

    def run(self):
        yt_cmd = resolve_yt_dlp_command()
        if yt_cmd is None:
            self.completed.emit(False, "failed", "不明", "不明", "yt-dlp が見つかりません。")
            return

        try:
            before_version = self._get_version(yt_cmd)

            if getattr(sys, "frozen", False) or "__compiled__" in globals():
                # ---- パッケージ版: APPDATA へバイナリを直接ダウンロード ----
                try:
                    output = self._update_packaged(yt_cmd, before_version)
                    process_returncode = 0
                except PermissionError as e:
                    self.completed.emit(False, "failed", before_version, before_version,
                                        f"権限エラー: {e}")
                    return
                except Exception as e:
                    self.completed.emit(False, "failed", before_version, before_version,
                                        f"yt-dlp 更新エラー: {e}")
                    return
            else:
                # ---- Python モジュール版: yt-dlp -U ----
                process = subprocess.Popen(
                    yt_cmd + ["-U"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=self._create_flags(),
                )
                output, _ = process.communicate()
                process_returncode = process.returncode

                if process_returncode != 0 and self._is_pypi_update_hint(output):
                    pip_ok, pip_output = self._run_pip_update()
                    output = (output or "") + "\n\n[pip fallback]\n" + (pip_output or "")
                    if pip_ok:
                        process_returncode = 0

            # 更新後のバージョンを取得（APPDATAのバイナリが優先されるので再解決）
            new_cmd = resolve_yt_dlp_command()
            after_version = self._get_version(new_cmd) if new_cmd else before_version

            if process_returncode == 0:
                state = "up_to_date" if before_version == after_version else "updated"
                self.completed.emit(True, state, before_version, after_version, output)
            else:
                self.completed.emit(False, "failed", before_version, after_version, output)

        except Exception as e:
            self.completed.emit(False, "failed", "不明", "不明", f"yt-dlp 更新エラー: {e}")


# ---------------------------------------------------------------------------
# YtDlpCheckThread
# ---------------------------------------------------------------------------

class YtDlpCheckThread(_YtDlpMixin, QThread):
    # (ok, state, current_version, latest_version, output)
    completed = Signal(bool, str, str, str, str)

    def _fetch_latest_version(self) -> str:
        latest_url = "https://github.com/yt-dlp/yt-dlp/releases/latest"
        req = urllib.request.Request(
            latest_url, headers={"User-Agent": "Sagami-Youtube-Downloader"}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            final_url = response.geturl()
        parsed = urllib.parse.urlparse(final_url)
        parts = (parsed.path or "").strip("/").split("/")
        if len(parts) >= 4 and parts[-2] == "tag":
            return parts[-1]
        return ""

    def run(self):
        yt_cmd = resolve_yt_dlp_command()
        if yt_cmd is None:
            self.completed.emit(False, "failed", "不明", "不明", "yt-dlp が見つかりません。")
            return

        try:
            current_version = self._get_version(yt_cmd)
            latest_version = self._fetch_latest_version()
            if not latest_version:
                self.completed.emit(
                    False, "failed", current_version, current_version,
                    "最新バージョンの取得に失敗しました。"
                )
                return

            if current_version and current_version != "不明" and \
                    is_newer_version(latest_version, current_version):
                self.completed.emit(True, "update_available", current_version, latest_version, "")
            else:
                self.completed.emit(True, "up_to_date", current_version, latest_version, "")

        except Exception as e:
            self.completed.emit(False, "failed", "不明", "不明", str(e))


# ---------------------------------------------------------------------------
# BinariesEnsureThread
# ---------------------------------------------------------------------------

class BinariesEnsureThread(QThread):
    status = Signal(str)
    done = Signal(bool, str)

    def run(self):
        try:
            ok, msg = ensure_windows_binaries(self.status.emit)
        except Exception as e:
            ok, msg = False, str(e)
        self.done.emit(ok, msg)


# ---------------------------------------------------------------------------
# AppUpdateThread
# ---------------------------------------------------------------------------

class AppUpdateThread(QThread):
    completed = Signal(bool, str, str, str, str, str, str, str)

    def __init__(self, source_url: str):
        super().__init__()
        self.source_url = (source_url or "").strip()

    def _github_latest_release_api(self, url: str) -> str:
        text = (url or "").strip().rstrip("/")
        match = re.match(r"^https?://github\.com/([^/]+)/([^/]+)$", text)
        if not match:
            raise ValueError("GitHubリポジトリURLの形式が不正です。")
        owner, repo = match.group(1), match.group(2)
        return f"https://api.github.com/repos/{owner}/{repo}/releases/latest"

    def _github_tags_api(self, url: str) -> str:
        text = (url or "").strip().rstrip("/")
        match = re.match(r"^https?://github\.com/([^/]+)/([^/]+)$", text)
        if not match:
            raise ValueError("GitHubリポジトリURLの形式が不正です。")
        owner, repo = match.group(1), match.group(2)
        return f"https://api.github.com/repos/{owner}/{repo}/tags"

    def _http_get_json(self, url: str):
        req = urllib.request.Request(url, headers={"User-Agent": "Sagami-Youtube-Downloader"})
        with self._urlopen_with_ssl_fallback(req, url, timeout=10) as response:
            payload = response.read().decode("utf-8")
        return json.loads(payload)

    def _http_get_text(self, url: str):
        req = urllib.request.Request(url, headers={"User-Agent": "Sagami-Youtube-Downloader"})
        with self._urlopen_with_ssl_fallback(req, url, timeout=10) as response:
            payload = response.read().decode("utf-8", errors="replace")
            final_url = response.geturl()
        return payload, final_url

    def _is_known_update_host(self, url: str) -> bool:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
        trusted_suffixes = ("github.com", "githubusercontent.com", "githubassets.com")
        return any(host == s or host.endswith("." + s) for s in trusted_suffixes)

    def _urlopen_with_ssl_fallback(self, req, url: str, timeout: int = 10):
        def _is_ssl_error(exc):
            if isinstance(exc, ssl.SSLCertVerificationError):
                return True
            if isinstance(exc, urllib.error.URLError):
                return isinstance(getattr(exc, "reason", None), ssl.SSLCertVerificationError)
            return False

        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except Exception as first_error:
            if not _is_ssl_error(first_error):
                raise
            try:
                import certifi
                ctx = ssl.create_default_context(cafile=certifi.where())
                return urllib.request.urlopen(req, timeout=timeout, context=ctx)
            except Exception as second_error:
                if not _is_ssl_error(second_error):
                    raise
            if self._is_known_update_host(url):
                insecure_ctx = ssl._create_unverified_context()
                return urllib.request.urlopen(req, timeout=timeout, context=insecure_ctx)
            raise first_error

    def _pick_installer_asset_url(self, release_data: dict) -> str:
        assets = release_data.get("assets") or []
        urls = []
        for item in assets:
            name = str(item.get("name", "")).lower()
            url = str(item.get("browser_download_url", "")).strip()
            if url and (name.endswith(".exe") or name.endswith(".msi")):
                urls.append((name, url))
        if not urls:
            return ""
        preferred = [u for u in urls if ("setup" in u[0] or "installer" in u[0])]
        return (preferred[0] if preferred else urls[0])[1]

    def _github_release_latest_page(self, url: str) -> str:
        text = (url or "").strip().rstrip("/")
        match = re.match(r"^https?://github\.com/([^/]+)/([^/]+)$", text)
        if not match:
            raise ValueError("GitHubリポジトリURLの形式が不正です。")
        owner, repo = match.group(1), match.group(2)
        return f"https://github.com/{owner}/{repo}/releases/latest"

    def _extract_version_from_release_url(self, url: str) -> str:
        if not url:
            return ""
        parsed = urllib.parse.urlparse(url)
        parts = (parsed.path or "").strip("/").split("/")
        if len(parts) >= 4 and parts[-2] == "tag":
            return parts[-1]
        return ""

    def _pick_installer_from_html(self, html: str, base_url: str) -> str:
        if not html:
            return ""
        hrefs = re.findall(r'href="([^"]+)"', html, flags=re.IGNORECASE)
        urls = []
        for href in hrefs:
            if not href:
                continue
            full = ("https://github.com" + href) if href.startswith("/") else href
            if not full.startswith("http"):
                continue
            low = full.lower()
            if not (low.endswith(".exe") or low.endswith(".msi")):
                continue
            if "/releases/download/" not in low:
                continue
            urls.append((low.split("/")[-1], full))
        if not urls:
            return ""
        preferred = [u for u in urls if ("setup" in u[0] or "installer" in u[0])]
        return (preferred[0] if preferred else urls[0])[1]

    def _load_release(self):
        if not self.source_url:
            raise ValueError("更新元URLが未設定です。")
        try:
            data = self._http_get_json(self._github_latest_release_api(self.source_url))
            latest_version = str(data.get("tag_name", "")).strip()
            release_page_url = str(data.get("html_url", "")).strip()
            installer_url = self._pick_installer_asset_url(data)
            notes = str(data.get("body", "")).strip()
            published_at = str(data.get("published_at", "")).strip()
            if latest_version:
                return latest_version, release_page_url, notes, published_at, installer_url
        except urllib.error.HTTPError as e:
            if getattr(e, "code", None) in (403, 429):
                try:
                    latest_page = self._github_release_latest_page(self.source_url)
                    html, final_url = self._http_get_text(latest_page)
                    latest_version = self._extract_version_from_release_url(final_url)
                    release_page_url = final_url or latest_page
                    installer_url = self._pick_installer_from_html(html, release_page_url)
                    notes = "GitHub API の制限のため、HTMLから取得しました。"
                    if latest_version:
                        return latest_version, release_page_url, notes, "", installer_url
                except Exception:
                    raise
            if getattr(e, "code", None) != 404:
                raise

        tags = self._http_get_json(self._github_tags_api(self.source_url))
        if not isinstance(tags, list) or not tags:
            raise ValueError("GitHub からタグ情報を取得できませんでした。")
        latest_version = str(tags[0].get("name", "")).strip()
        if not latest_version:
            raise ValueError("GitHub タグ名を取得できませんでした。")
        release_page_url = self.source_url.rstrip("/") + "/releases"
        notes = "GitHub Release が未作成のため、タグを基準に更新判定しました。"
        return latest_version, release_page_url, notes, "", ""

    def run(self):
        try:
            latest_version, release_page_url, notes, published_at, installer_url = \
                self._load_release()

            if not latest_version:
                self.completed.emit(
                    False, "failed", "", "", "", "",
                    "", "GitHub release の tag_name がありません。"
                )
                return

            state = "update_available" if is_newer_version(latest_version, VERSION) else "up_to_date"
            self.completed.emit(
                True, state, VERSION, latest_version,
                release_page_url, notes, published_at, installer_url
            )
        except Exception as e:
            reason = str(e).strip() or repr(e)
            self.completed.emit(False, "failed", VERSION, "", "", reason, "", "")