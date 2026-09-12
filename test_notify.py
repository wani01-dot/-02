import os
import requests


LINE_TOKEN = os.environ.get(
    "LINE_CHANNEL_ACCESS_TOKEN",
    ""
)

LINE_TO = os.environ.get(
    "LINE_TO",
    ""
)

LINE_API_URL = (
    "https://api.line.me/v2/bot/message/push"
)


def send_line(text):

    if not LINE_TOKEN:
        raise RuntimeError(
            "LINE_CHANNEL_ACCESS_TOKEN がありません"
        )

    if not LINE_TO:
        raise RuntimeError(
            "LINE_TO がありません"
        )

    response = requests.post(
        LINE_API_URL,

        headers={
            "Authorization":
                f"Bearer {LINE_TOKEN}",

            "Content-Type":
                "application/json",
        },

        json={
            "to":
                LINE_TO,

            "messages": [
                {
                    "type":
                        "text",

                    "text":
                        text,
                }
            ],
        },

        timeout=30,
    )

    print(
        "LINE status:",
        response.status_code,
    )

    print(
        "LINE response:",
        response.text,
    )

    response.raise_for_status()


def main():

    message = """【FANYで公開】
🔵軟水 / 🟡ピュート / 🔴めぞん

📅 2026/10/3(土)
🎫 六本木ブラゴーリパーク
📍 YOSHIMOTO ROPPONGI THEATER（東京都）
⏰ 開場12:00 / 開演12:30
📡 配信あり

掲載元：FANY
🔗 https://ticket.fany.lol/reception/67245/53623"""

    print(
        "===== LINEテスト通知 ====="
    )

    print(
        message
    )

    send_line(
        message
    )

    print(
        "テスト通知成功"
    )


if __name__ == "__main__":
    main()
