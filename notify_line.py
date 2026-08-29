import json
import os
import requests


# ==========================================
# 設定
# ==========================================

NEW_EVENTS_FILE = "new_events.json"
PERFORMERS_FILE = "performers.json"

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


# ==========================================
# JSON読み込み
# ==========================================

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


# ==========================================
# 文字整理
# ==========================================

def clean(text):
    return str(
        text or ""
    ).strip()


# ==========================================
# 公演まとめ用キー
# ==========================================

def performance_key(event):
    """
    同じ公演をまとめる。

    同日・同時間・同タイトル・同会場
    なら同じライブとして扱う。
    """

    return "|".join([
        clean(
            event.get(
                "date",
                ""
            )
        ),
        clean(
            event.get(
                "startTime",
                ""
            )
        ),
        clean(
            event.get(
                "title",
                ""
            )
        ),
        clean(
            event.get(
                "venue",
                ""
            )
        ),
    ])


# ==========================================
# LINE送信
# ==========================================

def send_line(text):

    if not LINE_TOKEN:
        print(
            "LINE_CHANNEL_ACCESS_TOKEN"
            " が設定されていません"
        )
        return False

    if not LINE_TO:
        print(
            "LINE_TO が設定されていません"
        )
        return False

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
                    "type": "text",
                    "text": text
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

    return True


# ==========================================
# メイン
# ==========================================

def main():

    # --------------------------------------
    # 新規公演
    # --------------------------------------

    new_events = load_json(
        NEW_EVENTS_FILE,
        []
    )

    if not isinstance(
        new_events,
        list
    ):
        new_events = []


    # --------------------------------------
    # 出演者設定
    # --------------------------------------

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
        if performer.get(
            "id"
        )
    }


    # --------------------------------------
    # notify=trueだけ
    # --------------------------------------

    target_events = []

    for event in new_events:

        performer_id = event.get(
            "performerId",
            ""
        )

        performer = performer_map.get(
            performer_id
        )

        if not performer:
            continue

        if not performer.get(
            "notify",
            False
        ):
            continue

        target_events.append(
            event
        )


    # --------------------------------------
    # 0件なら終了
    # --------------------------------------

    if not target_events:

        print(
            "通知対象の新規公演はありません。"
        )

        return


    # --------------------------------------
    # 同じ公演をまとめる
    # --------------------------------------

    grouped = {}


    for event in target_events:

        key = performance_key(
            event
        )

        performer_id = event.get(
            "performerId",
            ""
        )

        performer = performer_map.get(
            performer_id,
            {}
        )

        performer_name = performer.get(
            "name",
            performer_id
        )


        if key not in grouped:

            grouped[key] = {

                "date":
                    clean(
                        event.get(
                            "date",
                            ""
                        )
                    ),

                "startTime":
                    clean(
                        event.get(
                            "startTime",
                            ""
                        )
                    ),

                "title":
                    clean(
                        event.get(
                            "title",
                            ""
                        )
                    ),

                "venue":
                    clean(
                        event.get(
                            "venue",
                            ""
                        )
                    ),

                "source":
                    clean(
                        event.get(
                            "source",
                            ""
                        )
                    ),

                "sourceUrl":
                    clean(
                        event.get(
                            "sourceUrl",
                            ""
                        )
                    ),

                "performers":
                    [],
            }


        if (
            performer_name
            not in grouped[
                key
            ][
                "performers"
            ]
        ):

            grouped[
                key
            ][
                "performers"
            ].append(
                performer_name
            )


    # --------------------------------------
    # 並び替え
    # --------------------------------------

    performances = list(
        grouped.values()
    )

    performances.sort(
        key=lambda item: (
            item.get(
                "date",
                ""
            ),
            item.get(
                "startTime",
                ""
            ),
            item.get(
                "title",
                ""
            )
        )
    )


    # --------------------------------------
    # メッセージ作成
    # --------------------------------------

    blocks = []


    for item in performances:

        performer_text = "・".join(
            item.get(
                "performers",
                []
            )
        )

        date = item.get(
            "date",
            ""
        )

        start_time = item.get(
            "startTime",
            ""
        )

        title = item.get(
            "title",
            ""
        )

        venue = item.get(
            "venue",
            ""
        )

        source = item.get(
            "source",
            ""
        )

        source_url = item.get(
            "sourceUrl",
            ""
        )


        lines = []


        lines.append(
            f"🎙 {performer_text}"
        )


        if date:
            lines.append(
                f"📅 {date}"
            )


        if title:
            lines.append(
                f"🎫 {title}"
            )


        if venue:
            lines.append(
                f"📍 {venue}"
            )


        if start_time:
            lines.append(
                f"⏰ 開演 {start_time}"
            )


        if source:
            lines.append(
                f"掲載元：{source.upper()}"
            )


        if source_url:
            lines.append(
                f"🔗 {source_url}"
            )


        blocks.append(
            "\n".join(
                lines
            )
        )


    # --------------------------------------
    # LINEの1メッセージ上限対策
    # --------------------------------------

    messages = []

    current = (
        "【新しい出演情報】\n\n"
    )


    for block in blocks:

        addition = (
            block
            + "\n\n"
        )

        # LINEテキスト上限より
        # 余裕を持って4500文字程度
        if (
            len(current)
            + len(addition)
            > 4500
        ):

            messages.append(
                current.rstrip()
            )

            current = (
                "【新しい出演情報 続き】\n\n"
                + addition
            )

        else:

            current += addition


    if current.strip():

        messages.append(
            current.rstrip()
        )


    # --------------------------------------
    # LINE送信
    # --------------------------------------

    sent_count = 0


    for message in messages:

        if send_line(
            message
        ):

            sent_count += 1


    print(
        f"{len(performances)}件の"
        "新規公演を"
        f"{sent_count}通のLINEで"
        "通知しました。"
    )


# ==========================================
# 実行
# ==========================================

if __name__ == "__main__":
    main()
