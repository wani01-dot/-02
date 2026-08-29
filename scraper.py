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
    "Accept-Language": "ja-JP,ja;q=0.9"
}


# ==========================================
# JSON
# ==========================================

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
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


def make_date(year, month, day):
    return (
        f"{int(year):04d}-"
        f"{int(month):02d}-"
        f"{int(day):02d}"
    )


def event_key(event):
    return "|".join([
        event.get("performerId", ""),
        event.get("date", ""),
        event.get("startTime", ""),
        clean(event.get("title", "")).lower(),
        clean(event.get("venue", "")).lower()
    ])


# ==========================================
# FANY
# ==========================================

def scrape_fany(session, performer):

    performer_id = performer["id"]
    performer_name = performer["name"]

    print("")
    print(
        f"FANY検索: {performer_name}"
    )

    search_url = (
        FANY_URL
        + "?"
        + urlencode({
            "keywords": performer_name,
            "search_type": "search_string"
        })
    )

    response = session.get(
        search_url,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    lines = []

    for raw in soup.get_text("\n").splitlines():

        line = clean(raw)

        if line:
            lines.append(line)


    # ======================================
    # 日付
    # ======================================

    date_pattern = re.compile(
        r"^(20\d{2})/"
        r"(\d{1,2})/"
        r"(\d{1,2})"
    )

    start_pattern = re.compile(
        r"開演\s*(\d{1,2}:\d{2})"
    )

    indexes = []

    for index, line in enumerate(lines):

        if (
            date_pattern.match(line)
            and "開演" in line
        ):
            indexes.append(index)


    events = []


    # ======================================
    # 公演ごとに解析
    # ======================================

    for number, start_index in enumerate(indexes):

        if number + 1 < len(indexes):

            end_index = (
                indexes[number + 1]
            )

        else:

            end_index = len(lines)


        block = lines[
            start_index:end_index
        ]


        if not block:
            continue


        # ==================================
        # 出演者欄
        # ==================================

        try:

            performer_index = (
                block.index("出演")
            )

        except ValueError:

            continue


        performer_lines = []


        for line in block[
            performer_index + 1:
        ]:

            if any(
                word in line
                for word in [
                    "発売",
                    "受付期間",
                    "受付中",
                    "受付終了",
                    "受付前",
                    "抽選",
                    "先着"
                ]
            ):
                break

            performer_lines.append(
                line
            )


        performer_text = " ".join(
            performer_lines
        )


        # 本当に出演欄に名前があるか
        if (
            performer_name
            not in performer_text
        ):
            continue


        # ==================================
        # 日付
        # ==================================

        date_match = (
            date_pattern.match(
                block[0]
            )
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


        # ==================================
        # 開演時間
        # ==================================

        start_match = (
            start_pattern.search(
                block[0]
            )
        )


        start_time = ""


        if start_match:

            start_time = (
                start_match.group(1)
            )


        # ==================================
        # 会場
        # ==================================

        venue = ""


        for line in block:

            if re.search(
                r"（[^）]*(?:都|道|府|県)）",
                line
            ):

                venue = line
                break


        # ==================================
        # 公演タイトル
        # ==================================

        title = ""


        noise = {
            "日",
            "月",
            "火",
            "水",
            "木",
            "金",
            "土",
            "出演"
        }


        for line in block[1:]:

            if line in noise:
                continue

            if line == venue:
                continue

            if any(
                word in line
                for word in [
                    "発売",
                    "受付期間",
                    "受付中",
                    "受付終了",
                    "受付前",
                    "抽選",
                    "先着"
                ]
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
                search_url

        })


    print(
        f"FANY {performer_name}: "
        f"{len(events)}件"
    )


    return events


# ==========================================
# TIGET
# ==========================================

def scrape_tiget(session, performer):

    performer_id = performer["id"]
    performer_name = performer["name"]

    print(
        f"TIGET検索: {performer_name}"
    )


    search_url = (
        TIGET_URL
        + "?"
        + urlencode({
            "q[words]": performer_name
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
            f"TIGET取得失敗: {error}"
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


        if re.match(
            r"^/events/\d+",
            href
        ):

            event_url = urljoin(
                TIGET_BASE,
                href
            )


            if (
                event_url
                not in event_urls
            ):

                event_urls.append(
                    event_url
                )


    events = []


    # 最大50件まで確認
    for event_url in event_urls[:50]:

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


        detail_text = clean(
            detail_soup.get_text(
                " ",
                strip=True
            )
        )


        # 芸人名がページに無ければ除外
        if (
            performer_name
            not in detail_text
        ):
            continue


        # ==================================
        # 日付
        # ==================================

        date_match = re.search(

            r"(20\d{2})"
            r"[年/\-.]"
            r"(\d{1,2})"
            r"[月/\-.]"
            r"(\d{1,2})"
            r"日?",

            detail_text
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


        # ==================================
        # 開演時間
        # ==================================

        time_match = re.search(

            r"(?:開演|START)"
            r"\s*[:：]?\s*"
            r"(\d{1,2}:\d{2})",

            detail_text,

            re.IGNORECASE
        )


        start_time = ""


        if time_match:

            start_time = (
                time_match.group(1)
            )


        # ==================================
        # タイトル
        # ==================================

        title = "公演名不明"


        if detail_soup.title:

            title = clean(
                detail_soup.title.get_text()
            )


            title = re.sub(
                r"\s*[|｜]\s*TIGET.*$",
                "",
                title
            )


        # ==================================
        # 会場
        # ==================================

        venue = ""


        venue_match = re.search(

            r"(?:会場|場所)"
            r"\s*[:：]?\s*"
            r"(.{1,80}?)"
            r"(?=\s(?:開場|開演|出演|料金|チケット|$))",

            detail_text
        )


        if venue_match:

            venue = clean(
                venue_match.group(1)
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
                event_url

        })


    print(
        f"TIGET {performer_name}: "
        f"{len(events)}件"
    )


    return events


# ==========================================
# 重複削除
# ==========================================

def remove_duplicates(events):

    result = []

    seen = set()


    for event in events:

        key = event_key(
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
# メイン処理
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


    # ======================================
    # 芸人設定
    # ======================================

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
            "performers.jsonに芸人がいません"
        )

        save_json(
            NEW_EVENTS_FILE,
            []
        )

        return


    # ======================================
    # 前回のイベント
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


    old_keys = {

        event_key(event)

        for event in old_events

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
    # 芸人ごとに検索
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
            ["fany"]
        )


        # ==================================
        # FANY
        # ==================================

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
                    f"FANYエラー: {error}"
                )


        # ==================================
        # TIGET
        # ==================================

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
                    f"TIGETエラー: {error}"
                )


    # ======================================
    # 重複削除
    # ======================================

    all_events = remove_duplicates(
        all_events
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

        if (
            event_key(event)
            not in old_keys
        ):

            new_events.append(
                event
            )


    # ======================================
    # events.json
    # ======================================

    output = {

        "syncedAt":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "performers":
            performers,

        "events":
            all_events

    }


    save_json(
        EVENTS_FILE,
        output
    )


    # ======================================
    # new_events.json
    # 0件でも必ず作成
    # ======================================

    save_json(
        NEW_EVENTS_FILE,
        new_events
    )


    # ======================================
    # 結果表示
    # ======================================

    print("")
    print(
        "============================"
    )

    print(
        f"全公演数: {len(all_events)}件"
    )

    print(
        f"新規公演数: {len(new_events)}件"
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

            for event in all_events

            if (
                event.get(
                    "performerId"
                )
                == performer_id
            )

        )


        print(
            f"{performer_name}: "
            f"{count}件"
        )


    # ======================================
    # 新規公演をログ表示
    # ======================================

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

                f"{performer_name} | "

                f"{event.get('date', '')} | "

                f"{event.get('startTime', '')} | "

                f"{event.get('title', '')} | "

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
