"""LoL 電競 adapter：系列賽比分、BO 數、中立場地。"""

from datetime import date

from conftest import league, load_fixture
from sources import lolesports


def _games():
    events = load_fixture("lolesports_worlds.json")["data"]["schedule"]["events"]
    return [lolesports._to_game(league("worlds"), e) for e in events]


def test_完賽的比分是拿下幾小場():
    done = [g for g in _games() if g.finished]
    assert [g.score_line() for g in done] == ["TES 1 - 0 G2", "PSG 0 - 1 GEN"]


def test_沒有主客場():
    for game in _games():
        assert game.neutral
        assert " vs " in game.matchup and " @ " not in game.matchup


def test_未開打_時長按_BO_數估():
    pending = [g for g in _games() if g.state == "pre"]
    assert pending, "fixture 裡應該要有未開打的場次"
    for game in pending:
        assert game.home_score is None
        assert game.note.startswith("BO3")
        assert game.duration_min == lolesports.BO_DURATION[3]


def test_fetch_自己裁切區間(monkeypatch):
    payload = load_fixture("lolesports_worlds.json")
    monkeypatch.setattr(lolesports, "_get", lambda path, params: payload)

    everything = lolesports.fetch(league("worlds"), date(2000, 1, 1), date(2100, 1, 1))
    nothing = lolesports.fetch(league("worlds"), date(2000, 1, 1), date(2000, 1, 2))

    assert len(everything) == 4
    assert nothing == []
