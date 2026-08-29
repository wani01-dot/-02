import os
import requests

token = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
to = os.environ["LINE_TO"]

message = """【新しい出演情報】

■ 2026-09-01
【テスト】軟水 新規公演通知テスト
会場：テスト会場
開演：19:00
https://ticket.fany.lol/
"""

response = requests.post(
    "https://api.line.me/v2/bot/message/push",
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    },
    json={
        "to": to,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    },
    timeout=30
)

print("status:", response.status_code)
print("response:", response.text)

response.raise_for_status()
