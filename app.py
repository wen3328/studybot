
import os
import json
import datetime
import pytz
import re
from flask import Flask, request, abort

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# === Flask App ===
app = Flask(__name__)

# === LINE Bot 初始化 ===
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# === 台灣時區 ===
tz = pytz.timezone("Asia/Taipei")

# === 讀取每日回覆 JSON ===
with open("daily_replies_2025.json", "r", encoding="utf-8") as f:
    daily_replies = json.load(f)

# === 根路由檢查 ===
@app.route("/", methods=["GET"])
def index():
    return "LINE Bot is running."

# === Webhook 接收 ===
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

# === 主訊息邏輯處理 ===
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = event.message.text.strip()
    
    # ✅ 只要訊息中包含「目前進度」就回覆
    if "目前進度" not in user_msg:
        return


    now = datetime.datetime.now(tz)
    hour = now.hour

    today_str = now.strftime("%Y-%m-%d")
    yesterday_str = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    # 判斷使用早晚回覆
    if 21 <= hour <= 23:
        reply_msg = daily_replies.get(today_str, {}).get("evening")
    elif 0 <= hour < 9:
        reply_msg = daily_replies.get(yesterday_str, {}).get("evening")
    else:
        reply_msg = daily_replies.get(today_str, {}).get("morning")

    if not reply_msg:
        reply_msg = "📆 今天沒有設定回覆句，請確認日期是否在範圍內"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_msg)
    )

if __name__ == "__main__":
    app.run(debug=True)
