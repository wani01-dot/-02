import json
import os
import re

import requests


NEW_EVENTS_FILE = "new_events.json"
THEATER_EVENTS_FILE = "theater_events.json"

PERFORMERS_FILE = "performers.json"

NOTIFIED_FILE = "notified_events.json"
THEATER_NOTIFIED_FILE = "theater_notified_events.json"


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
            encoding="utf-8",
        ) as f:
            return json.load(f)

    except (
        FileNotFoundError,
        json.JSONDecodeError,
    ):
        return default


def save_json(path, data):
    with open(
        path,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )


# =========================================================
# 共通
# =========================================================

def clean(text):
    return re.sub(
        r"\s+",
        " ",
        str(text or ""),
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
            "",
        )

    return text


def normalize_venue(text):
    return (
        clean(text)
        .lower()
        .replace(
            " ",
            "",
        )
        .replace(
            "　",
            "",
        )
    )


# =========================================================
# 通常チケットサイト用 通知キー
# =========================================================

def stable_notification_key(event):
    return "|".join([
        event.get(
            "performerId",
            "",
        ),
        event.get(
            "date",
            "",
        ),
        event.get(
            "startTime",
            "",
        ),
        normalize_venue(
            event.get(
                "venue",
                "",
            )
        ),
    ])


def loose_notification_key(event):
    return "|".join([
        event.get(
            "performerId",
            "",
        ),
        event.get(
            "date",
            "",
        ),
        normalize_venue(
            event.get(
                "venue",
                "",
            )
        ),
        normalize_title(
            event.get(
                "title",
                "",
            )
        ),
    ])


def source_notification_key(event):
    source = event.get(
        "source",
        "",
    )

    performer_id = event.get(
        "performerId",
        "",
    )

    url = event.get(
        "sourceUrl",
        "",
    )

    # =====================================================
    # TIGET
    # =====================================================

    if source == "tiget":
        match = re.search(
            r"/events/(\d+)",
            url,
        )

        if match:
            return (
                "tiget|"
                + performer_id
                + "|"
                + match.group(1)
            )

    # =====================================================
    # FANY
    # =====================================================

    if source == "fany":
        match = re.search(
            r"/reception/(\d+)/(\d+)",
            url,
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

    # =====================================================
    # イープラス
    # =====================================================

    if source == "eplus":
        match = re.search(
            r"/sf/detail/([^/?#]+)",
            url,
        )

        if match:
            return (
                "eplus|"
                + performer_id
                + "|"
                + match.group(1)
            )

    # =====================================================
    # LivePocket
    # 現在停止中でも将来用として残す
    # =====================================================

    if source == "livepocket":
        match = re.search(
            r"/e/([^/?#]+)",
            url,
        )

        if match:
            return (
                "livepocket|"
                + performer_id
                + "|"
                + match.group(1)
            )

    return ""


# =========================================================
# 劇場公式用 通知キー
#
# 通常チケットサイトとは完全に別管理。
# これにより同じ公演でも
#
# 劇場公開 → 通知
# FANY公開 → 別通知
#
# が可能。
# =========================================================

def theater_notification_key(event):
    existing_key = clean(
        event.get(
            "theaterSourceKey",
            "",
        )
    )

    if existing_key:
        return existing_key

    return "|".join([
        "theater",

        clean(
            event.get(
                "theaterId",
                "",
            )
        ),

        clean(
            event.get(
                "performerId",
                "",
            )
        ),

        clean(
            event.get(
                "date",
                "",
            )
        ),

        clean(
            event.get(
                "startTime",
                "",
            )
        ),

        normalize_title(
            event.get(
                "title",
                "",
            )
        ),
    ])


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
        response.status_code,
    )

    print(
        "LINE response:",
        response.text,
    )

    response.raise_for_status()


# =========================================================
# 掲載元名称
# =========================================================

def source_display_name(source):
    mapping = {
        "fany":
            "FANY",

        "tiget":
            "TIGET",

        "eplus":
            "イープラス",

        "livepocket":
            "LivePocket",

        "theater":
            "劇場公式",
    }

    return mapping.get(
        source,
        source.upper(),
    )


# =========================================================
# 通常チケットサイトの通知対象
# =========================================================

def get_ticket_send_events(
    new_events,
    performer_map,
    stable_keys,
    loose_keys,
    source_keys,
):
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
            False,
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
            and
            source_key in source_keys
        ):
            print(
                "通知済みURLのためスキップ:",
                source_key,
            )

            continue

        if stable_key in stable_keys:
            print(
                "通知済みstableKeyのためスキップ:",
                stable_key,
            )

            continue

        if loose_key in loose_keys:
            print(
                "通知済みlooseKeyのためスキップ:",
                loose_key,
            )

            continue

        send_events.append(
            event
        )

    return send_events


# =========================================================
# 劇場公式の通知対象
# =========================================================

def get_theater_send_events(
    theater_events,
    performer_map,
    theater_keys,
):
    send_events = []

    for event in theater_events:
        performer = performer_map.get(
            event.get(
                "performerId"
            )
        )

        if not performer:
            continue

        # performers.json の notify 設定をそのまま使用
        if not performer.get(
            "notify",
            False,
        ):
            continue

        key = theater_notification_key(
            event
        )

        if not key:
            continue

        if key in theater_keys:
            continue

        send_events.append(
            event
        )

    return send_events


# =========================================================
# 通常チケットサイト
# 同じ公演をまとめる
# =========================================================

def group_ticket_events(
    events,
):
    grouped = {}

    for event in events:
        source_key = (
            source_notification_key(
                event
            )
        )

        if source_key:
            group_key = (
                event.get(
                    "source",
                    "",
                )
                +
                "|"
                +
                re.sub(
                    r"^[^|]+\|[^|]+\|",
                    "",
                    source_key,
                )
            )

        else:
            group_key = "|".join([
                event.get(
                    "source",
                    "",
                ),
                event.get(
                    "date",
                    "",
                ),
                event.get(
                    "startTime",
                    "",
                ),
                normalize_title(
                    event.get(
                        "title",
                        "",
                    )
                ),
                normalize_venue(
                    event.get(
                        "venue",
                        "",
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

    return grouped


# =========================================================
# 劇場公式
# 同一公演の複数芸人をまとめる
# =========================================================

def group_theater_events(
    events,
):
    grouped = {}

    for event in events:
        group_key = "|".join([
            clean(
                event.get(
                    "theaterId",
                    "",
                )
            ),

            clean(
                event.get(
                    "date",
                    "",
                )
            ),

            clean(
                event.get(
                    "startTime",
                    "",
                )
            ),

            normalize_title(
                event.get(
                    "title",
                    "",
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

    return grouped


# =========================================================
# 出演者名
# =========================================================

def get_group_names(
    events,
    performer_map,
):
    names = []

    for item in events:
        performer = performer_map.get(
            item.get(
                "performerId"
            ),
            {},
        )

        name = performer.get(
            "name",
            item.get(
                "performerId",
                "",
            ),
        )

        if (
            name
            and
            name not in names
        ):
            names.append(
                name
            )

    return names


# =========================================================
# 通常チケットサイト メッセージ
# =========================================================

def build_ticket_blocks(
    send_events,
    performer_map,
):
    blocks = []

    grouped = group_ticket_events(
        send_events
    )

    for group in grouped.values():
        event = group[
            "event"
        ]

        names = get_group_names(
            group[
                "events"
            ],
            performer_map,
        )

        source = event.get(
            "source",
            "",
        )

        source_name = (
            source_display_name(
                source
            )
        )

        lines = [
            "【"
            + source_name
            + "で公開】",

            "🎙 "
            + "・".join(
                names
            ),

            "📅 "
            + event.get(
                "date",
                "",
            ),

            "🎫 "
            + event.get(
                "title",
                "公演名不明",
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

    return blocks


# =========================================================
# 劇場公式 メッセージ
# =========================================================

def build_theater_blocks(
    send_events,
    performer_map,
):
    blocks = []

    grouped = group_theater_events(
        send_events
    )

    for group in grouped.values():
        event = group[
            "event"
        ]

        names = get_group_names(
            group[
                "events"
            ],
            performer_map,
        )

        theater_name = (
            event.get(
                "theaterName"
            )
            or
            event.get(
                "venue"
            )
            or
            "劇場"
        )

        lines = [
            "【劇場公式で公開】",

            "🎙 "
            + "・".join(
                names
            ),

            "📅 "
            + event.get(
                "date",
                "",
            ),

            "🎫 "
            + event.get(
                "title",
                "公演名不明",
            ),

            "📍 "
            + theater_name,
        ]

        if event.get(
            "startTime"
        ):
            lines.append(
                "⏰ 開演 "
                + event.get(
                    "startTime"
                )
            )

        lines.append(
            "掲載元：劇場公式"
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

    return blocks


# =========================================================
# MAIN
# =========================================================

def main():

    # =====================================================
    # 通常チケットサイト
    # =====================================================

    new_events = load_json(
        NEW_EVENTS_FILE,
        [],
    )

    if not isinstance(
        new_events,
        list,
    ):
        new_events = []

    # =====================================================
    # 劇場公式
    # =====================================================

    theater_data = load_json(
        THEATER_EVENTS_FILE,
        {
            "events":
                []
        },
    )

    if isinstance(
        theater_data,
        list,
    ):
        theater_events = theater_data

    else:
        theater_events = theater_data.get(
            "events",
            [],
        )

    # =====================================================
    # 出演者
    # =====================================================

    config = load_json(
        PERFORMERS_FILE,
        {
            "performers":
                []
        },
    )

    performers = config.get(
        "performers",
        [],
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
    # 通常チケットサイト履歴
    # =====================================================

    notified = load_json(
        NOTIFIED_FILE,
        {},
    )

    stable_keys = set(
        notified.get(
            "stableKeys",
            [],
        )
    )

    loose_keys = set(
        notified.get(
            "looseKeys",
            [],
        )
    )

    source_keys = set(
        notified.get(
            "sourceKeys",
            [],
        )
    )

    # =====================================================
    # 劇場公式履歴
    # =====================================================

    theater_history_exists = (
        os.path.exists(
            THEATER_NOTIFIED_FILE
        )
    )

    theater_notified = load_json(
        THEATER_NOTIFIED_FILE,
        {
            "theaterKeys":
                []
        },
    )

    theater_keys = set(
        theater_notified.get(
            "theaterKeys",
            [],
        )
    )

    # =====================================================
    # 劇場公式 初回基準登録
    #
    # 現在ある181件などを
    # いきなり大量通知しないため。
    #
    # 初回は現在の劇場掲載分を
    # 「すでに確認済み」として登録。
    # =====================================================

    if not theater_history_exists:
        baseline_count = 0

        for event in theater_events:
            key = theater_notification_key(
                event
            )

            if not key:
                continue

            theater_keys.add(
                key
            )

            baseline_count += 1

        save_json(
            THEATER_NOTIFIED_FILE,
            {
                "theaterKeys":
                    sorted(
                        theater_keys
                    )
            },
        )

        print(
            "劇場公式通知の初回基準を登録:",
            baseline_count,
            "件",
        )

        print(
            "初回の劇場公演はLINE通知しません。"
        )

    # =====================================================
    # 通知対象
    # =====================================================

    ticket_send_events = (
        get_ticket_send_events(
            new_events,
            performer_map,
            stable_keys,
            loose_keys,
            source_keys,
        )
    )

    # 初回基準登録した実行では
    # 劇場通知を出さない
    if not theater_history_exists:
        theater_send_events = []

    else:
        theater_send_events = (
            get_theater_send_events(
                theater_events,
                performer_map,
                theater_keys,
            )
        )

    print(
        "通常サイト通知候補:",
        len(
            ticket_send_events
        ),
        "件",
    )

    print(
        "劇場公式通知候補:",
        len(
            theater_send_events
        ),
        "件",
    )

    # =====================================================
    # 何もない
    # =====================================================

    if (
        not ticket_send_events
        and
        not theater_send_events
    ):
        print(
            "通知対象の新規公演はありません。"
        )

        return

    # =====================================================
    # メッセージ作成
    # =====================================================

    blocks = []

    blocks.extend(
        build_theater_blocks(
            theater_send_events,
            performer_map,
        )
    )

    blocks.extend(
        build_ticket_blocks(
            ticket_send_events,
            performer_map,
        )
    )

    message = (
        "\n\n".join(
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
    # LINE送信成功後
    # 通常サイト履歴追加
    # =====================================================

    for event in ticket_send_events:
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
                source_key,
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
        },
    )

    # =====================================================
    # LINE送信成功後
    # 劇場公式履歴追加
    # =====================================================

    for event in theater_send_events:
        key = theater_notification_key(
            event
        )

        if key:
            theater_keys.add(
                key
            )

            print(
                "劇場通知済み登録:",
                key,
            )

    save_json(
        THEATER_NOTIFIED_FILE,
        {
            "theaterKeys":
                sorted(
                    theater_keys
                )
        },
    )

    print(
        "通常サイト:",
        len(
            ticket_send_events
        ),
        "件",
    )

    print(
        "劇場公式:",
        len(
            theater_send_events
        ),
        "件",
    )

    print(
        "LINE通知しました。"
    )

    print(
        "現在の通常sourceKeys:",
        len(
            source_keys
        ),
    )

    print(
        "現在の劇場theaterKeys:",
        len(
            theater_keys
        ),
    )


if __name__ == "__main__":
    main()
