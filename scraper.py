import json
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup


# ==========================================
# 設定
# ==========================================

PERFORMERS_FILE = "performers.json"
EVENTS_FILE = "events.json"
NEW_EVENTS_FILE = "new_events.json"

FANY_URL = "https://ticket.fany.lol/search/event"

TIGET_URL = "https://tiget.net/events"
TIGET_BASE = "https://tiget.net"

JST = timezone(
    timedelta(hours=9)
)

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


# ==========================================
# JSON
# ==========================================

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


# ==========================================
# 共通
# ==========================================

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
    text = clean(
        text
    ).lower()

    text = text.replace(
        " ",
        ""
    )

    text = text.replace(
        "　",
        ""
    )

    return text


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


# ==========================================
# 今日
# ==========================================

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


# ==========================================
# 新規判定キー
# ==========================================

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


    # TIGET
    if (
        source == "tiget"
        and source_url
    ):
        return "|".join([
            "tiget",
            performer_id,
            source_url
        ])


    # FANY
    if source == "fany":

        date = event.get(
            "date",
            ""
        )

        venue = normalize_venue(
            event.get(
                "venue",
                ""
            )
        )

        start_time = event.get(
            "startTime",
            ""
        )

        if start_time:

            return "|".join([
                "fany",
                performer_id,
                date,
                venue,
                start_time
            ])

        return "|".join([
            "fany",
            performer_id,
            date,
            venue
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


# ==========================================
# FANY再通知防止
# ==========================================

def fany_loose_key(
    event
):

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
        )
    ])


# ==========================================
# カレンダー重複判定
# ==========================================

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


# ==========================================
# FANY
# ==========================================

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


def is_sales_line(
    line
):

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
    ]

    return any(
        word in line
        for word in words
    )


def scrape_fany(
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
        f"FANY検索: {performer_name}"
    )


    search_url = (
        FANY_URL
        + "?"
        + urlencode({
            "keywords":
                performer_name,
            "search_type":
                "search_string"
        })
    )


    response = session.get(
        search_url,
        timeout=30
    )

    response.raise_for_status()


    lines = get_fany_lines(
        response.text
    )


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


    print(
        "FANY公演候補: "
        f"{len(event_indexes)}件"
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


        date = make_date(
            year,
            month,
            day
        )


        # 過去公演はここで除外
        if not is_today_or_future(
            date
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

            performer_parts = []


            for line in block[
                performer_index + 1:
            ]:

                if is_sales_line(
                    line
                ):
                    break

                performer_parts.append(
                    line
                )


            performer_text = (
                " ".join(
                    performer_parts
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
        # 開演時間
        # ----------------------------------

        start_time = ""


        for line in block[
            :10
        ]:

            start_match = (
                FANY_START_RE.search(
                    line
                )
            )

            if start_match:

                start_time = (
                    start_match.group(1)
                )

                break


        # ----------------------------------
        # 会場
        # ----------------------------------

        venue = ""

        venue_index = None


        for index, line in enumerate(
            block[:15]
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
                and "開場" not in candidate
                and "開演" not in candidate
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


            for line in block[
                1:10
            ]:

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
                date,

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


    print(
        f"FANY {performer_name}: "
        f"{len(events)}件"
    )


    return events


# ==========================================
# TIGET
# ==========================================

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


    print(
        f"TIGET検索: {performer_name}"
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
            f"TIGET検索失敗: {error}"
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
            f"/events/{match.group(1)}"
        )


        if (
            event_url
            not in event_urls
        ):

            event_urls.append(
                event_url
            )


    print(
        "TIGET公演候補: "
        f"{len(event_urls)}件"
    )


    events = []


    for event_url in event_urls[
        :50
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


        if not title:

            if detail_soup.title:

                title = clean(
                    detail_soup.title.get_text()
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


        date = make_date(
            year,
            month,
            day
        )


        # 過去公演は除外
        if not is_today_or_future(
            date
        ):
            continue


        # ----------------------------------
        # 開演時間
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
                date,

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
        f"TIGET {performer_name}: "
        f"{len(events)}件"
    )


    return events


# ==========================================
# 重複削除
# ==========================================

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


# ==========================================
# メイン
# ==========================================

def main():

    print(
        "============================"
    )

    print(
        "出演情報取得開始"
    )

    print(
        "今日以降のみ保存"
    )

    print(
        "今日(JST): "
        f"{today_jst()}"
    )

    print(
        "============================"
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
            "芸人が登録されていません"
        )

        save_json(
            NEW_EVENTS_FILE,
            []
        )

        return


    # ======================================
    # 旧データ
    # ======================================

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


    # 過去データは比較対象からも除外
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
        for event
        in old_events
        if (
            event.get(
                "source"
            ) == "fany"
        )
    }


    # ======================================
    # HTTP
    # ======================================

    session = requests.Session()

    session.headers.update(
        HEADERS
    )


    all_events = []


    # ======================================
    # 芸人ごと
    # ======================================

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
            f"--- {performer_name} ---"
        )


        sources = performer.get(
            "sources",
            [
                "fany",
                "tiget"
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
                    f"{error}"
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
                    f"{error}"
                )


    # ======================================
    # 念のため未来だけ
    # ======================================

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


    # ======================================
    # 重複
    # ======================================

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


    # ======================================
    # 並び替え
    # ======================================

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
            )
        )
    )


    # ======================================
    # 新規判定
    # ======================================

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


    # ======================================
    # 保存
    # ======================================

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


    # ======================================
    # ログ
    # ======================================

    print("")
    print(
        "============================"
    )

    print(
        f"今日以降の全公演数: "
        f"{len(all_events)}件"
    )

    print(
        f"新規公演数: "
        f"{len(new_events)}件"
    )


    for performer in performers:

        performer_id = performer.get(
            "id",
            ""
        )

        performer_name = performer.get(
            "name",
            performer_id
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
            f"{performer_name}: "
            f"{count}件"
        )


    if new_events:

        print("")
        print(
            "=== 新規公演 ==="
        )


        for event in new_events:

            performer_name = next(
                (
                    p.get(
                        "name",
                        ""
                    )
                    for p
                    in performers
                    if (
                        p.get(
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
                f"{performer_name}"
                f" | "
                f"{event.get('date', '')}"
                f" | "
                f"{event.get('startTime', '')}"
                f" | "
                f"{event.get('title', '')}"
                f" | "
                f"{event.get('venue', '')}"
                f" | "
                f"{event.get('source', '')}"
            )


    print(
        "============================"
    )


# ==========================================
# 実行
# ==========================================

if __name__ == "__main__":
    main()
