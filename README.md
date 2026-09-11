# catchGame — 多聯賽賽程提醒與賽果推播

把你關注的各聯賽賽程整合起來，做兩件事：

1. **開賽提醒** — 比賽即將開打時，用 **Telegram** 推一則「🔔 即將開賽」。
2. **賽果推播** — 比賽結束後，用 **Telegram** 把比分送到你手機。
3. **每日摘要** — 每天早上 07:00 推一則「接下來 24 小時的賽事」。
4. **行事曆訂閱** — 另外產生一個 `.ics`，iPhone 訂閱後可以直接在行事曆上瀏覽賽程
   （預設**不響鈴**，因為提醒已經交給 Telegram，兩邊都開會收到兩次通知）。

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
        ├──► Telegram Bot ──────► 開賽提醒 / 賽果 / 每日摘要
        └──► docs/calendar.ics ──► iPhone 行事曆訂閱（純瀏覽，不響鈴）
```

### 關於開賽提醒的準時度

GitHub Actions 的 cron **不保證準時**，而且延遲的幅度比直覺上大得多 —— 實測延遲
20～60 分鐘是常態，尖峰時整槍被丟掉也會發生。所以做法不是「在開賽前 15 分鐘觸發
一次」，而是**每 10 分鐘檢查一次**，把還沒提醒過的比賽推出去，並記錄已推播的避免重複。

關鍵是提醒視窗**同時往回看**（`REMIND_CATCHUP_MINUTES`，預設 60 分鐘）：

- 正常情況 → 開賽前 20～5 分鐘收到「🔔 即將開賽 … 12 分鐘後」。
- 排程遲到 → 補送一則「🔔 即將開賽 … 已開打 25 分鐘」。

如果視窗只看未來（`now < start`），排程延遲一旦超過 20 分鐘，比賽開打的瞬間就會從
視窗裡消失，**那場比賽永遠不會被提醒，而且不留任何痕跡**。往回延伸之後最糟的情況
是「晚到」而不是「沒到」—— 真正擋住重複推播的是 `state.json` 的 `reminded` 紀錄，
不是視窗的左邊界。

要更精準只能改用有常駐主機的方案（VPS + crontab）或外部準時排程器打
`workflow_dispatch` API，那就得多管一個服務。

### 排程一次都沒觸發怎麼辦

新建 repo 的第一次排程註冊會延遲（免費公開 repo 的 schedule 走最低優先佇列），
偶爾要等上幾小時。確認方式 —— 這個 API 不需要登入：

```bash
curl -s "https://api.github.com/repos/a010380/catchGame/actions/runs?event=schedule"   | grep total_count
```

`total_count` 還是 0 就代表 GitHub 的 cron 一次都沒跑過，Actions 頁面上看到的
全是你手動按 Run workflow 的那幾次。這種情況只能等，或改用外部排程器觸發。

想改回讓 iPhone 行事曆響鈴（準時但會塞滿行事曆通知）：把 `config.py` 的
`ALARM_MINUTES_BEFORE` 改成 `15`，並把 `notify.yml` 的 `schedule` 區塊註解掉。

---

## 檔案結構

| 檔案 | 作用 |
| --- | --- |
| `config.py` | **唯一需要你動的設定檔**：聯賽開關、關注球隊、提醒分鐘數、補送視窗 |
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

**3-1. 先到 GitHub 網頁上建立一個空的 repo。**

`git remote add` 只是告訴 Git「遠端在哪」，**它不會幫你建 repo**。所以先開
<https://github.com/new>：

- **Repository name** 填 `catchGame`
- 選 **Public**（見下方說明）
- **不要**勾 "Add a README file"、.gitignore、license —— 本機已經有了，勾了會衝突

**3-2. 設定你的 Git 身分**（沒設過的話，commit 作者會顯示 `unknown`）：

```bash
git config --global user.name  "你的名字"
git config --global user.email "你的email"
```

**3-3. 推上去。** 把下面的 `你的GitHub帳號` 換成真的帳號名稱 —— 這是佔位字串，
直接照貼會得到 `error: 400`：

```bash
git init
git add .
git commit -m "feat: 賽事提醒與賽果推播"
git branch -M main
git remote add origin https://github.com/a010380/catchGame.git
git push -u origin main
```

第一次 push 時會跳出 GitHub 登入視窗，用瀏覽器授權即可（不需要自己產生 token）。

> 如果 remote 網址打錯了，用 `git remote set-url origin <正確網址>` 改掉，
> 或先 `git remote remove origin` 再重新 add。

> **建議設成 public repo。** Actions 對公開 repo 的免費額度無上限；私人 repo 每月 2000 分鐘，而本專案的排程大約會用掉 1400 分鐘（見下方「用量」）。這個 repo 裡沒有任何私密內容 —— token 是放在 GitHub Secrets，不在程式碼裡。

### 步驟 4：設定 Secrets

到 repo 的 **Settings → Secrets and variables → Actions → New repository secret**，加兩筆：

| Name | Value |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | 步驟 2 拿到的 token |
| `TELEGRAM_CHAT_ID` | 步驟 2 拿到的 chat id |

### 步驟 4.5：確認 Actions 有寫入權限

`calendar.yml` 和 `notify.yml` 需要把產生的 `.ics` 與推播紀錄 commit 回 repo，
所以 Actions 必須有寫入權限。

到 **Settings → Actions → General → Workflow permissions**，確認選的是
**Read and write permissions**。

2023 年之後建立的 repo 預設是唯讀，如果沒改，workflow 會在最後 commit 那一步失敗，
錯誤訊息長這樣：

```
remote: Permission to <帳號>/catchGame.git denied to github-actions[bot].
fatal: unable to access ...: The requested URL returned error: 403
```

### 步驟 5：開啟 GitHub Pages

**Settings → Pages → Source** 選 `Deploy from a branch`，branch 選 `main`、資料夾選 **`/docs`**，儲存。

一兩分鐘後你的行事曆網址就是：

```
https://a010380.github.io/catchGame/calendar.ics
```

### 步驟 6：iPhone 訂閱行事曆

**設定 → 行事曆 → 帳號 → 加入帳號 → 其他 → 加入已訂閱的行事曆**，貼上上面那個網址。

> 更簡單的做法：直接用 iPhone 的 Safari 開
> `webcal://a010380.github.io/catchGame/calendar.ics`，會直接跳出訂閱對話框。
>
> 訂閱後「我的賽事表」會出現在行事曆 App 裡。**它不會響鈴**（提醒交給 Telegram），
> 純粹是讓你可以在行事曆上一眼看到整週賽程。

### 步驟 7：手動觸發一次，確認全部正常

到 repo 的 **Actions** 頁面，三個 workflow 各點一次 **Run workflow**：

- **更新賽程行事曆** → 跑完後 `docs/calendar.ics` 會有新的 commit
- **今日賽事摘要** → 手機會收到接下來 24 小時的賽程
- **開賽提醒與賽果推播** → 如果當下沒有即將開賽或剛結束的比賽，它會正常跑完但不發訊息（這是對的）

---

## 排程時間

| Workflow | 執行時間（台灣時間） | 做什麼 |
| --- | --- | --- |
| `notify.yml` | **全天每 10 分鐘** | 開賽提醒 + 賽果推播 |
| `calendar.yml` | 每 6 小時（04 / 10 / 16 / 22 點） | 重新產生 `.ics` 並 commit |
| `digest.yml` | 每天 07:00 | 推播「接下來 24 小時有哪些比賽」 |

**為什麼 `notify.yml` 要全天跑**：三個聯賽的時段幾乎鋪滿一整天 ——
LCK 在台灣時間 13:00 開打、CPBL 18:35、MLB 則是台灣的凌晨到上午。
留任何空檔都會讓那個時段的比賽漏掉提醒或賽果。

**為什麼提醒和賽果合併成一個 workflow**：兩個 job 各自 commit 同一個
`state.json` 會互相衝突，而且重複的 checkout 與 pip install 純屬浪費。

**每 6 小時更新行事曆的原因**：季後賽的對戰組合要等上一輪打完才確定
（行事曆上會先顯示 `TBD vs GEN`），跑得勤一點隊名才會早點補上。
賽程沒變動時 workflow 會跳過 commit，不會產生雜訊。

### 用量

`notify.yml` 每天 144 次、`calendar.yml` 4 次、`digest.yml` 1 次，每次約 1 分鐘，
合計約每月 4500 分鐘。**公開 repo 的 Actions 分鐘數無上限，所以這不用省。**
如果你把 repo 改成 private，免費額度只有 2000 分鐘/月，會不夠 ——
那就得把 `notify.yml` 的 cron 調成 `*/30` 並縮小到有比賽的時段。

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
python main.py remind       # 推播即將開賽的比賽
python main.py results      # 推播剛結束的比賽比分
python main.py tick         # remind + results（排程實際跑的就是這個）
python main.py test-notify  # 送一則測試訊息
```

## 已知限制

- **ESPN 是非官方公開端點**，沒有正式文件也沒有 SLA，隨時可能改結構或擋存取。程式已針對這點做了防護：單場解析失敗會跳過而非整批失敗、單一聯賽抓失敗不影響其他聯賽、User-Agent 被 WAF 擋下時會自動換一組重試。
- **比賽時長是估算的**（MLB 3.5 小時、NBA 2.5 小時等），ESPN 不提供預計結束時間。行事曆上的區塊長度僅供參考，不影響開賽提醒的準確度。
- **摘要用的是「接下來 24 小時」而不是「今天」。** 美洲聯賽的比賽落在台灣時間的清晨，
  早上 8 點推摘要時「今天」的比賽早就打完了，按日期切會永遠報空。想調整涵蓋範圍
  改 `main.py` 的 `DIGEST_HOURS`。
- **開賽提醒的送達時間會浮動**，正常是開賽前 20～5 分鐘，排程遲到時會變成開賽後
  才補送（訊息上會標「已開打 X 分鐘」）。原因見上面「關於開賽提醒的準時度」。
- **賽果推播最慢會延遲 10 分鐘**（排程間隔），排程本身遲到時會更久。
- **GitHub 的排程不保證觸發。** 程式這邊能做的是「遲到也一定補送」，但如果 GitHub
  整天不跑 cron，就什麼都不會發生。見上面「排程一次都沒觸發怎麼辦」。
