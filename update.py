import argparse
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from datetime import datetime

APP_NAME = "SagamiYoutubeDownloader"


# -----------------------------
# logging
# -----------------------------

def log(msg):

    log_dir = Path(tempfile.gettempdir()) / APP_NAME
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / "updater.log"

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{now}] {msg}\n")


# -----------------------------
# wait process
# -----------------------------

def _process_exists_windows(pid: int) -> bool:
    """
    Windows で PID が生存しているか確認する。
    os.kill(pid, 0) は Windows では TerminateProcess を呼ぶため使用不可。
    OpenProcess で存在確認する。
    """
    import ctypes
    SYNCHRONIZE = 0x00100000
    handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if handle == 0:
        return False
    # WAIT_TIMEOUT=258 ならまだ動いている、0 なら終了済み
    result = ctypes.windll.kernel32.WaitForSingleObject(handle, 0)
    ctypes.windll.kernel32.CloseHandle(handle)
    return result == 258  # WAIT_TIMEOUT


def wait_process_exit(pid, timeout=120):

    log(f"waiting for process {pid}")

    start = time.time()
    is_windows = (os.name == "nt")

    while True:

        if time.time() - start > timeout:
            log("timeout waiting process")
            return False

        if is_windows:
            alive = _process_exists_windows(pid)
        else:
            try:
                os.kill(pid, 0)
                alive = True
            except OSError:
                alive = False

        if not alive:
            log("process closed")
            return True

        time.sleep(0.5)


# -----------------------------
# download installer
# -----------------------------

def download_file(url):

    log(f"download start {url}")

    temp_dir = Path(tempfile.gettempdir()) / APP_NAME
    temp_dir.mkdir(exist_ok=True)

    installer = temp_dir / "installer.exe"

    urllib.request.urlretrieve(url, installer)

    log(f"download complete {installer}")

    return installer


# -----------------------------
# run installer
# -----------------------------

def run_installer(installer):

    cmd = [
        str(installer),
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/SP-",
    ]

    log(f"run installer {cmd}")

    subprocess.Popen(
        cmd,
        creationflags=subprocess.CREATE_NO_WINDOW
    )


# -----------------------------
# main
# -----------------------------

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument("--url", required=True)
    parser.add_argument("--pid", type=int)

    args = parser.parse_args()

    log("updater start")

    # Downloader終了待機
    if args.pid:
        wait_process_exit(args.pid)

    # installer download
    try:
        installer = download_file(args.url)
    except Exception as e:
        log(f"download error {e}")
        sys.exit(1)

    # installer start
    try:
        run_installer(installer)
    except Exception as e:
        log(f"installer start error {e}")
        sys.exit(1)

    log("installer launched")
    log("updater exit")

    sys.exit(0)


if __name__ == "__main__":
    main()