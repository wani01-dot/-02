import calendar
import json
import re
from datetime import datetime, timezone, timedelta, date
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup


PERFORMERS_FILE = "performers.json"
EVENTS_FILE = "events.json"
NEW_EVENTS_FILE = "new_events.json"
NOTIFIED_FILE = "notified_events.json"

FANY_SEARCH_URL = "https://ticket.fany.lol/search/event"
FANY_BASE = "https://ticket.fany.lol"

TIGET_SEARCH_URL = "https://tiget.net/events"
TIGET_BASE = "https://tiget.net"

JST = timezone(
    timedelta(hours=9)
)

FUTURE_DAYS = 365
FANY_PAGE_LIMIT = 10

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) "
        "Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language":
        "ja-JP,ja;q=0.9",
}


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


def make_date(
    year,
    month,
    day
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


def is_today_or_future(
    date_string
):
    try:
        event_date = datetime.strptime(
            date_string,
            "%Y-%m-%d"
        ).date()

        return (
            event_date
            >= today_jst()
        )

    except ValueError:
        return False


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
        + f"({weekday})"
    )


def build_month_ranges():
    start = today_jst()

    final_date = (
        start
        + timedelta(
            days=FUTURE_DAYS
        )
    )

    ranges = []

    current = start

    while current <= final_date:
        last_day = calendar.monthrange(
            current.year,
            current.month
        )[1]

        month_end = date(
            current.year,
            current.month,
            last_day
        )

        if month_end > final_date:
            month_end = final_date

        ranges.append(
            (
                current,
                month_end
            )
        )

        current = (
            month_end
            + timedelta(days=1)
        )

    return ranges


# =========================================================
# イベント識別
# =========================================================

def identity_key(event):
    source_key = (
        source_notification_key(
            event
        )
    )

    if source_key:
        return source_key

    return "|".join([
        event.get(
            "source",
            ""
        ),
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
        normalize_title(
            event.get(
                "title",
                ""
            )
        ),
    ])


def calendar_key(event):
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
        normalize_title(
            event.get(
                "title",
                ""
            )
        ),
    ])


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

FANY_RECEPTION_RE = re.compile(
    r"/reception/\d+/\d+"
)


def is_sales_line(line):
    words = [
        "発売",
        "受付期間",
        "受付中",
        "受付終了",
        "受付前",
        "抽選",
        "先着",
        "FANY ID",
        "プレミアムメンバー",
        "FANYコミュ",
    ]

    return any(
        word in line
        for word in words
    )


def html_to_lines(html):
    soup = BeautifulSoup(
        html,
        "html.parser"
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
    search_url
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
            < len(event_indexes)
        ):
            end_index = event_indexes[
                number + 1
            ]
        else:
            end_index = len(lines)

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

        year, month, day = (
            date_match.groups()
        )

        event_date = make_date(
            year,
            month,
            day
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

        for line in block[:12]:
            match = FANY_START_RE.search(
                line
            )

            if match:
                start_time = (
                    match.group(1)
                )
                break

        venue = ""
        venue_index = None

        for index, line in enumerate(
            block[:20]
        ):
            if re.search(
                r"（[^）]*(?:都|道|府|県)）$",
                line
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
                and "開場"
                    not in candidate
                and "開演"
                    not in candidate
                and candidate != "出演"
            ):
                title = candidate

        if not title:
            title = "公演名不明"

        events.append({
            "performerId":
                performer_id,

            "date":
                event_date,

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
        })

    return events


def find_reception_candidates(html):
    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    result = []
    seen = set()

    for link in soup.find_all(
        "a",
        href=True
    ):
        href = link.get(
            "href",
            ""
        )

        if not FANY_RECEPTION_RE.search(
            href
        ):
            continue

        url = urljoin(
            FANY_BASE,
            href
        )

        if url in seen:
            continue

        seen.add(
            url
        )

        container = link

        selected_lines = []

        for _ in range(10):
            if not container:
                break

            container = (
                container.parent
            )

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
            year, month, day = (
                match.groups()
            )

            event_date = make_date(
                year,
                month,
                day
            )
            break

    for line in lines:
        match = FANY_START_RE.search(
            line
        )

        if match:
            start_time = (
                match.group(1)
            )
            break

    for line in lines:
        if re.search(
            r"（[^）]*(?:都|道|府|県)）$",
            line
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
    html
):
    candidates = [
        candidate_info(
            item
        )
        for item
        in find_reception_candidates(
            html
        )
    ]

    for event in events:
        best = None
        best_score = -1

        for candidate in candidates:
            if (
                candidate["date"]
                != event.get(
                    "date",
                    ""
                )
            ):
                continue

            score = 5

            if (
                candidate["startTime"]
                and
                candidate["startTime"]
                == event.get(
                    "startTime",
                    ""
                )
            ):
                score += 5

            if (
                normalize_venue(
                    candidate["venue"]
                )
                ==
                normalize_venue(
                    event.get(
                        "venue",
                        ""
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


def request_fany_range(
    session,
    performer,
    start_date,
    end_date
):
    params = {
        "keywords":
            performer["name"],

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
        + "?"
        + urlencode(params)
    )

    response = session.get(
        search_url,
        timeout=30
    )

    response.raise_for_status()

    lines = html_to_lines(
        response.text
    )

    events = (
        parse_fany_text_events(
            lines,
            performer,
            search_url
        )
    )

    attach_fany_urls(
        events,
        response.text
    )

    return (
        count_fany_blocks(
            lines
        ),
        events
    )


def scrape_fany_range(
    session,
    performer,
    start_date,
    end_date,
    depth=0
):
    try:
        (
            block_count,
            events
        ) = request_fany_range(
            session,
            performer,
            start_date,
            end_date
        )

    except Exception as error:
        print(
            "FANY取得失敗:",
            error
        )
        return []

    if (
        block_count
        < FANY_PAGE_LIMIT
    ):
        return events

    if start_date >= end_date:
        return events

    total_days = (
        end_date
        - start_date
    ).days

    middle = (
        start_date
        + timedelta(
            days=total_days // 2
        )
    )

    return (
        scrape_fany_range(
            session,
            performer,
            start_date,
            middle,
            depth + 1
        )
        +
        scrape_fany_range(
            session,
            performer,
            middle
            + timedelta(days=1),
            end_date,
            depth + 1
        )
    )


def scrape_fany(
    session,
    performer
):
    print(
        "FANY検索:",
        performer["name"]
    )

    events = []

    for (
        start_date,
        end_date
    ) in build_month_ranges():

        events.extend(
            scrape_fany_range(
                session,
                performer,
                start_date,
                end_date
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

    print(
        "FANY",
        performer["name"],
        len(result),
        "件"
    )

    return result


# =========================================================
# TIGET
# =========================================================

def get_next_value(
    lines,
    label
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
        title
    )

    title = re.sub(
        r"\s+のチケット.*$",
        "",
        title
    )

    return clean(
        title
    )


def get_tiget_title(
    soup,
    search_title
):
    search_title = (
        clean_tiget_title(
            search_title
        )
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
        }
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
        }
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
                    strip=True
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


def scrape_tiget(
    session,
    performer
):
    performer_id = performer[
        "id"
    ]

    performer_name = performer[
        "name"
    ]

    print(
        "TIGET検索:",
        performer_name
    )

    response = session.get(
        TIGET_SEARCH_URL,
        params={
            "q[words]":
                performer_name
        },
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    event_map = {}

    for link in soup.find_all(
        "a",
        href=True
    ):
        href = link.get(
            "href",
            ""
        )

        match = re.match(
            r"^/events/(\d+)",
            href
        )

        if not match:
            continue

        event_url = (
            TIGET_BASE
            + "/events/"
            + match.group(1)
        )

        title = clean(
            link.get_text(
                " ",
                strip=True
            )
        )

        if event_url not in event_map:
            event_map[
                event_url
            ] = title

    events = []

    for (
        event_url,
        search_title
    ) in event_map.items():

        try:
            response = session.get(
                event_url,
                timeout=20
            )

            response.raise_for_status()

        except Exception as error:
            print(
                "TIGET詳細失敗:",
                event_url,
                error
            )
            continue

        detail_soup = BeautifulSoup(
            response.text,
            "html.parser"
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

        if performer_name not in whole_text:
            continue

        date_match = re.search(
            r"(20\d{2})年"
            r"(\d{1,2})月"
            r"(\d{1,2})日",
            whole_text
        )

        if not date_match:
            continue

        year, month, day = (
            date_match.groups()
        )

        event_date = make_date(
            year,
            month,
            day
        )

        if not is_today_or_future(
            event_date
        ):
            continue

        time_match = re.search(
            r"開演\s*[:：]?\s*"
            r"(\d{1,2}:\d{2})",
            whole_text
        )

        start_time = (
            time_match.group(1)
            if time_match
            else ""
        )

        venue = clean(
            get_next_value(
                lines,
                "会場"
            )
        )

        title = get_tiget_title(
            detail_soup,
            search_title
        )

        events.append({
            "performerId":
                performer_id,

            "date":
                event_date,

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
        })

    print(
        "TIGET",
        performer_name,
        len(events),
        "件"
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

        seen.add(
            key
        )

        result.append(
            event
        )

    return result


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
        "URL再通知防止版"
    )

    print(
        "================================"
    )

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

    old_data = load_json(
        EVENTS_FILE,
        {
            "events": []
        }
    )

    if isinstance(
        old_data,
        list
    ):
        old_events = old_data
    else:
        old_events = old_data.get(
            "events",
            []
        )

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
    # 既にevents.jsonにあるものは通知済みにする
    #
    # これが今回の重要な保険。
    # TIGET 518800もここで封印される。
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
                sorted(stable_keys),

            "looseKeys":
                sorted(loose_keys),

            "sourceKeys":
                sorted(source_keys),
        }
    )

    print(
        "既存公演を通知済みに登録:",
        len(old_events),
        "件"
    )

    print(
        "通知済みURL/ID:",
        len(source_keys)
    )

    # =====================================================
    # スクレイピング
    # =====================================================

    session = requests.Session()

    session.headers.update(
        HEADERS
    )

    all_events = []

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
            ]
        )

        if "fany" in sources:
            try:
                all_events.extend(
                    scrape_fany(
                        session,
                        performer
                    )
                )
            except Exception as error:
                print(
                    "FANYエラー:",
                    error
                )

        if "tiget" in sources:
            try:
                all_events.extend(
                    scrape_tiget(
                        session,
                        performer
                    )
                )
            except Exception as error:
                print(
                    "TIGETエラー:",
                    error
                )

    all_events = [
        event
        for event in all_events
        if is_today_or_future(
            event.get(
                "date",
                ""
            )
        )
    ]

    all_events = remove_duplicates(
        all_events
    )

    all_events.sort(
        key=lambda event: (
            event.get(
                "date",
                ""
            ),
            event.get(
                "startTime",
                ""
            ),
            event.get(
                "performerId",
                ""
            ),
        )
    )

    # =====================================================
    # 本当に新しい公演だけ
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

        # 最優先
        # TIGET公演ID / FANY受付ID
        if (
            source_key
            and source_key in source_keys
        ):
            continue

        # 日付＋時間＋会場
        if stable_key in stable_keys:
            continue

        # 日付＋会場＋タイトル
        if loose_key in loose_keys:
            continue

        new_events.append(
            event
        )

    output = {
        "syncedAt":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "performers":
            performers,

        "events":
            all_events,
    }

    save_json(
        EVENTS_FILE,
        output
    )

    save_json(
        NEW_EVENTS_FILE,
        new_events
    )

    print("")
    print(
        "================================"
    )

    print(
        "現在の公演数:",
        len(all_events)
    )

    print(
        "本当の新規公演:",
        len(new_events)
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
            )
        )

    print(
        "================================"
    )


if __name__ == "__main__":
    main()
