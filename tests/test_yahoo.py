"""Yahoo（CPBL）adapter。

2026 球季 Yahoo 只出現過兩種狀態值：status.type.final（387 場）與
status.type.postponed（45 場）。舊版把 postpone 歸到「結束」，所以這 45 場
雨天延賽都會被推成賽果。
"""

from datetime import date

import pytest

from conftest import league, load_fixture
from sources import yahoo


def _game(kind: str):
    board = load_fixture("yahoo_cpbl.json")[kind]
    game_id, raw = next(iter(board["games"].items()))
    return yahoo._to_game(league("cpbl"), game_id, raw, board["teams"])


@pytest.mark.parametrize("status_type, expected", [
    ("status.type.final", "post"),
    ("status.type.final_overtime", "post"),
    ("status.type.pregame", "pre"),
    ("status.type.scheduled", "pre"),
    ("status.type.delayed", "pre"),
    ("status.type.in_progress", "in"),
    ("status.type.postponed", "void"),
    ("status.type.cancelled", "void"),
    ("status.type.suspended", "void"),
    # 同時含 final 與 suspend：仍然不算正式完賽
    ("status.type.final_suspended", "void"),
])
def test_狀態對應(status_type, expected):
    assert yahoo._map_state(status_type) == expected


def test_完賽_中文隊名與比分():
    game = _game("final")
    assert game.finished
    assert game.score_line() == "樂天 5 - 4 統一"


def test_延賽是_void_且備註是中文():
    game = _game("postponed")
    assert game.state == "void"
    assert game.home_score is None and game.away_score is None
    # Yahoo 給的 status_description 是英文 "Postponed"
    assert game.note == "延賽"
    assert game.matchup == "樂天 @ 富邦"


def test_fetch_逐日查詢並去重(monkeypatch):
    """跨時區的比賽可能在相鄰兩天的查詢都出現。"""
    board = load_fixture("yahoo_cpbl.json")["final"]
    days = []
    monkeypatch.setattr(yahoo, "_get", lambda day, path: days.append(day) or board)

    games = yahoo.fetch(league("cpbl"), date(2026, 3, 19), date(2026, 3, 21))

    assert days == [date(2026, 3, 19), date(2026, 3, 20), date(2026, 3, 21)]
    assert len(games) == 1
