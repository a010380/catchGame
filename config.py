"""所有可調整的設定都集中在這裡，改這個檔案就好，不用動程式邏輯。"""

# 顯示時間用的時區
TIMEZONE = "Asia/Taipei"

# 行事曆訂閱的名稱（會顯示在 iPhone 行事曆列表裡）
CALENDAR_NAME = "我的賽事表"

# 行事曆往後抓幾天的賽程
SCHEDULE_DAYS_AHEAD = 14

# 查賽果時往回看幾天（跨時區的比賽可能跨日，所以至少 2 天）
RESULTS_LOOKBACK_DAYS = 2

# 開賽前幾分鐘提醒（由 iPhone 行事曆負責響，不靠伺服器）
ALARM_MINUTES_BEFORE = 15

# 賽果推播已送出的紀錄保留幾天（避免 state.json 無限長大）
STATE_RETENTION_DAYS = 14


# 聯賽清單。
#
#   enabled        設 False 就完全跳過，不會抓也不會推
#   source         目前只有 "espn"；CPBL 與電競要另外寫 adapter（見 README）
#   path           ESPN API 的路徑片段
#   duration_min   行事曆上這場比賽要佔多久（ESPN 不提供結束時間，只能估）
#   teams          只關注特定球隊時填入隊名或縮寫（例：["NYY", "Dodgers"]）
#                  留空 [] = 該聯賽全部比賽都要
LEAGUES = [
    {
        "key": "mlb",
        "name": "MLB",
        "emoji": "⚾",
        "enabled": True,
        "source": "espn",
        "path": "baseball/mlb",
        "duration_min": 210,
        "teams": [],
    },
    # ---- 以下已接好，確認 MLB 運作正常後把 enabled 改 True 即可 ----
    {
        "key": "nba",
        "name": "NBA",
        "emoji": "🏀",
        "enabled": False,
        "source": "espn",
        "path": "basketball/nba",
        "duration_min": 150,
        "teams": [],
    },
    {
        "key": "nfl",
        "name": "NFL",
        "emoji": "🏈",
        "enabled": False,
        "source": "espn",
        "path": "football/nfl",
        "duration_min": 195,
        "teams": [],
    },
    {
        "key": "epl",
        "name": "英超",
        "emoji": "⚽",
        "enabled": False,
        "source": "espn",
        "path": "soccer/eng.1",
        "duration_min": 120,
        "teams": [],
    },
    {
        "key": "laliga",
        "name": "西甲",
        "emoji": "⚽",
        "enabled": False,
        "source": "espn",
        "path": "soccer/esp.1",
        "duration_min": 120,
        "teams": [],
    },
]


def enabled_leagues():
    return [lg for lg in LEAGUES if lg.get("enabled")]
