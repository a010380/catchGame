"""賽事提醒主程式。

用法：
  python main.py preview      抓賽程印在畫面上（不碰 Telegram，最適合第一次測試）
  python main.py calendar     產生 docs/calendar.ics（給 iPhone 行事曆訂閱）
  python main.py digest       推播「接下來 24 小時」摘要
  python main.py remind       推播即將開賽的比賽（開賽前 20 分鐘內）
  python main.py results      推播剛結束的比賽比分（會記錄避免重複）
  python main.py tick         remind + results，排程實際跑的就是這個
  python main.py chat-id      找出你的 Telegram chat id（只需要 BOT_TOKEN）
  python main.py test-notify  送一則測試訊息，確認 Telegram 設定正確
"""

import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import config
import icsfile
import notify
import sources
import state
from models import Game

CALENDAR_PATH = Path(__file__).parent / "docs" / "calendar.ics"

# 摘要要涵蓋往後幾小時。24 小時剛好蓋住美洲聯賽在台灣清晨的整個時段。
DIGEST_HOURS = 24

# Windows 主控台預設不是 UTF-8，直接印中文會變亂碼；Linux/Actions 上不受影響。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def _tz() -> ZoneInfo:
    return ZoneInfo(config.TIMEZONE)


def collect(days_back: int, days_ahead: int) -> list[Game]:
    """抓取所有啟用聯賽在指定區間內的比賽。

    單一聯賽抓失敗時只警告不中斷 —— 一個聯賽的 API 掛掉不該讓其他聯賽的提醒也停擺。
    """
    leagues = config.enabled_leagues()
    if not leagues:
        print("config.py 裡沒有任何 enabled 的聯賽。", file=sys.stderr)
        return []

    # ESPN 的日期參數是以美東日期為準，前後各多抓一天避免跨時區漏掉邊界場次
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days_back + 1)
    end = today + timedelta(days=days_ahead + 1)

    games: list[Game] = []
    for league in leagues:
        try:
            fetched = sources.fetch(league, start, end)
            games.extend(fetched)
            print(f"  {league['name']}: {len(fetched)} 場")
        except Exception as err:
            print(f"  {league['name']}: 抓取失敗 — {err}", file=sys.stderr)
    games.sort(key=lambda g: g.start)
    return games


def _fmt_time(game: Game) -> str:
    return game.local_start().strftime("%m/%d %H:%M")


# ---------------------------------------------------------------- commands


def cmd_preview(_args) -> int:
    print("抓取賽程中…")
    games = collect(days_back=1, days_ahead=config.SCHEDULE_DAYS_AHEAD)
    if not games:
        print("沒有抓到任何比賽。")
        return 1

    print(f"\n共 {len(games)} 場（時間為 {config.TIMEZONE}）\n")
    current_day = None
    for game in games:
        day = game.local_start().date()
        if day != current_day:
            current_day = day
            print(f"── {day:%Y-%m-%d (%a)} ──")
        label = {"pre": " ", "in": "▶", "post": "✓"}.get(game.state, " ")
        line = f" {label} {_fmt_time(game)}  {game.emoji} {game.league_name:6} {game.score_line()}"
        if game.note:
            line += f"  [{game.note}]"
        print(line)
    return 0


def cmd_calendar(_args) -> int:
    print("抓取賽程中…")
    # 往回抓幾天，這樣行事曆上前幾天的比賽會帶著比分，不是空的對戰組合
    games = collect(days_back=3, days_ahead=config.SCHEDULE_DAYS_AHEAD)
    if not games:
        print("沒有抓到任何比賽，維持原有的行事曆檔不動。", file=sys.stderr)
        return 1

    CALENDAR_PATH.parent.mkdir(parents=True, exist_ok=True)
    CALENDAR_PATH.write_text(icsfile.build(games), encoding="utf-8", newline="")
    size_kb = CALENDAR_PATH.stat().st_size / 1024
    print(f"\n已寫入 {CALENDAR_PATH.relative_to(Path(__file__).parent)}"
          f"（{len(games)} 場，{size_kb:.1f} KB）")
    return 0


def cmd_digest(_args) -> int:
    print("抓取接下來 24 小時的賽程…")
    games = collect(days_back=0, days_ahead=2)

    now = datetime.now(timezone.utc)
    horizon = now + timedelta(hours=DIGEST_HOURS)
    upcoming = [
        g for g in games
        if not g.finished and now <= g.start <= horizon
    ]

    local_now = datetime.now(_tz())
    header = (
        f"<b>📅 接下來 {DIGEST_HOURS} 小時的賽事</b>\n"
        f"<i>{local_now:%m/%d %H:%M} 起</i>"
    )
    if not upcoming:
        notify.send(f"{header}\n\n這段時間沒有你關注的比賽。")
        print("接下來 24 小時沒有比賽，已送出空摘要。")
        return 0

    lines = [header, ""]
    current_league = None
    current_day = None
    for game in upcoming:
        if game.league_name != current_league:
            current_league = game.league_name
            current_day = None
            lines.append(f"{game.emoji} <b>{notify.esc(game.league_name)}</b>")
        day = game.local_start().date()
        if day != current_day:
            current_day = day
            lines.append(f"  <u>{day:%m/%d (%a)}</u>")
        note = f" <i>({notify.esc(game.note)})</i>" if game.note else ""
        lines.append(
            f"    {game.local_start():%H:%M}  {notify.esc(game.matchup)}{note}"
        )
    notify.send("\n".join(lines))
    print(f"已推播 {len(upcoming)} 場比賽。")
    return 0


def cmd_remind(_args) -> int:
    """推播即將開賽的比賽。

    刻意把同一批比賽併成一則訊息 —— CPBL 三場同時 18:35 開打、MLB 常常
    十幾場擠在同一個時段，一場一則會變成連續轟炸。
    """
    print("檢查即將開賽的比賽…")
    games = collect(days_back=0, days_ahead=1)

    now = datetime.now(timezone.utc)
    lead = timedelta(minutes=config.REMIND_LEAD_MINUTES)

    data = state.load()
    upcoming = [
        g for g in games
        if not g.finished
        and now < g.start <= now + lead
        and not state.already(data, "reminded", g.uid)
    ]

    if not upcoming:
        state.save(data)
        print("這個時段沒有即將開賽的比賽。")
        return 0

    lines = ["<b>🔔 即將開賽</b>", ""]
    current_league = None
    for game in upcoming:
        if game.league_name != current_league:
            current_league = game.league_name
            lines.append(f"{game.emoji} <b>{notify.esc(game.league_name)}</b>")
        mins = max(1, round((game.start - now).total_seconds() / 60))
        note = f" <i>({notify.esc(game.note)})</i>" if game.note else ""
        lines.append(
            f"  {game.local_start():%H:%M}（{mins} 分鐘後）"
            f"  {notify.esc(game.matchup)}{note}"
        )

    notify.send("\n".join(lines))

    for game in upcoming:
        state.mark(data, "reminded", game.uid)
    state.prune(data)
    state.save(data)
    print(f"已推播 {len(upcoming)} 場開賽提醒。")
    return 0


def cmd_tick(args) -> int:
    """排程每次醒來要做的事：先提醒即將開賽，再推播剛結束的賽果。

    合併成一個指令是為了讓排程只跑一個 job —— 兩個 job 各自 commit
    同一個 state.json 會互相衝突，而且重複的 checkout / pip install 很浪費。
    """
    codes = [cmd_remind(args), cmd_results(args)]
    return max(codes)


def cmd_results(_args) -> int:
    print("檢查已結束的比賽…")
    games = collect(days_back=config.RESULTS_LOOKBACK_DAYS, days_ahead=0)

    # 第一次執行時 state.json 還不存在，如果照常推播會一次補送過去幾天
    # 所有比賽的賽果。這種情況只建立基準，不發通知。
    first_run = not state.STATE_PATH.exists()
    data = state.load()

    if first_run:
        for game in games:
            if game.finished:
                state.mark(data, "notified", game.uid)
        state.save(data)
        print(f"首次執行：已把 {len(data['notified'])} 場既有賽果設為基準，未發送通知。")
        return 0
    pending = [
        g for g in games
        if g.finished and not state.already(data, "notified", g.uid)
    ]

    if not pending:
        removed = state.prune(data)
        state.save(data)
        print(f"沒有新結束的比賽。（清掉 {removed} 筆過期紀錄）")
        return 0

    lines = ["<b>🏁 賽果</b>", ""]
    current_league = None
    for game in pending:
        if game.league_name != current_league:
            current_league = game.league_name
            lines.append(f"{game.emoji} <b>{notify.esc(game.league_name)}</b>")
        lines.append(
            f"  {_fmt_time(game)}  {notify.esc(game.score_line())}"
        )

    notify.send("\n".join(lines))

    # 推播成功才記錄，失敗時下次排程會重試
    for game in pending:
        state.mark(data, "notified", game.uid)
    removed = state.prune(data)
    state.save(data)
    print(f"已推播 {len(pending)} 場賽果。（清掉 {removed} 筆過期紀錄）")
    return 0


def cmd_chat_id(_args) -> int:
    """找出你的 chat id —— 取代手動貼 getUpdates 網址的做法。"""
    bot = notify.describe_bot()
    username = bot.get("username", "?")
    print(f"Bot 連線正常：@{username}（{bot.get('first_name')}）")
    print()

    chats = notify.find_chats()
    if not chats:
        print("找不到任何對話紀錄。請照以下順序做：")
        print(f"  1. 在 Telegram 搜尋 @{username}")
        print("  2. 按 START，或隨便傳一句話給它")
        print("  3. 回來再執行一次 python main.py chat-id")
        print()
        print("（Telegram 只保留最近約 24 小時的訊息紀錄，")
        print("  所以要先傳訊息、再馬上查。）")
        return 1

    print("找到以下對話，把 chat id 設成 TELEGRAM_CHAT_ID：")
    print()
    for chat in chats:
        name = " ".join(
            filter(None, [chat.get("first_name"), chat.get("last_name")])
        ) or chat.get("title") or ""
        print(f"  chat id = {chat['id']}    （{chat.get('type')} {name}）")
    return 0


def cmd_test_notify(_args) -> int:
    now = datetime.now(_tz()).strftime("%Y-%m-%d %H:%M:%S")
    notify.send(
        "<b>✅ catchGame 測試訊息</b>\n\n"
        f"如果你看到這則訊息，Telegram 設定正確。\n"
        f"本機時間：{now} ({config.TIMEZONE})"
    )
    print("測試訊息已送出，請看你的 Telegram。")
    return 0


COMMANDS = {
    "chat-id": cmd_chat_id,
    "preview": cmd_preview,
    "remind": cmd_remind,
    "tick": cmd_tick,
    "calendar": cmd_calendar,
    "digest": cmd_digest,
    "results": cmd_results,
    "test-notify": cmd_test_notify,
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="多聯賽賽程整合：行事曆訂閱 + Telegram 賽果推播",
    )
    parser.add_argument("command", choices=sorted(COMMANDS), help="要執行的動作")
    args = parser.parse_args()
    try:
        return COMMANDS[args.command](args)
    except notify.NotConfigured as err:
        print(f"設定不完整：{err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
