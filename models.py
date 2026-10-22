"""跨聯賽的統一賽事格式。

每個資料來源（ESPN / CPBL 爬蟲 / 電競 API）都各自負責把原始資料
轉成 Game，後面的行事曆與推播就不需要知道資料從哪來。
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import config

# pre  = 還沒開打
# in   = 進行中
# post = 已結束（有正式比分）
# void = 延賽 / 取消 / 中止 / 保留：原定時間不會打完，也沒有正式比分。
#        要跟 post 分開，因為資料源常把它們也標成「結束」（ESPN 的 state
#        是 post、CPBL 的關鍵字也落在結束那邊），混在一起就會推出一則
#        「0 - 0」的假賽果；也要跟 pre 分開，否則原定時間一到會照樣提醒開賽。
STATES = ("pre", "in", "post", "void")


@dataclass
class Game:
    uid: str  # 全域唯一，用來當行事曆 UID 與推播去重的 key
    league_key: str
    league_name: str
    emoji: str
    start: datetime  # 一律是帶 tzinfo 的 UTC 時間
    duration_min: int
    home: str
    away: str
    home_score: str | None = None
    away_score: str | None = None
    state: str = "pre"
    status_detail: str = ""
    link: str = ""
    note: str = ""  # 例如「延賽」、「第 9 局下」
    # 電競這類沒有主客場概念的賽事設 True，顯示時用「A vs B」而不是「A @ B」
    neutral: bool = False
    _tags: list[str] = field(default_factory=list)  # 隊名/縮寫，供 teams 篩選用

    @property
    def end(self) -> datetime:
        return self.start + timedelta(minutes=self.duration_min)

    @property
    def matchup(self) -> str:
        """有主客場的寫成「客 @ 主」，中立場地的寫成「A vs B」。"""
        if self.neutral:
            return f"{self.away} vs {self.home}"
        return f"{self.away} @ {self.home}"

    @property
    def finished(self) -> bool:
        return self.state == "post"

    @property
    def void(self) -> bool:
        return self.state == "void"

    def local_start(self) -> datetime:
        return self.start.astimezone(ZoneInfo(config.TIMEZONE))

    def score_line(self) -> str:
        """已結束的比賽回傳含比分的字串，否則只回對戰組合。"""
        if self.home_score is None or self.away_score is None:
            return self.matchup
        return f"{self.away} {self.away_score} - {self.home_score} {self.home}"

    def matches_teams(self, teams: list[str]) -> bool:
        """teams 留空代表全都要；否則只要有一邊命中就算。"""
        if not teams:
            return True
        haystack = " ".join(self._tags).lower()
        return any(t.strip().lower() in haystack for t in teams if t.strip())
