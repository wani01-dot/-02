import json
import os
import re

from datetime import datetime
from difflib import SequenceMatcher

import requests


NEW_EVENTS_FILE = "new_events.json"
THEATER_EVENTS_FILE = "theater_events.json"
STREAM_EVENTS_FILE = "stream_events.json"

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
# 通知表示設定
# =========================================================

PERFORMER_NOTIFICATION_ORDER = [
    "nansui",
    "pyuto",
    "maison",
]


PERFORMER_EMOJI = {
    "nansui": "🔵",
    "pyuto": "🟡",
    "maison": "🔴",
}


WEEKDAYS_JA = [
    "月",
    "火",
    "水",
    "木",
    "金",
    "土",
    "日",
]


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
        str(
            text
            or
            ""
        ),
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
        "（",
        "）",
        "(",
        ")",
        "‐",
        "-",
        "―",
        "ー",
    ]:

        text = text.replace(
            char,
            "",
        )

    return text


def normalize_venue(text):

    return (
        clean(
            text
        )
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


def unique_strings(values):

    result = []

    for value in values:

        value = clean(
            value
        )

        if (
            value
            and
            value not in result
        ):

            result.append(
                value
            )

    return result


# =========================================================
# 日付表示
#
# 2026-10-03
# ↓
# 2026/10/3(土)
# =========================================================

def format_notification_date(
    date_text,
):

    value = clean(
        date_text
    )

    try:

        date = datetime.strptime(
            value,
            "%Y-%m-%d",
        )

        weekday = WEEKDAYS_JA[
            date.weekday()
        ]

        return (
            f"{date.year}/"
            f"{date.month}/"
            f"{date.day}"
            f"({weekday})"
        )

    except ValueError:

        return value


# =========================================================
# 開場 / 開演表示
# =========================================================

def format_time_line(
    event,
):

    open_time = clean(
        event.get(
            "openTime",
            "",
        )
    )

    start_time = clean(
        event.get(
            "startTime",
            "",
        )
    )

    parts = []

    if open_time:

        parts.append(
            "開場"
            +
            open_time
        )

    if start_time:

        parts.append(
            "開演"
            +
            start_time
        )

    if not parts:

        return ""

    return (
        "⏰ "
        +
        " / ".join(
            parts
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
                +
                performer_id
                +
                "|"
                +
                match.group(1)
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
                +
                performer_id
                +
                "|"
                +
                match.group(1)
                +
                "|"
                +
                match.group(2)
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
                +
                performer_id
                +
                "|"
                +
                match.group(1)
            )


    # =====================================================
    # LivePocket
    # =====================================================

    if source == "livepocket":

        match = re.search(
            r"/e/([^/?#]+)",
            url,
        )

        if match:

            return (
                "livepocket|"
                +
                performer_id
                +
                "|"
                +
                match.group(1)
            )

    return ""


# =========================================================
# 劇場公式用 通知キー
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
# 配信データ
# =========================================================

def load_stream_events():

    data = load_json(
        STREAM_EVENTS_FILE,
        [],
    )


    if isinstance(
        data,
        list,
    ):

        return data


    if isinstance(
        data,
        dict,
    ):

        events = data.get(
            "events",
            [],
        )

        if isinstance(
            events,
            list,
        ):

            return events


    return []


# =========================================================
# 配信公演との照合
# =========================================================

def event_performer_ids(event):

    result = []


    performer_id = clean(
        event.get(
            "performerId",
            "",
        )
    )


    if performer_id:

        result.append(
            performer_id
        )


    tracked = event.get(
        "trackedPerformers",
        [],
    )


    if isinstance(
        tracked,
        list,
    ):

        result.extend(
            tracked
        )


    performer_ids = event.get(
        "performerIds",
        [],
    )


    if isinstance(
        performer_ids,
        list,
    ):

        result.extend(
            performer_ids
        )


    return unique_strings(
        result
    )


def titles_look_same(
    normal_title,
    stream_title,
):

    a = normalize_title(
        normal_title
    )

    b = normalize_title(
        stream_title
    )


    if (
        not a
        or
        not b
    ):

        return False


    if a == b:

        return True


    shorter_length = min(
        len(a),
        len(b),
    )


    if (
        shorter_length
        >=
        8
        and
        (
            a in b
            or
            b in a
        )
    ):

        return True


    similarity = SequenceMatcher(
        None,
        a,
        b,
    ).ratio()


    return (
        similarity
        >=
        0.78
    )


def has_streaming(
    event,
    stream_events,
):

    event_date = clean(
        event.get(
            "date",
            "",
        )
    )


    event_title = clean(
        event.get(
            "title",
            "",
        )
    )


    event_start = clean(
        event.get(
            "startTime",
            "",
        )
    )


    event_performers = set(
        event_performer_ids(
            event
        )
    )


    for stream_event in stream_events:

        stream_date = clean(
            stream_event.get(
                "date",
                "",
            )
        )


        if (
            event_date
            !=
            stream_date
        ):

            continue


        stream_title = clean(
            stream_event.get(
                "title",
                "",
            )
        )


        if titles_look_same(
            event_title,
            stream_title,
        ):

            return True


        stream_start = clean(
            stream_event.get(
                "startTime",
                "",
            )
        )


        stream_performers = set(
            event_performer_ids(
                stream_event
            )
        )


        performer_overlap = bool(
            event_performers
            &
            stream_performers
        )


        if (
            event_start
            and
            stream_start
            and
            event_start
            ==
            stream_start
            and
            performer_overlap
        ):

            title_similarity = (
                SequenceMatcher(
                    None,

                    normalize_title(
                        event_title
                    ),

                    normalize_title(
                        stream_title
                    ),
                )
                .ratio()
            )


            if (
                title_similarity
                >=
                0.5
            ):

                return True


    return False


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
# 通知に表示する追跡芸人
#
# 表示順：
# 🔵軟水 / 🟡ピュート / 🔴めぞん
# =========================================================

def get_group_performer_ids(
    events,
):

    ids = []


    for item in events:

        performer_id = clean(
            item.get(
                "performerId",
                "",
            )
        )


        if (
            performer_id
            and
            performer_id not in ids
        ):

            ids.append(
                performer_id
            )


        tracked = item.get(
            "trackedPerformers",
            [],
        )


        if isinstance(
            tracked,
            list,
        ):

            for tracked_id in tracked:

                tracked_id = clean(
                    tracked_id
                )

                if (
                    tracked_id
                    and
                    tracked_id not in ids
                ):

                    ids.append(
                        tracked_id
                    )


    ordered = []


    for performer_id in (
        PERFORMER_NOTIFICATION_ORDER
    ):

        if performer_id in ids:

            ordered.append(
                performer_id
            )


    for performer_id in ids:

        if (
            performer_id
            not in ordered
        ):

            ordered.append(
                performer_id
            )


    return ordered


def format_group_performers(
    events,
    performer_map,
):

    performer_ids = (
        get_group_performer_ids(
            events
        )
    )


    labels = []


    for performer_id in performer_ids:

        performer = performer_map.get(
            performer_id,
            {},
        )


        name = (
            performer.get(
                "name"
            )
            or
            performer_id
        )


        emoji = (
            PERFORMER_EMOJI.get(
                performer_id,
                "⚪"
            )
        )


        labels.append(
            emoji
            +
            name
        )


    if not labels:

        return "🎙 出演者不明"


    return " / ".join(
        labels
    )


# =========================================================
# 通常チケットサイト メッセージ
# =========================================================

def build_ticket_blocks(
    send_events,
    performer_map,
    stream_events,
):

    blocks = []


    grouped = group_ticket_events(
        send_events
    )


    for group in grouped.values():

        event = group[
            "event"
        ]


        source = event.get(
            "source",
            "",
        )


        source_name = (
            source_display_name(
                source
            )
        )


        performer_line = (
            format_group_performers(
                group[
                    "events"
                ],
                performer_map,
            )
        )


        date_line = (
            "📅 "
            +
            format_notification_date(
                event.get(
                    "date",
                    "",
                )
            )
        )


        title_line = (
            "🎫 "
            +
            event.get(
                "title",
                "公演名不明",
            )
        )


        lines = [
            "【"
            +
            source_name
            +
            "で公開】",

            performer_line,

            "",

            date_line,

            title_line,
        ]


        venue = clean(
            event.get(
                "venue",
                "",
            )
        )


        if venue:

            lines.append(
                "📍 "
                +
                venue
            )


        time_line = format_time_line(
            event
        )


        if time_line:

            lines.append(
                time_line
            )


        if has_streaming(
            event,
            stream_events,
        ):

            lines.append(
                "📡 配信あり"
            )

        else:

            lines.append(
                "📡 配信なし"
            )


        lines.append(
            ""
        )


        lines.append(
            "掲載元："
            +
            source_name
        )


        source_url = clean(
            event.get(
                "sourceUrl",
                "",
            )
        )


        if source_url:

            lines.append(
                "🔗 "
                +
                source_url
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
    stream_events,
):

    blocks = []


    grouped = group_theater_events(
        send_events
    )


    for group in grouped.values():

        event = group[
            "event"
        ]


        performer_line = (
            format_group_performers(
                group[
                    "events"
                ],
                performer_map,
            )
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

            performer_line,

            "",

            "📅 "
            +
            format_notification_date(
                event.get(
                    "date",
                    "",
                )
            ),

            "🎫 "
            +
            event.get(
                "title",
                "公演名不明",
            ),

            "📍 "
            +
            theater_name,
        ]


        time_line = format_time_line(
            event
        )


        if time_line:

            lines.append(
                time_line
            )


        if has_streaming(
            event,
            stream_events,
        ):

            lines.append(
                "📡 配信あり"
            )

        else:

            lines.append(
                "📡 配信なし"
            )


        lines.append(
            ""
        )


        lines.append(
            "掲載元：劇場公式"
        )


        source_url = clean(
            event.get(
                "sourceUrl",
                "",
            )
        )


        if source_url:

            lines.append(
                "🔗 "
                +
                source_url
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
    # 配信
    # =====================================================

    stream_events = (
        load_stream_events()
    )


    print(
        "配信照合データ:",
        len(
            stream_events
        ),
        "件",
    )


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

        theater_events = (
            theater_data
        )

    else:

        theater_events = (
            theater_data.get(
                "events",
                [],
            )
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
    # =====================================================

    if not theater_history_exists:

        baseline_count = 0


        for event in theater_events:

            key = (
                theater_notification_key(
                    event
                )
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
            stream_events,
        )
    )


    blocks.extend(
        build_ticket_blocks(
            ticket_send_events,
            performer_map,
            stream_events,
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
