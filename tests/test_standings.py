"""戰績：解析、排序、版面、什麼時候推。

fixture 是 2026-11-09 的真實 ESPN 戰績（只留用得到的欄位）。
"""

import pytest

import config
import main
import notify
import sources
from conftest import league, load_fixture, make_game
from sources import espn


@pytest.fixture
def nba_divisions(monkeypatch):
    """NBA 預設只分東西區；分組的版面改用 NBA 的分組資料來測。"""
    monkeypatch.setitem(league("nba"), "standings", True)


@pytest.fixture
def standings(monkeypatch):
    """讓 espn.fetch_standings 讀 fixture，不連網路。"""
    data = load_fixture("espn_standings.json")
    by_path = {"basketball/nba": "nba", "football/nfl": "nfl", "soccer/eng.1": "epl"}

    def fake_get(url):
        if "/basketball/nba/standings" in url and "level=2" in url:
            return data["nba_conference"]
        for path, key in by_path.items():
            if f"/{path}/standings" in url:
                return data[key]
        raise AssertionError(f"沒有這個 fixture：{url}")

    monkeypatch.setattr(espn, "_get", fake_get)


# ---------------------------------------------------------------- 解析與排序


def test_分組模式_NBA_拆成兩區六組_中文名稱(standings, nba_divisions):
    tables = espn.fetch_standings(league("nba"))
    assert [(t.conference, t.division) for t in tables] == [
        ("東區", "大西洋組"), ("東區", "中央組"), ("東區", "東南組"),
        ("西區", "西北組"), ("西區", "太平洋組"), ("西區", "西南組"),
    ]
    assert all(len(t.rows) == 5 for t in tables)


def test_分組內自己排序_不照_ESPN_的順序(standings, nba_divisions):
    """ESPN 回的大西洋組第一筆是 2-7 的 Nets，不能照抄。"""
    raw_first = load_fixture("espn_standings.json")["nba"]["children"][0]["children"][0]
    assert raw_first["standings"]["entries"][0]["team"]["shortDisplayName"] == "Nets"

    atlantic = espn.fetch_standings(league("nba"))[0]
    assert [r.team for r in atlantic.rows] == ["76ers", "Celtics", "Knicks", "Raptors", "Nets"]
    pcts = [r.win_pct for r in atlantic.rows]
    assert pcts == sorted(pcts, reverse=True)


def test_NFL_八個分區(standings):
    tables = espn.fetch_standings(league("nfl"))
    assert len(tables) == 8
    assert {t.conference for t in tables} == {"AFC", "NFC"}
    assert all(len(t.rows) == 4 for t in tables)


def test_NBA_預設只分東西區_照官方種子序(standings):
    tables = espn.fetch_standings(league("nba"))
    assert [(t.conference, t.division) for t in tables] == [("東區", ""), ("西區", "")]
    assert all(len(t.rows) == 15 for t in tables)
    for table in tables:
        assert [r.seed for r in table.rows] == list(range(1, 16))
        assert table.rows[0].games_behind == "-"   # 勝差以分區龍頭計算，不是分組


def test_NBA_東西區版面_沒有分組標題_種子序在前(standings):
    block = main._standings_block(league("nba"), espn.fetch_standings(league("nba")))
    lines = _lines_in_pre(block)
    assert "東區" in lines and "西區" in lines
    assert not any(name in block for name in ("大西洋組", "西南組"))
    first = lines[lines.index("東區") + 1]
    assert first.startswith(" 1 ")
    assert lines[lines.index("西區") - 1].startswith("15 ")


def test_同勝率照官方種子序_不自己猜():
    """5-4 同勝率的兩隊，誰前誰後由官方的破除規則決定（對戰成績等），這裡照種子序。"""
    rows = [
        espn.StandingRow("A", 5, 4, win_pct=0.556, seed=6),
        espn.StandingRow("B", 5, 4, win_pct=0.556, seed=5),
        espn.StandingRow("C", 6, 3, win_pct=0.667, seed=4),
    ]
    assert [r.team for r in espn._sort_conference(rows)] == ["C", "B", "A"]


def test_足球是單一積分榜_照官方排名(standings):
    tables = espn.fetch_standings(league("epl"))
    assert len(tables) == 1
    table = tables[0]
    assert table.conference == "" and table.division == ""
    assert [r.rank for r in table.rows] == list(range(1, 21))
    assert table.rows[0].team == "Arsenal" and table.rows[0].points == 27


def test_沒翻譯到的名稱照原文(monkeypatch, nba_divisions):
    node = {"children": [{"name": "Some New Conference", "children": [
        {"name": "Brand New Division", "standings": {"entries": [
            {"team": {"shortDisplayName": "A"},
             "stats": [{"name": "wins", "value": 1}, {"name": "losses", "value": 0},
                       {"name": "winPercent", "value": 1.0}]},
        ]}},
    ]}]}
    monkeypatch.setattr(espn, "_get", lambda url: node)
    tables = espn.fetch_standings(league("nba"))
    assert (tables[0].conference, tables[0].division) == ("Some New Conference", "Brand New Division")


def test_足球沒有排名時退回積分與淨勝球():
    rows = [
        espn.StandingRow("A", 1, 0, points=3, goal_diff="+1"),
        espn.StandingRow("B", 1, 0, points=3, goal_diff="+4"),
        espn.StandingRow("C", 2, 0, points=6, goal_diff="0"),
    ]
    assert [r.team for r in espn._sort_table(rows)] == ["C", "B", "A"]


# ---------------------------------------------------------------- 版面


def _lines_in_pre(block: str) -> list[str]:
    return block.split("<pre>")[1].split("</pre>")[0].split("\n")


@pytest.mark.parametrize("key", ["nba", "nfl", "epl"])
def test_每行不超過手機寬度(standings, key):
    block = main._standings_block(league(key), espn.fetch_standings(league(key)))
    assert block.count("<pre>") == 1 and block.count("</pre>") == 1
    assert max(len(line) for line in _lines_in_pre(block)) <= 40


def test_有和局才顯示_T_欄(standings, nba_divisions):
    nfl = main._standings_block(league("nfl"), espn.fetch_standings(league("nfl")))
    nba = main._standings_block(league("nba"), espn.fetch_standings(league("nba")))
    assert "W-L-T" in nfl and "5-2-1" in nfl   # 這季 Giants 有一場和局
    assert "W-L-T" not in nba and "9-2 " in nba


def test_隊名的特殊字元有跳脫(standings):
    tables = espn.fetch_standings(league("nba"))
    tables[0].rows[0].team = "A&M <X>"
    block = main._standings_block(league("nba"), tables)
    assert "A&amp;M &lt;X&gt;" in block


def test_裝箱不會切開任何一段():
    blocks = ["<b>📊 戰績</b>"] + [f"<pre>{'x' * 1500}</pre>" for _ in range(5)]
    messages = main._pack(blocks)
    assert len(messages) > 1
    for msg in messages:
        assert len(msg) <= notify.MAX_LEN
        assert msg.count("<pre>") == msg.count("</pre>")
    assert "\n\n".join(messages) == "\n\n".join(blocks)


# ---------------------------------------------------------------- 什麼時候推


def _final(uid, key, minutes=-200):
    return make_game(uid, "post", minutes_from_now=minutes,
                     home_score="1", away_score="0", league_key=key)


def test_這一輪打完才推():
    pending = [_final("nba-1", "nba")]
    games = pending + [make_game("nba-2", "pre", minutes_from_now=60 * 20, league_key="nba")]
    assert [lg["key"] for lg in main._leagues_ready_for_standings(pending, games)] == ["nba"]


def test_還有比賽在打就不推():
    pending = [_final("nba-1", "nba")]
    games = pending + [make_game("nba-2", "in", minutes_from_now=-30, league_key="nba")]
    assert main._leagues_ready_for_standings(pending, games) == []


def test_下一場很快就開打就先不推():
    """英超週末的時段之間只隔 2-3 小時，要等最後一個時段打完。"""
    soon = config.STANDINGS_QUIET_HOURS * 60 - 30
    pending = [_final("epl-1", "epl")]
    games = pending + [make_game("epl-2", "pre", minutes_from_now=soon, league_key="epl")]
    assert main._leagues_ready_for_standings(pending, games) == []


def test_別的聯賽在打不影響():
    pending = [_final("nba-1", "nba")]
    games = pending + [make_game("nfl-1", "in", league_key="nfl")]
    assert [lg["key"] for lg in main._leagues_ready_for_standings(pending, games)] == ["nba"]


def test_沒有戰績資料源的聯賽不推():
    pending = [_final("cpbl-1", "cpbl"), _final("worlds-1", "worlds")]
    assert main._leagues_ready_for_standings(pending, pending) == []


def test_設定關掉就不推(monkeypatch):
    monkeypatch.setitem(league("nba"), "standings", False)
    pending = [_final("nba-1", "nba")]
    assert main._leagues_ready_for_standings(pending, pending) == []


# ---------------------------------------------------------------- 跟賽果串起來


def test_賽果之後另外一則戰績(tmp_state, sent, standings, monkeypatch):
    monkeypatch.setattr(main, "collect", lambda **_: ([_final("nba-1", "nba")], []))

    main.cmd_results(None)

    assert len(sent) == 2
    assert "🏁 賽果" in sent[0] and "戰績" not in sent[0]
    assert "📊 戰績" in sent[1] and "東區" in sent[1] and "大西洋組" not in sent[1]


def test_戰績壞掉不影響賽果(tmp_state, sent, monkeypatch):
    def boom(_league):
        raise RuntimeError("ESPN 掛了")

    monkeypatch.setattr(sources, "fetch_standings", boom)
    monkeypatch.setattr(main, "collect", lambda **_: ([_final("nba-1", "nba")], []))

    assert main.cmd_results(None) == 0
    assert len(sent) == 1 and "🏁 賽果" in sent[0]
    import state
    assert state.already(state.load(), "notified", "nba-1")
