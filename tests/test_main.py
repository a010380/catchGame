"""main.py 的推播流程：抓取失敗告警、賽果、開賽提醒、每日摘要時間控制。

collect() 一律換成回傳假資料，所以這裡測的是「拿到這些比賽之後該推什麼」，
不碰網路。
"""

import config
import main
import state
from conftest import make_game


def _feed(monkeypatch, games, failed=()):
    monkeypatch.setattr(main, "collect", lambda **_: (list(games), list(failed)))


# ---------------------------------------------------------------- 抓取失敗告警


def test_偶發失敗只警告_連續失敗才紅燈(tmp_state, capsys):
    data = state.load()
    threshold = config.FAIL_STREAK_ALERT

    codes = [main._report_failures(data, ["epl"]) for _ in range(threshold)]

    assert codes == [0] * (threshold - 1) + [1]
    out = capsys.readouterr().out
    assert "::warning::" in out
    assert f"::error::英超（連續 {threshold} 次）" in out


def test_成功一次就歸零(tmp_state):
    data = state.load()
    for _ in range(config.FAIL_STREAK_ALERT - 1):
        main._report_failures(data, ["epl"])
    assert main._report_failures(data, []) == 0
    # 歸零後重新累積，第一次失敗不會紅燈
    assert main._report_failures(data, ["epl"]) == 0


def test_全部聯賽都失敗_立刻紅燈(tmp_state):
    everything = [lg["key"] for lg in config.enabled_leagues()]
    assert main._report_failures(state.load(), everything) == 1


# ---------------------------------------------------------------- 賽果 / 延賽


def test_賽果與延賽併成一則_且不重送(tmp_state, sent, monkeypatch):
    _feed(monkeypatch, [
        make_game("mlb-1", "post", minutes_from_now=-200, home_score="5", away_score="3"),
        make_game("mlb-2", "void", minutes_from_now=-200, note="延賽"),
        make_game("mlb-3", "pre", minutes_from_now=60),
    ])

    main.cmd_results(None)
    main.cmd_results(None)

    assert len(sent) == 1
    msg = sent[0]
    assert "🏁 賽果" in msg and "mlb-1-away 3 - 5 mlb-1-home" in msg
    assert "⚠️ 延賽 / 取消" in msg and "mlb-2-away @ mlb-2-home（延賽）" in msg
    assert "mlb-3" not in msg


def test_延賽不會被當成_0比0_的賽果(tmp_state, sent, monkeypatch):
    _feed(monkeypatch, [make_game("mlb-2", "void", minutes_from_now=-200, note="取消")])
    main.cmd_results(None)
    assert "🏁 賽果" not in sent[0]
    assert "0 - 0" not in sent[0]


def test_沒有新東西就不送(tmp_state, sent, monkeypatch):
    _feed(monkeypatch, [make_game("mlb-3", "pre", minutes_from_now=60)])
    main.cmd_results(None)
    assert sent == []


def test_首次執行只建基準_不推播(tmp_state, sent, monkeypatch):
    tmp_state.unlink()
    _feed(monkeypatch, [
        make_game("mlb-1", "post", minutes_from_now=-200, home_score="1", away_score="0"),
        make_game("mlb-2", "void", minutes_from_now=-200, note="延賽"),
    ])

    main.cmd_results(None)

    assert sent == []
    data = state.load()
    assert state.already(data, "notified", "mlb-1")
    assert state.already(data, "voided", "mlb-2")


def test_推播失敗就不記錄_下次重試(tmp_state, monkeypatch):
    import notify

    def boom(_text):
        raise RuntimeError("Telegram 掛了")

    monkeypatch.setattr(notify, "send", boom)
    _feed(monkeypatch, [make_game("mlb-1", "post", minutes_from_now=-200,
                                  home_score="1", away_score="0")])
    try:
        main.cmd_results(None)
    except RuntimeError:
        pass
    assert not state.already(state.load(), "notified", "mlb-1")


# ---------------------------------------------------------------- 開賽提醒


def test_開賽提醒的視窗(tmp_state, sent, monkeypatch):
    lead, catchup = config.REMIND_LEAD_MINUTES, config.REMIND_CATCHUP_MINUTES
    _feed(monkeypatch, [
        make_game("soon", minutes_from_now=lead - 5),
        make_game("late", "in", minutes_from_now=-(catchup - 10)),   # 排程遲到，照樣補送
        make_game("far", minutes_from_now=lead + 30),                # 還太早
        make_game("gone", "in", minutes_from_now=-(catchup + 10)),   # 超過補送視窗
        make_game("void", "void", minutes_from_now=5, note="延賽"),  # 不會開打
        make_game("done", "post", minutes_from_now=-5, home_score="1", away_score="0"),
    ])

    main.cmd_remind(None)

    msg = sent[0]
    assert "soon-away" in msg and "分鐘後" in msg
    assert "late-away" in msg and "已開打" in msg
    for absent in ("far-", "gone-", "void-", "done-"):
        assert absent not in msg


def test_開賽提醒不重送(tmp_state, sent, monkeypatch):
    _feed(monkeypatch, [make_game("soon", minutes_from_now=10)])
    main.cmd_remind(None)
    main.cmd_remind(None)
    assert len(sent) == 1


# ---------------------------------------------------------------- 每日摘要時間控制


def _freeze(monkeypatch, hh: int, mm: int):
    """把 main 看到的「現在」固定在台灣時間今天的 hh:mm。"""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    fixed = datetime.now(ZoneInfo(config.TIMEZONE)).replace(
        hour=hh, minute=mm, second=0, microsecond=0
    )

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)

    monkeypatch.setattr(main, "datetime", Frozen)


def test_摘要_太早不送(tmp_state, monkeypatch):
    monkeypatch.setattr(config, "DIGEST_NOT_BEFORE", "06:30")
    _freeze(monkeypatch, 5, 0)
    assert "早於" in main._digest_gate(state.load(), force=False)
    _freeze(monkeypatch, 6, 30)
    assert main._digest_gate(state.load(), force=False) is None


def test_摘要_今天送過就不再送(tmp_state, monkeypatch):
    monkeypatch.setattr(config, "DIGEST_NOT_BEFORE", "06:30")
    _freeze(monkeypatch, 7, 0)
    data = state.load()
    assert main._digest_gate(data, force=False) is None
    main._mark_digest_sent(data)
    assert "已經送過" in main._digest_gate(state.load(), force=False)


def test_摘要_force_無視限制(tmp_state, monkeypatch):
    monkeypatch.setattr(config, "DIGEST_NOT_BEFORE", "06:30")
    _freeze(monkeypatch, 5, 0)
    data = state.load()
    main._mark_digest_sent(data)
    assert main._digest_gate(state.load(), force=True) is None


# ---------------------------------------------------------------- tick


def test_tick_只抓一次_範圍涵蓋提醒與賽果(tmp_state, sent, monkeypatch):
    calls = []

    def fake_collect(**window):
        calls.append(window)
        return [
            make_game("soon", minutes_from_now=10),
            make_game("done", "post", minutes_from_now=-200, home_score="2", away_score="1"),
        ], []

    monkeypatch.setattr(main, "collect", fake_collect)

    main.cmd_tick(None)

    assert calls == [{"days_back": config.RESULTS_LOOKBACK_DAYS, "days_ahead": 1}]
    assert len(sent) == 2
    assert "即將開賽" in sent[0] and "soon-away" in sent[0]
    assert "賽果" in sent[1] and "done-away 1 - 2 done-home" in sent[1]


def test_tick_連續失敗一次只加一(tmp_state, sent, monkeypatch):
    """舊版 remind 和 results 各自回報一次，一次 tick 加 2，20 分鐘就紅燈。"""
    _feed(monkeypatch, [], failed=["epl"])
    main.cmd_tick(None)
    assert state.fail_streak(state.load(), "epl") == 1


def test_tick_賽果失敗時提醒的紀錄不能丟(tmp_state, monkeypatch):
    import notify

    def send(text):
        if "賽果" in text:
            raise RuntimeError("Telegram 掛了")

    monkeypatch.setattr(notify, "send", send)
    _feed(monkeypatch, [
        make_game("soon", minutes_from_now=10),
        make_game("done", "post", minutes_from_now=-200, home_score="2", away_score="1"),
    ])

    assert main.cmd_tick(None) == 1

    data = state.load()
    assert state.already(data, "reminded", "soon")       # 送出去的要記住，不然會重送
    assert not state.already(data, "notified", "done")   # 沒送出去的不能記，下次重試


def test_tick_首次執行_賽果只建基準(tmp_state, sent, monkeypatch):
    """舊版 remind 先跑、先把 state.json 建出來，results 就判斷不出是首次執行，
    會把過去幾天的賽果一次全部補送。"""
    tmp_state.unlink()
    _feed(monkeypatch, [
        make_game("done", "post", minutes_from_now=-200, home_score="2", away_score="1"),
    ])

    main.cmd_tick(None)

    assert sent == []
    assert state.already(state.load(), "notified", "done")
