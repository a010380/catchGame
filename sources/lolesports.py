"""LoL 電競（LCK / LCP / MSI / Worlds）adapter。

用 lolesports.com 前端自己在呼叫的 Esports API。那個 x-api-key 是寫死在
該網站的 JS 裡的公開值，所有訪客共用，不是個人憑證，所以不需要申請也不用
放進 secrets。

與傳統運動不同的兩點，在這裡要特別處理：

1. **沒有主客場。** API 回的 teams 是一個兩元素陣列，順序就是官方顯示順序，
   不代表誰是主隊。Game.home / away 只是沿用同一組欄位來裝，顯示時仍是
   「A vs B」的語意。
2. **一場「比賽」是一個系列賽。** BO1/BO3/BO5 的比分是「拿下幾小場」
   （gameWins），不是總得分，而且整場的長度差很多，所以行事曆的時間長度
   要按 BO 數估。
"""

import time
from datetime import date, datetime, timezone

import requests

from models import Game

BASE = "https://esports-api.lolesports.com/persisted/gw"
API_KEY = "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z"
HEADERS = {"x-api-key": API_KEY, "User-Agent": "Mozilla/5.0"}
TIMEOUT = 25
RETRIES = 3

# API 的 state 對應到本專案的統一狀態
STATE_MAP = {
    "unstarted": "pre",
    "inProgress": "in",
    "completed": "post",
}

# BO 數 -> 行事曆上預估要佔多久（分鐘）。含選角與換場休息。
BO_DURATION = {1: 75, 2: 150, 3: 165, 5: 270}


def _get(path: str, params: dict) -> dict:
    last_err = None
    for attempt in range(RETRIES):
        try:
            resp = requests.get(
                f"{BASE}/{path}", params=params, headers=HEADERS, timeout=TIMEOUT
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as err:
            last_err = err
            if attempt < RETRIES - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"lolesports API 失敗: {path}\n{last_err}")


def _parse_dt(raw: str) -> datetime:
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def fetch(league: dict, start: date, end: date) -> list[Game]:
    league_id = league.get("league_id")
    if not league_id:
        raise ValueError(f"聯賽 {league.get('key')} 缺少 league_id 設定")

    payload = _get("getSchedule", {"hl": "en-US", "leagueId": league_id})
    events = ((payload.get("data") or {}).get("schedule") or {}).get("events") or []

    games: list[Game] = []
    for event in events:
        try:
            game = _to_game(league, event)
        except Exception:
            # 單場資料異常（例如對手還沒定、結構有變）就跳過，不影響其他場次
            continue
        # API 一次回整個賽季的區間，這裡自己裁切成呼叫端要的範圍
        if start <= game.start.date() <= end:
            games.append(game)

    games.sort(key=lambda g: g.start)
    return games


def _team_label(team: dict) -> str:
    """優先用隊伍代號（GEN / T1 / HLE），推播訊息裡最好讀。"""
    return team.get("code") or team.get("name") or "TBD"


def _to_game(league: dict, event: dict) -> Game:
    if event.get("type") != "match":
        # 目前 API 只會回 match，但先擋著，免得之後多出 show 之類的類型
        raise ValueError(f"不支援的 event 類型: {event.get('type')}")

    match = event["match"]
    teams = match.get("teams") or []
    if len(teams) < 2:
        raise ValueError("隊伍資料不足")

    state = STATE_MAP.get(event.get("state"), "pre")
    bo = ((match.get("strategy") or {}).get("count")) or 1

    wins = [(t.get("result") or {}).get("gameWins") for t in teams]
    if state == "pre" or any(w is None for w in wins):
        wins = [None, None]

    # blockName 是賽程階段（Week 3 / Playoffs / Finals），對電競來說是重要資訊
    block = event.get("blockName") or ""
    note_parts = [f"BO{bo}"]
    if block:
        note_parts.append(block)
    if state == "in":
        note_parts.append("進行中")

    slug = (event.get("league") or {}).get("slug") or league["key"]

    return Game(
        uid=f"{league['key']}-{match['id']}",
        league_key=league["key"],
        league_name=league["name"],
        emoji=league.get("emoji", ""),
        start=_parse_dt(event["startTime"]),
        duration_min=BO_DURATION.get(bo, league.get("duration_min", 180)),
        # 電競沒有主客場，teams[0] / teams[1] 只是官方的顯示順序
        home=_team_label(teams[1]),
        away=_team_label(teams[0]),
        home_score=str(wins[1]) if wins[1] is not None else None,
        away_score=str(wins[0]) if wins[0] is not None else None,
        state=state,
        status_detail=block,
        neutral=True,  # 電競沒有主客場
        link=f"https://lolesports.com/schedule?leagues={slug}",
        note=" · ".join(note_parts),
        _tags=[
            str(v)
            for t in teams
            for v in (t.get("code"), t.get("name"))
            if v
        ],
    )
