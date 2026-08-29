import json
import os
import requests

LINE_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_TO = os.environ["LINE_TO"]


# =====================================
# 新規公演を読み込む
# =====================================

with open("new_events.json", encoding="utf-8") as f:
    new_events = json.load(f)


# =====================================
# 出演者設定を読み込む
# =====================================

with open("performers.json", encoding="utf-8") as f:
    performer_config = json.load(f)

performers = performer_config.get("performers", [])


# performerId → 名前
performer_names = {
    p.get("id"): p.get("name", p.get("id"))
    for p in performers
}


# =====================================
# 通知対象を取得
# =====================================

# notify: true が設定されている出演者を通知対象にする
target_ids = {
    p.get("id")
    for p in performers
    if p.get("notify") is True
}


# notification.performer_ids 方式にも対応
notification_config = performer_config.get("notification", {})

for performer_id in notification_config.get("performer_ids", []):
    target_ids.add(performer_id)


# =====================================
# 通知対象の新規公演を抽出
# =====================================

targets = []

for event in new_events:

    performer_id = event.get("performerId", "")

    if performer_id in target_ids:
        targets.append(event)


# 新しい対象公演が無ければ終了
if not targets:
    print("通知対象の新規公演はありません。")
    raise SystemExit(0)


# =====================================
# LINEメッセージ作成
# =====================================

lines = ["【新しい出演情報】"]


for event in targets:

    performer_id = event.get("performerId", "")
    performer_name = performer_names.get(
        performer_id,
        performer_id or "出演者不明"
    )

    date = event.get("date", "日付不明")
    title = event.get("title", "")
    venue = event.get("venue", "")
    start_time = (
        event.get("startTime")
        or event.get("start_time")
        or ""
    )

    event_url = (
        event.get("sourceUrl")
        or event.get("url")
        or ""
    )

    lines.append("")
    lines.append(f"🎙️ {performer_name}")
    lines.append(f"📅 {date}")

    # タイトルがおかしい場合は表示しない
    invalid_titles = {
        "",
        "月",
        "火",
        "水",
        "木",
        "金",
        "土",
        "日",
    }

    if title not in invalid_titles:
        lines.append(f"🎫 {title}")

    if venue:
        lines.append(f"📍 {venue}")

    if start_time:
        lines.append(f"⏰ 開演 {start_time}")

    if event_url:
        lines.append(f"🔗 {event_url}")


message = "\n".join(lines)

# LINEの上限対策
message = message[:4900]


# =====================================
# LINE送信
# =====================================

response = requests.post(
    "https://api.line.me/v2/bot/message/push",
    headers={
        "Authorization": f"Bearer {LINE_TOKEN}",
        "Content-Type": "application/json",
    },
    json={
        "to": LINE_TO,
        "messages": [
            {
                "type": "text",
                "text": message,
            }
        ],
    },
    timeout=30,
)


print("LINE status:", response.status_code)
print("LINE response:", response.text)

response.raise_for_status()

print(f"{len(targets)}件の新規公演をLINE通知しました。")
