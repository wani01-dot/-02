import os
import requests

token = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
to = os.environ["LINE_TO"]

url = "https://api.line.me/v2/bot/message/push"

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

data = {
    "to": to,
    "messages": [
        {
            "type": "text",
            "text": "芸人出演情報カレンダーからのテスト通知です！"
        }
    ]
}

response = requests.post(
    url,
    headers=headers,
    json=data,
    timeout=30
)

print("status:", response.status_code)
print("response:", response.text)

response.raise_for_status()
