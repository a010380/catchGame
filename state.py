"""記錄「哪些比賽已經通知過」，避免每次排程重複通知。

分成幾個獨立的桶（bucket）：
  notified  賽果已推播（key 是比賽 uid）
  reminded  開賽提醒已推播（key 是比賽 uid）
  digest    每日摘要已推播（key 是台灣日期，一天只送一次）
彼此互不影響。

另外還有一個形狀不同的桶：
  failures  每個聯賽「連續抓取失敗幾次」的計數（key 是聯賽 key），
            用來判斷是偶發抖動還是真的壞掉。抓成功就歸零。

檔案會被 GitHub Actions commit 回 repo，這樣下一次排程才讀得到上一次的結果
（Actions 的執行環境是用完即丟的，不會保留檔案）。
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config

STATE_PATH = Path(__file__).with_name("state.json")


BUCKETS = ("notified", "reminded", "digest")

# 連續失敗計數。值是 {"count": n, "since": iso}，不是時間戳，所以不能放進
# BUCKETS —— prune() 會把裡面的值當 ISO 時間解析。
FAILURES = "failures"

# 寫檔前要比對的所有桶。failures 也算，否則計數永遠不會被存下來。
_TRACKED = BUCKETS + (FAILURES,)


def _empty() -> dict:
    return {bucket: {} for bucket in _TRACKED}


def load() -> dict:
    if not STATE_PATH.exists():
        return _empty()
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # 檔案壞掉時寧可重新開始，也不要讓整個排程失敗
        return _empty()
    for bucket in _TRACKED:
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
            if all(previous.get(b) == data.get(b) for b in _TRACKED):
                return
        except json.JSONDecodeError:
            pass  # 檔案壞掉就照常覆寫

    data["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    STATE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def fail_streak(data: dict, league_key: str) -> int:
    """這個聯賽目前連續失敗幾次。"""
    return int((data[FAILURES].get(league_key) or {}).get("count", 0))


def record_fetch(data: dict, league_key: str, ok: bool) -> int:
    """記錄一次抓取結果，回傳更新後的連續失敗次數。

    成功就把紀錄整個刪掉（而不是把 count 設成 0）—— 正常狀態下 failures
    應該是空的 {}，這樣 state.json 不會被一堆 0 塞滿，save() 的比對也不會
    因為「0 變成 0」而誤判有變動。
    """
    if ok:
        data[FAILURES].pop(league_key, None)
        return 0
    entry = data[FAILURES].get(league_key) or {}
    count = int(entry.get("count", 0)) + 1
    data[FAILURES][league_key] = {
        "count": count,
        "since": entry.get("since")
        or datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return count


def already(data: dict, bucket: str, uid: str) -> bool:
    return uid in data[bucket]


def mark(data: dict, bucket: str, uid: str) -> None:
    data[bucket][uid] = datetime.now(timezone.utc).isoformat(timespec="seconds")


def prune(data: dict) -> int:
    """丟掉太舊的紀錄。比賽結束超過保留天數後就不可能再被重複推播。

    不動 failures —— 那裡面記的是「現在壞著」的狀態，要靠抓取成功才歸零，
    不該因為壞得夠久就自動消失。
    """
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
