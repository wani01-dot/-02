import calendar
import json
import re
from datetime import datetime, timezone, timedelta, date
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup

from eplus_scraper import scrape_eplus
from livepocket_scraper import scrape_livepocket

PERFORMERS_FILE = "performers.json"
EVENTS_FILE = "events.json"
NEW_EVENTS_FILE = "new_events.json"
NOTIFIED_FILE = "notified_events.json"

FANY_SEARCH_URL = "https://ticket.fany.lol/search/event"
FANY_BASE = "https://ticket.fany.lol"

TIGET_SEARCH_URL = "https://tiget.net/events"
TIGET_BASE = "https://tiget.net"

JST = timezone(timedelta(hours=9))

FUTURE_DAYS = 365
FANY_PAGE_LIMIT = 10
NEW_HOURS = 48

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) "
        "Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
}


# =========================================================
# JSON
# =========================================================

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (
        FileNotFoundError,
        json.JSONDecodeError,
    ):
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
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
    text = clean(text).lower()

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
        .replace(" ", "")
        .replace("　", "")
    )


def make_date(
    year,
    month,
    day,
):
    return (
        f"{int(year):04d}-"
        f"{int(month):02d}-"
        f"{int(day):02d}"
    )


def today_jst():
    return datetime.now(
        JST
    ).date()


def now_iso():
    return datetime.now(
        timezone.utc
    ).isoformat()


def new_until_iso():
    return (
        datetime.now(
            timezone.utc
        )
        +
        timedelta(
            hours=NEW_HOURS
        )
    ).isoformat()


def is_today_or_future(
    date_string,
):
    try:
        event_date = datetime.strptime(
            date_string,
            "%Y-%m-%d",
        ).date()

        return (
            event_date
            >=
            today_jst()
        )

    except ValueError:
        return False


def unique_strings(values):
    result = []
    seen = set()

    for value in values:
        value = clean(value)

        if not value:
            continue

        if value in seen:
            continue

        seen.add(value)
        result.append(value)

    return result


# =========================================================
# 通知キー
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

    return ""


# =========================================================
# FANY日付
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


def fany_date_string(value):
    weekday = WEEKDAYS_JA[
        value.weekday()
    ]

    return (
        value.strftime(
            "%Y/%m/%d"
        )
        +
        f"({weekday})"
    )


def build_month_ranges():
    start = today_jst()

    final_date = (
        start
        +
        timedelta(
            days=FUTURE_DAYS
        )
    )

    ranges = []
    current = start

    while current <= final_date:
        last_day = calendar.monthrange(
            current.year,
            current.month,
        )[1]

        month_end = date(
            current.year,
            current.month,
            last_day,
        )

        if month_end > final_date:
            month_end = final_date

        ranges.append(
            (
                current,
                month_end,
            )
        )

        current = (
            month_end
            +
            timedelta(
                days=1
            )
        )

    return ranges


# =========================================================
# イベント識別
# =========================================================

def identity_key(event):
    source_key = source_notification_key(
        event
    )

    if source_key:
        return source_key

    return "|".join([
        event.get(
            "source",
            "",
        ),
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
        normalize_title(
            event.get(
                "title",
                "",
            )
        ),
    ])


def calendar_key(event):
    return "|".join([
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


# =========================================================
# HTML
# =========================================================

def html_to_lines(html):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    lines = []

    for raw in soup.get_text(
        "\n"
    ).splitlines():

        line = clean(raw)

        if line:
            lines.append(line)

    return lines


# =========================================================
# 日時解析
# =========================================================

FULL_DATETIME_PATTERNS = [
    re.compile(
        r"(20\d{2})年"
        r"\s*(\d{1,2})月"
        r"\s*(\d{1,2})日"
        r"(?:\s*[（(][^）)]*[）)])?"
        r"[^\d]{0,20}"
        r"(\d{1,2}):(\d{2})"
    ),
    re.compile(
        r"(20\d{2})[/-]"
        r"(\d{1,2})[/-]"
        r"(\d{1,2})"
        r"(?:\s*[（(][^）)]*[）)])?"
        r"[^\d]{0,20}"
        r"(\d{1,2}):(\d{2})"
    ),
]


def make_jst_datetime(
    year,
    month,
    day,
    hour,
    minute,
):
    try:
        return datetime(
            int(year),
            int(month),
            int(day),
            int(hour),
            int(minute),
            tzinfo=JST,
        )

    except ValueError:
        return None


def extract_japanese_datetimes(text):
    text = clean(text)

    matches = []

    for pattern in FULL_DATETIME_PATTERNS:
        for match in pattern.finditer(
            text
        ):
            value = make_jst_datetime(
                *match.groups()
            )

            if value:
                matches.append(
                    (
                        match.start(),
                        match.end(),
                        value,
                    )
                )

    matches.sort(
        key=lambda item: item[0]
    )

    unique_matches = []
    seen = set()

    for item in matches:
        key = (
            item[0],
            item[2].isoformat(),
        )

        if key in seen:
            continue

        seen.add(key)
        unique_matches.append(item)

    if not unique_matches:
        return []

    first_start, first_end, first_value = (
        unique_matches[0]
    )

    result = [
        first_value
    ]

    if len(unique_matches) >= 2:
        result.append(
            unique_matches[1][2]
        )

        return [
            value.isoformat()
            for value in result
        ]

    tail = text[
        first_end:
    ]

    month_day_match = re.search(
        r"(?:～|〜|~|－|-|から|まで)"
        r"\s*"
        r"(\d{1,2})(?:月|/|-)"
        r"(\d{1,2})(?:日)?"
        r"[^\d]{0,20}"
        r"(\d{1,2}):(\d{2})",
        tail,
    )

    if month_day_match:
        (
            month,
            day,
            hour,
            minute,
        ) = month_day_match.groups()

        year = first_value.year

        try:
            candidate = datetime(
                year,
                int(month),
                int(day),
                int(hour),
                int(minute),
                tzinfo=JST,
            )

            if (
                candidate < first_value
                and
                int(month)
                <
                first_value.month
            ):
                candidate = datetime(
                    year + 1,
                    int(month),
                    int(day),
                    int(hour),
                    int(minute),
                    tzinfo=JST,
                )

            result.append(
                candidate
            )

        except ValueError:
            pass

    else:
        time_only_match = re.search(
            r"(?:～|〜|~|－|-|から|まで)"
            r"\s*"
            r"(\d{1,2}):(\d{2})",
            tail,
        )

        if time_only_match:
            hour, minute = (
                time_only_match.groups()
            )

            try:
                candidate = (
                    first_value.replace(
                        hour=int(hour),
                        minute=int(minute),
                        second=0,
                        microsecond=0,
                    )
                )

                if candidate < first_value:
                    candidate += timedelta(
                        days=1
                    )

                result.append(
                    candidate
                )

            except ValueError:
                pass

    return [
        value.isoformat()
        for value in result
    ]


def parse_japanese_datetime(text):
    values = extract_japanese_datetimes(
        text
    )

    if values:
        return values[0]

    return ""


# =========================================================
# 販売種別
# =========================================================

ADVANCE_WORDS = [
    "先行",
    "抽選",
    "プレミアムメンバー",
    "FANY ID",
    "FANYコミュ",
    "ファンクラブ",
]


FIRST_COME_WORDS = [
    "一般発売",
    "一般販売",
    "一般受付",
    "先着",
    "発売",
    "販売開始",
    "受付開始",
]


SALE_MARKER_WORDS = [
    "先行",
    "抽選",
    "一般発売",
    "一般販売",
    "先着",
    "発売",
    "販売開始",
    "受付開始",
    "受付期間",
    "販売期間",
    "申込期間",
    "申し込み期間",
    "FANY ID",
    "プレミアムメンバー",
    "FANYコミュ",
]


def detect_sale_category(text):
    text = clean(text)

    if any(
        word in text
        for word in ADVANCE_WORDS
    ):
        return "advance"

    if any(
        word in text
        for word in FIRST_COME_WORDS
    ):
        return "first_come"

    return ""


def detect_sale_label(
    text,
    category,
):
    text = clean(text)

    if category == "advance":
        labels = [
            "FANY IDプレミアムメンバー先行",
            "FANY IDメンバー先行",
            "プレミアムメンバー先行",
            "FANYコミュ先行",
            "ファンクラブ先行",
            "抽選先行",
            "先行受付",
            "先行販売",
            "先行",
            "抽選",
        ]

    else:
        labels = [
            "一般発売",
            "一般販売",
            "一般受付",
            "先着販売",
            "先着",
            "販売開始",
            "発売",
        ]

    for label in labels:
        if label in text:
            return label

    if category == "advance":
        return "先行販売"

    if category == "first_come":
        return "先着販売"

    return ""


def is_sale_marker(line):
    text = clean(line)

    return any(
        word in text
        for word in SALE_MARKER_WORDS
    )


def extract_sale_periods(lines):
    marker_indexes = [
        index
        for index, line in enumerate(lines)
        if is_sale_marker(line)
    ]

    periods = []
    seen = set()

    for marker_number, index in enumerate(
        marker_indexes
    ):
        if (
            marker_number + 1
            <
            len(marker_indexes)
        ):
            next_marker = marker_indexes[
                marker_number + 1
            ]
        else:
            next_marker = len(lines)

        start = max(
            0,
            index - 1,
        )

        end = min(
            next_marker,
            index + 8,
        )

        context_lines = lines[
            start:end
        ]

        context = " ".join(
            context_lines
        )

        category = detect_sale_category(
            context
        )

        if not category:
            continue

        datetimes = extract_japanese_datetimes(
            context
        )

        if not datetimes:
            continue

        start_at = datetimes[0]

        end_at = (
            datetimes[1]
            if len(datetimes) >= 2
            else ""
        )

        label = detect_sale_label(
            context,
            category,
        )

        key = (
            category,
            label,
            start_at,
            end_at,
        )

        if key in seen:
            continue

        seen.add(key)

        periods.append({
            "category":
                category,

            "label":
                label,

            "startAt":
                start_at,

            "endAt":
                end_at,

            "_anchorIndex":
                index,

            "_context":
                context,
        })

    periods.sort(
        key=lambda item:
            item.get(
                "startAt",
                "",
            )
    )

    return periods


def public_sale_period(period):
    return {
        "category":
            period.get(
                "category",
                "",
            ),

        "label":
            period.get(
                "label",
                "",
            ),

        "startAt":
            period.get(
                "startAt",
                "",
            ),

        "endAt":
            period.get(
                "endAt",
                "",
            ),
    }


def choose_primary_sale_period(
    periods,
):
    if not periods:
        return None

    first_come = [
        period
        for period in periods
        if period.get(
            "category"
        )
        ==
        "first_come"
    ]

    candidates = (
        first_come
        if first_come
        else periods
    )

    return sorted(
        candidates,
        key=lambda item:
            item.get(
                "startAt",
                "",
            ),
    )[0]


# =========================================================
# FANY
# =========================================================

FANY_DATE_RE = re.compile(
    r"^(20\d{2})/"
    r"(\d{1,2})/"
    r"(\d{1,2})"
)

FANY_START_RE = re.compile(
    r"開演\s*(\d{1,2}:\d{2})"
)

FANY_OPEN_RE = re.compile(
    r"開場\s*(\d{1,2}:\d{2})"
)

FANY_RECEPTION_RE = re.compile(
    r"/reception/\d+/\d+"
)

PRICE_RE = re.compile(
    r"(?:￥|¥)\s*[\d,]+(?:円)?"
)


# =========================================================
# FANY販売情報
# =========================================================

def normalize_ticket_status(line):
    text = clean(line)

    mapping = [
        (
            "予定数終了",
            "予定数終了",
        ),
        (
            "予定枚数終了",
            "予定数終了",
        ),
        (
            "残りわずか",
            "残りわずか",
        ),
        (
            "残席わずか",
            "残りわずか",
        ),
        (
            "販売中",
            "販売中",
        ),
        (
            "受付中",
            "受付中",
        ),
        (
            "販売終了",
            "販売終了",
        ),
        (
            "受付終了",
            "受付終了",
        ),
        (
            "完売",
            "予定数終了",
        ),
    ]

    for source, result in mapping:
        if text == source:
            return result

    return ""


def is_ticket_type(line):
    text = clean(line)

    return bool(
        re.fullmatch(
            r"(?:"
            r"前売|当日|"
            r"前売券|当日券|"
            r"一般|一般券|"
            r"大人|小人|"
            r"学生|学生券|"
            r"学割|"
            r"高校生|大学生|"
            r"中学生|小学生|"
            r"シニア"
            r")",
            text,
        )
    )


def extract_price(line):
    match = PRICE_RE.search(
        clean(line)
    )

    if not match:
        return ""

    return clean(
        match.group(0)
    )


def is_sales_line(line):
    return is_sale_marker(
        line
    )


def is_ticket_option_name_candidate(
    line,
):
    text = clean(line)

    if not text:
        return False

    if len(text) > 70:
        return False

    if normalize_ticket_status(
        text
    ):
        return False

    if is_ticket_type(
        text
    ):
        return False

    if extract_price(
        text
    ):
        return False

    if FANY_DATE_RE.match(
        text
    ):
        return False

    bad_words = [
        "開場",
        "開演",
        "出演",
        "会場",
        "料金",
        "発売",
        "販売",
        "受付",
        "抽選",
        "先着",
        "お問い合わせ",
        "注意事項",
        "公演概要",
        "FANY ID",
        "プレミアム",
        "閉じる",
        "PAGE TOP",
    ]

    if any(
        word in text
        for word in bad_words
    ):
        return False

    if re.search(
        r"（[^）]*(?:都|道|府|県)）$",
        text,
    ):
        return False

    return True


def find_previous_ticket_type(
    lines,
    status_index,
):
    start = max(
        0,
        status_index - 4,
    )

    for index in range(
        status_index - 1,
        start - 1,
        -1,
    ):
        if is_ticket_type(
            lines[index]
        ):
            return (
                index,
                clean(
                    lines[index]
                ),
            )

    return (
        None,
        "",
    )


def find_ticket_option_name_with_index(
    lines,
    before_index,
):
    start = max(
        0,
        before_index - 7,
    )

    for index in range(
        before_index - 1,
        start - 1,
        -1,
    ):
        line = clean(
            lines[index]
        )

        if is_ticket_option_name_candidate(
            line
        ):
            return (
                index,
                line,
            )

    return (
        None,
        "",
    )


def find_ticket_price(
    lines,
    status_index,
):
    start = max(
        0,
        status_index - 2,
    )

    end = min(
        len(lines),
        status_index + 5,
    )

    for index in range(
        status_index + 1,
        end,
    ):
        price = extract_price(
            lines[index]
        )

        if price:
            return price

    for index in range(
        status_index - 1,
        start - 1,
        -1,
    ):
        price = extract_price(
            lines[index]
        )

        if price:
            return price

    return ""


def sale_period_matches_option(
    period,
    option,
):
    context = clean(
        period.get(
            "_context",
            "",
        )
    )

    name = clean(
        option.get(
            "name",
            "",
        )
    )

    ticket_type = clean(
        option.get(
            "type",
            "",
        )
    )

    if (
        name
        and name in context
    ):
        return True

    if (
        not name
        and
        ticket_type
        and
        ticket_type in context
    ):
        return True

    return False


def attach_sale_periods_to_options(
    options,
    sale_periods,
):
    if not options:
        return options

    any_explicit_match = any(
        sale_period_matches_option(
            period,
            option,
        )
        for period in sale_periods
        for option in options
    )

    for option in options:
        matched = []

        if any_explicit_match:
            matched = [
                period
                for period in sale_periods
                if sale_period_matches_option(
                    period,
                    option,
                )
            ]

        if not matched:
            matched = sale_periods

        option[
            "salePeriods"
        ] = [
            public_sale_period(
                period
            )
            for period in matched
        ]

        primary = choose_primary_sale_period(
            matched
        )

        option[
            "saleStartAt"
        ] = (
            primary.get(
                "startAt",
                "",
            )
            if primary
            else ""
        )

        option[
            "saleEndAt"
        ] = (
            primary.get(
                "endAt",
                "",
            )
            if primary
            else ""
        )

        option[
            "saleCategory"
        ] = (
            primary.get(
                "category",
                "",
            )
            if primary
            else ""
        )

        option[
            "saleLabel"
        ] = (
            primary.get(
                "label",
                "",
            )
            if primary
            else ""
        )

        option.pop(
            "_statusIndex",
            None,
        )

        option.pop(
            "_typeIndex",
            None,
        )

        option.pop(
            "_nameIndex",
            None,
        )

    return options


def get_fany_ticket_options(
    lines,
    sale_periods=None,
):
    if sale_periods is None:
        sale_periods = (
            extract_sale_periods(
                lines
            )
        )

    options = []
    seen = set()

    for index, line in enumerate(
        lines
    ):
        status = normalize_ticket_status(
            line
        )

        if not status:
            continue

        (
            type_index,
            ticket_type,
        ) = find_previous_ticket_type(
            lines,
            index,
        )

        name_before = (
            type_index
            if type_index is not None
            else index
        )

        (
            name_index,
            name,
        ) = find_ticket_option_name_with_index(
            lines,
            name_before,
        )

        price = find_ticket_price(
            lines,
            index,
        )

        if (
            not name
            and not ticket_type
            and not price
        ):
            continue

        if (
            not ticket_type
            and not price
        ):
            continue

        key = (
            name,
            ticket_type,
            status,
            price,
        )

        if key in seen:
            continue

        seen.add(key)

        options.append({
            "name":
                name,

            "type":
                ticket_type,

            "status":
                status,

            "price":
                price,

            "_statusIndex":
                index,

            "_typeIndex":
                type_index,

            "_nameIndex":
                name_index,
        })

    return attach_sale_periods_to_options(
        options,
        sale_periods,
    )


def summarize_ticket_status(
    ticket_options,
    lines,
):
    statuses = [
        option.get(
            "status",
            "",
        )
        for option in ticket_options
        if option.get(
            "status"
        )
    ]

    if statuses:
        if (
            "残りわずか"
            in statuses
        ):
            return "残りわずか"

        ended_statuses = {
            "予定数終了",
            "販売終了",
            "受付終了",
        }

        active_statuses = {
            "販売中",
            "受付中",
            "残りわずか",
        }

        has_ended = any(
            status in ended_statuses
            for status in statuses
        )

        has_active = any(
            status in active_statuses
            for status in statuses
        )

        if (
            has_ended
            and has_active
        ):
            return "一部予定数終了"

        if (
            statuses
            and all(
                status in ended_statuses
                for status in statuses
            )
        ):
            if (
                "予定数終了"
                in statuses
            ):
                return "予定数終了"

            return "販売終了"

        if has_active:
            return "販売中"

    text = " ".join(
        lines
    )

    if "残りわずか" in text:
        return "残りわずか"

    if "予定数終了" in text:
        return "予定数終了"

    return ""


# =========================================================
# FANY検索結果
# =========================================================

def count_fany_blocks(lines):
    return sum(
        1
        for line in lines
        if FANY_DATE_RE.match(
            line
        )
    )


def parse_fany_text_events(
    lines,
    performer,
    search_url,
):
    performer_id = performer[
        "id"
    ]

    performer_name = performer[
        "name"
    ]

    event_indexes = []

    for index, line in enumerate(
        lines
    ):
        if FANY_DATE_RE.match(
            line
        ):
            event_indexes.append(
                index
            )

    events = []

    for number, start_index in enumerate(
        event_indexes
    ):
        if (
            number + 1
            <
            len(event_indexes)
        ):
            end_index = event_indexes[
                number + 1
            ]

        else:
            end_index = len(
                lines
            )

        block = lines[
            start_index:end_index
        ]

        if not block:
            continue

        date_match = FANY_DATE_RE.match(
            block[0]
        )

        if not date_match:
            continue

        (
            year,
            month,
            day,
        ) = date_match.groups()

        event_date = make_date(
            year,
            month,
            day,
        )

        if not is_today_or_future(
            event_date
        ):
            continue

        performer_text = ""

        try:
            performer_index = block.index(
                "出演"
            )

            parts = []

            for line in block[
                performer_index + 1:
            ]:
                if is_sales_line(
                    line
                ):
                    break

                parts.append(
                    line
                )

            performer_text = " ".join(
                parts
            )

        except ValueError:
            performer_text = " ".join(
                block
            )

        if (
            performer_name
            not in performer_text
        ):
            continue

        start_time = ""

        for line in block[:15]:
            match = FANY_START_RE.search(
                line
            )

            if match:
                start_time = match.group(
                    1
                )
                break

        open_time = ""

        for line in block[:15]:
            match = FANY_OPEN_RE.search(
                line
            )

            if match:
                open_time = match.group(
                    1
                )
                break

        venue = ""
        venue_index = None

        for index, line in enumerate(
            block[:25]
        ):
            if re.search(
                r"（[^）]*(?:都|道|府|県)）$",
                line,
            ):
                venue = line
                venue_index = index
                break

        title = ""

        if (
            venue_index is not None
            and venue_index > 0
        ):
            candidate = clean(
                block[
                    venue_index - 1
                ]
            )

            if (
                candidate
                and candidate != ")"
                and "開場" not in candidate
                and "開演" not in candidate
                and candidate != "出演"
            ):
                title = candidate

        if not title:
            title = "公演名不明"

        block_text = " ".join(
            block
        )

        ticket_status = ""

        if (
            "残りわずか"
            in block_text
        ):
            ticket_status = (
                "残りわずか"
            )

        elif (
            "予定数終了"
            in block_text
        ):
            ticket_status = (
                "予定数終了"
            )

        events.append({
            "performerId":
                performer_id,

            "date":
                event_date,

            "openTime":
                open_time,

            "startTime":
                start_time,

            "title":
                title,

            "venue":
                venue,

            "source":
                "fany",

            "sourceUrl":
                search_url,

            "ticketStatus":
                ticket_status,

            "ticketOptions":
                [],

            "saleStartAt":
                "",

            "saleEndAt":
                "",

            "saleCategory":
                "",

            "salePeriods":
                [],

            "performersText":
                [],
        })

    return events


def find_reception_candidates(html):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    result = []
    seen = set()

    for link in soup.find_all(
        "a",
        href=True,
    ):
        href = link.get(
            "href",
            "",
        )

        if not FANY_RECEPTION_RE.search(
            href
        ):
            continue

        url = urljoin(
            FANY_BASE,
            href,
        )

        if url in seen:
            continue

        seen.add(url)

        container = link
        selected_lines = []

        for _ in range(
            10
        ):
            if not container:
                break

            container = container.parent

            if not container:
                break

            lines = []

            for raw in container.get_text(
                "\n"
            ).splitlines():

                text = clean(
                    raw
                )

                if text:
                    lines.append(
                        text
                    )

            date_count = sum(
                1
                for line in lines
                if FANY_DATE_RE.match(
                    line
                )
            )

            if (
                date_count == 1
                and "出演" in lines
            ):
                selected_lines = lines
                break

        if selected_lines:
            result.append({
                "url":
                    url,

                "lines":
                    selected_lines,
            })

    return result


def candidate_info(candidate):
    lines = candidate[
        "lines"
    ]

    event_date = ""
    start_time = ""
    venue = ""

    for line in lines:
        match = FANY_DATE_RE.match(
            line
        )

        if match:
            (
                year,
                month,
                day,
            ) = match.groups()

            event_date = make_date(
                year,
                month,
                day,
            )

            break

    for line in lines:
        match = FANY_START_RE.search(
            line
        )

        if match:
            start_time = match.group(
                1
            )
            break

    for line in lines:
        if re.search(
            r"（[^）]*(?:都|道|府|県)）$",
            line,
        ):
            venue = line
            break

    return {
        "date":
            event_date,

        "startTime":
            start_time,

        "venue":
            venue,

        "url":
            candidate[
                "url"
            ],
    }


def attach_fany_urls(
    events,
    html,
):
    candidates = [
        candidate_info(
            item
        )
        for item in find_reception_candidates(
            html
        )
    ]

    for event in events:
        best = None
        best_score = -1

        for candidate in candidates:
            if (
                candidate[
                    "date"
                ]
                !=
                event.get(
                    "date",
                    "",
                )
            ):
                continue

            score = 5

            if (
                candidate[
                    "startTime"
                ]
                and
                candidate[
                    "startTime"
                ]
                ==
                event.get(
                    "startTime",
                    "",
                )
            ):
                score += 5

            if (
                normalize_venue(
                    candidate[
                        "venue"
                    ]
                )
                ==
                normalize_venue(
                    event.get(
                        "venue",
                        "",
                    )
                )
            ):
                score += 4

            if score > best_score:
                best = candidate
                best_score = score

        if (
            best
            and best_score >= 9
        ):
            event[
                "sourceUrl"
            ] = best[
                "url"
            ]


# =========================================================
# FANY詳細ページ
# =========================================================

def get_fany_open_time(lines):
    for line in lines:
        match = FANY_OPEN_RE.search(
            line
        )

        if match:
            return match.group(
                1
            )

    return ""


def get_fany_performers(lines):
    performers = []
    start_index = None

    for index, line in enumerate(
        lines
    ):
        if line in [
            "出演",
            "出演者",
        ]:
            start_index = (
                index + 1
            )
            break

    if start_index is None:
        return []

    stop_words = [
        "料金",
        "チケット",
        "発売",
        "販売",
        "受付",
        "公演概要",
        "注意事項",
        "お問い合わせ",
        "開場",
        "開演",
    ]

    for line in lines[
        start_index:
    ]:
        if any(
            word in line
            for word in stop_words
        ):
            break

        text = clean(
            line
        )

        if not text:
            continue

        if re.match(
            r"^20\d{2}[/-]\d",
            text,
        ):
            break

        if len(text) > 120:
            continue

        performers.append(
            text
        )

    cleaned = []

    for line in performers:
        parts = re.split(
            r"[／/、,，]+",
            line,
        )

        for part in parts:
            part = clean(
                part
            )

            if not part:
                continue

            if part in [
                "出演",
                "出演者",
            ]:
                continue

            cleaned.append(
                part
            )

    return unique_strings(
        cleaned
    )


def enrich_fany_event(
    session,
    event,
    detail_cache,
):
    url = event.get(
        "sourceUrl",
        "",
    )

    if not re.search(
        r"/reception/\d+/\d+",
        url,
    ):
        return event

    if url in detail_cache:
        detail = detail_cache[
            url
        ]

    else:
        try:
            response = session.get(
                url,
                timeout=20,
            )

            response.raise_for_status()

            lines = html_to_lines(
                response.text
            )

            sale_periods_raw = (
                extract_sale_periods(
                    lines
                )
            )

            ticket_options = (
                get_fany_ticket_options(
                    lines,
                    sale_periods_raw,
                )
            )

            primary_sale = (
                choose_primary_sale_period(
                    sale_periods_raw
                )
            )

            detail = {
                "ticketOptions":
                    ticket_options,

                "ticketStatus":
                    summarize_ticket_status(
                        ticket_options,
                        lines,
                    ),

                "salePeriods":
                    [
                        public_sale_period(
                            period
                        )
                        for period
                        in sale_periods_raw
                    ],

                "saleStartAt":
                    (
                        primary_sale.get(
                            "startAt",
                            "",
                        )
                        if primary_sale
                        else ""
                    ),

                "saleEndAt":
                    (
                        primary_sale.get(
                            "endAt",
                            "",
                        )
                        if primary_sale
                        else ""
                    ),

                "saleCategory":
                    (
                        primary_sale.get(
                            "category",
                            "",
                        )
                        if primary_sale
                        else ""
                    ),

                "openTime":
                    get_fany_open_time(
                        lines
                    ),

                "performersText":
                    get_fany_performers(
                        lines
                    ),
            }

        except Exception as error:
            print(
                "FANY詳細取得失敗:",
                url,
                error,
            )

            detail = {}

        detail_cache[
            url
        ] = detail

    event[
        "ticketOptions"
    ] = detail.get(
        "ticketOptions",
        event.get(
            "ticketOptions",
            [],
        ),
    )

    if (
        "ticketStatus"
        in detail
    ):
        event[
            "ticketStatus"
        ] = detail.get(
            "ticketStatus",
            event.get(
                "ticketStatus",
                "",
            ),
        )

    event[
        "salePeriods"
    ] = detail.get(
        "salePeriods",
        event.get(
            "salePeriods",
            [],
        ),
    )

    event[
        "saleStartAt"
    ] = detail.get(
        "saleStartAt",
        event.get(
            "saleStartAt",
            "",
        ),
    )

    event[
        "saleEndAt"
    ] = detail.get(
        "saleEndAt",
        event.get(
            "saleEndAt",
            "",
        ),
    )

    event[
        "saleCategory"
    ] = detail.get(
        "saleCategory",
        event.get(
            "saleCategory",
            "",
        ),
    )

    if detail.get(
        "openTime"
    ):
        event[
            "openTime"
        ] = detail[
            "openTime"
        ]

    if detail.get(
        "performersText"
    ):
        event[
            "performersText"
        ] = detail[
            "performersText"
        ]

    return event


def request_fany_range(
    session,
    performer,
    start_date,
    end_date,
):
    params = {
        "keywords":
            performer[
                "name"
            ],

        "from":
            fany_date_string(
                start_date
            ),

        "to":
            fany_date_string(
                end_date
            ),

        "prefectures":
            "0",

        "genre":
            "0",

        "search_type":
            "form",
    }

    search_url = (
        FANY_SEARCH_URL
        +
        "?"
        +
        urlencode(
            params
        )
    )

    response = session.get(
        search_url,
        timeout=30,
    )

    response.raise_for_status()

    lines = html_to_lines(
        response.text
    )

    events = parse_fany_text_events(
        lines,
        performer,
        search_url,
    )

    attach_fany_urls(
        events,
        response.text,
    )

    return (
        count_fany_blocks(
            lines
        ),
        events,
    )


def scrape_fany_range(
    session,
    performer,
    start_date,
    end_date,
    depth=0,
):
    try:
        (
            block_count,
            events,
        ) = request_fany_range(
            session,
            performer,
            start_date,
            end_date,
        )

    except Exception as error:
        print(
            "FANY取得失敗:",
            error,
        )

        return []

    if (
        block_count
        <
        FANY_PAGE_LIMIT
    ):
        return events

    if start_date >= end_date:
        return events

    total_days = (
        end_date
        -
        start_date
    ).days

    middle = (
        start_date
        +
        timedelta(
            days=total_days // 2
        )
    )

    return (
        scrape_fany_range(
            session,
            performer,
            start_date,
            middle,
            depth + 1,
        )
        +
        scrape_fany_range(
            session,
            performer,
            middle
            +
            timedelta(
                days=1
            ),
            end_date,
            depth + 1,
        )
    )


def scrape_fany(
    session,
    performer,
    detail_cache,
):
    print(
        "FANY検索:",
        performer[
            "name"
        ],
    )

    events = []

    for (
        start_date,
        end_date,
    ) in build_month_ranges():

        events.extend(
            scrape_fany_range(
                session,
                performer,
                start_date,
                end_date,
            )
        )

    unique = {}

    for event in events:
        unique[
            identity_key(
                event
            )
        ] = event

    result = list(
        unique.values()
    )

    enriched = []

    for event in result:
        enriched.append(
            enrich_fany_event(
                session,
                event,
                detail_cache,
            )
        )

    print(
        "FANY",
        performer[
            "name"
        ],
        len(
            enriched
        ),
        "件",
    )

    return enriched


# =========================================================
# TIGET
# =========================================================

def get_next_value(
    lines,
    label,
):
    try:
        index = lines.index(
            label
        )

    except ValueError:
        return ""

    for line in lines[
        index + 1:
    ]:
        line = clean(
            line
        )

        if line:
            return line

    return ""


def is_bad_tiget_title(title):
    title = clean(
        title
    )

    if not title:
        return True

    bad_words = [
        "基本利用無料のチケット販売システム",
        "TIGET チゲット",
        "ライブイベントのチケット販売",
        "チケット販売・購入・予約",
    ]

    return any(
        word in title
        for word in bad_words
    )


def clean_tiget_title(title):
    title = clean(
        title
    )

    title = re.sub(
        r"\s*[|｜]\s*TIGET.*$",
        "",
        title,
    )

    title = re.sub(
        r"\s+のチケット.*$",
        "",
        title,
    )

    return clean(
        title
    )


def get_tiget_title(
    soup,
    search_title,
):
    search_title = clean_tiget_title(
        search_title
    )

    if (
        search_title
        and not is_bad_tiget_title(
            search_title
        )
    ):
        return search_title

    og = soup.find(
        "meta",
        attrs={
            "property":
                "og:title"
        },
    )

    if (
        og
        and og.get(
            "content"
        )
    ):
        candidate = clean_tiget_title(
            og.get(
                "content"
            )
        )

        if not is_bad_tiget_title(
            candidate
        ):
            return candidate

    twitter = soup.find(
        "meta",
        attrs={
            "name":
                "twitter:title"
        },
    )

    if (
        twitter
        and twitter.get(
            "content"
        )
    ):
        candidate = clean_tiget_title(
            twitter.get(
                "content"
            )
        )

        if not is_bad_tiget_title(
            candidate
        ):
            return candidate

    for tag in [
        "h1",
        "h2",
        "h3",
    ]:
        for heading in soup.find_all(
            tag
        ):
            candidate = clean_tiget_title(
                heading.get_text(
                    " ",
                    strip=True,
                )
            )

            if (
                candidate
                and len(candidate) >= 3
                and not is_bad_tiget_title(
                    candidate
                )
                and candidate not in [
                    "出演者",
                    "開催日",
                    "会場",
                    "イベント詳細",
                ]
            ):
                return candidate

    return "公演名不明"


def get_tiget_performers(lines):
    performers = []
    start_index = None

    for index, line in enumerate(
        lines
    ):
        if line in [
            "出演者",
            "出演",
        ]:
            start_index = (
                index + 1
            )
            break

    if start_index is None:
        return []

    stop_words = [
        "開催日",
        "会場",
        "開場",
        "開演",
        "料金",
        "チケット",
        "イベント詳細",
        "販売",
        "受付",
    ]

    for line in lines[
        start_index:
    ]:
        if any(
            word in line
            for word in stop_words
        ):
            break

        text = clean(
            line
        )

        if not text:
            continue

        if len(text) > 120:
            continue

        performers.append(
            text
        )

    result = []

    for line in performers:
        result.extend(
            re.split(
                r"[／/、,，]+",
                line,
            )
        )

    return unique_strings(
        result
    )


def get_tiget_ticket_status(lines):
    text = " ".join(
        lines
    )

    if (
        "残りわずか" in text
        or
        "残席わずか" in text
    ):
        return "残りわずか"

    if (
        "予定数終了" in text
        or
        "完売" in text
    ):
        return "予定数終了"

    if (
        "販売中" in text
        or
        "受付中" in text
    ):
        return "販売中"

    if (
        "販売終了" in text
        or
        "受付終了" in text
    ):
        return "販売終了"

    return ""


def scrape_tiget(
    session,
    performer,
):
    performer_id = performer[
        "id"
    ]

    performer_name = performer[
        "name"
    ]

    print(
        "TIGET検索:",
        performer_name,
    )

    response = session.get(
        TIGET_SEARCH_URL,
        params={
            "q[words]":
                performer_name
        },
        timeout=30,
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    event_map = {}

    for link in soup.find_all(
        "a",
        href=True,
    ):
        href = link.get(
            "href",
            "",
        )

        match = re.match(
            r"^/events/(\d+)",
            href,
        )

        if not match:
            continue

        event_url = (
            TIGET_BASE
            +
            "/events/"
            +
            match.group(1)
        )

        title = clean(
            link.get_text(
                " ",
                strip=True,
            )
        )

        if (
            event_url
            not in event_map
        ):
            event_map[
                event_url
            ] = title

    events = []

    for (
        event_url,
        search_title,
    ) in event_map.items():

        try:
            response = session.get(
                event_url,
                timeout=20,
            )

            response.raise_for_status()

        except Exception as error:
            print(
                "TIGET詳細失敗:",
                event_url,
                error,
            )
            continue

        detail_soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        lines = []

        for raw in detail_soup.get_text(
            "\n"
        ).splitlines():

            line = clean(
                raw
            )

            if line:
                lines.append(
                    line
                )

        whole_text = " ".join(
            lines
        )

        if (
            performer_name
            not in whole_text
        ):
            continue

        date_match = re.search(
            r"(20\d{2})年"
            r"(\d{1,2})月"
            r"(\d{1,2})日",
            whole_text,
        )

        if not date_match:
            continue

        (
            year,
            month,
            day,
        ) = date_match.groups()

        event_date = make_date(
            year,
            month,
            day,
        )

        if not is_today_or_future(
            event_date
        ):
            continue

        time_match = re.search(
            r"開演\s*[:：]?\s*"
            r"(\d{1,2}:\d{2})",
            whole_text,
        )

        start_time = (
            time_match.group(1)
            if time_match
            else ""
        )

        open_match = re.search(
            r"開場\s*[:：]?\s*"
            r"(\d{1,2}:\d{2})",
            whole_text,
        )

        open_time = (
            open_match.group(1)
            if open_match
            else ""
        )

        venue = clean(
            get_next_value(
                lines,
                "会場",
            )
        )

        title = get_tiget_title(
            detail_soup,
            search_title,
        )

        performers_text = (
            get_tiget_performers(
                lines
            )
        )

        sale_periods_raw = (
            extract_sale_periods(
                lines
            )
        )

        primary_sale = (
            choose_primary_sale_period(
                sale_periods_raw
            )
        )

        events.append({
            "performerId":
                performer_id,

            "date":
                event_date,

            "openTime":
                open_time,

            "startTime":
                start_time,

            "title":
                title,

            "venue":
                venue,

            "source":
                "tiget",

            "sourceUrl":
                event_url,

            "ticketStatus":
                get_tiget_ticket_status(
                    lines
                ),

            "ticketOptions":
                [],

            "saleStartAt":
                (
                    primary_sale.get(
                        "startAt",
                        "",
                    )
                    if primary_sale
                    else ""
                ),

            "saleEndAt":
                (
                    primary_sale.get(
                        "endAt",
                        "",
                    )
                    if primary_sale
                    else ""
                ),

            "saleCategory":
                (
                    primary_sale.get(
                        "category",
                        "",
                    )
                    if primary_sale
                    else ""
                ),

            "salePeriods":
                [
                    public_sale_period(
                        period
                    )
                    for period
                    in sale_periods_raw
                ],

            "performersText":
                performers_text,
        })

    print(
        "TIGET",
        performer_name,
        len(
            events
        ),
        "件",
    )

    return events


# =========================================================
# 重複整理
# =========================================================

def remove_duplicates(events):
    result = []
    seen = set()

    for event in events:
        key = identity_key(
            event
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(event)

    return result


# =========================================================
# 過去イベント照合
# =========================================================

def build_old_event_maps(
    old_events,
):
    maps = {
        "source":
            {},

        "stable":
            {},

        "loose":
            {},
    }

    for event in old_events:
        source_key = (
            source_notification_key(
                event
            )
        )

        if source_key:
            maps[
                "source"
            ][
                source_key
            ] = event

        maps[
            "stable"
        ][
            stable_notification_key(
                event
            )
        ] = event

        maps[
            "loose"
        ][
            loose_notification_key(
                event
            )
        ] = event

    return maps


def find_old_event(
    event,
    old_maps,
):
    source_key = (
        source_notification_key(
            event
        )
    )

    if (
        source_key
        and source_key
        in old_maps[
            "source"
        ]
    ):
        return old_maps[
            "source"
        ][
            source_key
        ]

    stable_key = (
        stable_notification_key(
            event
        )
    )

    if (
        stable_key
        in old_maps[
            "stable"
        ]
    ):
        return old_maps[
            "stable"
        ][
            stable_key
        ]

    loose_key = (
        loose_notification_key(
            event
        )
    )

    if (
        loose_key
        in old_maps[
            "loose"
        ]
    ):
        return old_maps[
            "loose"
        ][
            loose_key
        ]

    return None


# =========================================================
# 新着情報
# =========================================================

def apply_discovery_metadata(
    events,
    old_events,
    new_events,
):
    old_maps = build_old_event_maps(
        old_events
    )

    new_keys = {
        identity_key(
            event
        )
        for event in new_events
    }

    current_time = now_iso()
    until_time = new_until_iso()

    for event in events:
        old_event = find_old_event(
            event,
            old_maps,
        )

        if old_event:
            event[
                "firstSeenAt"
            ] = (
                old_event.get(
                    "firstSeenAt"
                )
                or
                old_event.get(
                    "discoveredAt"
                )
                or
                current_time
            )

            event[
                "newUntil"
            ] = old_event.get(
                "newUntil",
                "",
            )

        else:
            event[
                "firstSeenAt"
            ] = current_time

            if (
                identity_key(
                    event
                )
                in new_keys
            ):
                event[
                    "newUntil"
                ] = until_time

            else:
                event[
                    "newUntil"
                ] = ""


# =========================================================
# 追跡芸人
# =========================================================

def attach_tracked_performers(
    events,
):
    groups = {}

    for event in events:
        key = calendar_key(
            event
        )

        groups.setdefault(
            key,
            [],
        )

        performer_id = event.get(
            "performerId",
            "",
        )

        if (
            performer_id
            and performer_id
            not in groups[key]
        ):
            groups[
                key
            ].append(
                performer_id
            )

    for event in events:
        event[
            "trackedPerformers"
        ] = groups.get(
            calendar_key(
                event
            ),
            [],
        )


# =========================================================
# 販売開始通知用キー
# =========================================================

def make_ticket_sale_key(
    event,
    option,
    period,
):
    source_key = (
        source_notification_key(
            event
        )
        or
        identity_key(
            event
        )
    )

    return "|".join([
        source_key,
        clean(
            option.get(
                "name",
                "",
            )
        ),
        clean(
            option.get(
                "type",
                "",
            )
        ),
        period.get(
            "category",
            "",
        ),
        period.get(
            "startAt",
            "",
        ),
    ])


def attach_ticket_sale_keys(
    events,
):
    for event in events:
        options = event.get(
            "ticketOptions",
            [],
        )

        for option in options:
            periods = option.get(
                "salePeriods",
                [],
            )

            for period in periods:
                period[
                    "saleKey"
                ] = make_ticket_sale_key(
                    event,
                    option,
                    period,
                )


# =========================================================
# ログ用
# =========================================================

def count_ticket_option_sale_starts(
    events,
):
    count = 0

    for event in events:
        for option in event.get(
            "ticketOptions",
            [],
        ):
            if option.get(
                "saleStartAt"
            ):
                count += 1

    return count


def count_sale_periods(
    events,
    category=None,
):
    count = 0

    for event in events:
        for period in event.get(
            "salePeriods",
            [],
        ):
            if (
                category is None
                or
                period.get(
                    "category"
                )
                ==
                category
            ):
                count += 1

    return count


# =========================================================
# MAIN
# =========================================================

def main():
    print(
        "================================"
    )

    print(
        "出演情報取得開始"
    )

    print(
        "券種別販売期間＋販売分類＋新着48時間版"
    )

    print(
        "================================"
    )

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

    old_data = load_json(
        EVENTS_FILE,
        {
            "events":
                []
        },
    )

    if isinstance(
        old_data,
        list,
    ):
        old_events = old_data

    else:
        old_events = old_data.get(
            "events",
            [],
        )

    # =====================================================
    # 通知済み履歴
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
    # 既存公演を通知済みに登録
    # =====================================================

    for event in old_events:
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

    print(
        "既存公演を通知済みに登録:",
        len(
            old_events
        ),
        "件",
    )

    print(
        "通知済みURL/ID:",
        len(
            source_keys
        ),
    )

    # =====================================================
    # スクレイピング
    # =====================================================

    session = requests.Session()

    session.headers.update(
        HEADERS
    )

    all_events = []

    fany_detail_cache = {}

    for performer in performers:
        if not performer.get(
            "name"
        ):
            continue

        sources = performer.get(
            "sources",
            [
                "fany",
                "tiget",
            ],
        )

        if "fany" in sources:
            try:
                all_events.extend(
                    scrape_fany(
                        session,
                        performer,
                        fany_detail_cache,
                    )
                )

            except Exception as error:
                print(
                    "FANYエラー:",
                    error,
                )

        if "tiget" in sources:
            try:
                all_events.extend(
                    scrape_tiget(
                        session,
                        performer,
                    )
                )

            except Exception as error:
                print(
                    "TIGETエラー:",
                    error,
                )
                
        if "eplus" in sources:
            try:
                all_events.extend(
                    scrape_eplus(
                        session,
                        performer,
                    )
                )

            except Exception as error:
                print(
                    "イープラスエラー:",
                    error,
                )
                
                        if "livepocket" in sources:
            try:
                all_events.extend(
                    scrape_livepocket(
                        session,
                        performer,
                    )
                )

            except Exception as error:
                print(
                    "LivePocketエラー:",
                    error,
                )
                
    # =====================================================
    # 過去公演除外
    # =====================================================

    all_events = [
        event
        for event in all_events
        if is_today_or_future(
            event.get(
                "date",
                "",
            )
        )
    ]

    all_events = remove_duplicates(
        all_events
    )

    # =====================================================
    # 本当の新規公演
    # =====================================================

    new_events = []

    for event in all_events:
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
            and source_key
            in source_keys
        ):
            continue

        if stable_key in stable_keys:
            continue

        if loose_key in loose_keys:
            continue

        new_events.append(
            event
        )

    # =====================================================
    # firstSeenAt / newUntil
    # =====================================================

    apply_discovery_metadata(
        all_events,
        old_events,
        new_events,
    )

    # =====================================================
    # 共演情報
    # =====================================================

    attach_tracked_performers(
        all_events
    )

    # =====================================================
    # 販売通知キー
    # =====================================================

    attach_ticket_sale_keys(
        all_events
    )

    # =====================================================
    # 並び替え
    # =====================================================

    all_events.sort(
        key=lambda event: (
            event.get(
                "date",
                "",
            ),
            event.get(
                "startTime",
                "",
            ),
            event.get(
                "performerId",
                "",
            ),
        )
    )

    # =====================================================
    # 保存
    # =====================================================

    output = {
        "syncedAt":
            now_iso(),

        "performers":
            performers,

        "events":
            all_events,
    }

    save_json(
        EVENTS_FILE,
        output,
    )

    save_json(
        NEW_EVENTS_FILE,
        new_events,
    )

    # =====================================================
    # ログ
    # =====================================================

    status_count = sum(
        1
        for event in all_events
        if event.get(
            "ticketStatus"
        )
    )

    ticket_option_event_count = sum(
        1
        for event in all_events
        if event.get(
            "ticketOptions"
        )
    )

    ticket_option_total = sum(
        len(
            event.get(
                "ticketOptions",
                [],
            )
        )
        for event in all_events
    )

    sale_start_count = sum(
        1
        for event in all_events
        if event.get(
            "saleStartAt"
        )
    )

    ticket_option_sale_start_count = (
        count_ticket_option_sale_starts(
            all_events
        )
    )

    advance_period_count = (
        count_sale_periods(
            all_events,
            "advance",
        )
    )

    first_come_period_count = (
        count_sale_periods(
            all_events,
            "first_come",
        )
    )

    performer_detail_count = sum(
        1
        for event in all_events
        if event.get(
            "performersText"
        )
    )

    open_time_count = sum(
        1
        for event in all_events
        if event.get(
            "openTime"
        )
    )

    new_until_count = sum(
        1
        for event in all_events
        if event.get(
            "newUntil"
        )
    )

    print("")
    print(
        "================================"
    )

    print(
        "現在の公演数:",
        len(
            all_events
        ),
    )

    print(
        "販売状況取得:",
        status_count,
        "件",
    )

    print(
        "販売枠取得公演:",
        ticket_option_event_count,
        "件",
    )

    print(
        "販売枠合計:",
        ticket_option_total,
        "件",
    )

    print(
        "公演代表の販売開始日時:",
        sale_start_count,
        "件",
    )

    print(
        "券種別販売開始日時:",
        ticket_option_sale_start_count,
        "件",
    )

    print(
        "先行販売期間:",
        advance_period_count,
        "件",
    )

    print(
        "先着販売期間:",
        first_come_period_count,
        "件",
    )

    print(
        "出演者詳細取得:",
        performer_detail_count,
        "件",
    )

    print(
        "開場時間取得:",
        open_time_count,
        "件",
    )

    print(
        "48時間NEW:",
        new_until_count,
        "件",
    )

    print(
        "本当の新規公演:",
        len(
            new_events
        ),
    )

    for event in new_events:
        print(
            "NEW:",
            event.get(
                "performerId"
            ),
            event.get(
                "date"
            ),
            event.get(
                "title"
            ),
            event.get(
                "sourceUrl"
            ),
        )

    print(
        "================================"
    )


if __name__ == "__main__":
    main()
