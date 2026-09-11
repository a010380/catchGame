"""記錄「哪些比賽已經通知過」，避免每次排程重複通知。

分成兩個獨立的桶（bucket）：
  notified  賽果已推播
  reminded  開賽提醒已推播
同一場比賽會各進一次，互不影響。

檔案會被 GitHub Actions commit 回 repo，這樣下一次排程才讀得到上一次的結果
（Actions 的執行環境是用完即丟的，不會保留檔案）。
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config

STATE_PATH = Path(__file__).with_name("state.json")


BUCKETS = ("notified", "reminded")


def _empty() -> dict:
    return {bucket: {} for bucket in BUCKETS}


def load() -> dict:
    if not STATE_PATH.exists():
        return _empty()
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # 檔案壞掉時寧可重新開始，也不要讓整個排程失敗
        return _empty()
    for bucket in BUCKETS:
        data.setdefault(bucket, {})
    return data


def save(data: dict) -> None:
    """只有在推播紀錄真的有變動時才寫檔。

    `updated_at` 每次都會變，如果無條件寫檔，排程每 30 分鐘就會產生一筆
    「內容其實沒變」的 commit，一年下來上萬筆雜訊。所以先比對 notified
    的內容，沒變就整個跳過 —— workflow 那邊的 `git diff --staged --quiet`
    就會判定無變化而不 commit。
    """
    if STATE_PATH.exists():
        try:
            previous = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if all(previous.get(b) == data.get(b) for b in BUCKETS):
                return
        except json.JSONDecodeError:
            pass  # 檔案壞掉就照常覆寫

    data["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    STATE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def already(data: dict, bucket: str, uid: str) -> bool:
    return uid in data[bucket]


def mark(data: dict, bucket: str, uid: str) -> None:
    data[bucket][uid] = datetime.now(timezone.utc).isoformat(timespec="seconds")


def prune(data: dict) -> int:
    """丟掉太舊的紀錄。比賽結束超過保留天數後就不可能再被重複推播。"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=config.STATE_RETENTION_DAYS)
    removed = 0
    for bucket in BUCKETS:
        stale = []
        for uid, stamp in data[bucket].items():
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
            del data[bucket][uid]
        removed += len(stale)
    return removed
