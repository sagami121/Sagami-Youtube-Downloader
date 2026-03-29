import re

def parse_timecode_to_seconds(value: str):
    text = (value or "").strip()
    if not text:
        return None

    if text.isdigit():
        return int(text)

    parts = text.split(":")
    if len(parts) not in (2, 3):
        return None
    if not all(p.isdigit() for p in parts):
        return None

    if len(parts) == 2:
        mm, ss = map(int, parts)
        if ss >= 60:
            return None
        return mm * 60 + ss

    hh, mm, ss = map(int, parts)
    if mm >= 60 or ss >= 60:
        return None
    return hh * 3600 + mm * 60 + ss

def parse_time_range(value: str):
    raw = (value or "").strip()
    if not raw:
        return None, None, None

    normalized = raw.replace(" ", "").replace("～", "~").replace("〜", "~").replace("－", "~").replace("-", "~")
    if "~" not in normalized:
        return None, None, "時間指定は `開始~終了` で入力してください。(例: 0:00~0:15)"

    start_raw, end_raw = normalized.split("~", 1)
    start_sec = parse_timecode_to_seconds(start_raw)
    end_sec = parse_timecode_to_seconds(end_raw)
    if start_sec is None or end_sec is None:
        return None, None, "時間の形式が不正です。`秒` / `mm:ss` / `hh:mm:ss` を使ってください。"
    if start_sec >= end_sec:
        return None, None, "開始時間は終了時間より前にしてください。"

    return str(start_sec), str(end_sec), None

def tail_text(text: str, max_lines: int = 8):
    lines = [line for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return ""
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    return "\n".join(lines)

def version_key(version: str):
    text = (version or "").strip().lower()
    if text.startswith("v"):
        text = text[1:]
    nums = [int(x) for x in re.findall(r"\d+", text)]
    
    pre_rank = 0
    pre_num = 0
    if "alpha" in text:
        pre_rank = -3
    elif "beta" in text:
        pre_rank = -2
    elif "rc" in text:
        pre_rank = -1
    match = re.search(r"(alpha|beta|rc)\s*(\d+)?", text)
    if match and match.group(2):
        pre_num = int(match.group(2))
    
    return (nums, pre_rank, pre_num)

def is_newer_version(latest: str, current: str) -> bool:
    if not latest or not current:
        return False
    return version_key(latest) > version_key(current)

def extract_latest_changelog_entry(changelog_text: str) -> str:
    lines = (changelog_text or "").splitlines()
    block = []
    started = False
    for line in lines:
        if line.strip():
            started = True
            block.append(line.rstrip())
        elif started:
            break
    return "\n".join(block).strip()
