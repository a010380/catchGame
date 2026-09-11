# catchGame — 多聯賽賽程提醒與賽果推播

把你關注的各聯賽賽程整合起來，做兩件事：

1. **開賽提醒** — 產生一個行事曆訂閱檔（`.ics`），iPhone 訂閱後由**內建行事曆**負責在開賽前 15 分鐘響鈴。
2. **賽果推播** — 比賽結束後，用 **Telegram** 把比分送到你手機，另外每天早上推一則「接下來 24 小時的賽事」摘要。

目前啟用：**MLB**。NBA / NFL / 英超 / 西甲的程式已經接好，在 `config.py` 把 `enabled` 改成 `True` 就會生效。

---

## 為什麼不做成 iOS App？

原本的想法是用 Python 寫 App 上 TestFlight。技術上可行，但對這個需求是最貴又最脆弱的路線：

- iOS **不允許**第三方 App 長期在背景抓資料或倒數，「開賽提醒」本質上必須由手機以外的東西觸發。
- TestFlight 每個 build 只有 **90 天**，到期要重新打包上傳。
- 需要 **99 美元/年**的開發者帳號 + Mac + Xcode。
- 爬蟲邏輯放在 App 內，對方網站一改版就得重新打包發版（CPBL 幾乎確定要爬蟲）。

所以這個專案把工作分成兩半，各自交給最適合的角色：

```
GitHub Actions（免費排程，代替你按「執行」）
        │
        ▼
  Python 抓賽程 / 比分
        │
        ├──► docs/calendar.ics ──► iPhone 行事曆訂閱 ──► 開賽前 15 分鐘提醒
        └──► Telegram Bot ──────────────────────────► 賽果與今日摘要推播
```

**開賽提醒交給行事曆、不交給排程**，是因為 GitHub Actions 的 cron 不保證準時（尖峰可能延遲 5～15 分鐘），拿來觸發「開賽前 15 分鐘」會失準。改由 iPhone 內建行事曆響鈴，準時、不耗任何伺服器資源，而且賽程改期時下一次更新會自動同步。

---

## 檔案結構

| 檔案 | 作用 |
| --- | --- |
| `config.py` | **唯一需要你動的設定檔**：聯賽開關、關注球隊、提醒分鐘數 |
| `main.py` | 進入點，所有指令都從這裡跑 |
| `models.py` | 跨聯賽的統一賽事格式 `Game` |
| `sources/espn.py` | ESPN 公開 API adapter（一支覆蓋 MLB/NBA/NFL/英超/西甲） |
| `icsfile.py` | 產生符合 RFC 5545 的行事曆檔 |
| `notify.py` | Telegram 推播 |
| `state.py` | 記錄已推播的比賽，避免重複通知 |
| `docs/calendar.ics` | 產生出來的行事曆，由 GitHub Pages 對外提供 |
| `.github/workflows/` | 三個排程：更新行事曆、推播賽果、今日摘要 |

---

## 設定步驟

### 步驟 1：本機先跑起來看看（不需要任何帳號）

```bash
pip install -r requirements.txt
python main.py preview
```

會印出未來兩週的 MLB 賽程（台灣時間）。`✓` 是已結束並附比分，`▶` 是進行中，空白是還沒打。

想調整關注範圍就改 [`config.py`](config.py)：

```python
# 只想看洋基和道奇：
"teams": ["Yankees", "Dodgers"],   # 留空 [] = 該聯賽全部比賽
```

### 步驟 2：建立 Telegram Bot

1. 手機或電腦開 Telegram，搜尋 **@BotFather**，傳 `/newbot`。
2. 依指示取名，完成後它會給你一串 **token**（長得像 `123456789:AAH...`）。
3. **先在 Telegram 跟這個 bot 傳一句話**（搜尋你的 bot 名稱，按 START 或隨便打「hi」）。

   這步不能跳過 —— Telegram 只會讓你查到「已經跟 bot 對話過」的人的 id。

4. 設定 token 後執行 `chat-id` 指令，它會直接印出你的 chat id：

   ```bash
   # PowerShell
   $env:TELEGRAM_BOT_TOKEN="你的token"
   python main.py chat-id
   ```

   ```
   Bot 連線正常：@你的bot_bot（catchGame）

   找到以下對話，把 chat id 設成 TELEGRAM_CHAT_ID：

     chat id = 1045957668    （private Jackson）
   ```

   > 如果顯示「找不到任何對話紀錄」，就是第 3 步沒做，或是傳訊息後隔太久
   > （Telegram 只保留最近約 24 小時的紀錄）。回去傳一句話再跑一次就好。

5. 測試推播：

   ```bash
   $env:TELEGRAM_CHAT_ID="上一步拿到的數字"
   python main.py test-notify
   ```

   手機收到「✅ catchGame 測試訊息」就代表通了。

### 步驟 3：推上 GitHub

```bash
git init
git add .
git commit -m "feat: 賽事提醒與賽果推播"
git branch -M main
git remote add origin https://github.com/<你的帳號>/catchGame.git
git push -u origin main
```

> **建議設成 public repo。** Actions 對公開 repo 的免費額度無上限；私人 repo 每月 2000 分鐘，而本專案的排程大約會用掉 1400 分鐘（見下方「用量」）。這個 repo 裡沒有任何私密內容 —— token 是放在 GitHub Secrets，不在程式碼裡。

### 步驟 4：設定 Secrets

到 repo 的 **Settings → Secrets and variables → Actions → New repository secret**，加兩筆：

| Name | Value |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | 步驟 2 拿到的 token |
| `TELEGRAM_CHAT_ID` | 步驟 2 拿到的 chat id |

### 步驟 5：開啟 GitHub Pages

**Settings → Pages → Source** 選 `Deploy from a branch`，branch 選 `main`、資料夾選 **`/docs`**，儲存。

一兩分鐘後你的行事曆網址就是：

```
https://<你的帳號>.github.io/catchGame/calendar.ics
```

### 步驟 6：iPhone 訂閱行事曆

**設定 → 行事曆 → 帳號 → 加入帳號 → 其他 → 加入已訂閱的行事曆**，貼上上面那個網址。

> 貼網址時把 `https://` 保留即可。訂閱後「我的賽事表」會出現在行事曆 App 裡，每場比賽會自動在**開賽前 15 分鐘**通知你。

### 步驟 7：手動觸發一次，確認全部正常

到 repo 的 **Actions** 頁面，三個 workflow 各點一次 **Run workflow**：

- **更新賽程行事曆** → 跑完後 `docs/calendar.ics` 會有新的 commit
- **今日賽事摘要** → 手機會收到今天的賽程
- **推播賽果** → 第一次執行只會建立基準、不發通知（避免一次補送過去幾天所有比分），第二次之後才會真的推播

---

## 排程時間

| Workflow | 執行時間（台灣時間） | 做什麼 |
| --- | --- | --- |
| `calendar.yml` | 每天 04:00 | 重新產生 `.ics` 並 commit |
| `digest.yml` | 每天 08:00 | 推播「接下來 24 小時有哪些比賽」 |
| `results.yml` | 02:00–17:00 每 30 分鐘 | 推播剛結束的比賽比分 |

`results.yml` 的時段是**照 MLB 設的**（MLB 開賽集中在 UTC 16:00–02:00，結束落在 UTC 18:00–08:00）。之後啟用英超、西甲、LCK 等其他時區的聯賽時，記得把 `.github/workflows/results.yml` 裡的 cron 範圍放寬，否則那些聯賽的賽果會漏掉。

### 用量

`results.yml` 每天 30 次 × 約 1 分鐘 ≈ 每月 900 分鐘，加上另外兩個約 90 分鐘，總計約 1000～1400 分鐘。公開 repo 無上限；私人 repo 的免費額度是 2000 分鐘/月，剛好夠但沒什麼餘裕 —— 這是建議設 public 的原因。

### 一個要注意的地方

GitHub 對**沒有任何活動超過 60 天**的 repo 會自動停用排程 workflow。本專案每天都會 commit 一次行事曆，所以正常運作下不會被停。

---

## 之後要加的聯賽

### 已經接好，改一行就開（NBA / NFL / 英超 / 西甲）

[`config.py`](config.py) 裡把對應聯賽的 `enabled` 改成 `True`：

```python
{
    "key": "nba",
    "enabled": True,     # ← 改這裡
    ...
}
```

先跑 `python main.py preview` 確認抓得到資料再 push。（NBA 在 7–9 月是休賽期，那段時間抓到 0 場是正常的。）

### 還需要寫 adapter（CPBL / 電競）

這兩個 ESPN 沒有，需要各自的資料來源：

| 聯賽 | 資料來源 | 難度 |
| --- | --- | --- |
| **CPBL** | 官方無開放 API，需要爬 `cpbl.com.tw` 的賽程與即時比分頁 | 中 — 網站改版就要修，但只要改 adapter，不用動其他程式 |
| **LoL 電競**（LCK / LCP / MSI / Worlds） | Riot 的 Esports API（`esports-api.lolesports.com`）或 Leaguepedia API | 中 — 需要處理 BO3/BO5 的系列賽與單場的差別 |

新增方式：在 [`sources/`](sources/) 下寫一個新檔案，提供 `fetch(league, start, end) -> list[Game]`，然後在 [`sources/__init__.py`](sources/__init__.py) 的 `_ADAPTERS` 註冊。行事曆、推播、去重的邏輯完全不用改。

---

## 指令一覽

```bash
python main.py chat-id      # 找出你的 Telegram chat id（只需要 BOT_TOKEN）
python main.py preview      # 印出賽程（不碰 Telegram，測試用）
python main.py calendar     # 產生 docs/calendar.ics
python main.py digest       # 推播接下來 24 小時的賽程摘要
python main.py results      # 推播剛結束的比賽比分
python main.py test-notify  # 送一則測試訊息
```

## 已知限制

- **ESPN 是非官方公開端點**，沒有正式文件也沒有 SLA，隨時可能改結構或擋存取。程式已針對這點做了防護：單場解析失敗會跳過而非整批失敗、單一聯賽抓失敗不影響其他聯賽、User-Agent 被 WAF 擋下時會自動換一組重試。
- **比賽時長是估算的**（MLB 3.5 小時、NBA 2.5 小時等），ESPN 不提供預計結束時間。行事曆上的區塊長度僅供參考，不影響開賽提醒的準確度。
- **摘要用的是「接下來 24 小時」而不是「今天」。** 美洲聯賽的比賽落在台灣時間的清晨，
  早上 8 點推摘要時「今天」的比賽早就打完了，按日期切會永遠報空。想調整涵蓋範圍
  改 `main.py` 的 `DIGEST_HOURS`。
- **賽果推播最慢會延遲 30 分鐘**（排程間隔）。想更即時就把 cron 改成 `*/15`，但要注意 Actions 用量會翻倍。
