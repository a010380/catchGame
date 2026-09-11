"""記錄「哪些比賽的賽果已經推播過」，避免每次排程重複通知。

檔案會被 GitHub Actions commit 回 repo，這樣下一次排程才讀得到上一次的結果
（Actions 的執行環境是用完即丟的，不會保留檔案）。
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config

STATE_PATH = Path(__file__).with_name("state.json")


def load() -> dict:
    if not STATE_PATH.exists():
        return {"notified": {}}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # 檔案壞掉時寧可重新開始，也不要讓整個排程失敗
        return {"notified": {}}
    data.setdefault("notified", {})
    return data


def save(data: dict) -> None:
    data["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    STATE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def already_notified(data: dict, uid: str) -> bool:
    return uid in data["notified"]


def mark_notified(data: dict, uid: str) -> None:
    data["notified"][uid] = datetime.now(timezone.utc).isoformat(timespec="seconds")


def prune(data: dict) -> int:
    """丟掉太舊的紀錄。比賽結束超過保留天數後就不可能再被重複推播。"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=config.STATE_RETENTION_DAYS)
    stale = []
    for uid, stamp in data["notified"].items():
        try:
            when = datetime.fromisoformat(stamp)
        except ValueError:
            stale.append(uid)
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when < cutoff:
            stale.append(uid)
    for uid in stale:
        del data["notified"][uid]
    return len(stale)
