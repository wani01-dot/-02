import json
import re
from datetime import datetime, timezone, timedelta

from playwright.sync_api import sync_playwright


PERFORMERS_FILE = "performers.json"
OUTPUT_FILE = "theater_events.json"

JST = timezone(
    timedelta(hours=9)
)


THEATERS = [
    {
        "id": "roppongi",
        "name": "六本木",
        "venue": "よしもと六本木シアター",
        "url": "https://roppongi.yoshimoto.co.jp/schedule/",
    },
    {
        "id": "jimbocho",
        "name": "神保町",
        "venue": "神保町よしもと漫才劇場",
        "url": "https://jimbocho-manzaigekijyo.yoshimoto.co.jp/schedule/",
    },
    {
        "id": "shibuya",
        "name": "渋谷",
        "venue": "渋谷よしもと漫才劇場",
        "url": "https://shibuya-manzaigekijyo.yoshimoto.co.jp/schedule/",
    },
    {
        "id": "morinomiya",
        "name": "森ノ宮",
        "venue": "森ノ宮よしもと漫才劇場",
        "url": "https://morinomiya-manzaigekijyo.yoshimoto.co.jp/schedule/",
    },
    {
        "id": "manzaigekijyo",
        "name": "よしもと漫才劇場",
        "venue": "よしもと漫才劇場",
        "url": "https://manzaigekijyo.yoshimoto.co.jp/schedule/",
    },
    {
        "id": "makuhari",
        "name": "幕張",
        "venue": "よしもと幕張イオンモール劇場",
        "url": "https://makuhari.yoshimoto.co.jp/schedule/",
    },
    {
        "id": "dotonbori",
        "name": "道頓堀",
        "venue": "Yogibo META VALLEY",
        "url": "https://dotonbori.yoshimoto.co.jp/schedule/",
    },
    {
        "id": "omiya",
        "name": "大宮",
        "venue": "大宮ラクーンよしもと劇場",
        "url": "https://omiya.yoshimoto.co.jp/schedule/",
    },
    {
        "id": "fukuoka",
        "name": "福岡",
        "venue": "よしもと福岡 大和証券劇場",
        "url": "https://fukuokagekijyo.yoshimoto.co.jp/schedule/",
    },
    {
        "id": "ngk",
        "name": "なんばグランド花月",
        "venue": "なんばグランド花月",
        "url": "https://ngk.yoshimoto.co.jp/schedule/",
    },
]


# =========================================================
# JSON
# =========================================================

def load_json(
    path,
    default,
):
    try:
        with open(
            path,
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(
                file
            )

    except (
        FileNotFoundError,
        json.JSONDecodeError,
    ):
        return default


def save_json(
    path,
    data,
):
    with open(
        path,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            data,
            file,
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


def now_iso():
    return datetime.now(
        timezone.utc
    ).isoformat()


def today_jst():
    return datetime.now(
        JST
    ).date()


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


# =========================================================
# 月
# =========================================================

MONTH_RE = re.compile(
    r"^(1[0-2]|[1-9])月$"
)


def get_month_number(label):
    match = MONTH_RE.fullmatch(
        clean(
            label
        )
    )

    if not match:
        return None

    return int(
        match.group(1)
    )


def infer_year(month):
    today = today_jst()

    current_month = (
        today.month
    )

    year = today.year

    # 例:
    # 2026年12月に
    # 1月・2月が表示された場合は2027年
    if (
        month < current_month
        and
        (
            current_month
            -
            month
        )
        >= 6
    ):
        year += 1

    return year


def find_month_labels(page):
    labels = []

    locator = page.locator(
        "a, button, [role='button'], li, div, span"
    )

    try:
        count = locator.count()

    except Exception:
        return []

    for index in range(
        min(
            count,
            3000,
        )
    ):
        item = locator.nth(
            index
        )

        try:
            text = clean(
                item.inner_text(
                    timeout=200
                )
            )

        except Exception:
            continue

        if MONTH_RE.fullmatch(
            text
        ):
            labels.append(
                text
            )

    return unique_strings(
        labels
    )


def click_month(
    page,
    label,
):
    selectors = [
        "a",
        "button",
        "[role='button']",
        "li",
        "div",
        "span",
    ]

    for selector in selectors:
        locator = page.locator(
            selector
        )

        try:
            count = locator.count()

        except Exception:
            continue

        for index in range(
            min(
                count,
                2000,
            )
        ):
            item = locator.nth(
                index
            )

            try:
                text = clean(
                    item.inner_text(
                        timeout=150
                    )
                )

            except Exception:
                continue

            if text != label:
                continue

            try:
                item.scroll_into_view_if_needed(
                    timeout=1000
                )

                item.click(
                    timeout=2500,
                    force=True,
                )

                page.wait_for_timeout(
                    1600
                )

                return True

            except Exception:
                continue

    return False


# =========================================================
# 公演解析
# =========================================================

DAY_RE = re.compile(
    r"^(3[01]|[12]\d|[1-9])$"
)

WEEKDAY_RE = re.compile(
    r"^[月火水木金土日]$"
)

TIME_LINE_RE = re.compile(
    r"開場\s*"
    r"(\d{1,2}:\d{2})"
    r".*?"
    r"開演\s*"
    r"(\d{1,2}:\d{2})"
)

START_ONLY_RE = re.compile(
    r"開演\s*"
    r"(\d{1,2}:\d{2})"
)


def body_to_lines(text):
    result = []

    for raw in str(
        text or ""
    ).splitlines():

        line = clean(
            raw
        )

        if line:
            result.append(
                line
            )

    return result


def is_day_header(
    lines,
    index,
):
    if (
        index
        >=
        len(lines)
    ):
        return False

    if not DAY_RE.fullmatch(
        lines[index]
    ):
        return False

    if (
        index + 1
        <
        len(lines)
        and
        WEEKDAY_RE.fullmatch(
            lines[
                index + 1
            ]
        )
    ):
        return True

    return False


def split_day_blocks(lines):
    indexes = []

    for index in range(
        len(lines)
    ):
        if is_day_header(
            lines,
            index,
        ):
            indexes.append(
                index
            )

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

        day = int(
            lines[start]
        )

        block_lines = lines[
            start + 2:end
        ]

        blocks.append({
            "day":
                day,

            "lines":
                block_lines,
        })

    return blocks


def find_time_line(line):
    match = TIME_LINE_RE.search(
        line
    )

    if match:
        return {
            "openTime":
                match.group(1),

            "startTime":
                match.group(2),
        }

    match = START_ONLY_RE.search(
        line
    )

    if match:
        return {
            "openTime":
                "",

            "startTime":
                match.group(1),
        }

    return None


def is_noise_line(line):
    text = clean(
        line
    )

    noise = [
        "SCHEDULE",
        "スケジュール",
        "チケット",
        "トップ",
        "お知らせ",
        "劇場案内",
        "PAGE TOP",
        "前売券が完売した際には",
    ]

    if any(
        word in text
        for word in noise
    ):
        return True

    if MONTH_RE.fullmatch(
        text
    ):
        return True

    return False


def parse_events_from_day_block(
    theater,
    year,
    month,
    day,
    lines,
    performers,
):
    events = []

    time_indexes = []

    for index, line in enumerate(
        lines
    ):
        time_info = find_time_line(
            line
        )

        if time_info:
            time_indexes.append(
                index
            )

    for number, time_index in enumerate(
        time_indexes
    ):
        time_line = lines[
            time_index
        ]

        time_info = find_time_line(
            time_line
        )

        if not time_info:
            continue

        # タイトルは基本的に
        # 開場・開演行の直前
        title = ""

        for back in range(
            time_index - 1,
            max(
                -1,
                time_index - 5,
            ),
            -1,
        ):
            candidate = clean(
                lines[
                    back
                ]
            )

            if not candidate:
                continue

            if is_noise_line(
                candidate
            ):
                continue

            if find_time_line(
                candidate
            ):
                continue

            title = candidate
            break

        if not title:
            continue

        if (
            number + 1
            <
            len(time_indexes)
        ):
            next_time_index = (
                time_indexes[
                    number + 1
                ]
            )

        else:
            next_time_index = len(
                lines
            )

        detail_lines = lines[
            time_index + 1:
            next_time_index
        ]

        # 次公演タイトルが
        # detail_lines末尾に混ざることがあるので
        # 次の開演行直前の1行は除外
        if (
            number + 1
            <
            len(time_indexes)
            and
            detail_lines
        ):
            possible_next_title = clean(
                detail_lines[-1]
            )

            if (
                possible_next_title
                and
                not any(
                    performer.get(
                        "name",
                        ""
                    )
                    in possible_next_title
                    for performer in performers
                )
            ):
                detail_lines = (
                    detail_lines[:-1]
                )

        performers_text = unique_strings(
            detail_lines
        )

        whole_detail = " ".join(
            [
                title,
                time_line,
            ]
            +
            detail_lines
        )

        matched_performers = []

        for performer in performers:
            performer_name = clean(
                performer.get(
                    "name",
                    ""
                )
            )

            if not performer_name:
                continue

            if (
                performer_name
                in whole_detail
            ):
                matched_performers.append(
                    performer
                )

        if not matched_performers:
            continue

        event_date = make_date(
            year,
            month,
            day,
        )

        # 過去公演は保存しない
        try:
            event_date_value = (
                datetime.strptime(
                    event_date,
                    "%Y-%m-%d",
                ).date()
            )

            if (
                event_date_value
                <
                today_jst()
            ):
                continue

        except Exception:
            continue

        for performer in matched_performers:
            event = {
                "performerId":
                    performer.get(
                        "id",
                        ""
                    ),

                "date":
                    event_date,

                "openTime":
                    time_info.get(
                        "openTime",
                        ""
                    ),

                "startTime":
                    time_info.get(
                        "startTime",
                        ""
                    ),

                "title":
                    title,

                "venue":
                    theater.get(
                        "venue",
                        theater.get(
                            "name",
                            "",
                        ),
                    ),

                "source":
                    "theater",

                "sourceUrl":
                    theater.get(
                        "url",
                        ""
                    ),

                "theaterId":
                    theater.get(
                        "id",
                        ""
                    ),

                "theaterName":
                    theater.get(
                        "name",
                        ""
                    ),

                "ticketStatus":
                    "",

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
                    performers_text,

                "publishedVia":
                    "theater",
            }

            event[
                "theaterSourceKey"
            ] = make_theater_source_key(
                event
            )

            events.append(
                event
            )

    return events


# =========================================================
# 劇場公開キー
# =========================================================

def make_theater_source_key(
    event,
):
    return "|".join([
        "theater",
        clean(
            event.get(
                "theaterId",
                ""
            )
        ),
        clean(
            event.get(
                "performerId",
                ""
            )
        ),
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
        normalize_title(
            event.get(
                "title",
                ""
            )
        ),
    ])


# =========================================================
# 1劇場
# =========================================================

def scrape_theater(
    browser,
    theater,
    performers,
):
    print("")
    print(
        "================================"
    )

    print(
        "劇場:",
        theater[
            "name"
        ],
    )

    context = browser.new_context(
        locale="ja-JP",
        timezone_id="Asia/Tokyo",
        user_agent=(
            "Mozilla/5.0 "
            "(iPhone; CPU iPhone OS 18_0 like Mac OS X) "
            "AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) "
            "Version/18.0 Mobile/15E148 Safari/604.1"
        ),
        viewport={
            "width": 390,
            "height": 844,
        },
    )

    page = context.new_page()

    events = []

    try:
        page.goto(
            theater[
                "url"
            ],
            wait_until="domcontentloaded",
            timeout=45000,
        )

        page.wait_for_timeout(
            4000
        )

        month_labels = (
            find_month_labels(
                page
            )
        )

        print(
            "月候補:",
            month_labels,
        )

        # 月タブが見つからない場合でも
        # 現在表示分だけ確認
        if not month_labels:
            body_text = page.locator(
                "body"
            ).inner_text(
                timeout=10000
            )

            lines = body_to_lines(
                body_text
            )

            current_month = (
                today_jst().month
            )

            current_year = (
                today_jst().year
            )

            for day_block in split_day_blocks(
                lines
            ):
                events.extend(
                    parse_events_from_day_block(
                        theater,
                        current_year,
                        current_month,
                        day_block[
                            "day"
                        ],
                        day_block[
                            "lines"
                        ],
                        performers,
                    )
                )

            return events

        for month_label in month_labels:
            month = get_month_number(
                month_label
            )

            if not month:
                continue

            year = infer_year(
                month
            )

            print(
                "確認:",
                f"{year}年{month}月",
            )

            clicked = click_month(
                page,
                month_label,
            )

            if not clicked:
                print(
                    "月タブクリック失敗:",
                    month_label,
                )

            page.wait_for_timeout(
                1200
            )

            try:
                body_text = page.locator(
                    "body"
                ).inner_text(
                    timeout=10000
                )

            except Exception:
                body_text = ""

            lines = body_to_lines(
                body_text
            )

            day_blocks = split_day_blocks(
                lines
            )

            before_count = len(
                events
            )

            for day_block in day_blocks:
                events.extend(
                    parse_events_from_day_block(
                        theater,
                        year,
                        month,
                        day_block[
                            "day"
                        ],
                        day_block[
                            "lines"
                        ],
                        performers,
                    )
                )

            added_count = (
                len(events)
                -
                before_count
            )

            print(
                "対象公演:",
                added_count,
                "件",
            )

    except Exception as error:
        print(
            "劇場取得失敗:",
            theater[
                "name"
            ],
            error,
        )

    finally:
        context.close()

    return events


# =========================================================
# 重複整理
# =========================================================

def remove_duplicates(events):
    result = []
    seen = set()

    for event in events:
        key = event.get(
            "theaterSourceKey",
            ""
        )

        if not key:
            key = "|".join([
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
                event.get(
                    "theaterId",
                    ""
                ),
            ])

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
        "劇場公式スケジュール取得開始"
    )

    print(
        "10劇場 / 選択可能月すべて"
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

    performers = [
        performer
        for performer
        in performers
        if performer.get(
            "name"
        )
    ]

    print(
        "対象芸人:",
        " / ".join(
            performer.get(
                "name",
                ""
            )
            for performer
            in performers
        ),
    )

    all_events = []

    with sync_playwright() as playwright:
        browser = (
            playwright.chromium.launch(
                headless=True
            )
        )

        try:
            for theater in THEATERS:
                theater_events = (
                    scrape_theater(
                        browser,
                        theater,
                        performers,
                    )
                )

                print(
                    "劇場取得結果:",
                    theater[
                        "name"
                    ],
                    len(
                        theater_events
                    ),
                    "件",
                )

                all_events.extend(
                    theater_events
                )

        finally:
            browser.close()

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
                "theaterId",
                ""
            ),
            event.get(
                "performerId",
                ""
            ),
        )
    )

    output = {
        "syncedAt":
            now_iso(),

        "events":
            all_events,
    }

    save_json(
        OUTPUT_FILE,
        output,
    )

    print("")
    print(
        "================================"
    )

    print(
        "劇場公式公演:",
        len(
            all_events
        ),
        "件",
    )

    for event in all_events:
        print(
            "THEATER:",
            event.get(
                "theaterName"
            ),
            event.get(
                "performerId"
            ),
            event.get(
                "date"
            ),
            event.get(
                "startTime"
            ),
            event.get(
                "title"
            ),
        )

    print(
        "保存:",
        OUTPUT_FILE,
    )

    print(
        "================================"
    )


if __name__ == "__main__":
    main()
