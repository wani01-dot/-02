import calendar
import json
import re
from datetime import datetime, timezone, timedelta, date
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup


# =========================================================
# 基本設定
# =========================================================

PERFORMERS_FILE = "performers.json"
EVENTS_FILE = "events.json"
NEW_EVENTS_FILE = "new_events.json"

FANY_URL = "https://ticket.fany.lol/search/event"

TIGET_URL = "https://tiget.net/events"
TIGET_BASE = "https://tiget.net"

JST = timezone(
    timedelta(hours=9)
)

# 今日から何日先まで探すか
FUTURE_DAYS = 365

# FANYで10件出たら
# 「まだ後ろに公演が隠れている可能性あり」と判断
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
# 共通処理
# =========================================================

def clean(text):
    return re.sub(
        r"\s+",
        " ",
        text or ""
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
# FANY用日付文字列
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


def fany_date_string(
    value
):
    weekday = WEEKDAYS_JA[
        value.weekday()
    ]

    return (
        value.strftime(
            "%Y/%m/%d"
        )
        + f"({weekday})"
    )


# =========================================================
# 月ごとの検索範囲を作る
# =========================================================

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

        next_day = (
            month_end
            + timedelta(days=1)
        )

        current = next_day

    return ranges


# =========================================================
# 重複 / 新規判定
# =========================================================

def identity_key(event):
    source = event.get(
        "source",
        ""
    )

    performer_id = event.get(
        "performerId",
        ""
    )

    source_url = event.get(
        "sourceUrl",
        ""
    )

    # TIGETはURLが固有
    if (
        source == "tiget"
        and source_url
    ):
        return "|".join([
            "tiget",
            performer_id,
            source_url,
        ])

    # FANYは検索URLが固有ではないので
    # URLをIDには使わない
    if source == "fany":

        return "|".join([
            "fany",
            performer_id,
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

    return "|".join([
        source,
        performer_id,
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


def fany_loose_key(event):
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
# FANY解析
# =========================================================

FANY_DATE_RE = re.compile(
    r"^(20\d{2})/"
    r"(\d{1,2})/"
    r"(\d{1,2})"
)

FANY_START_RE = re.compile(
    r"開演\s*(\d{1,2}:\d{2})"
)


def get_fany_lines(html):
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


# =========================================================
# FANY公演ブロック数
# =========================================================

def count_fany_blocks(lines):
    count = 0

    for line in lines:
        if FANY_DATE_RE.match(
            line
        ):
            count += 1

    return count


# =========================================================
# FANY公演解析
# =========================================================

def parse_fany_events(
    lines,
    performer,
    source_url
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
            end_index = (
                event_indexes[
                    number + 1
                ]
            )

        else:
            end_index = len(
                lines
            )

        block = lines[
            start_index:end_index
        ]

        if not block:
            continue

        # ----------------------------------
        # 日付
        # ----------------------------------

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

        # ----------------------------------
        # 出演者
        # ----------------------------------

        performer_text = ""

        try:
            performer_index = (
                block.index(
                    "出演"
                )
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

            performer_text = (
                " ".join(parts)
            )

        except ValueError:

            performer_text = (
                " ".join(block)
            )

        if (
            performer_name
            not in performer_text
        ):
            continue

        # ----------------------------------
        # 開演時間
        # ----------------------------------

        start_time = ""

        for line in block[:12]:

            match = (
                FANY_START_RE.search(
                    line
                )
            )

            if match:
                start_time = (
                    match.group(1)
                )
                break

        # ----------------------------------
        # 会場
        # ----------------------------------

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

        # ----------------------------------
        # タイトル
        # ----------------------------------

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
            ):
                title = candidate

        if not title:

            noise = {
                "日",
                "月",
                "火",
                "水",
                "木",
                "金",
                "土",
                ")",
                "出演",
            }

            for line in block[1:12]:

                if line in noise:
                    continue

                if line == venue:
                    continue

                if (
                    "開場" in line
                    or "開演" in line
                ):
                    continue

                if is_sales_line(
                    line
                ):
                    continue

                title = line
                break

        if not title:
            title = (
                "公演名不明"
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
                "fany",

            "sourceUrl":
                source_url,
        })

    return events


# =========================================================
# FANY範囲検索
# =========================================================

def request_fany_range(
    session,
    performer,
    start_date,
    end_date
):
    performer_name = performer[
        "name"
    ]

    params = {
        "keywords":
            performer_name,

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
        FANY_URL
        + "?"
        + urlencode(
            params
        )
    )

    response = session.get(
        search_url,
        timeout=30
    )

    response.raise_for_status()

    lines = get_fany_lines(
        response.text
    )

    block_count = (
        count_fany_blocks(
            lines
        )
    )

    events = parse_fany_events(
        lines,
        performer,
        search_url
    )

    return (
        block_count,
        events
    )


# =========================================================
# FANY自動分割
# =========================================================

def scrape_fany_range(
    session,
    performer,
    start_date,
    end_date,
    depth=0
):
    indent = "  " * depth

    try:

        block_count, events = (
            request_fany_range(
                session,
                performer,
                start_date,
                end_date
            )
        )

    except Exception as error:

        print(
            indent
            + "❌ "
            + str(start_date)
            + "〜"
            + str(end_date)
            + " "
            + str(error)
        )

        return []

    print(
        indent
        + str(start_date)
        + "〜"
        + str(end_date)
        + " 表示="
        + str(block_count)
        + "件"
        + " / 対象="
        + str(len(events))
        + "件"
    )

    # --------------------------------------
    # 10件未満
    # → ページ上限に当たっていないと判断
    # --------------------------------------

    if (
        block_count
        < FANY_PAGE_LIMIT
    ):
        return events

    # --------------------------------------
    # 1日検索ならこれ以上割れない
    # --------------------------------------

    if (
        start_date
        >= end_date
    ):

        print(
            indent
            + "⚠️ 1日で10件表示されています"
        )

        return events

    # --------------------------------------
    # 10件表示された
    # → 上限の可能性があるので半分にする
    # --------------------------------------

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

    right_start = (
        middle
        + timedelta(days=1)
    )

    left = scrape_fany_range(
        session,
        performer,
        start_date,
        middle,
        depth + 1
    )

    right = scrape_fany_range(
        session,
        performer,
        right_start,
        end_date,
        depth + 1
    )

    return (
        left
        + right
    )


# =========================================================
# FANY 全期間
# =========================================================

def scrape_fany(
    session,
    performer
):
    performer_name = performer[
        "name"
    ]

    print("")
    print(
        "FANY月別検索: "
        + performer_name
    )

    all_events = []

    month_ranges = (
        build_month_ranges()
    )

    for (
        start_date,
        end_date
    ) in month_ranges:

        events = scrape_fany_range(
            session,
            performer,
            start_date,
            end_date
        )

        all_events.extend(
            events
        )

    # --------------------------------------
    # 重複削除
    # --------------------------------------

    unique = {}

    for event in all_events:

        key = identity_key(
            event
        )

        unique[key] = event

    result = list(
        unique.values()
    )

    print(
        "FANY "
        + performer_name
        + ": "
        + str(
            len(result)
        )
        + "件"
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

    print("")
    print(
        "TIGET検索: "
        + performer_name
    )

    search_url = (
        TIGET_URL
        + "?"
        + urlencode({
            "q[words]":
                performer_name
        })
    )

    try:

        response = session.get(
            search_url,
            timeout=30
        )

        response.raise_for_status()

    except Exception as error:

        print(
            "TIGET検索失敗: "
            + str(error)
        )

        return []

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    event_urls = []

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

        event_url = urljoin(
            TIGET_BASE,
            "/events/"
            + match.group(1)
        )

        if (
            event_url
            not in event_urls
        ):
            event_urls.append(
                event_url
            )

    print(
        "TIGET候補: "
        + str(
            len(event_urls)
        )
        + "件"
    )

    events = []

    for event_url in event_urls[
        :100
    ]:

        try:

            detail = session.get(
                event_url,
                timeout=20
            )

            detail.raise_for_status()

        except Exception:
            continue

        detail_soup = BeautifulSoup(
            detail.text,
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

        # ----------------------------------
        # 出演者
        # ----------------------------------

        performer_section = ""

        try:

            performer_index = (
                lines.index(
                    "出演者"
                )
            )

            parts = []

            for line in lines[
                performer_index + 1:
            ]:

                if line in [
                    "開催日",
                    "会場",
                    "主催または登録者",
                    "イベントのお問い合わせ",
                ]:
                    break

                parts.append(
                    line
                )

            performer_section = (
                " ".join(parts)
            )

        except ValueError:

            performer_section = (
                whole_text
            )

        if (
            performer_name
            not in performer_section
        ):
            continue

        # ----------------------------------
        # タイトル
        # ----------------------------------

        title = ""

        h1 = detail_soup.find(
            "h1"
        )

        if h1:

            title = clean(
                h1.get_text(
                    " ",
                    strip=True
                )
            )

        if (
            not title
            and detail_soup.title
        ):

            title = clean(
                detail_soup.title
                    .get_text()
            )

            title = re.sub(
                r"\s+のチケット.*$",
                "",
                title
            )

        if not title:
            title = (
                "公演名不明"
            )

        # ----------------------------------
        # 日付
        # ----------------------------------

        date_text = get_next_value(
            lines,
            "開催日"
        )

        date_match = re.search(
            r"(20\d{2})年"
            r"(\d{1,2})月"
            r"(\d{1,2})日",
            date_text
        )

        if not date_match:

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

        # ----------------------------------
        # 開演
        # ----------------------------------

        start_time = ""

        time_match = re.search(
            r"開演\s*"
            r"(\d{1,2}:\d{2})",
            whole_text
        )

        if time_match:

            start_time = (
                time_match.group(1)
            )

        # ----------------------------------
        # 会場
        # ----------------------------------

        venue = get_next_value(
            lines,
            "会場"
        )

        venue = clean(
            venue
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
        "TIGET "
        + performer_name
        + ": "
        + str(
            len(events)
        )
        + "件"
    )

    return events


# =========================================================
# 重複削除
# =========================================================

def remove_exact_duplicates(
    events
):
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


def merge_cross_site(
    events
):
    result = {}

    priority = {
        "fany": 1,
        "tiget": 2,
    }

    for event in events:

        key = calendar_key(
            event
        )

        if key not in result:

            result[key] = event
            continue

        current = result[
            key
        ]

        if (
            priority.get(
                event.get(
                    "source",
                    ""
                ),
                99
            )
            <
            priority.get(
                current.get(
                    "source",
                    ""
                ),
                99
            )
        ):

            result[
                key
            ] = event

    return list(
        result.values()
    )


# =========================================================
# メイン
# =========================================================

def main():

    print(
        "================================"
    )

    print(
        "出演情報取得開始"
    )

    print(
        "FANY月別＋自動分割モード"
    )

    print(
        "今日(JST): "
        + str(
            today_jst()
        )
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

    if not performers:

        print(
            "performers.jsonに"
            "芸人がありません"
        )

        save_json(
            NEW_EVENTS_FILE,
            []
        )

        return


    # =====================================================
    # 旧データ
    # =====================================================

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

    old_events = [
        event
        for event in old_events
        if is_today_or_future(
            event.get(
                "date",
                ""
            )
        )
    ]

    old_identity_keys = {
        identity_key(event)
        for event in old_events
    }

    old_tiget_urls = {
        (
            event.get(
                "performerId",
                ""
            ),
            event.get(
                "sourceUrl",
                ""
            )
        )
        for event in old_events
        if (
            event.get(
                "source"
            ) == "tiget"
            and event.get(
                "sourceUrl"
            )
        )
    }

    old_fany_loose_keys = {
        fany_loose_key(
            event
        )
        for event in old_events
        if (
            event.get(
                "source"
            ) == "fany"
        )
    }


    # =====================================================
    # HTTP
    # =====================================================

    session = requests.Session()

    session.headers.update(
        HEADERS
    )

    all_events = []


    # =====================================================
    # 芸人ごと
    # =====================================================

    for performer in performers:

        performer_id = (
            performer.get(
                "id",
                ""
            )
        )

        performer_name = (
            performer.get(
                "name",
                ""
            )
        )

        if (
            not performer_id
            or not performer_name
        ):
            continue

        print("")
        print(
            "################################"
        )

        print(
            performer_name
        )

        print(
            "################################"
        )

        sources = performer.get(
            "sources",
            [
                "fany",
                "tiget",
            ]
        )

        # FANY
        if "fany" in sources:

            try:

                events = scrape_fany(
                    session,
                    performer
                )

                all_events.extend(
                    events
                )

            except Exception as error:

                print(
                    "FANYエラー: "
                    + str(error)
                )

        # TIGET
        if "tiget" in sources:

            try:

                events = scrape_tiget(
                    session,
                    performer
                )

                all_events.extend(
                    events
                )

            except Exception as error:

                print(
                    "TIGETエラー: "
                    + str(error)
                )


    # =====================================================
    # 今日以降のみ
    # =====================================================

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


    # =====================================================
    # 重複整理
    # =====================================================

    all_events = (
        remove_exact_duplicates(
            all_events
        )
    )

    all_events = (
        merge_cross_site(
            all_events
        )
    )


    # =====================================================
    # 並び替え
    # =====================================================

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
            event.get(
                "title",
                ""
            ),
        )
    )


    # =====================================================
    # 新規判定
    # =====================================================

    new_events = []

    for event in all_events:

        identity = identity_key(
            event
        )

        if (
            identity
            in old_identity_keys
        ):
            continue


        # TIGET
        if (
            event.get(
                "source"
            ) == "tiget"
        ):

            key = (
                event.get(
                    "performerId",
                    ""
                ),
                event.get(
                    "sourceUrl",
                    ""
                )
            )

            if (
                key
                in old_tiget_urls
            ):
                continue


        # FANY
        if (
            event.get(
                "source"
            ) == "fany"
        ):

            loose_key = (
                fany_loose_key(
                    event
                )
            )

            if (
                loose_key
                in old_fany_loose_keys
            ):
                continue


        new_events.append(
            event
        )


    # =====================================================
    # 保存
    # =====================================================

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


    # =====================================================
    # ログ
    # =====================================================

    print("")
    print(
        "================================"
    )

    print(
        "今日以降の全公演数: "
        + str(
            len(all_events)
        )
        + "件"
    )

    print(
        "新規公演数: "
        + str(
            len(new_events)
        )
        + "件"
    )


    for performer in performers:

        performer_id = (
            performer.get(
                "id",
                ""
            )
        )

        performer_name = (
            performer.get(
                "name",
                performer_id
            )
        )

        count = sum(
            1
            for event
            in all_events
            if (
                event.get(
                    "performerId"
                )
                ==
                performer_id
            )
        )

        print(
            performer_name
            + ": "
            + str(count)
            + "件"
        )


    if new_events:

        print("")
        print(
            "=== 新規公演 ==="
        )

        for event in new_events:

            performer_name = next(
                (
                    performer.get(
                        "name",
                        ""
                    )
                    for performer
                    in performers
                    if (
                        performer.get(
                            "id"
                        )
                        ==
                        event.get(
                            "performerId"
                        )
                    )
                ),
                event.get(
                    "performerId",
                    ""
                )
            )

            print(
                performer_name
                + " | "
                + event.get(
                    "date",
                    ""
                )
                + " | "
                + event.get(
                    "startTime",
                    ""
                )
                + " | "
                + event.get(
                    "title",
                    ""
                )
                + " | "
                + event.get(
                    "venue",
                    ""
                )
                + " | "
                + event.get(
                    "source",
                    ""
                )
            )


    print(
        "================================"
    )


# =========================================================
# 実行
# =========================================================

if __name__ == "__main__":
    main()
