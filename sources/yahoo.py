"""Yahoo 運動 scoreboard adapter —— 目前用來抓 CPBL。

**為什麼不直接爬 CPBL 官網？**

`cpbl.com.tw` 整站（含它自己的 JSON 端點）都在 HiNetCDN 的
「Anti-DDoS Flood Protection」後面，任何程式化請求都會收到 HTTP 428，
必須先通過一段做瀏覽器指紋檢測（螢幕尺寸、加密時戳標頭）的 JS 挑戰。
那是對方刻意設置的存取控制，硬繞過去既脆弱（對方一改就壞）也不恰當。

Yahoo 運動有完整的 CPBL 資料，而且是它自己網站在用的公開 JSON 端點，
**隊名直接就是中文**（樂天、中信、統一…），不需要自己維護對照表。

限制：這個端點一次只能查一天，所以抓區間要逐日呼叫。查兩週約 17 次請求，
單次回應約 50KB，對排程來說可以接受。
"""

import time
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

from models import Game

URL = "https://api-secure.sports.yahoo.com/v1/editorial/s/scoreboard"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Accept-Language": "zh-TW,zh;q=0.9",
}
TIMEOUT = 25
RETRIES = 3

# 一次抓取最多查幾天，避免設定寫錯時打出上百次請求
MAX_DAYS = 45

# Yahoo 的 status_type 對應到本專案的統一狀態。
# 已知值：status.type.pregame / status.type.final。
# 其他（延賽、保留、進行中）用下面的關鍵字判斷。
STATE_EXACT = {
    "status.type.pregame": "pre",
    "status.type.scheduled": "pre",
    "status.type.final": "post",
    "status.type.final_overtime": "post",
}
POST_KEYWORDS = ("final", "complete", "cancel", "postpone", "suspend")


def _get(day: date, path: str) -> dict:
    params = {
        "leagues": path,
        "date": day.isoformat(),
        "lang": "zh-Hant-TW",
        "region": "TW",
    }
    last_err = None
    for attempt in range(RETRIES):
        try:
            resp = requests.get(URL, params=params, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp.json()["service"]["scoreboard"]
        except Exception as err:
            last_err = err
            if attempt < RETRIES - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Yahoo 運動請求失敗（{path} {day}）\n{last_err}")


def _map_state(status_type: str) -> str:
    if status_type in STATE_EXACT:
        return STATE_EXACT[status_type]
    lowered = (status_type or "").lower()
    if any(k in lowered for k in POST_KEYWORDS):
        return "post"
    if "pre" in lowered or "sched" in lowered or "delay" in lowered:
        return "pre"
    return "in"


def _days(start: date, end: date) -> list[date]:
    span = (end - start).days
    if span < 0:
        return []
    if span + 1 > MAX_DAYS:
        end = start + timedelta(days=MAX_DAYS - 1)
        span = MAX_DAYS - 1
    return [start + timedelta(days=i) for i in range(span + 1)]


def fetch(league: dict, start: date, end: date) -> list[Game]:
    path = league.get("path")
    if not path:
        raise ValueError(f"聯賽 {league.get('key')} 缺少 path 設定")

    games: list[Game] = []
    seen: set[str] = set()
    for day in _days(start, end):
        board = _get(day, path)
        teams = board.get("teams") or {}
        for game_id, raw in (board.get("games") or {}).items():
            if game_id in seen:
                continue  # 跨時區的比賽可能在相鄰兩天的查詢都出現
            seen.add(game_id)
            try:
                games.append(_to_game(league, game_id, raw, teams))
            except Exception:
                continue

    games.sort(key=lambda g: g.start)
    return games


def _team_name(teams: dict, team_id: str) -> str:
    team = teams.get(team_id) or {}
    return team.get("display_name") or team.get("abbr") or team_id or "TBD"


def _full_name(teams: dict, team_id: str) -> str:
    """完整隊名（樂天桃猿），用來做 config 的 teams 篩選比對。"""
    team = teams.get(team_id) or {}
    first, last = team.get("first_name") or "", team.get("last_name") or ""
    return (first + last) or _team_name(teams, team_id)


def _to_game(league: dict, game_id: str, raw: dict, teams: dict) -> Game:
    # start_time 是 RFC 2822 格式："Fri, 11 Sep 2026 10:35:00 +0000"
    start = parsedate_to_datetime(raw["start_time"]).astimezone(timezone.utc)

    state = _map_state(raw.get("status_type", ""))
    away_pts = raw.get("total_away_points")
    home_pts = raw.get("total_home_points")
    if state == "pre":
        away_pts = home_pts = None

    away_id, home_id = raw.get("away_team_id", ""), raw.get("home_team_id", "")

    note = ""
    if raw.get("is_time_tba"):
        note = "開賽時間未定"
    elif state == "in":
        note = raw.get("status_description") or "進行中"
    elif state == "post" and raw.get("status_description") not in ("Final", None, ""):
        # 延賽、保留比賽等非單純 Final 的結果，把原文帶上比較不會誤讀
        note = raw["status_description"]

    return Game(
        uid=f"{league['key']}-{game_id}",
        league_key=league["key"],
        league_name=league["name"],
        emoji=league.get("emoji", ""),
        start=start,
        duration_min=league.get("duration_min", 210),
        home=_team_name(teams, home_id),
        away=_team_name(teams, away_id),
        home_score=str(home_pts) if home_pts is not None else None,
        away_score=str(away_pts) if away_pts is not None else None,
        state=state,
        status_detail=raw.get("status_description") or "",
        link=f"https://tw.sports.yahoo.com/{league.get('path', '')}/scoreboard",
        note=note,
        _tags=[
            _team_name(teams, home_id), _team_name(teams, away_id),
            _full_name(teams, home_id), _full_name(teams, away_id),
        ],
    )
