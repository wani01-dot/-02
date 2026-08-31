import json
import os
import re

import requests


NEW_EVENTS_FILE = "new_events.json"
PERFORMERS_FILE = "performers.json"
NOTIFIED_FILE = "notified_events.json"

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


# =========================================================
# JSON
# =========================================================

def load_json(path, default):
    try:
        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:
            return json.load(f)

    except (
        FileNotFoundError,
        json.JSONDecodeError
    ):
        return default


def save_json(path, data):
    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


# =========================================================
# 共通
# =========================================================

def clean(text):
    return re.sub(
        r"\s+",
        " ",
        str(text or "")
    ).strip()


def normalize_title(text):
    text = clean(
        text
    ).lower()

    for char in [
        " ",
        "　",
        "「",
        "」",
        "『",
        "』",
        "【",
        "】",
        "・",
        "！",
        "!",
        "？",
        "?",
        "：",
        ":",
        "〜",
        "～",
    ]:
        text = text.replace(
            char,
            ""
        )

    return text


def normalize_venue(text):
    return (
        clean(text)
        .lower()
        .replace(" ", "")
        .replace("　", "")
    )


# =========================================================
# 通知キー
# =========================================================

def stable_notification_key(event):
    return "|".join([
        event.get(
            "performerId",
            ""
        ),
        event.get(
            "date",
            ""
        ),
        event.get(
            "startTime",
            ""
        ),
        normalize_venue(
            event.get(
                "venue",
                ""
            )
        ),
    ])


def loose_notification_key(event):
    return "|".join([
        event.get(
            "performerId",
            ""
        ),
        event.get(
            "date",
            ""
        ),
        normalize_venue(
            event.get(
                "venue",
                ""
            )
        ),
        normalize_title(
            event.get(
                "title",
                ""
            )
        ),
    ])


def source_notification_key(event):
    source = event.get(
        "source",
        ""
    )

    performer_id = event.get(
        "performerId",
        ""
    )

    url = event.get(
        "sourceUrl",
        ""
    )

    # TIGETはイベント番号で固定
    if source == "tiget":
        match = re.search(
            r"/events/(\d+)",
            url
        )

        if match:
            return (
                "tiget|"
                + performer_id
                + "|"
                + match.group(1)
            )

    # FANYは受付番号で固定
    if source == "fany":
        match = re.search(
            r"/reception/(\d+)/(\d+)",
            url
        )

        if match:
            return (
                "fany|"
                + performer_id
                + "|"
                + match.group(1)
                + "|"
                + match.group(2)
            )

    return ""


# =========================================================
# LINE
# =========================================================

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
        response.status_code
    )

    print(
        "LINE response:",
        response.text
    )

    response.raise_for_status()


# =========================================================
# MAIN
# =========================================================

def main():
    new_events = load_json(
        NEW_EVENTS_FILE,
        []
    )

    if not isinstance(
        new_events,
        list
    ):
        new_events = []

    config = load_json(
        PERFORMERS_FILE,
        {
            "performers": []
        }
    )

    performers = config.get(
        "performers",
        []
    )

    performer_map = {
        performer.get(
            "id"
        ):
        performer

        for performer
        in performers
    }

    # =====================================================
    # 通知済み履歴
    # =====================================================

    notified = load_json(
        NOTIFIED_FILE,
        {}
    )

    stable_keys = set(
        notified.get(
            "stableKeys",
            []
        )
    )

    loose_keys = set(
        notified.get(
            "looseKeys",
            []
        )
    )

    source_keys = set(
        notified.get(
            "sourceKeys",
            []
        )
    )

    # =====================================================
    # LINE送信直前の再チェック
    # =====================================================

    send_events = []

    for event in new_events:
        performer = performer_map.get(
            event.get(
                "performerId"
            )
        )

        if not performer:
            continue

        if not performer.get(
            "notify",
            False
        ):
            continue

        source_key = (
            source_notification_key(
                event
            )
        )

        stable_key = (
            stable_notification_key(
                event
            )
        )

        loose_key = (
            loose_notification_key(
                event
            )
        )

        if (
            source_key
            and source_key in source_keys
        ):
            print(
                "通知済みURLのためスキップ:",
                source_key
            )
            continue

        if stable_key in stable_keys:
            print(
                "通知済みstableKeyのためスキップ:",
                stable_key
            )
            continue

        if loose_key in loose_keys:
            print(
                "通知済みlooseKeyのためスキップ:",
                loose_key
            )
            continue

        send_events.append(
            event
        )

    if not send_events:
        print(
            "通知対象の新規公演はありません。"
        )
        return

    # =====================================================
    # 同じ公演をまとめる
    # =====================================================

    grouped = {}

    for event in send_events:
        source_key = (
            source_notification_key(
                event
            )
        )

        if source_key:
            group_key = (
                event.get(
                    "source",
                    ""
                )
                + "|"
                + re.sub(
                    r"^[^|]+\|[^|]+\|",
                    "",
                    source_key
                )
            )

        else:
            group_key = "|".join([
                event.get(
                    "date",
                    ""
                ),
                event.get(
                    "startTime",
                    ""
                ),
                normalize_title(
                    event.get(
                        "title",
                        ""
                    )
                ),
                normalize_venue(
                    event.get(
                        "venue",
                        ""
                    )
                ),
            ])

        if group_key not in grouped:
            grouped[
                group_key
            ] = {
                "event":
                    event,

                "events":
                    [],
            }

        grouped[
            group_key
        ][
            "events"
        ].append(
            event
        )

    # =====================================================
    # メッセージ
    # =====================================================

    blocks = []

    for group in grouped.values():
        event = group[
            "event"
        ]

        names = []

        for item in group[
            "events"
        ]:
            performer = performer_map.get(
                item.get(
                    "performerId"
                ),
                {}
            )

            name = performer.get(
                "name",
                item.get(
                    "performerId",
                    ""
                )
            )

            if name not in names:
                names.append(
                    name
                )

        lines = [
            "🎙 "
            + "・".join(
                names
            ),

            "📅 "
            + event.get(
                "date",
                ""
            ),

            "🎫 "
            + event.get(
                "title",
                "公演名不明"
            ),
        ]

        if event.get(
            "venue"
        ):
            lines.append(
                "📍 "
                + event.get(
                    "venue"
                )
            )

        if event.get(
            "startTime"
        ):
            lines.append(
                "⏰ 開演 "
                + event.get(
                    "startTime"
                )
            )

        source_name = (
            event.get(
                "source",
                ""
            ).upper()
        )

        if source_name:
            lines.append(
                "掲載元："
                + source_name
            )

        if event.get(
            "sourceUrl"
        ):
            lines.append(
                "🔗 "
                + event.get(
                    "sourceUrl"
                )
            )

        blocks.append(
            "\n".join(
                lines
            )
        )

    message = (
        "【新しい出演情報】\n\n"
        + "\n\n".join(
            blocks
        )
    )

    # =====================================================
    # LINE送信
    # =====================================================

    send_line(
        message
    )

    # =====================================================
    # LINE送信成功後だけ履歴追加
    # =====================================================

    for event in send_events:
        stable_keys.add(
            stable_notification_key(
                event
            )
        )

        loose_keys.add(
            loose_notification_key(
                event
            )
        )

        source_key = (
            source_notification_key(
                event
            )
        )

        if source_key:
            source_keys.add(
                source_key
            )

            print(
                "通知済みID登録:",
                source_key
            )

    save_json(
        NOTIFIED_FILE,
        {
            "stableKeys":
                sorted(
                    stable_keys
                ),

            "looseKeys":
                sorted(
                    loose_keys
                ),

            "sourceKeys":
                sorted(
                    source_keys
                ),
        }
    )

    print(
        len(send_events),
        "件をLINE通知しました。"
    )

    print(
        "現在の通知済みsourceKeys:",
        len(source_keys)
    )


if __name__ == "__main__":
    main()
