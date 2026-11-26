import json
import os
import re

from datetime import datetime, timedelta
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urlsplit
from zoneinfo import ZoneInfo

import requests

from notification_dedup import matches_any, same_show


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

def post_line(message, *, retry_key=None, timeout=30):
    if not LINE_TOKEN:
        raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN がありません")
    if not LINE_TO:
        raise RuntimeError("LINE_TO がありません")

    headers = {"Authorization": f"Bearer {LINE_TOKEN}"}
    if retry_key:
        headers["X-Line-Retry-Key"] = retry_key
    return requests.post(
        LINE_API_URL,
        headers=headers,
        json={"to": LINE_TO, "messages": [message]},
        timeout=timeout,
    )


def send_line(message):
    response = post_line(message)
    print(f"LINE Flex送信: status {response.status_code}", flush=True)
    if not response.ok:
        print("LINE response:", response.text, flush=True)
    response.raise_for_status()


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


CALENDAR_URL = os.environ.get(
    "LINE_CALENDAR_URL", "https://wani01-dot.github.io/-02/"
)
DIGEST_PERFORMERS = {
    "maison": "🔴めぞん",
    "pyuto": "🟡ピュート",
    "nansui": "🔵軟水",
}
JST = ZoneInfo("Asia/Tokyo")
DIGEST_LIMIT = 6
SALE_NEAR_DAYS = 7


def sale_datetime(value):
    try:
        result = datetime.fromisoformat(clean(value))
    except ValueError:
        return None
    if result.tzinfo is None:
        return result.replace(tzinfo=JST)
    return result.astimezone(JST)


def digest_sale(events, now):
    upcoming = []
    inferred = []
    statuses = []
    for event in events:
        for record in [event, *(event.get("ticketOptions") or [])]:
            if not isinstance(record, dict):
                continue
            statuses.append(clean(record.get("status") or record.get("ticketStatus")))
            periods = [
                {
                    "startAt": record.get("saleStartAt"),
                    "endAt": record.get("saleEndAt"),
                    "label": record.get("saleLabel"),
                },
                *(record.get("salePeriods") or []),
            ]
            for period in periods:
                if not isinstance(period, dict):
                    continue
                start = sale_datetime(period.get("startAt"))
                end = sale_datetime(period.get("endAt"))
                label = clean(period.get("label")) or "発売"
                if end and end <= now:
                    inferred.append("受付期間終了")
                elif start and start > now:
                    upcoming.append((start, label))
                elif start:
                    inferred.append("受付期間中")

    statuses = unique_strings(statuses) or unique_strings(inferred)
    if upcoming:
        start, label = min(upcoming)
        timing = "発売間近" if start <= now + timedelta(days=SALE_NEAR_DAYS) else "発売予定"
        status = f"{timing} {start:%m/%d %H:%M}（{label}）"
        if statuses:
            status += " / " + "・".join(statuses)
        return start, status
    return None, "・".join(statuses) or "発売状況未確認"


def flex_text(text, **style):
    return {"type": "text", "text": text, "wrap": True, **style}


def calendar_button(label, performer, style="link"):
    url = urlsplit(CALENDAR_URL)
    query = dict(parse_qsl(url.query, keep_blank_values=True))
    query["performer"] = performer
    return {
        "type": "button",
        "style": style,
        "height": "sm",
        "action": {
            "type": "uri",
            "label": label,
            "uri": url._replace(query=urlencode(query)).geturl(),
        },
    }


def build_line_digest(ticket_events, theater_events, stream_events, *, related=(), now=None, displayed=None, groups=None):
    now = now or datetime.now(JST)
    if groups is None:
        groups = [
            *group_ticket_events(ticket_events).values(),
            *group_theater_events(theater_events).values(),
        ]
    if not groups:
        return None

    counts = dict.fromkeys(DIGEST_PERFORMERS, 0)
    shows = []
    for group in groups:
        event = group["event"]
        records = group["events"] + [item for item in related if same_show(event, item)]
        ids = {pid for item in records for pid in event_performer_ids(item)}
        for pid in counts.keys() & ids:
            counts[pid] += 1
        streaming = any(
            item.get("hasStreaming") is True or has_streaming(item, stream_events)
            for item in records
        )
        sale_start, sale_status = digest_sale(records, now)
        shows.append((event, ids, streaming, sale_start, sale_status))

    def sort_key(show):
        event, _, streaming, start, _ = show
        if start and start <= now + timedelta(days=SALE_NEAR_DAYS):
            return (0, start, "", "")
        return (1 if streaming else 2, now, event.get("date") or "", event.get("startTime") or "")

    shows.sort(key=sort_key)
    total = len(shows)
    streaming_count = sum(show[2] for show in shows)
    body = [
        flex_text(f"📡 配信あり {streaming_count}件", size="sm", color="#355766"),
    ]

    preview = shows[:DIGEST_LIMIT]
    if displayed is not None:
        displayed.update(id(show[0]) for show in preview)
    if streaming_count and not any(show[2] for show in preview):
        stream_event = next(show[0] for show in shows if show[2])
        title = clean(stream_event.get("title")) or "公演名不明"
        body.append(flex_text(f"配信公演：{title[:100]}", size="sm", maxLines=2))

    for event, ids, streaming, _, sale_status in preview:
        names = " / ".join(label for pid, label in DIGEST_PERFORMERS.items() if pid in ids)
        date = format_notification_date(event.get("date")) or "公演日未定"
        start = clean(event.get("startTime"))
        details = " ".join(filter(None, [date, start, names]))
        title = flex_text((clean(event.get("title")) or "公演名不明")[:100], weight="bold", maxLines=2)
        source_url = clean(event.get("sourceUrl"))
        if source_url.startswith(("https://", "http://")) and len(source_url) <= 1000:
            title["action"] = {"type": "uri", "label": "公演詳細", "uri": source_url}

        body.extend([
            {"type": "separator", "color": "#DEE7EB"},
            title,
            flex_text(details, size="xs", color="#425866"),
        ])
        venue = clean(event.get("venue"))
        if venue:
            body.append(flex_text(venue[:100], size="xs", color="#425866", maxLines=2))
        body.append(flex_text(sale_status[:120], size="sm", color="#234E60", maxLines=3))
        if streaming:
            body.append(flex_text("📡 配信あり", size="xs", color="#17654E"))

    if total > DIGEST_LIMIT:
        body.append(flex_text(f"ほか {total - DIGEST_LIMIT}件はカレンダーへ", size="sm", color="#425866"))

    return {
        "type": "flex",
        "altText": f"ワラいどっとこむ｜新着 {total} 公演",
        "contents": {
            "type": "bubble",
            "size": "mega",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#123744",
                "spacing": "sm",
                "contents": [
                    flex_text("ワラいどっとこむ｜新着ライブ", size="sm", color="#D5EEF0"),
                    flex_text(f"新着 {total} 公演", size="xl", weight="bold", color="#FFFFFF"),
                ],
            },
            "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": body},
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    *(calendar_button(f"{label} {counts[pid]}件", pid) for pid, label in DIGEST_PERFORMERS.items()),
                    calendar_button("全公演をカレンダーで確認", "all", "primary"),
                ],
            },
        },
    }


def main():
    workflow_file = os.environ.get("GITHUB_WORKFLOW_REF", "").split("@", 1)[0]
    if os.environ.get("GITHUB_ACTIONS") == "true" and workflow_file.endswith((
        "/.github/workflows/sync.yml", "/.github/workflows/theater-probe.yml",
    )):
        raise RuntimeError("旧通知経路は停止済みです。notification_pipeline.py を使用してください")

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
    # 劇場公式とFANY等の重複通知防止
    # =====================================================
    # 先行劇場通知では、前回保存された通常公演も照合する。
    # 通常通知では、劇場の通知済み公演だけを照合する。
    # 同じ公演は出演者・日付・開始時刻・タイトルで判定。
    ticket_data = load_json("events.json", {"events": []})
    known_ticket_events = (
        ticket_data if isinstance(ticket_data, list)
        else ticket_data.get("events", [])
    )
    if not isinstance(known_ticket_events, list):
        known_ticket_events = []

    # 既存の通常通知履歴に登録された公演に限定する。
    notified_ticket_events = [
        e for e in known_ticket_events
        if (
            stable_notification_key(e) in stable_keys
            or loose_notification_key(e) in loose_keys
            or (
                source_notification_key(e)
                and source_notification_key(e) in source_keys
            )
        )
    ]

    # 先行通知で既に送った劇場公演は、通常サイト側から除外。
    notified_theater_events = [
        e for e in theater_events
        if theater_notification_key(e) in theater_keys
    ]

    candidate_ticket_events = list(ticket_send_events)
    candidate_theater_events = list(theater_send_events)
    original_ticket_count = len(ticket_send_events)
    ticket_send_events = [
        e for e in ticket_send_events
        if not matches_any(e, notified_theater_events)
    ]

    original_theater_count = len(theater_send_events)
    theater_send_events = [
        e for e in theater_send_events
        if not matches_any(e, notified_ticket_events)
        and not matches_any(e, ticket_send_events)
    ]

    # 同一回で複数サイトから同じ公演を取得した場合も抑止。
    def unique_shows(events):
        selected = []
        for event in events:
            if not matches_any(event, selected):
                selected.append(event)
        return selected

    ticket_send_events = unique_shows(ticket_send_events)
    theater_send_events = unique_shows(theater_send_events)

    # 省略した候補の通知履歴も記録して、後日再通知されるのを防ぐ。
    suppressed_tickets = [
        e for e in candidate_ticket_events
        if e not in ticket_send_events
    ]
    suppressed_theaters = [
        e for e in candidate_theater_events
        if e not in theater_send_events
    ]

    def record_suppressed():
        for event in suppressed_tickets:
            stable_keys.add(stable_notification_key(event))
            loose_keys.add(loose_notification_key(event))
            source_key = source_notification_key(event)
            if source_key:
                source_keys.add(source_key)
        for event in suppressed_theaters:
            key = theater_notification_key(event)
            if key:
                theater_keys.add(key)

    def save_histories():
        save_json(NOTIFIED_FILE, {
            "stableKeys": sorted(stable_keys),
            "looseKeys": sorted(loose_keys),
            "sourceKeys": sorted(source_keys),
        })
        save_json(THEATER_NOTIFIED_FILE, {
            "theaterKeys": sorted(theater_keys),
        })

    print(
        "重複通知除外: 通常",
        original_ticket_count - len(ticket_send_events),
        "件 / 劇場",
        original_theater_count - len(theater_send_events),
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
        record_suppressed()
        if suppressed_tickets or suppressed_theaters:
            save_histories()
        return


    # =====================================================
    # メッセージ作成
    # =====================================================

    message = build_line_digest(
        ticket_send_events,
        theater_send_events,
        stream_events,
        related=suppressed_tickets + suppressed_theaters,
    )
    send_line(message)

    record_suppressed()

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
