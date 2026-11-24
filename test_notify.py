"""Send a sample digest when the existing manual LINE test workflow is run."""

import json

from notify_line import build_line_digest, send_line


def main():
    sample = {
        "performerId": "nansui",
        "date": "2026-10-03",
        "startTime": "12:30",
        "title": "六本木ブラゴーリパーク",
        "venue": "YOSHIMOTO ROPPONGI THEATER（東京都）",
        "source": "fany",
        "ticketStatus": "販売中",
        "hasStreaming": True,
    }
    message = build_line_digest([sample], [], [])
    print(json.dumps(message, ensure_ascii=False, indent=2))
    send_line(message)
    print("テスト通知成功")


if __name__ == "__main__":
    main()
