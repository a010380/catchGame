"""資料來源 adapter。

每個 adapter 只需要提供一個 fetch(league, start_date, end_date) -> list[Game]。
新增聯賽時在這裡註冊，main.py 不用改。
"""

from datetime import date

from models import Game
from sources import espn, lolesports, yahoo

_ADAPTERS = {
    "espn": espn.fetch,
    "lolesports": lolesports.fetch,
    "yahoo": yahoo.fetch,
}


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
