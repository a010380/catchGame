"""資料來源 adapter。

每個 adapter 只需要提供一個 fetch(league, start_date, end_date) -> list[Game]。
新增聯賽時在這裡註冊，main.py 不用改。
"""

from datetime import date

from models import Game, StandingTable
from sources import espn, lolesports, yahoo

_ADAPTERS = {
    "espn": espn.fetch,
    "lolesports": lolesports.fetch,
    "yahoo": yahoo.fetch,
}


# 有提供戰績的資料源。CPBL（Yahoo 沒有戰績端點）與電競（瑞士輪 / 淘汰賽，
# 沒有傳統戰績表）不在這裡。
_STANDINGS = {
    "espn": espn.fetch_standings,
}


def supports_standings(league: dict) -> bool:
    return league.get("standings", False) and league.get("source") in _STANDINGS


def fetch_standings(league: dict) -> list[StandingTable]:
    return _STANDINGS[league["source"]](league)


def fetch(league: dict, start: date, end: date) -> list[Game]:
    source = league.get("source")
    adapter = _ADAPTERS.get(source)
    if adapter is None:
        raise ValueError(
            f"聯賽 {league.get('key')} 指定了未知的 source: {source!r}"
            f"（目前支援：{', '.join(sorted(_ADAPTERS))}）"
        )
    games = adapter(league, start, end)
    return [g for g in games if g.matches_teams(league.get("teams", []))]
