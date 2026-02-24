import argparse
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
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
    target = Path(tempfile.gettempdir()) / f"sagami_update_{int(time.time())}_{name}"
    req = urllib.request.Request(url, headers={"User-Agent": "Sagami-Youtube-Downloader-Updater"})
    with urllib.request.urlopen(req, timeout=60) as response:
        data = response.read()
    target.write_bytes(data)
    return target


def try_start_installer(installer_path: Path) -> bool:
    ext = installer_path.suffix.lower()
    flags = (subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS) if os.name == "nt" else 0

    if ext == ".msi":
        subprocess.Popen(["msiexec", "/i", str(installer_path), "/qn", "/norestart"], creationflags=flags)
        return True

    arg_sets = [
        ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"],
        ["/SILENT", "/NORESTART"],
        ["/S", "/NORESTART"],
        ["/quiet", "/norestart"],
    ]

    for extra in arg_sets:
        try:
            p = subprocess.Popen([str(installer_path), *extra], creationflags=flags)
            time.sleep(2.0)
            code = p.poll()
            if code is None or code == 0:
                return True
        except Exception:
            continue

    try:
        os.startfile(str(installer_path))
        return True
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--installer-url", required=True)
    parser.add_argument("--current-pid", type=int, default=0)
    args = parser.parse_args()

    try:
        wait_for_process_exit(args.current_pid, timeout_sec=120)
        installer_path = download_installer(args.installer_url)
        ok = try_start_installer(installer_path)
        if not ok:
            raise RuntimeError("インストーラーの起動に失敗しました。")
        write_ini_log(
            "update_started",
            {
                "installer_url": args.installer_url,
                "installer_path": str(installer_path),
                "pid_waited": args.current_pid,
            },
            prefix="update_started",
        )
    except Exception as e:
        write_ini_log(
            "update_error",
            {
                "installer_url": args.installer_url,
                "pid_waited": args.current_pid,
                "error": repr(e),
            },
            prefix="update_error",
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
