"""Send one labeled LINE Flex digest using synthetic events."""

from datetime import datetime, time, timedelta

from notify_line import JST, build_line_digest, send_line


def build_sample_message(now):
    today = now.date()
    sale_start = datetime.combine(today + timedelta(days=1), time(10), tzinfo=JST)

    events = [
        {
            "performerId": "maison",
            "trackedPerformers": ["maison", "nansui"],
            "title": "めぞん・軟水 合同ライブ（サンプル）",
            "date": (today + timedelta(days=10)).isoformat(),
            "startTime": "19:00",
            "venue": "サンプル劇場",
            "source": "fany",
            "saleStartAt": sale_start.isoformat(),
            "saleLabel": "一般発売",
            "hasStreaming": True,
        },
        {
            "performerId": "pyuto",
            "title": "ピュートの週末ライブ（サンプル）",
            "date": (today + timedelta(days=6)).isoformat(),
            "startTime": "14:00",
            "venue": "サンプル劇場",
            "source": "tiget",
            "ticketStatus": "販売中",
        },
        {
            "performerId": "nansui",
            "title": "軟水の夜公演（サンプル）",
            "date": (today + timedelta(days=8)).isoformat(),
            "startTime": "20:00",
            "venue": "サンプル劇場",
            "source": "fany",
            "ticketStatus": "予定数終了",
        },
    ]
    message = build_line_digest(events, [], [], now=now)
    message["altText"] = "【テスト通知】" + message["altText"]
    heading = message["contents"]["header"]["contents"][0]
    heading["text"] = "【テスト通知】サンプル公演"
    return message


def main():
    send_line(build_sample_message(datetime.now(JST)))


if __name__ == "__main__":
    main()
