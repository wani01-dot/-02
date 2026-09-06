import json
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


EPLUS_BASE = "https://eplus.jp"

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
        value = clean(value)

        if not value:
            continue

        if value in seen:
            continue

        seen.add(value)
        result.append(value)

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

        line = clean(raw)

        if line:
            lines.append(
                line
            )

    return lines


# =========================================================
# 日時
# =========================================================

DATETIME_RE = re.compile(
    r"(20\d{2})"
    r"[/-]"
    r"(\d{1,2})"
    r"[/-]"
    r"(\d{1,2})"
    r"(?:\s*[（(][^）)]*[）)])?"
    r"[^\d]{0,20}"
    r"(\d{1,2})"
    r":"
    r"(\d{2})"
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

    for match in DATETIME_RE.finditer(
        text
    ):
        value = make_datetime_iso(
            *match.groups()
        )

        if (
            value
            and value not in result
        ):
            result.append(
                value
            )

    return result


# =========================================================
# イープラス販売種別
# =========================================================

def get_sale_category(label):
    label = clean(
        label
    )

    # 抽選は必ず先行扱い
    if "抽選" in label:
        return "advance"

    # 「先着先行」も先行販売として扱う
    if "先行" in label:
        return "advance"

    # 一般発売など
    if (
        "先着" in label
        or
        "一般発売" in label
        or
        "一般販売" in label
        or
        "発売" in label
    ):
        return "first_come"

    return ""


def clean_sale_label(label):
    label = clean(
        label
    )

    label = re.sub(
        r"^先着[★☆]?",
        "",
        label,
    )

    label = re.sub(
        r"^抽選[★☆]?",
        "",
        label,
    )

    return clean(
        label
    )


def normalize_eplus_status(text):
    text = clean(
        text
    )

    if (
        "残りわずか"
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
        "完売"
        in text
    ):
        return "予定数終了"

    if (
        "受付中"
        in text
        or
        "販売中"
        in text
    ):
        return "販売中"

    if (
        "受付終了"
        in text
        or
        "販売終了"
        in text
    ):
        return "販売終了"

    if (
        "受付前"
        in text
        or
        "販売前"
        in text
    ):
        return "販売前"

    return ""


def is_sale_heading(line):
    text = clean(
        line
    )

    if not text:
        return False

    if text.startswith(
        "先着"
    ):
        return True

    if text.startswith(
        "抽選"
    ):
        return True

    return False


# =========================================================
# 販売受付解析
# =========================================================

def parse_sale_period_from_block(
    label,
    block,
):
    category = get_sale_category(
        label
    )

    if not category:
        return None

    text = " ".join(
        block
    )

    datetimes = extract_datetimes(
        text
    )

    if not datetimes:
        return None

    start_at = datetimes[0]

    end_at = (
        datetimes[1]
        if len(datetimes) >= 2
        else ""
    )

    return {
        "category":
            category,

        "label":
            clean_sale_label(
                label
            ),

        "startAt":
            start_at,

        "endAt":
            end_at,
    }


def parse_eplus_sale_options(
    lines,
):
    headings = []

    for index, line in enumerate(
        lines
    ):
        if is_sale_heading(
            line
        ):
            headings.append(
                index
            )

    options = []
    periods = []
    seen = set()

    for number, start_index in enumerate(
        headings
    ):
        if (
            number + 1
            <
            len(headings)
        ):
            end_index = headings[
                number + 1
            ]

        else:
            end_index = min(
                len(lines),
                start_index + 15,
            )

        block = lines[
            start_index:end_index
        ]

        if not block:
            continue

        label = clean(
            block[0]
        )

        # イープラス上部の検索フィルター
        # 「先着」等を誤取得しないため、
        # 受付期間があるブロックだけ対象にする
        if not any(
            "受付期間"
            in line
            for line in block
        ):
            continue

        period = (
            parse_sale_period_from_block(
                label,
                block,
            )
        )

        if not period:
            continue

        status = ""

        for line in block[
            1:
        ]:
            candidate = (
                normalize_eplus_status(
                    line
                )
            )

            if candidate:
                status = candidate
                break

        key = (
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

        if key in seen:
            continue

        seen.add(
            key
        )

        periods.append(
            dict(
                period
            )
        )

        option_type = (
            "抽選"
            if period[
                "category"
            ]
            ==
            "advance"
            and
            "抽選"
            in label
            else
            "先着"
        )

        options.append({
            "name":
                period[
                    "label"
                ]
                or
                label,

            "type":
                option_type,

            "status":
                status,

            "price":
                "",

            "saleStartAt":
                period[
                    "startAt"
                ],

            "saleEndAt":
                period[
                    "endAt"
                ],

            "saleCategory":
                period[
                    "category"
                ],

            "saleLabel":
                period[
                    "label"
                ],

            "salePeriods":
                [
                    dict(
                        period
                    )
                ],
        })

    return (
        options,
        periods,
    )


# =========================================================
# 販売状況集約
# =========================================================

def summarize_ticket_status(
    options,
):
    statuses = [
        option.get(
            "status",
            "",
        )
        for option
        in options
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

    active = {
        "販売中",
    }

    ended = {
        "予定数終了",
        "販売終了",
    }

    has_active = any(
        status in active
        for status in statuses
    )

    has_ended = any(
        status in ended
        for status in statuses
    )

    if (
        has_active
        and has_ended
    ):
        return "一部予定数終了"

    if all(
        status in ended
        for status in statuses
    ):
        if (
            "予定数終了"
            in statuses
        ):
            return "予定数終了"

        return "販売終了"

    if has_active:
        return "販売中"

    if (
        statuses
        and all(
            status
            ==
            "販売前"
            for status
            in statuses
        )
    ):
        return "販売前"

    return ""


# =========================================================
# JSON-LD
# =========================================================

def walk_json(value):
    if isinstance(
        value,
        dict,
    ):
        yield value

        for child in value.values():
            yield from walk_json(
                child
            )

    elif isinstance(
        value,
        list,
    ):
        for child in value:
            yield from walk_json(
                child
            )


def get_jsonld_events(
    soup,
):
    events = []

    for script in soup.find_all(
        "script",
        attrs={
            "type":
                "application/ld+json"
        },
    ):
        raw = script.string

        if not raw:
            raw = script.get_text(
                " ",
                strip=True,
            )

        if not raw:
            continue

        try:
            data = json.loads(
                raw
            )

        except Exception:
            continue

        for item in walk_json(
            data
        ):
            item_type = item.get(
                "@type",
                ""
            )

            if (
                item_type
                ==
                "Event"
                or
                (
                    isinstance(
                        item_type,
                        list,
                    )
                    and
                    "Event"
                    in item_type
                )
            ):
                events.append(
                    item
                )

    return events


def normalize_detail_url(url):
    return clean(
        str(
            url
            or ""
        )
    ).split(
        "#",
        1,
    )[0]


def choose_jsonld_event(
    soup,
    detail_url,
):
    items = get_jsonld_events(
        soup
    )

    if not items:
        return None

    normalized_url = (
        normalize_detail_url(
            detail_url
        )
    )

    for item in items:
        item_url = (
            normalize_detail_url(
                item.get(
                    "url",
                    ""
                )
            )
        )

        if (
            item_url
            and
            (
                item_url
                ==
                normalized_url
                or
                item_url in normalized_url
                or
                normalized_url in item_url
            )
        ):
            return item

    return items[0]


# =========================================================
# 詳細URL
# =========================================================

EPLUS_DETAIL_RE = re.compile(
    r"https?://"
    r"(?:www\.)?"
    r"eplus\.jp"
    r"/sf/detail/"
    r"[^\"'<>\s]+"
)


def get_eplus_detail_urls(
    html,
):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    result = []
    seen = set()

    # 通常のaタグ
    for link in soup.find_all(
        "a",
        href=True,
    ):
        href = clean(
            link.get(
                "href",
                ""
            )
        )

        if (
            "/sf/detail/"
            not in href
        ):
            continue

        url = urljoin(
            EPLUS_BASE,
            href,
        )

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

    # JSON-LDやJavaScript内のURLも拾う
    for match in EPLUS_DETAIL_RE.finditer(
        html
    ):
        url = match.group(
            0
        )

        url = (
            url
            .replace(
                "\\/",
                "/",
            )
            .split(
                "#",
                1,
            )[0]
        )

        if url in seen:
            continue

        seen.add(
            url
        )

        result.append(
            url
        )

    # JSON-LD
    for item in get_jsonld_events(
        soup
    ):
        url = clean(
            item.get(
                "url",
                ""
            )
        )

        if not url:
            continue

        if (
            "/sf/detail/"
            not in url
        ):
            continue

        url = urljoin(
            EPLUS_BASE,
            url,
        )

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
# 公演基本情報
# =========================================================

def parse_iso_start_date(
    value,
):
    value = clean(
        value
    )

    if not value:
        return (
            "",
            "",
        )

    match = re.match(
        r"(20\d{2})-"
        r"(\d{2})-"
        r"(\d{2})"
        r"(?:T"
        r"(\d{2}):"
        r"(\d{2})"
        r")?",
        value,
    )

    if not match:
        return (
            "",
            "",
        )

    (
        year,
        month,
        day,
        hour,
        minute,
    ) = match.groups()

    event_date = make_date(
        year,
        month,
        day,
    )

    start_time = ""

    if (
        hour is not None
        and
        minute is not None
    ):
        start_time = (
            f"{hour}:{minute}"
        )

    return (
        event_date,
        start_time,
    )


def get_event_date_from_text(
    text,
):
    match = re.search(
        r"(20\d{2})"
        r"\s*/\s*"
        r"(\d{1,2})"
        r"\s*/\s*"
        r"(\d{1,2})",
        text,
    )

    if not match:
        return ""

    return make_date(
        *match.groups()
    )


def get_start_time_from_text(
    text,
):
    match = re.search(
        r"開演"
        r"\s*[：:]?\s*"
        r"(\d{1,2}:\d{2})",
        text,
    )

    if not match:
        return ""

    return match.group(
        1
    )


def get_open_time_from_text(
    text,
):
    match = re.search(
        r"開場"
        r"\s*[：:]?\s*"
        r"(\d{1,2}:\d{2})",
        text,
    )

    if not match:
        return ""

    return match.group(
        1
    )


def get_location_from_jsonld(
    item,
):
    if not item:
        return ""

    location = item.get(
        "location",
        {}
    )

    if isinstance(
        location,
        list,
    ):
        location = (
            location[0]
            if location
            else {}
        )

    if not isinstance(
        location,
        dict,
    ):
        return clean(
            location
        )

    name = clean(
        location.get(
            "name",
            ""
        )
    )

    address = location.get(
        "address",
        {}
    )

    region = ""

    if isinstance(
        address,
        dict,
    ):
        region = clean(
            address.get(
                "addressRegion",
                ""
            )
        )

    if (
        name
        and region
    ):
        return (
            f"{name}（{region}）"
        )

    return name


# =========================================================
# タイトル
# =========================================================

def clean_eplus_title(
    title,
):
    title = clean(
        title
    )

    title = re.sub(
        r"\s*[-｜|]\s*イープラス.*$",
        "",
        title,
    )

    title = re.sub(
        r"のチケット情報.*$",
        "",
        title,
    )

    return clean(
        title
    )


def get_eplus_title(
    soup,
    json_event,
):
    if json_event:
        title = clean(
            json_event.get(
                "name",
                ""
            )
        )

        if title:
            return title

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
        title = clean_eplus_title(
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
        title = clean_eplus_title(
            h1.get_text(
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

def get_eplus_performers(
    lines,
):
    result = []

    stop_words = [
        "次へ",
        "受付期間",
        "受付中",
        "受付前",
        "受付終了",
        "予定枚数終了",
        "予定数終了",
        "チケット一覧",
        "ご注意",
        "公演日",
        "会場",
        "料金",
    ]

    for index, line in enumerate(
        lines
    ):
        if clean(
            line
        ) != "出演":
            continue

        for candidate in lines[
            index + 1:
            index + 8
        ]:
            candidate = clean(
                candidate
            )

            if not candidate:
                continue

            if is_sale_heading(
                candidate
            ):
                break

            if any(
                word == candidate
                or candidate.startswith(
                    word
                )
                for word
                in stop_words
            ):
                break

            if len(
                candidate
            ) > 150:
                continue

            parts = re.split(
                r"[／/、,，]+",
                candidate,
            )

            for part in parts:
                part = clean(
                    part
                )

                if part:
                    result.append(
                        part
                    )

    return unique_strings(
        result
    )


# =========================================================
# 公演詳細取得
# =========================================================

def scrape_eplus_detail(
    session,
    performer,
    detail_url,
):
    response = session.get(
        detail_url,
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

    json_event = choose_jsonld_event(
        soup,
        detail_url,
    )

    event_date = ""
    start_time = ""

    if json_event:
        (
            event_date,
            start_time,
        ) = parse_iso_start_date(
            json_event.get(
                "startDate",
                ""
            )
        )

    if not event_date:
        event_date = (
            get_event_date_from_text(
                whole_text
            )
        )

    if not start_time:
        start_time = (
            get_start_time_from_text(
                whole_text
            )
        )

    if not event_date:
        return None

    if not is_today_or_future(
        event_date
    ):
        return None

    open_time = (
        get_open_time_from_text(
            whole_text
        )
    )

    title = get_eplus_title(
        soup,
        json_event,
    )

    venue = get_location_from_jsonld(
        json_event
    )

    if not venue:
        # 最後の保険
        match = re.search(
            r"([^\n]{2,100})"
            r"（"
            r"(東京都|北海道|大阪府|京都府|"
            r".{2,4}県)"
            r"）"
            r"\s*開演",
            whole_text,
        )

        if match:
            venue = (
                clean(
                    match.group(
                        1
                    )
                )
                +
                "（"
                +
                clean(
                    match.group(
                        2
                    )
                )
                +
                "）"
            )

    (
        ticket_options,
        sale_periods,
    ) = parse_eplus_sale_options(
        lines
    )

    primary_sale = None

    first_come = [
        period
        for period in sale_periods
        if period.get(
            "category"
        )
        ==
        "first_come"
    ]

    if first_come:
        primary_sale = sorted(
            first_come,
            key=lambda item:
                item.get(
                    "startAt",
                    ""
                ),
        )[0]

    elif sale_periods:
        primary_sale = sorted(
            sale_periods,
            key=lambda item:
                item.get(
                    "startAt",
                    ""
                ),
        )[0]

    performers_text = (
        get_eplus_performers(
            lines
        )
    )

    performer_name = clean(
        performer.get(
            "name",
            ""
        )
    )

    # 人物ページ由来なので原則対象。
    # 出演者欄が取得できた場合は
    # 念のため対象芸人を確認する。
    if (
        performers_text
        and
        performer_name
        and
        not any(
            performer_name
            in value
            for value
            in performers_text
        )
    ):
        # ページによって出演欄が受付単位で
        # 分断されることがあるため、
        # ページ全文にもいなければ除外
        if (
            performer_name
            not in whole_text
        ):
            return None

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
            "eplus",

        "sourceUrl":
            detail_url,

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
# メイン
# =========================================================

def scrape_eplus(
    session,
    performer,
):
    performer_name = performer.get(
        "name",
        ""
    )

    print(
        "イープラス検索:",
        performer_name,
    )

    source_urls = performer.get(
        "sourceUrls",
        {},
    )

    word_url = source_urls.get(
        "eplus",
        "",
    )

    if not word_url:
        print(
            "イープラスURL未設定:",
            performer_name,
        )

        return []

    try:
        response = session.get(
            word_url,
            timeout=30,
        )

        response.raise_for_status()

    except Exception as error:
        print(
            "イープラス人物ページ取得失敗:",
            word_url,
            error,
        )

        return []

    detail_urls = (
        get_eplus_detail_urls(
            response.text
        )
    )

    print(
        "イープラス詳細候補:",
        performer_name,
        len(
            detail_urls
        ),
        "件",
    )

    events = []
    seen = set()

    for detail_url in detail_urls:
        try:
            event = (
                scrape_eplus_detail(
                    session,
                    performer,
                    detail_url,
                )
            )

        except Exception as error:
            print(
                "イープラス詳細取得失敗:",
                detail_url,
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
        "イープラス",
        performer_name,
        len(
            events
        ),
        "件",
    )

    return events
