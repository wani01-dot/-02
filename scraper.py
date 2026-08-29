import json
import re
from datetime import datetime, timezone
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
# 共通処理
# ==========================================

def clean(text):
    return re.sub(
        r"\s+",
        " ",
        text or ""
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
        "〖",
        "〗",
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
# 新規判定用キー
# ==========================================

def identity_key(event):
    """
    TIGETはURLがイベントごとに固有なので
    URLを優先。

    FANY検索URLは芸人ごとに同じなので
    日付・時間・タイトルで判定。
    """

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

    if (
        source == "tiget"
        and source_url
    ):
        return (
            "tiget|"
            + performer_id
            + "|"
            + source_url
        )

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


def fany_lines(html):
    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    result = []

    for raw in soup.get_text(
        "\n"
    ).splitlines():

        line = clean(raw)

        if line:
            result.append(
                line
            )

    return result


def is_fany_sales_line(line):
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
        "一般発売",
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

    lines = fany_lines(
        response.text
    )

    print(
        f"FANYページ行数: {len(lines)}"
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

        first_line = block[0]

        date_match = (
            FANY_DATE_RE.match(
                first_line
            )
        )

        if not date_match:
            continue

        # ----------------------------------
        # 出演欄
        # ----------------------------------

        performer_text = ""

        for i, line in enumerate(
            block
        ):
            if line == "出演":

                performer_parts = []

                for performer_line in block[
                    i + 1:
                ]:

                    if is_fany_sales_line(
                        performer_line
                    ):
                        break

                    performer_parts.append(
                        performer_line
                    )

                performer_text = (
                    " ".join(
                        performer_parts
                    )
                )

                break

        # 「出演」表記が見つからない場合でも
        # ブロック全体に芸人名があるか確認
        if performer_text:

            if (
                performer_name
                not in performer_text
            ):
                continue

        else:

            whole_block = " ".join(
                block
            )

            if (
                performer_name
                not in whole_block
            ):
                continue

        # ----------------------------------
        # 日付
        # ----------------------------------

        year, month, day = (
            date_match.groups()
        )

        date = make_date(
            year,
            month,
            day
        )

        # ----------------------------------
        # 開演時間
        # ----------------------------------

        start_time = ""

        start_match = (
            FANY_START_RE.search(
                first_line
            )
        )

        if start_match:
            start_time = (
                start_match.group(1)
            )

        # ----------------------------------
        # 会場
        # ----------------------------------

        venue = ""

        for line in block:

            if re.search(
                r"（[^）]*"
                r"(?:都|道|府|県)"
                r"）$",
                line
            ):
                venue = line
                break

        # ----------------------------------
        # タイトル
        # ----------------------------------

        title = ""

        noise = {
            "日",
            "月",
            "火",
            "水",
            "木",
            "金",
            "土",
            "出演",
        }

        for line in block[1:]:

            if line in noise:
                continue

            if line == venue:
                continue

            if is_fany_sales_line(
                line
            ):
                continue

            if re.match(
                r"^[日月火水木金土]$",
                line
            ):
                continue

            title = line
            break

        if not title:
            title = "公演名不明"

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
# TIGET補助
# ==========================================

def get_next_value(
    lines,
    label
):
    """
    TIGETの

    会場
    座・高円寺2

    のような構造から値を取る
    """

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

        if not line:
            continue

        return line

    return ""


# ==========================================
# TIGET
# ==========================================

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

        except Exception as error:
            print(
                "TIGET詳細取得失敗: "
                f"{event_url}"
            )
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
        # 出演者確認
        # ----------------------------------

        performer_section = ""

        try:
            p_index = lines.index(
                "出演者"
            )

            parts = []

            for line in lines[
                p_index + 1:
            ]:

                if line in [
                    "開催日",
                    "主催または登録者",
                    "会場",
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
            title = "公演名不明"

        # ----------------------------------
        # 開催日
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

        # ラベル取得失敗時の保険
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

        # TIGETでは
        # 座・高円寺2(東京都)
        # のように取得できる
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
# サイト内重複削除
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


# ==========================================
# FANY / TIGET重複統合
# ==========================================

def merge_cross_site(
    events
):
    """
    同じ芸人・同じ日・同じ時間・
    ほぼ同じタイトルなら1件にする。

    FANY情報を優先。
    """

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

        current_source = (
            current.get(
                "source",
                ""
            )
        )

        new_source = (
            event.get(
                "source",
                ""
            )
        )

        if (
            priority.get(
                new_source,
                99
            )
            <
            priority.get(
                current_source,
                99
            )
        ):
            result[key] = event

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
        "============================"
    )

    # --------------------------------------
    # 出演者設定
    # --------------------------------------

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

    # --------------------------------------
    # 前回データ
    # --------------------------------------

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
        old_events = (
            old_data.get(
                "events",
                []
            )
        )

    # --------------------------------------
    # 前回イベントのID
    # --------------------------------------

    old_identity_keys = {
        identity_key(event)
        for event in old_events
    }

    # 旧バージョンのTIGETデータ用
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
            )
            == "tiget"
            and event.get(
                "sourceUrl"
            )
        )
    }

    # --------------------------------------
    # HTTP
    # --------------------------------------

    session = requests.Session()

    session.headers.update(
        HEADERS
    )

    all_events = []

    # --------------------------------------
    # 各芸人
    # --------------------------------------

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

        # ----------------------------------
        # FANY
        # ----------------------------------

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

        # ----------------------------------
        # TIGET
        # ----------------------------------

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

    # --------------------------------------
    # 重複整理
    # --------------------------------------

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

    # --------------------------------------
    # 並び替え
    # --------------------------------------

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

    # --------------------------------------
    # 新規判定
    # --------------------------------------

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

        # TIGETは会場名などが修正されても
        # URLが同じなら再通知しない
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

    # --------------------------------------
    # 保存
    # --------------------------------------

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

    # --------------------------------------
    # ログ
    # --------------------------------------

    print("")
    print(
        "============================"
    )

    print(
        f"全公演数: "
        f"{len(all_events)}件"
    )

    print(
        f"新規公演数: "
        f"{len(new_events)}件"
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
            f"{performer_name}: "
            f"{count}件"
        )

    # --------------------------------------
    # 新規ライブ詳細
    # --------------------------------------

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
