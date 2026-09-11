"""所有可調整的設定都集中在這裡，改這個檔案就好，不用動程式邏輯。"""

# 顯示時間用的時區
TIMEZONE = "Asia/Taipei"

# 行事曆訂閱的名稱（會顯示在 iPhone 行事曆列表裡）
CALENDAR_NAME = "我的賽事表"

# 行事曆往後抓幾天的賽程
SCHEDULE_DAYS_AHEAD = 14

# 查賽果時往回看幾天（跨時區的比賽可能跨日，所以至少 2 天）
RESULTS_LOOKBACK_DAYS = 2

# 行事曆檔裡要不要放提醒（VALARM）。
#
# 設 0 = 不放。因為開賽提醒已經改由 Telegram 負責（見下面的 REMIND_LEAD_MINUTES），
# 如果這裡也放提醒，同一場比賽會同時跳行事曆通知和 Telegram 通知。
# 想改回讓 iPhone 行事曆響鈴，把這個設成 15、並把 notify.yml 的排程關掉即可。
ALARM_MINUTES_BEFORE = 0

# Telegram 開賽提醒：比賽開始前幾分鐘內就推提醒。
#
# 這是一個「視窗」而不是精準時點 —— GitHub Actions 的排程不保證準時，
# 所以做法是每 10 分鐘檢查一次，把「還沒提醒過、且距離開賽在這個分鐘數
# 以內」的比賽推出去。正常情況下送達時間落在開賽前約 20 到 5 分鐘。
REMIND_LEAD_MINUTES = 20

# 排程遲到時，往回補送幾分鐘內開打的比賽。
#
# 為什麼需要這個：GitHub Actions 的排程延遲 20-60 分鐘是常態，有時整槍被丟掉。
# 如果提醒視窗只看未來（start > now），比賽一旦開打就從視窗裡消失，
# 那場比賽就永遠不會被提醒，而且沒有任何痕跡。所以視窗要往回延伸 ——
# 遲到的提醒會標成「已開打 X 分鐘」照樣送出，寧可晚到也不要無聲消失。
#
# 設成 0 就退回「只提醒還沒開打的」的舊行為（會漏）。
REMIND_CATCHUP_MINUTES = 60

# 賽果推播已送出的紀錄保留幾天（避免 state.json 無限長大）
STATE_RETENTION_DAYS = 14


# 聯賽清單。
#
#   enabled        設 False 就完全跳過，不會抓也不會推
#   source         "espn" / "yahoo" / "lolesports"
#   path           espn 與 yahoo 的路徑片段（lolesports 改用 league_id）
#   league_id      lolesports 專用，聯賽的數字 ID
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

    # ---- CPBL（透過 Yahoo 運動，隊名直接是中文）----
    {
        "key": "cpbl",
        "name": "CPBL",
        "emoji": "⚾",
        "enabled": True,
        "source": "yahoo",
        "path": "cpbl",
        "duration_min": 210,
        # 想只看特定球隊就填：["樂天", "中信"]（短名或全名都可比對）
        "teams": [],
    },

    # ---- LoL 電競。league_id 來自 lolesports 的 getLeagues ----
    {
        "key": "lck",
        "name": "LCK",
        "emoji": "🎮",
        "enabled": True,
        "source": "lolesports",
        "league_id": "98767991310872058",
        "duration_min": 180,
        "teams": [],
    },
    {
        "key": "lcp",
        "name": "LCP",
        "emoji": "🎮",
        "enabled": True,
        "source": "lolesports",
        "league_id": "113476371197627891",
        "duration_min": 180,
        "teams": [],
    },
    {
        "key": "msi",
        "name": "MSI",
        "emoji": "🏆",
        "enabled": True,
        "source": "lolesports",
        "league_id": "98767991325878492",
        "duration_min": 180,
        "teams": [],
    },
    {
        "key": "worlds",
        "name": "Worlds",
        "emoji": "🏆",
        "enabled": True,
        "source": "lolesports",
        "league_id": "98767975604431411",
        "duration_min": 180,
        "teams": [],
    },
]


def enabled_leagues():
    return [lg for lg in LEAGUES if lg.get("enabled")]
