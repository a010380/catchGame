"""產生可被 iPhone 行事曆訂閱的 .ics 檔。

刻意不用第三方 ics 套件：規格需要的部分很少，自己寫可以完全掌握
折行（RFC 5545 規定每行不得超過 75 個位元組）與字元轉義，
這兩點正是 iPhone 行事曆最容易吃不下檔案的地方。
"""

from datetime import datetime, timezone

import config
from models import Game

CRLF = "\r\n"


def _fold(line: str) -> str:
    """依 RFC 5545 折行：以位元組計算，續行開頭加一個空白。

    中文是多位元組字元，若按字元數切會切在字元中間產生亂碼，
    所以這裡逐字元累加位元組長度來切。
    """
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line

    out: list[str] = []
    current = ""
    current_len = 0
    limit = 75
    for ch in line:
        size = len(ch.encode("utf-8"))
        if current_len + size > limit:
            out.append(current)
            current = ch
            current_len = size + 1  # 續行多了一個前導空白
            limit = 75
        else:
            current += ch
            current_len += size
    out.append(current)
    return CRLF.join([out[0]] + [" " + part for part in out[1:]])


def _esc(text: str) -> str:
    """轉義 TEXT 型別的值：反斜線、分號、逗號、換行。"""
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _stamp(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _summary(game: Game) -> str:
    """行事曆標題。已結束的比賽直接把比分寫進標題，滑過去就看得到結果。"""
    prefix = f"{game.emoji} ".strip() + " " if game.emoji else ""
    if game.finished:
        return f"{prefix}{game.score_line()} (終)"
    return f"{prefix}{game.matchup}"


def _description(game: Game) -> str:
    lines = [f"聯賽：{game.league_name}"]
    local = game.local_start().strftime("%Y-%m-%d %H:%M")
    lines.append(f"開賽（{config.TIMEZONE}）：{local}")
    if game.note:
        lines.append(f"備註：{game.note}")
    if game.finished and game.status_detail:
        lines.append(f"狀態：{game.status_detail}")
    if game.link:
        lines.append(game.link)
    return "\n".join(lines)


def _event(game: Game, now: datetime) -> list[str]:
    lines = [
        "BEGIN:VEVENT",
        f"UID:{game.uid}@catchgame",
        f"DTSTAMP:{_stamp(now)}",
        f"DTSTART:{_stamp(game.start)}",
        f"DTEND:{_stamp(game.end)}",
        f"SUMMARY:{_esc(_summary(game))}",
        f"DESCRIPTION:{_esc(_description(game))}",
        f"CATEGORIES:{_esc(game.league_name)}",
        # 已結束的比賽不再是「待辦」，標成 TRANSPARENT 就不會佔用空閒/忙碌
        "TRANSP:TRANSPARENT" if game.finished else "TRANSP:OPAQUE",
    ]
    if game.link:
        lines.append(f"URL:{game.link}")
    if game.note == "開賽時間未定":
        lines.append("STATUS:TENTATIVE")

    # 只有還沒打的比賽需要提醒；已結束的再響就是騷擾
    if not game.finished and config.ALARM_MINUTES_BEFORE > 0:
        lines += [
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{_esc(_summary(game))}",
            f"TRIGGER:-PT{config.ALARM_MINUTES_BEFORE}M",
            "END:VALARM",
        ]
    lines.append("END:VEVENT")
    return lines


def build(games: list[Game], now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//catchGame//Sports Schedule//ZH-TW",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_esc(config.CALENDAR_NAME)}",
        f"X-WR-TIMEZONE:{config.TIMEZONE}",
        # 告訴 iPhone 每 4 小時回來抓一次更新（賽程改期才跟得上）
        "REFRESH-INTERVAL;VALUE=DURATION:PT4H",
        "X-PUBLISHED-TTL:PT4H",
    ]
    for game in sorted(games, key=lambda g: g.start):
        lines += _event(game, now)
    lines.append("END:VCALENDAR")

    return CRLF.join(_fold(line) for line in lines) + CRLF
