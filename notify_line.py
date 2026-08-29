import json
import os
import requests

LINE_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_TO = os.environ["LINE_TO"]

# 今回新しく見つかった公演
with open("new_events.json", encoding="utf-8") as f:
    new_events = json.load(f)

# 通知対象の出演者設定
with open("performers.json", encoding="utf-8") as f:
    performer_config = json.load(f)

notification_config = performer_config.get("notification", {})
target_ids = set(notification_config.get("performer_ids", []))

# 新規公演のうち、通知対象出演者が含まれるものだけ抽出
targets = []

for event in new_events:
    performer_id = event.get("performerId", "")

    if performer_id in target_ids:
        targets.append(event)
        
# 通知対象が0件なら何も送らず正常終了
if not targets:
    print("通知対象の新規公演はありません。")
    raise SystemExit(0)

# LINE Messaging API
url = "https://api.line.me/v2/bot/message/push"

headers = {
    "Authorization": f"Bearer {LINE_TOKEN}",
    "Content-Type": "application/json",
}

# 複数公演がある場合も1通にまとめる
lines = ["【新しい出演情報】"]

for event in targets:
    date = event.get("date", "日付不明")
    title = event.get("title", "公演名不明")
    venue = event.get("venue", "")
    start_time = event.get("start_time", "")
    event_url = event.get("url", "")

    lines.append("")
    lines.append(f"■ {date}")
    lines.append(title)

    if venue:
        lines.append(f"会場：{venue}")

    if start_time:
        lines.append(f"開演：{start_time}")

    if event_url:
        lines.append(event_url)

message = "\n".join(lines)

# LINEは1メッセージ5000文字までなので念のため制限
message = message[:4900]

payload = {
    "to": LINE_TO,
    "messages": [
        {
            "type": "text",
            "text": message
        }
    ]
}

response = requests.post(
    url,
    headers=headers,
    json=payload,
    timeout=30
)

print("LINE status:", response.status_code)
print("LINE response:", response.text)

response.raise_for_status()

print(f"{len(targets)}件の新規公演をLINE通知しました。")
