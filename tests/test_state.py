"""推播紀錄：去重、過期清理、連續失敗計數。"""

import json
from datetime import datetime, timedelta, timezone

import state


def test_mark_與_already(tmp_state):
    data = state.load()
    assert not state.already(data, "notified", "mlb-1")
    state.mark(data, "notified", "mlb-1")
    assert state.already(data, "notified", "mlb-1")
    # 不同桶互不影響
    assert not state.already(data, "voided", "mlb-1")


def test_存檔後讀得回來(tmp_state):
    data = state.load()
    state.mark(data, "voided", "cpbl-9")
    state.save(data)
    assert state.already(state.load(), "voided", "cpbl-9")


def test_內容沒變就不寫檔(tmp_state):
    """不然排程每 10 分鐘就會產生一個只有 updated_at 變動的 commit。"""
    data = state.load()
    state.mark(data, "notified", "mlb-1")
    state.save(data)
    first = tmp_state.read_text(encoding="utf-8")

    state.save(state.load())

    assert tmp_state.read_text(encoding="utf-8") == first


def test_prune_清掉過期紀錄_但不動_failures(tmp_state):
    data = state.load()
    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    data["notified"]["old"] = old
    data["voided"]["old"] = old
    state.mark(data, "notified", "new")
    state.record_fetch(data, "epl", ok=False)

    removed = state.prune(data)

    assert removed == 2
    assert list(data["notified"]) == ["new"]
    assert data["voided"] == {}
    assert state.fail_streak(data, "epl") == 1


def test_連續失敗計數_成功就歸零(tmp_state):
    data = state.load()
    assert [state.record_fetch(data, "epl", ok=False) for _ in range(3)] == [1, 2, 3]
    since = data[state.FAILURES]["epl"]["since"]
    state.record_fetch(data, "epl", ok=False)
    # since 記的是「第一次失敗」的時間，不會每次被覆蓋
    assert data[state.FAILURES]["epl"]["since"] == since

    assert state.record_fetch(data, "epl", ok=True) == 0
    # 成功是整筆刪掉，不是留一個 0
    assert data[state.FAILURES] == {}


def test_壞掉的檔案就重新開始(tmp_state):
    tmp_state.write_text("{not json", encoding="utf-8")
    data = state.load()
    assert data["notified"] == {} and data[state.FAILURES] == {}


def test_舊版檔案缺桶也能讀(tmp_state):
    tmp_state.write_text(json.dumps({"notified": {"a": "2026-01-01T00:00:00+00:00"}}),
                         encoding="utf-8")
    data = state.load()
    assert "voided" in data and state.FAILURES in data
