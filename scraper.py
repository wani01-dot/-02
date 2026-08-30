import calendar
import json
import re
from datetime import datetime, timezone, timedelta, date
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup


# =========================================================
# 設定
# =========================================================

PERFORMERS_FILE = "performers.json"
EVENTS_FILE = "events.json"
NEW_EVENTS_FILE = "new_events.json"

FANY_SEARCH_URL = "https://ticket.fany.lol/search/event"
FANY_BASE = "https://ticket.fany.lol"

TIGET_SEARCH_URL = "https://tiget.net/events"
TIGET_BASE = "https://tiget.net"

JST = timezone(
    timedelta(hours=9)
)

# 今日から1年先まで
FUTURE_DAYS = 365

# FANYが10件表示されたら
# 期間を細かく分割する
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

        event_date = (
            datetime.strptime(
                date_string,
                "%Y-%m-%d"
            ).date()
        )

        return (
            event_date
            >= today_jst()
        )

    except ValueError:

        return False


# =========================================================
# FANY用日付
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
        +
        f"({weekday})"
    )


# =========================================================
# 月ごとの範囲
# =========================================================

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

    while (
        current
        <= final_date
    ):

        last_day = (
            calendar.monthrange(
                current.year,
                current.month
            )[1]
        )

        month_end = date(
            current.year,
            current.month,
            last_day
        )

        if (
            month_end
            > final_date
        ):

            month_end = (
                final_date
            )

        ranges.append(
            (
                current,
                month_end
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
# 判定キー
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

    # TIGETはイベントURLが固有
    if (
        source == "tiget"
        and event.get(
            "sourceUrl"
        )
    ):

        return "|".join([
            "tiget",
            performer_id,
            event.get(
                "sourceUrl",
                ""
            ),
        ])

    # FANYは受付URLが変わる可能性があるので
    # URLではなく公演情報で判定
    if (
        source == "fany"
    ):

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
            normalize_title(
                event.get(
                    "title",
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
# FANY基本
# =========================================================

FANY_DATE_RE = re.compile(
    r"^(20\d{2})/"
    r"(\d{1,2})/"
    r"(\d{1,2})"
)

FANY_START_RE = re.compile(
    r"開演\s*"
    r"(\d{1,2}:\d{2})"
)

FANY_RECEPTION_RE = re.compile(
    r"/reception/"
    r"\d+/"
    r"\d+"
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


# =========================================================
# FANY通常テキスト解析
#
# これは今までちゃんと公演を取得できた方式。
# 個別URLが取れなくても、この処理で公演は残す。
# =========================================================

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

        date_match = (
            FANY_DATE_RE.match(
                block[0]
            )
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
                " ".join(
                    parts
                )
            )

        except ValueError:

            performer_text = (
                " ".join(
                    block
                )
            )

        if (
            performer_name
            not in performer_text
        ):

            continue

        # ----------------------------------
        # 開演
        # ----------------------------------

        start_time = ""

        for line in block[
            :12
        ]:

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
                r"（[^）]*"
                r"(?:都|道|府|県)"
                r"）$",
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
                and candidate != "出演"
            ):

                title = candidate

        # 保険
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

            for line in block[
                1:12
            ]:

                if line in noise:
                    continue

                if line == venue:
                    continue

                if (
                    "開場" in line
                    or
                    "開演" in line
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

            # 最初は検索URL
            # あとで個別受付URLが見つかったら差し替える
            "sourceUrl":
                search_url,
        })

    return events


# =========================================================
# FANY受付リンク取得
# =========================================================

def find_reception_candidates(
    html
):

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

        link_text = clean(
            link.get_text(
                " ",
                strip=True
            )
        )

        # ----------------------------------
        # このリンクが属する公演カードを探す
        # ----------------------------------

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

            # 日付行がちょうど1つ含まれる
            # 小さい公演コンテナを採用
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

                selected_lines = (
                    lines
                )

                break

        if not selected_lines:
            continue

        result.append({
            "url":
                url,

            "linkText":
                link_text,

            "lines":
                selected_lines,
        })

    return result


# =========================================================
# FANYリンク候補を公演情報に変換
# =========================================================

def reception_candidate_info(
    candidate
):

    lines = candidate[
        "lines"
    ]

    date_value = ""

    start_time = ""

    title = ""

    venue = ""

    venue_index = None

    # 日付
    for line in lines:

        match = (
            FANY_DATE_RE.match(
                line
            )
        )

        if match:

            year, month, day = (
                match.groups()
            )

            date_value = (
                make_date(
                    year,
                    month,
                    day
                )
            )

            break

    # 開演
    for line in lines:

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

    # 会場
    for index, line in enumerate(
        lines
    ):

        if re.search(
            r"（[^）]*"
            r"(?:都|道|府|県)"
            r"）$",
            line
        ):

            venue = line

            venue_index = index

            break

    # タイトル
    if (
        venue_index is not None
        and venue_index > 0
    ):

        candidate_title = clean(
            lines[
                venue_index - 1
            ]
        )

        if (
            candidate_title
            and candidate_title != ")"
            and "開演"
                not in candidate_title
            and "開場"
                not in candidate_title
        ):

            title = (
                candidate_title
            )

    return {
        "date":
            date_value,

        "startTime":
            start_time,

        "title":
            title,

        "venue":
            venue,

        "url":
            candidate[
                "url"
            ],

        "linkText":
            candidate.get(
                "linkText",
                ""
            ),
    }


# =========================================================
# 公演と受付URLを紐付け
# =========================================================

def attach_fany_reception_urls(
    events,
    html
):

    candidates = (
        find_reception_candidates(
            html
        )
    )

    infos = [
        reception_candidate_info(
            candidate
        )
        for candidate
        in candidates
    ]

    success = 0

    for event in events:

        best = None

        best_score = -1

        for info in infos:

            score = 0

            # 日付一致
            if (
                info["date"]
                ==
                event.get(
                    "date",
                    ""
                )
            ):

                score += 5

            else:

                continue

            # 時間一致
            if (
                info["startTime"]
                and
                info["startTime"]
                ==
                event.get(
                    "startTime",
                    ""
                )
            ):

                score += 5

            # 会場一致
            if (
                normalize_venue(
                    info["venue"]
                )
                and
                normalize_venue(
                    info["venue"]
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

            # タイトル一致
            if (
                normalize_title(
                    info["title"]
                )
                and
                normalize_title(
                    info["title"]
                )
                ==
                normalize_title(
                    event.get(
                        "title",
                        ""
                    )
                )
            ):

                score += 5

            # 「一般発売」を少し優先
            if (
                "一般発売"
                in info.get(
                    "linkText",
                    ""
                )
            ):

                score += 1

            if (
                score
                > best_score
            ):

                best_score = score

                best = info

        # 日付一致だけでは弱いので
        # ある程度一致したものだけ採用
        if (
            best
            and best_score >= 9
        ):

            event[
                "sourceUrl"
            ] = best[
                "url"
            ]

            success += 1

    return success


# =========================================================
# FANY範囲取得
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
        FANY_SEARCH_URL
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

    html = response.text

    lines = html_to_lines(
        html
    )

    block_count = (
        count_fany_blocks(
            lines
        )
    )

    # 公演本体はテキスト方式で取得
    events = (
        parse_fany_text_events(
            lines,
            performer,
            search_url
        )
    )

    # 個別受付URLだけ後付け
    reception_success = (
        attach_fany_reception_urls(
            events,
            html
        )
    )

    return (
        block_count,
        events,
        reception_success
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

    indent = (
        "  " * depth
    )

    try:

        (
            block_count,
            events,
            reception_success
        ) = request_fany_range(
            session,
            performer,
            start_date,
            end_date
        )

    except Exception as error:

        print(
            indent
            +
            "FANY取得失敗 "
            +
            str(start_date)
            +
            "〜"
            +
            str(end_date)
            +
            ": "
            +
            str(error)
        )

        return []

    print(
        indent
        +
        str(start_date)
        +
        "〜"
        +
        str(end_date)
        +
        " 表示="
        +
        str(block_count)
        +
        "件"
        +
        " / 対象="
        +
        str(len(events))
        +
        "件"
        +
        " / 個別URL="
        +
        str(reception_success)
        +
        "件"
    )

    # 10件未満なら上限ではない
    if (
        block_count
        < FANY_PAGE_LIMIT
    ):

        return events

    # 1日ならもう分割できない
    if (
        start_date
        >= end_date
    ):

        return events

    days = (
        end_date
        -
        start_date
    ).days

    middle = (
        start_date
        +
        timedelta(
            days=days // 2
        )
    )

    right_start = (
        middle
        +
        timedelta(
            days=1
        )
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
        +
        right
    )


# =========================================================
# FANY全期間
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
        "FANY検索: "
        +
        performer_name
    )

    all_events = []

    for (
        start_date,
        end_date
    ) in build_month_ranges():

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

        # 同じ公演なら
        # 個別reception URLを持っている方を優先
        if (
            key
            in unique
        ):

            current = unique[
                key
            ]

            current_url = (
                current.get(
                    "sourceUrl",
                    ""
                )
            )

            new_url = (
                event.get(
                    "sourceUrl",
                    ""
                )
            )

            if (
                "/reception/"
                not in current_url
                and
                "/reception/"
                in new_url
            ):

                unique[
                    key
                ] = event

        else:

            unique[
                key
            ] = event

    result = list(
        unique.values()
    )

    print(
        "FANY "
        +
        performer_name
        +
        ": "
        +
        str(
            len(result)
        )
        +
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
        +
        performer_name
    )

    search_url = (
        TIGET_SEARCH_URL
        +
        "?"
        +
        urlencode({
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
            +
            str(error)
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
            +
            match.group(1)
        )

        if (
            event_url
            not in event_urls
        ):

            event_urls.append(
                event_url
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

        whole_text = (
            " ".join(
                lines
            )
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
                " ".join(
                    parts
                )
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
        +
        performer_name
        +
        ": "
        +
        str(
            len(events)
        )
        +
        "件"
    )

    return events


# =========================================================
# 重複整理
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

        if (
            key
            not in result
        ):

            result[
                key
            ] = event

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
        "FANY公演維持＋個別URL対応版"
    )

    print(
        "今日(JST): "
        +
        str(
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
        for event
        in old_events
        if is_today_or_future(
            event.get(
                "date",
                ""
            )
        )
    ]

    old_identity_keys = {
        identity_key(
            event
        )
        for event
        in old_events
    }

    old_fany_loose_keys = {
        fany_loose_key(
            event
        )
        for event
        in old_events
        if (
            event.get(
                "source"
            )
            == "fany"
        )
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
        for event
        in old_events
        if (
            event.get(
                "source"
            )
            == "tiget"
            and
            event.get(
                "sourceUrl"
            )
        )
    }

    # =====================================================
    # HTTP
    # =====================================================

    session = (
        requests.Session()
    )

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
            or
            not performer_name
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
        if (
            "fany"
            in sources
        ):

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
                    +
                    str(error)
                )

        # TIGET
        if (
            "tiget"
            in sources
        ):

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
                    +
                    str(error)
                )

    # =====================================================
    # 今日以降
    # =====================================================

    all_events = [
        event
        for event
        in all_events
        if is_today_or_future(
            event.get(
                "date",
                ""
            )
        )
    ]

    # =====================================================
    # 重複
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

        # ---------------------------------
        # FANY
        # 個別URLへ変わっただけなら通知しない
        # ---------------------------------

        if (
            event.get(
                "source"
            )
            == "fany"
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

        # ---------------------------------
        # TIGET
        # ---------------------------------

        if (
            event.get(
                "source"
            )
            == "tiget"
        ):

            tiget_key = (
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
                tiget_key
                in old_tiget_urls
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
        +
        str(
            len(all_events)
        )
        +
        "件"
    )

    print(
        "新規公演数: "
        +
        str(
            len(new_events)
        )
        +
        "件"
    )

    for performer in performers:

        pid = performer.get(
            "id",
            ""
        )

        name = performer.get(
            "name",
            pid
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
                pid
            )
        )

        print(
            name
            +
            ": "
            +
            str(count)
            +
            "件"
        )

    # =====================================================
    # FANYリンク状況
    # =====================================================

    fany_events = [
        event
        for event
        in all_events
        if (
            event.get(
                "source"
            )
            == "fany"
        )
    ]

    reception_count = sum(
        1
        for event
        in fany_events
        if (
            "/reception/"
            in event.get(
                "sourceUrl",
                ""
            )
        )
    )

    fallback_count = (
        len(fany_events)
        -
        reception_count
    )

    print("")
    print(
        "FANY個別URL成功: "
        +
        str(
            reception_count
        )
        +
        "件"
    )

    print(
        "FANY検索URL代用: "
        +
        str(
            fallback_count
        )
        +
        "件"
    )

    print(
        "================================"
    )


# =========================================================
# 実行
# =========================================================

if __name__ == "__main__":
    main()
