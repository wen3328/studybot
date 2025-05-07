import os
import json
import datetime
import pytz
import re
from flask import Flask, request, abort

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

import gspread
from oauth2client.service_account import ServiceAccountCredentials

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

# === Google Sheets 初始化 ===
def get_gsheet():
    try:
        cred_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
        if not cred_json:
            raise ValueError("❗ 找不到環境變數 GOOGLE_APPLICATION_CREDENTIALS_JSON")

        cred_dict = json.loads(cred_json)
        print("🔍 Service Account Email:", cred_dict.get("client_email"))

        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(cred_dict, scope)
        gc = gspread.authorize(credentials)

        # 嘗試打開試算表
        spreadsheet = gc.open_by_key("1kZGpA5J7b3lvCtqlo9wJp-FrKyYL1Qgt_7Cx5Pr4DSk")
        print("✅ 成功打開試算表標題：", spreadsheet.title)

        worksheet = spreadsheet.worksheet("每日進度紀錄（控制組）")
        print("✅ 成功打開工作表：每日進度紀錄（控制組）")
        return worksheet

    except Exception as e:
        print("❗ [get_gsheet] 發生錯誤：", e)
        raise


# === 寫入進度到表格 ===
def record_progress_to_sheet(sheet, display_name, log_date, time_tag, progress):
    # 轉換日期格式，例如 5/10
    date_str = log_date.astimezone(tz).strftime("%-m/%-d").lstrip("0")

    # 讀取第2列（日期）與第3列（早／晚）
    date_row = sheet.row_values(1)
    time_row = sheet.row_values(2)
    max_cols = max(len(date_row), len(time_row))
    target_col = None

    for col in range(3, max_cols):  # 從 D 欄（index=3）開始
        this_date = date_row[col].strip() if col < len(date_row) else ""
        this_time = time_row[col].strip() if col < len(time_row) else ""

        if (
            this_time == time_tag and
            this_date == date_str and
            (re.match(r"5/(1[0-9]|2[0-9])", this_date) or this_date == "5/8")
        ):
            target_col = col + 1  # gspread 從 1 開始算欄位
            break

    if not target_col:
        return f"⚠️ 找不到 {date_str} {time_tag} 的對應欄位"

    # 從 B5 開始逐列比對名稱
    normalized_display_name = display_name.strip()
    row_index = None
    current_row = 5

    while True:
        cell_value = sheet.cell(current_row, 2).value  # B 欄 = 第2欄
        if not cell_value:
            break  # 遇到空白，視為底部
        if cell_value.strip() == normalized_display_name:
            row_index = current_row
            break
        current_row += 1

    # 如果找不到名稱就新增
    if row_index is None:
        row_index = current_row
        sheet.update_cell(row_index, 2, normalized_display_name)
        print(f"➕ 新增名稱 {normalized_display_name} 於第 {row_index} 列")

    # 更新進度
    sheet.update_cell(row_index, target_col, str(progress))
    return f"✅ 已記錄我的 {date_str} {time_tag} 進度為 {progress}%"

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

    # ✅ 若不含「目前進度」就回覆一句話
    if "目前進度" not in user_msg:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="有關學業的問題，我可以點選單中的學業改善方針，幫助我更有方向面對學業拖延🙌🔥")
        )
        return

    now = datetime.datetime.now(tz)
    hour = now.hour

    # ✅ 根據時間決定：回覆哪一段話、記錄哪天的進度
    if 0 <= hour < 9:
        reply_msg = daily_replies.get((now - datetime.timedelta(days=1)).strftime("%Y-%m-%d"), {}).get("evening")
        log_date = now - datetime.timedelta(days=1)
        log_time_tag = "晚"
    elif 9 <= hour < 21:
        reply_msg = daily_replies.get(now.strftime("%Y-%m-%d"), {}).get("morning")
        log_date = now
        log_time_tag = "早"
    else:  # 21～23點
        reply_msg = daily_replies.get(now.strftime("%Y-%m-%d"), {}).get("evening")
        log_date = now
        log_time_tag = "晚"

    # ✅ 抓出進度百分比
    match = re.search(r"(\d{1,3})\s*%", user_msg)
    if match:
        progress = int(match.group(1))
        if 0 <= progress <= 100:
            user_id = event.source.user_id
            profile = line_bot_api.get_profile(user_id)
            name = profile.display_name
            sheet = get_gsheet()
            msg = record_progress_to_sheet(sheet, name, log_date, log_time_tag, progress)
            reply_msg = f"{reply_msg}\n{msg}"

    # 若無資料可回覆
    if not reply_msg:
        reply_msg = "📆 請確認實驗未開始/已結束，有任何問題請 mail 至 112462016@g.nccu.edu.tw 詢問，主旨為：學業拖延實驗_本名"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_msg)
    )


if __name__ == "__main__":
    app.run(debug=True)
