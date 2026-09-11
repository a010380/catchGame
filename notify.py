"""Telegram 推播。

只用到 Bot API 的 sendMessage，所以不需要額外套件。
兩個環境變數：
  TELEGRAM_BOT_TOKEN  跟 @BotFather 申請 bot 後拿到的 token
  TELEGRAM_CHAT_ID    你自己的 chat id（見 README 的取得方式）
"""

import html
import os
import time

import requests

API = "https://api.telegram.org/bot{token}/{method}"
TIMEOUT = 20
RETRIES = 3

# Telegram 單則訊息上限 4096 字元，留些餘裕
MAX_LEN = 3800


class NotConfigured(RuntimeError):
    pass


def bot_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise NotConfigured(
            "缺少 TELEGRAM_BOT_TOKEN。"
            "本機測試請先設環境變數，GitHub 上請設成 repository secret。"
        )
    return token


def _credentials() -> tuple[str, str]:
    token = bot_token()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not chat_id:
        raise NotConfigured(
            "缺少 TELEGRAM_CHAT_ID。先跟你的 bot 傳一句話，"
            "再執行 `python main.py chat-id` 取得。"
        )
    return token, chat_id


def describe_bot() -> dict:
    """回傳 bot 自己的資料，順便驗證 token 是否有效。"""
    resp = requests.get(
        API.format(token=bot_token(), method="getMe"), timeout=TIMEOUT
    )
    if resp.status_code == 404:
        raise RuntimeError(
            "Telegram 回 404 Not Found，代表 token 不正確（或網址裡的 token 掉了）。"
        )
    resp.raise_for_status()
    return resp.json()["result"]


def find_chats() -> list[dict]:
    """從 getUpdates 找出所有跟這個 bot 講過話的對話。

    Telegram 只保留最近約 24 小時的 updates，而且一旦被讀走就不會再出現，
    所以查不到時的解法一律是「再傳一句話給 bot」。
    """
    resp = requests.get(
        API.format(token=bot_token(), method="getUpdates"), timeout=TIMEOUT
    )
    resp.raise_for_status()
    chats: dict[int, dict] = {}
    for update in resp.json().get("result") or []:
        message = (
            update.get("message")
            or update.get("edited_message")
            or update.get("channel_post")
            or {}
        )
        chat = message.get("chat") or {}
        if chat.get("id"):
            chats[chat["id"]] = chat
    return list(chats.values())


def esc(text: str) -> str:
    """Telegram HTML parse_mode 需要轉義的字元。"""
    return html.escape(str(text), quote=False)


def _chunks(text: str) -> list[str]:
    """訊息太長時按行切開，不要切在半行中間。"""
    if len(text) <= MAX_LEN:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > MAX_LEN and current:
            chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks


def send(text: str) -> None:
    """送出一則（必要時自動分成多則）訊息。失敗會拋例外，讓 Actions 顯示紅燈。"""
    token, chat_id = _credentials()
    url = API.format(token=token, method="sendMessage")

    for chunk in _chunks(text):
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        last_err = None
        for attempt in range(RETRIES):
            try:
                resp = requests.post(url, json=payload, timeout=TIMEOUT)
                if resp.status_code == 429:
                    # 被限流，照 Telegram 指定的秒數等待後重試
                    wait = (resp.json().get("parameters") or {}).get("retry_after", 5)
                    last_err = f"429 rate limited, retry_after={wait}"
                    time.sleep(float(wait) + 1)
                    continue
                resp.raise_for_status()
                break
            except Exception as err:
                last_err = err
                if attempt < RETRIES - 1:
                    time.sleep(2 ** attempt)
        else:
            raise RuntimeError(f"Telegram 推播失敗: {last_err}")
