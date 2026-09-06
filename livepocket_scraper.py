import json
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


LIVEPOCKET_BASE = "https://livepocket.jp"

JST = timezone(
    timedelta(hours=9)
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


def make_date(
    year,
    month,
    day,
):
    try:
        return (
            f"{int(year):04d}-"
            f"{int(month):02d}-"
            f"{int(day):02d}"
        )
    except Exception:
        return ""


def today_jst():
    return datetime.now(
        JST
    ).date()


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

    except Exception:
        return False


def unique_strings(values):
    result = []
    seen = set()

    for value in values:
        value = clean(
            value
        )

        if not value:
            continue

        if value in seen:
            continue

        seen.add(
            value
        )

        result.append(
            value
        )

    return result


def html_to_lines(html):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    lines = []

    for raw in soup.get_text(
        "\n"
    ).splitlines():

        line = clean(
            raw
        )

        if line:
            lines.append(
                line
            )

    return lines


# =========================================================
# 日時
# =========================================================

FULL_DATETIME_RE = re.compile(
    r"(20\d{2})年"
    r"\s*(\d{1,2})月"
    r"\s*(\d{1,2})日"
    r"(?:\s*[（(][^）)]*[）)])?"
    r"\s*"
    r"(\d{1,2}):(\d{2})"
)


def make_datetime_iso(
    year,
    month,
    day,
    hour,
    minute,
):
    try:
        value = datetime(
            int(year),
            int(month),
            int(day),
            int(hour),
            int(minute),
            tzinfo=JST,
        )

        return value.isoformat()

    except Exception:
        return ""


def extract_datetimes(text):
    text = clean(
        text
    )

    result = []

    for match in FULL_DATETIME_RE.finditer(
        text
    ):
        value = make_datetime_iso(
            *match.groups()
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
# 販売種別
# =========================================================

def detect_sale_category(text):
    text = clean(
        text
    )

    if (
        "抽選"
        in text
        or
        "先行"
        in text
    ):
        return "advance"

    if (
        "先着"
        in text
        or
        "一般販売"
        in text
        or
        "一般発売"
        in text
        or
        "販売受付"
        in text
    ):
        return "first_come"

    return ""


def clean_sale_label(text):
    text = clean(
        text
    )

    text = re.sub(
        r"^(先着|抽選)\s*",
        "",
        text,
    )

    return clean(
        text
    )


# =========================================================
# 販売状態
# =========================================================

def normalize_ticket_status(text):
    text = clean(
        text
    )

    if (
        "売切間近"
        in text
        or
        "残りわずか"
        in text
        or
        "残席わずか"
        in text
    ):
        return "残りわずか"

    if (
        "予定枚数終了"
        in text
        or
        "予定数終了"
        in text
        or
        "売切"
        in text
        or
        "完売"
        in text
    ):
        return "予定数終了"

    if (
        "販売中"
        in text
        or
        "受付中"
        in text
    ):
        return "販売中"

    if (
        "販売終了"
        in text
        or
        "受付終了"
        in text
    ):
        return "販売終了"

    if (
        "販売前"
        in text
        or
        "受付前"
        in text
    ):
        return "販売前"

    return ""


def summarize_ticket_status(
    options,
):
    statuses = [
        option.get(
            "status",
            "",
        )
        for option in options
        if option.get(
            "status"
        )
    ]

    if not statuses:
        return ""

    if (
        "残りわずか"
        in statuses
    ):
        return "残りわずか"

    ended = {
        "予定数終了",
        "販売終了",
    }

    active = {
        "販売中",
        "残りわずか",
    }

    has_ended = any(
        status in ended
        for status in statuses
    )

    has_active = any(
        status in active
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
            status in ended
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

    if all(
        status == "販売前"
        for status in statuses
    ):
        return "販売前"

    return ""


# =========================================================
# 価格
# =========================================================

PRICE_RE = re.compile(
    r"[￥¥]\s*[\d,]+"
)


def extract_price(text):
    match = PRICE_RE.search(
        clean(
            text
        )
    )

    if not match:
        return ""

    return clean(
        match.group(0)
    )


# =========================================================
# 検索結果からイベントURL抽出
# =========================================================

LIVEPOCKET_EVENT_RE = re.compile(
    r"^/e/[A-Za-z0-9_\-]+"
)


def get_livepocket_event_urls(
    html,
):
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
        href = clean(
            link.get(
                "href",
                "",
            )
        )

        if not LIVEPOCKET_EVENT_RE.match(
            href
        ):
            continue

        url = urljoin(
            LIVEPOCKET_BASE,
            href,
        )

        url = url.split(
            "?",
            1,
        )[0]

        url = url.split(
            "#",
            1,
        )[0]

        if url in seen:
            continue

        seen.add(
            url
        )

        result.append(
            url
        )

    return result


# =========================================================
# 基本情報
# =========================================================

def get_next_value(
    lines,
    labels,
):
    if isinstance(
        labels,
        str,
    ):
        labels = [
            labels
        ]

    for index, line in enumerate(
        lines
    ):
        if line not in labels:
            continue

        for candidate in lines[
            index + 1:
            index + 5
        ]:
            candidate = clean(
                candidate
            )

            if candidate:
                return candidate

    return ""


def get_event_date(
    lines,
    whole_text,
):
    value = get_next_value(
        lines,
        "開催日",
    )

    match = re.search(
        r"(20\d{2})年"
        r"\s*(\d{1,2})月"
        r"\s*(\d{1,2})日",
        value,
    )

    if not match:
        match = re.search(
            r"(20\d{2})年"
            r"\s*(\d{1,2})月"
            r"\s*(\d{1,2})日",
            whole_text,
        )

    if not match:
        return ""

    return make_date(
        *match.groups()
    )


def get_event_time(
    lines,
    labels,
):
    value = get_next_value(
        lines,
        labels,
    )

    match = re.search(
        r"(\d{1,2}:\d{2})",
        value,
    )

    if match:
        return match.group(
            1
        )

    for index, line in enumerate(
        lines
    ):
        if line not in labels:
            continue

        block = " ".join(
            lines[
                index:
                index + 5
            ]
        )

        match = re.search(
            r"(\d{1,2}:\d{2})",
            block,
        )

        if match:
            return match.group(
                1
            )

    return ""


def get_livepocket_venue(
    lines,
):
    value = get_next_value(
        lines,
        "会場",
    )

    if not value:
        return ""

    value = re.sub(
        r"\s*〒\d{3}-\d{4}.*$",
        "",
        value,
    )

    return clean(
        value
    )


# =========================================================
# タイトル
# =========================================================

def clean_livepocket_title(
    text,
):
    text = clean(
        text
    )

    text = re.sub(
        r"のチケット情報"
        r"[｜|].*$",
        "",
        text,
    )

    text = re.sub(
        r"\s*[｜|]\s*"
        r"LivePocket.*$",
        "",
        text,
        flags=re.I,
    )

    return clean(
        text
    )


def get_livepocket_title(
    soup,
):
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
        title = clean_livepocket_title(
            og.get(
                "content"
            )
        )

        if title:
            return title

    h1 = soup.find(
        "h1"
    )

    if h1:
        title = clean_livepocket_title(
            h1.get_text(
                " ",
                strip=True,
            )
        )

        if title:
            return title

    if soup.title:
        title = clean_livepocket_title(
            soup.title.get_text(
                " ",
                strip=True,
            )
        )

        if title:
            return title

    return "公演名不明"


# =========================================================
# 出演者
# =========================================================

def get_livepocket_performers(
    lines,
):
    performers = []

    start_index = None

    for index, line in enumerate(
        lines
    ):
        if line == "出演者":
            start_index = (
                index + 1
            )
            break

    if start_index is None:
        return []

    stop_words = [
        "販売元",
        "概要",
        "詳細",
        "会場",
        "受付・チケット情報",
        "お問い合わせ",
        "入場方法",
    ]

    for line in lines[
        start_index:
    ]:
        text = clean(
            line
        )

        if not text:
            continue

        if (
            text in stop_words
            or any(
                text.startswith(
                    word
                )
                for word in stop_words
            )
        ):
            break

        if len(
            text
        ) > 120:
            continue

        parts = re.split(
            r"[／/、,，]+",
            text,
        )

        for part in parts:
            part = clean(
                part
            )

            if part:
                performers.append(
                    part
                )

    return unique_strings(
        performers
    )


# =========================================================
# 販売受付ブロック
# =========================================================

def is_sale_heading(
    line,
):
    text = clean(
        line
    )

    if text.startswith(
        "先着 "
    ):
        return True

    if text.startswith(
        "抽選 "
    ):
        return True

    if text in [
        "先着",
        "抽選",
    ]:
        return True

    return False


def find_sale_blocks(
    lines,
):
    indexes = [
        index
        for index, line in enumerate(
            lines
        )
        if is_sale_heading(
            line
        )
    ]

    blocks = []

    for number, start in enumerate(
        indexes
    ):
        if (
            number + 1
            <
            len(indexes)
        ):
            end = indexes[
                number + 1
            ]

        else:
            end = len(
                lines
            )

        block = lines[
            start:end
        ]

        if not any(
            "販売受付期間"
            in line
            for line in block
        ):
            continue

        blocks.append(
            block
        )

    return blocks


# =========================================================
# 券種抽出
# =========================================================

def is_ticket_name_candidate(
    line,
):
    text = clean(
        line
    )

    if not text:
        return False

    if len(text) > 100:
        return False

    if normalize_ticket_status(
        text
    ):
        return False

    if extract_price(
        text
    ):
        return False

    bad_words = [
        "販売受付期間",
        "支払い方法",
        "クレジットカード",
        "コンビニ決済",
        "LivePocketあと払い",
        "チケット購入後",
        "続きを見る",
        "閉じる",
        "ログイン",
        "新規会員登録",
        "販売終了",
        "販売中",
        "受付終了",
        "受付中",
    ]

    if any(
        word in text
        for word in bad_words
    ):
        return False

    return True


def parse_ticket_options_from_block(
    block,
    period,
):
    options = []
    seen = set()

    for index, line in enumerate(
        block
    ):
        status = normalize_ticket_status(
            line
        )

        if not status:
            continue

        if status not in [
            "販売中",
            "販売終了",
            "予定数終了",
            "残りわずか",
            "販売前",
        ]:
            continue

        name = ""

        for back in range(
            index - 1,
            max(
                -1,
                index - 5,
            ),
            -1,
        ):
            candidate = clean(
                block[
                    back
                ]
            )

            if is_ticket_name_candidate(
                candidate
            ):
                name = candidate
                break

        price = ""

        for forward in range(
            index + 1,
            min(
                len(block),
                index + 5,
            ),
        ):
            candidate_price = extract_price(
                block[
                    forward
                ]
            )

            if candidate_price:
                price = candidate_price
                break

        if not name:
            continue

        key = (
            name,
            status,
            price,
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        options.append({
            "name":
                name,

            "type":
                (
                    "抽選"
                    if period.get(
                        "category"
                    )
                    ==
                    "advance"
                    and
                    "抽選"
                    in period.get(
                        "label",
                        ""
                    )
                    else
                    "先着"
                ),

            "status":
                status,

            "price":
                price,

            "saleStartAt":
                period.get(
                    "startAt",
                    ""
                ),

            "saleEndAt":
                period.get(
                    "endAt",
                    ""
                ),

            "saleCategory":
                period.get(
                    "category",
                    ""
                ),

            "saleLabel":
                period.get(
                    "label",
                    ""
                ),

            "salePeriods":
                [
                    dict(
                        period
                    )
                ],
        })

    return options


# =========================================================
# 販売期間解析
# =========================================================

def parse_livepocket_sales(
    lines,
):
    all_options = []
    all_periods = []
    period_seen = set()
    option_seen = set()

    for block in find_sale_blocks(
        lines
    ):
        if not block:
            continue

        heading = clean(
            block[0]
        )

        category = detect_sale_category(
            heading
        )

        if not category:
            continue

        text = " ".join(
            block
        )

        datetimes = extract_datetimes(
            text
        )

        if not datetimes:
            continue

        start_at = datetimes[0]

        end_at = (
            datetimes[1]
            if len(
                datetimes
            )
            >=
            2
            else ""
        )

        period = {
            "category":
                category,

            "label":
                clean_sale_label(
                    heading
                ),

            "startAt":
                start_at,

            "endAt":
                end_at,
        }

        period_key = (
            period[
                "category"
            ],
            period[
                "label"
            ],
            period[
                "startAt"
            ],
            period[
                "endAt"
            ],
        )

        if (
            period_key
            not in period_seen
        ):
            period_seen.add(
                period_key
            )

            all_periods.append(
                dict(
                    period
                )
            )

        options = (
            parse_ticket_options_from_block(
                block,
                period,
            )
        )

        for option in options:
            option_key = (
                option.get(
                    "name",
                    ""
                ),
                option.get(
                    "type",
                    ""
                ),
                option.get(
                    "status",
                    ""
                ),
                option.get(
                    "price",
                    ""
                ),
                option.get(
                    "saleStartAt",
                    ""
                ),
            )

            if option_key in option_seen:
                continue

            option_seen.add(
                option_key
            )

            all_options.append(
                option
            )

    return (
        all_options,
        all_periods,
    )


# =========================================================
# 代表販売期間
# =========================================================

def choose_primary_period(
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
# 詳細ページ
# =========================================================

def scrape_livepocket_detail(
    session,
    performer,
    event_url,
):
    response = session.get(
        event_url,
        timeout=25,
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    lines = html_to_lines(
        response.text
    )

    whole_text = " ".join(
        lines
    )

    performer_name = clean(
        performer.get(
            "name",
            ""
        )
    )

    if (
        performer_name
        and performer_name
        not in whole_text
    ):
        return None

    event_date = get_event_date(
        lines,
        whole_text,
    )

    if not event_date:
        return None

    if not is_today_or_future(
        event_date
    ):
        return None

    start_time = get_event_time(
        lines,
        [
            "開演日時",
            "開演時間",
        ],
    )

    open_time = get_event_time(
        lines,
        [
            "開場日時",
            "開場時間",
        ],
    )

    title = get_livepocket_title(
        soup
    )

    venue = get_livepocket_venue(
        lines
    )

    performers_text = (
        get_livepocket_performers(
            lines
        )
    )

    (
        ticket_options,
        sale_periods,
    ) = parse_livepocket_sales(
        lines
    )

    primary_sale = (
        choose_primary_period(
            sale_periods
        )
    )

    return {
        "performerId":
            performer.get(
                "id",
                ""
            ),

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
            "livepocket",

        "sourceUrl":
            event_url,

        "ticketStatus":
            summarize_ticket_status(
                ticket_options
            ),

        "ticketOptions":
            ticket_options,

        "saleStartAt":
            (
                primary_sale.get(
                    "startAt",
                    ""
                )
                if primary_sale
                else ""
            ),

        "saleEndAt":
            (
                primary_sale.get(
                    "endAt",
                    ""
                )
                if primary_sale
                else ""
            ),

        "saleCategory":
            (
                primary_sale.get(
                    "category",
                    ""
                )
                if primary_sale
                else ""
            ),

        "salePeriods":
            sale_periods,

        "performersText":
            performers_text,
    }


# =========================================================
# MAIN
# =========================================================

def scrape_livepocket(
    session,
    performer,
):
    performer_name = performer.get(
        "name",
        ""
    )

    print(
        "LivePocket検索:",
        performer_name,
    )

    source_urls = performer.get(
        "sourceUrls",
        {},
    )

    search_url = source_urls.get(
        "livepocket",
        "",
    )

    if not search_url:
        print(
            "LivePocket URL未設定:",
            performer_name,
        )

        return []

    try:
        response = session.get(
            search_url,
            timeout=30,
        )

        response.raise_for_status()

    except Exception as error:
        print(
            "LivePocket検索ページ取得失敗:",
            search_url,
            error,
        )

        return []

    event_urls = (
        get_livepocket_event_urls(
            response.text
        )
    )

    print(
        "LivePocket詳細候補:",
        performer_name,
        len(
            event_urls
        ),
        "件",
    )

    events = []
    seen = set()

    for event_url in event_urls:
        try:
            event = (
                scrape_livepocket_detail(
                    session,
                    performer,
                    event_url,
                )
            )

        except Exception as error:
            print(
                "LivePocket詳細取得失敗:",
                event_url,
                error,
            )

            continue

        if not event:
            continue

        key = "|".join([
            event.get(
                "date",
                ""
            ),
            event.get(
                "startTime",
                ""
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

        if key in seen:
            continue

        seen.add(
            key
        )

        events.append(
            event
        )

    print(
        "LivePocket",
        performer_name,
        len(
            events
        ),
        "件",
    )

    return events
