"""統一賽事格式與行事曆輸出。"""

import config
import icsfile
from conftest import make_game


def test_比分與對戰顯示():
    game = make_game("g", "post", home_score="6", away_score="2")
    assert game.matchup == "g-away @ g-home"
    assert game.score_line() == "g-away 2 - 6 g-home"


def test_球隊過濾():
    game = make_game("g")
    game._tags = ["NYY", "Yankees", "New York Yankees"]
    assert game.matches_teams([])
    assert game.matches_teams(["yankees"])
    assert game.matches_teams(["Dodgers", "NYY"])
    assert not game.matches_teams(["Dodgers"])


def test_行事曆標題():
    done = make_game("a", "post", home_score="1", away_score="0")
    void = make_game("b", "void", note="取消")
    pre = make_game("c")
    assert icsfile._summary(done).endswith("a-away 0 - 1 a-home (終)")
    assert icsfile._summary(void).endswith("b-away @ b-home (取消)")
    assert icsfile._summary(pre).endswith("c-away @ c-home")


def test_延賽的比賽不會響鈴(monkeypatch):
    monkeypatch.setattr(config, "ALARM_MINUTES_BEFORE", 15)
    pre = icsfile.build([make_game("pre", minutes_from_now=60)])
    void = icsfile.build([make_game("void", "void", minutes_from_now=60, note="延賽")])
    assert "BEGIN:VALARM" in pre
    assert "BEGIN:VALARM" not in void
