import argparse
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error
import ssl
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


def write_ini_log(section: str, values: dict, prefix: str = "update") -> str:
    app_dir = Path(__file__).resolve().parent
    logs_dir = app_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = logs_dir / f"{prefix}_{ts}.txt"
    lines = [f"[{section}]"]
    for key, value in values.items():
        text = str(value).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")
        lines.append(f"{key}={text}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def wait_for_process_exit(pid: int, timeout_sec: int = 120):
    if pid <= 0:
        return
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="ignore",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            text = (out.stdout or "").lower()
            if "no tasks are running" in text or str(pid) not in text:
                return
        except Exception:
            return
        time.sleep(1.0)


def download_installer(url: str) -> Path:
    parsed = urlparse(url)
    name = Path(parsed.path).name or "installer.exe"
    temp_dir = Path(tempfile.gettempdir()) / "SagamiYoutubeDownloader"
    temp_dir.mkdir(parents=True, exist_ok=True)
    target = temp_dir / name
    req = urllib.request.Request(url, headers={"User-Agent": "Sagami-Youtube-Downloader-Updater"})
    with urlopen_with_ssl_fallback(req, url, timeout=60) as response:
        data = response.read()
    target.write_bytes(data)
    return target


def is_known_update_host(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    trusted_suffixes = (
        "github.com",
        "githubusercontent.com",
        "githubassets.com",
    )
    return any(host == suffix or host.endswith("." + suffix) for suffix in trusted_suffixes)


def urlopen_with_ssl_fallback(req, url: str, timeout: int = 60):
    def _is_ssl_verify_error(exc: Exception) -> bool:
        if isinstance(exc, ssl.SSLCertVerificationError):
            return True
        if isinstance(exc, urllib.error.URLError):
            reason = getattr(exc, "reason", None)
            return isinstance(reason, ssl.SSLCertVerificationError)
        return False

    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except Exception as first_error:
        if not _is_ssl_verify_error(first_error):
            raise
        certifi_ctx = None
        try:
            import certifi
            certifi_ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            certifi_ctx = None

        if certifi_ctx is not None:
            try:
                return urllib.request.urlopen(req, timeout=timeout, context=certifi_ctx)
            except Exception as second_error:
                if not _is_ssl_verify_error(second_error):
                    raise
                pass

        if is_known_update_host(url):
            insecure_ctx = ssl._create_unverified_context()
            return urllib.request.urlopen(req, timeout=timeout, context=insecure_ctx)
        raise first_error


def _run_and_wait(cmd: list[str], flags: int, timeout_sec: int = 1800) -> tuple[bool, int | None]:
    try:
        p = subprocess.Popen(cmd, creationflags=flags)
        code = p.wait(timeout=timeout_sec)
        return code == 0, code
    except subprocess.TimeoutExpired:
        return False, None
    except Exception:
        return False, None


def detect_installer_kind(installer_path: Path) -> str:
    name = installer_path.name.lower()
    ext = installer_path.suffix.lower()
    if ext == ".msi":
        return "msi"
    if "inno" in name or "setup" in name:
        return "inno"
    if "nsis" in name:
        return "nsis"
    return "exe"


def installer_profiles(installer_path: Path, kind: str) -> list[list[str]]:
    generic_profiles = [
        [str(installer_path), "/quiet", "/norestart"],
        [str(installer_path), "/SILENT", "/NORESTART"],
        [str(installer_path), "/S", "/NORESTART"],
        [str(installer_path), "/S"],
        [str(installer_path)],
    ]
    inno_profiles = [
        [str(installer_path), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/TASKS=desktopicon"],
        [str(installer_path), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"],
    ]
    nsis_profiles = [
        [str(installer_path), "/S"],
        [str(installer_path), "/S", "/NORESTART"],
    ]

    def _unique(cmds: list[list[str]]) -> list[list[str]]:
        seen = set()
        result = []
        for cmd in cmds:
            key = tuple(cmd)
            if key in seen:
                continue
            seen.add(key)
            result.append(cmd)
        return result

    if kind == "msi":
        return [["msiexec", "/i", str(installer_path), "/qn", "/norestart"]]
    if kind == "inno":
        return _unique(inno_profiles + nsis_profiles + generic_profiles)
    if kind == "nsis":
        return _unique(nsis_profiles + inno_profiles + generic_profiles)
    return _unique(generic_profiles + inno_profiles + nsis_profiles)


def run_installer_with_profiles(installer_path: Path) -> tuple[bool, list[dict]]:
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    kind = detect_installer_kind(installer_path)
    attempts = []
    for cmd in installer_profiles(installer_path, kind):
        ok, code = _run_and_wait(cmd, flags)
        attempts.append({"cmd": cmd, "ok": ok, "code": code, "kind": kind})
        if ok:
            return True, attempts
    return False, attempts


def relaunch_app(launch_path: str) -> bool:
    path = Path(launch_path).expanduser()
    if not path.exists():
        return False
    flags = (subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS) if os.name == "nt" else 0
    try:
        if path.suffix.lower() == ".py":
            subprocess.Popen([sys.executable, str(path)], creationflags=flags, cwd=str(path.parent))
        else:
            subprocess.Popen([str(path)], creationflags=flags, cwd=str(path.parent))
        return True
    except Exception:
        return False


def verify_installation(launch_path: str, install_dir: str, timeout_sec: int = 180) -> bool:
    deadline = time.time() + timeout_sec
    launch = Path(launch_path).expanduser() if launch_path else None
    install = Path(install_dir).expanduser() if install_dir else None

    while time.time() < deadline:
        if launch and launch.exists() and launch.is_file():
            try:
                if launch.stat().st_size > 0:
                    return True
            except Exception:
                pass
        if install and install.exists() and any(install.glob("*.exe")):
            return True
        time.sleep(1.0)
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--installer-url", required=True)
    parser.add_argument("--current-pid", type=int, default=0)
    parser.add_argument("--launch-path", default="")
    parser.add_argument("--install-dir", default="")
    args = parser.parse_args()

    attempts = []
    installer_path = None
    try:
        wait_for_process_exit(args.current_pid, timeout_sec=120)
        installer_path = download_installer(args.installer_url)
        ok, attempts = run_installer_with_profiles(installer_path)
        if not ok:
            raise RuntimeError("Installer execution failed.")

        installed = verify_installation(args.launch_path, args.install_dir, timeout_sec=300)
        if not installed:
            raise RuntimeError("Installation verification failed.")

        relaunched = False
        if args.launch_path:
            # Give installer side-effects a moment to settle before relaunch.
            time.sleep(2.0)
            relaunched = relaunch_app(args.launch_path)

        write_ini_log(
            "update_started",
            {
                "installer_url": args.installer_url,
                "installer_path": str(installer_path),
                "pid_waited": args.current_pid,
                "launch_path": args.launch_path,
                "install_dir": args.install_dir,
                "attempts": json.dumps(attempts, ensure_ascii=False),
                "installed": installed,
                "relaunched": relaunched,
            },
            prefix="update_started",
        )
    except Exception as e:
        rollback = False
        if args.launch_path:
            rollback = relaunch_app(args.launch_path)
        write_ini_log(
            "update_error",
            {
                "installer_url": args.installer_url,
                "installer_path": str(installer_path) if installer_path else "",
                "pid_waited": args.current_pid,
                "launch_path": args.launch_path,
                "install_dir": args.install_dir,
                "attempts": json.dumps(attempts, ensure_ascii=False),
                "rollback_relaunched": rollback,
                "error": repr(e),
            },
            prefix="update_error",
        )
        sys.exit(1)

if __name__ == "__main__":
    main()

