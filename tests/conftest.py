"""測試共用的工具。

原則：測試**不碰網路、不碰真的 state.json、不送 Telegram**。
- 資料源的回應用 tests/fixtures/ 裡存下來的真實 API 回應（裁剪過）。
- state.json 導到 pytest 的暫存目錄。
- notify.send 換成把訊息收進 list，測試再檢查內容。
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import notify  # noqa: E402
import state  # noqa: E402
from models import Game  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def league(key: str) -> dict:
    return next(lg for lg in config.LEAGUES if lg["key"] == key)


@pytest.fixture
def tmp_state(tmp_path, monkeypatch):
    """把 state.json 導到暫存檔，並預先建立（避免觸發「首次執行」只建基準的分支）。"""
    path = tmp_path / "state.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(state, "STATE_PATH", path)
    return path


@pytest.fixture
def sent(monkeypatch):
    """攔截所有 Telegram 推播，回傳收到的訊息清單。"""
    messages: list[str] = []
    monkeypatch.setattr(notify, "send", messages.append)
    return messages


def make_game(uid: str, state_: str = "pre", *, minutes_from_now: int = 0,
              home_score=None, away_score=None, note: str = "",
              league_key: str = "mlb") -> Game:
    lg = league(league_key)
    return Game(
        uid=uid,
        league_key=lg["key"],
        league_name=lg["name"],
        emoji=lg["emoji"],
        start=datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now),
        duration_min=lg["duration_min"],
        home=f"{uid}-home",
        away=f"{uid}-away",
        home_score=home_score,
        away_score=away_score,
        state=state_,
        note=note,
    )
