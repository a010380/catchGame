"""ESPN 公開 scoreboard API adapter。

一支 adapter 就覆蓋 MLB / NBA / NFL / 英超 / 西甲，差別只在 config 裡的 path。
這是非官方公開端點，沒有 API key、也沒有正式文件，所以解析時全部用寬鬆取值，
欄位缺失就跳過該場，不讓單一場次的異常炸掉整批。
"""

import time
from datetime import date, datetime, timezone

import requests

from models import Game

BASE = "https://site.api.espn.com/apis/site/v2/sports"
TIMEOUT = 25
RETRIES = 3

# ESPN 前面有一層 WAF，對 User-Agent 的接受條件很跳：
# "Mozilla/5.0" 可以過，但 "Mozilla/5.0 (compatible; ...)" 這種帶括號的會被 403。
# 那是對方的黑箱規則、隨時可能變動，所以準備多組標頭依序退讓。
HEADER_CANDIDATES = (
    {"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
    {"Accept": "application/json"},  # 用 requests 自己的預設 UA
)


def _get(url: str) -> dict:
    last_err = None
    for headers in HEADER_CANDIDATES:
        for attempt in range(RETRIES):
            try:
                resp = requests.get(url, headers=headers, timeout=TIMEOUT)
                if resp.status_code == 403:
                    # 被 WAF 擋下，重試同一組標頭沒意義，直接換下一組
                    last_err = "403 Forbidden（User-Agent 被 ESPN 擋下）"
                    break
                resp.raise_for_status()
                return resp.json()
            except Exception as err:  # 網路抖動或 ESPN 暫時 5xx
                last_err = err
                if attempt < RETRIES - 1:
                    time.sleep(2 ** attempt)
    raise RuntimeError(f"ESPN 請求失敗: {url}\n{last_err}")


def _parse_dt(raw: str) -> datetime:
    """ESPN 回傳的格式有 '2026-09-10T16:15Z' 也有帶秒的版本，兩種都吃。"""
    text = raw.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _side(competitors: list[dict], want: str) -> dict | None:
    for c in competitors:
        if c.get("homeAway") == want:
            return c
    return None


def _team_name(competitor: dict) -> str:
    team = competitor.get("team") or {}
    # shortDisplayName 比 displayName 短、在通知裡比較好讀；抓不到才退回較長的名稱
    return (
        team.get("shortDisplayName")
        or team.get("displayName")
        or team.get("abbreviation")
        or "TBD"
    )


def _tags(competitor: dict) -> list[str]:
    team = competitor.get("team") or {}
    return [
        str(v)
        for v in (
            team.get("abbreviation"),
            team.get("shortDisplayName"),
            team.get("displayName"),
            team.get("location"),
        )
        if v
    ]


def _months(start: date, end: date) -> list[str]:
    """把 start..end 展開成 YYYYMM 清單（含頭尾）。"""
    out, year, month = [], start.year, start.month
    while (year, month) <= (end.year, end.month):
        out.append(f"{year:04d}{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def fetch(league: dict, start: date, end: date) -> list[Game]:
    """逐月查詢再自己過濾出 start..end。

    為什麼不用 `dates=YYYYMMDD-YYYYMMDD` 區間：ESPN 的 scoreboard 端點對區間
    一律回 400 Bad Request（足球從一開始就不吃，其他運動也已經不吃了）。
    能用的只有單日 `YYYYMMDD` 與整月 `YYYYMM`，所以選整月 —— 兩週的視窗最多
    一到兩個請求，比逐日查 15 次輕得多，而且整月的量（MLB 旺季約 380 場）
    還在 limit 之內。
    """
    games: list[Game] = []
    seen: set[str] = set()
    for dates in _months(start, end):
        url = f"{BASE}/{league['path']}/scoreboard?dates={dates}&limit=1000"
        payload = _get(url)

        for event in payload.get("events") or []:
            try:
                game = _to_game(league, event)
            except Exception:
                # 單場解析失敗（欄位結構異常、對手未定等）就略過，不影響其他場次
                continue
            # 整月查詢會帶回區間外的場次，在這裡切回要的視窗；
            # seen 擋掉月份邊界可能的重複。
            if not (start <= game.start.date() <= end) or game.uid in seen:
                continue
            seen.add(game.uid)
            games.append(game)
    games.sort(key=lambda g: g.start)
    return games


def _to_game(league: dict, event: dict) -> Game:
    comp = (event.get("competitions") or [{}])[0]
    competitors = comp.get("competitors") or []
    home = _side(competitors, "home")
    away = _side(competitors, "away")
    if not home or not away:
        raise ValueError("找不到主客隊")

    status_type = ((comp.get("status") or event.get("status") or {}).get("type")) or {}
    state = status_type.get("state") or "pre"

    home_score = home.get("score")
    away_score = away.get("score")
    if state == "pre":
        # 未開打時 ESPN 會給 "0"，留著會誤導，直接清掉
        home_score = away_score = None

    note = ""
    if comp.get("timeValid") is False:
        note = "開賽時間未定"
    elif state == "in":
        note = status_type.get("shortDetail") or "進行中"
    elif comp.get("wasSuspended"):
        note = "比賽曾中斷"

    link = ""
    for item in event.get("links") or []:
        if "desktop" in (item.get("rel") or []) and item.get("href"):
            link = item["href"]
            break

    return Game(
        uid=f"{league['key']}-{event['id']}",
        league_key=league["key"],
        league_name=league["name"],
        emoji=league.get("emoji", ""),
        start=_parse_dt(comp.get("date") or event["date"]),
        duration_min=league.get("duration_min", 180),
        home=_team_name(home),
        away=_team_name(away),
        home_score=str(home_score) if home_score is not None else None,
        away_score=str(away_score) if away_score is not None else None,
        state=state,
        status_detail=status_type.get("detail") or status_type.get("description") or "",
        link=link,
        note=note,
        _tags=_tags(home) + _tags(away),
    )
