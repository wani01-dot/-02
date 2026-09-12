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
            f
