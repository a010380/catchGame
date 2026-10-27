"""ESPN adapter：狀態判斷、比分、日期查詢。

fixture 是真實的 ESPN 回應，其中三場是實際發生過的事故：
  401814780  MLB 延賽          Blue Jays @ White Sox
  401817103  MLB 取消（9/27）   Orioles @ Yankees    ← 曾被推成 0 - 0 的賽果
  401882849  西甲中止（10/10）  Athletic @ Rayo      ← 曾被推成 0 - 0 的賽果
"""

import copy
from datetime import date

import pytest

from conftest import league, load_fixture
from sources import espn


def _event(fixture: str, event_id: str) -> dict:
    events = load_fixture(fixture)["events"]
    return copy.deepcopy(next(e for e in events if e["id"] == event_id))


# ---------------------------------------------------------------- 狀態


@pytest.mark.parametrize("fixture, event_id, key, label", [
    ("espn_mlb.json", "401814780", "mlb", "延賽"),
    ("espn_mlb.json", "401817103", "mlb", "取消"),
    ("espn_soccer.json", "401882849", "laliga", "比賽中止"),
])
def test_沒打完的比賽是_void_不是賽果(fixture, event_id, key, label):
    """ESPN 對這些場次給 state=post，只有 completed=False 能分辨。"""
    raw = _event(fixture, event_id)
    assert raw["competitions"][0]["status"]["type"]["state"] == "post"

    game = espn._to_game(league(key), raw)

    assert game.state == "void"
    assert not game.finished
    assert game.note == label
    # ESPN 給的是 "0"，留著會被印成 0 - 0
    assert game.home_score is None and game.away_score is None
    assert game.score_line() == game.matchup


def test_正常完賽有比分():
    game = espn._to_game(league("mlb"), _event("espn_mlb.json", "401816759"))
    assert game.finished
    assert game.score_line() == "Mets 2 - 6 Rays"


def test_足球完賽():
    game = espn._to_game(league("epl"), _event("espn_soccer.json", "740913"))
    assert game.finished
    assert game.score_line() == "Wolves 0 - 4 West Ham"


def test_未開打時清掉比分():
    game = espn._to_game(league("mlb"), _event("espn_mlb.json", "401908045"))
    assert game.state == "pre"
    assert game.home_score is None and game.away_score is None


def test_進行中帶上即時狀態():
    raw = _event("espn_mlb.json", "401816759")
    status = raw["competitions"][0]["status"]["type"]
    status.update(state="in", completed=False, shortDetail="Top 7th")
    game = espn._to_game(league("mlb"), raw)
    assert game.state == "in"
    assert game.note == "Top 7th"


def test_未知的沒打完狀態退回_ESPN_的文字():
    raw = _event("espn_mlb.json", "401814780")
    raw["competitions"][0]["status"]["type"].update(
        name="STATUS_SOMETHING_NEW", detail="Delayed Indefinitely"
    )
    assert espn._to_game(league("mlb"), raw).note == "Delayed Indefinitely"


def test_開賽時間未定():
    raw = _event("espn_mlb.json", "401908045")
    raw["competitions"][0]["timeValid"] = False
    assert espn._to_game(league("mlb"), raw).note == "開賽時間未定"


# ---------------------------------------------------------------- 日期查詢


def test_月份展開_含跨年():
    assert espn._months(date(2026, 12, 20), date(2027, 1, 5)) == ["202612", "202701"]
    assert espn._months(date(2026, 10, 1), date(2026, 10, 31)) == ["202610"]


def test_fetch_逐月查詢_不用日期區間(monkeypatch):
    """ESPN 對 dates=起-迄 一律回 400，這是英超西甲曾經整個抓不到的原因。"""
    urls = []
    monkeypatch.setattr(espn, "_get", lambda url: urls.append(url) or {"events": []})

    espn.fetch(league("epl"), date(2026, 9, 25), date(2026, 10, 8))

    assert [u.split("dates=")[1].split("&")[0] for u in urls] == ["202609", "202610"]
    assert not any("-" in u.split("dates=")[1].split("&")[0] for u in urls)


def test_fetch_切回視窗並去掉跨月重複(monkeypatch):
    events = load_fixture("espn_mlb.json")["events"]
    # 兩個月份都回同一批，模擬月份邊界的重複
    monkeypatch.setattr(espn, "_get", lambda url: {"events": events})

    # 8/15–9/30 跨兩個月 → 查兩次，兩次都回同一批
    games = espn.fetch(league("mlb"), date(2026, 8, 15), date(2026, 9, 30))

    # 只留 9 月的兩場（9/1 完賽、9/27 取消），4 月與 10 月的被切掉
    assert [g.uid for g in games] == ["mlb-401816759", "mlb-401817103"]
