import json
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup


SEARCH_URL = "https://ticket.fany.lol/search/event"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8",
}


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def fetch(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    return response.text


def event_key(event):
    return "|".join([
        event.get("performerId", ""),
        event.get("date", ""),
        event.get("title", ""),
        event.get("venue", ""),
        event.get("startTime", ""),
    ])


def is_date_line(line):
    return re.search(
        r"^20\d{2}/\d{1,2}/\d{1,2}\([^)]+\)",
        line
    ) is not None


def parse_date(line):
    m = re.search(
        r"^(20\d{2})/(\d{1,2})/(\d{1,2})",
        line
    )

    if not m:
        return ""

    return (
        f"{int(m.group(1)):04d}-"
        f"{int(m.group(2)):02d}-"
        f"{int(m.group(3)):02d}"
    )


def parse_start_time(line):
    m = re.search(
        r"開演\s*(\d{1,2}:\d{2})",
        line
    )

    return m.group(1) if m else ""


def looks_like_venue(line):
    # FANYの会場名は多くの場合「（東京都）」等で終わる
    if re.search(
        r"（(?:東京都|北海道|大阪府|京都府|.{2,3}県)）$",
        line
    ):
        return True

    # 念のため劇場系名称も許可
    venue_words = [
        "劇場",
        "THEATER",
        "シアター",
        "ホール",
        "シネマ",
        "幕張",
        "ルミネ",
        "森ノ宮",
        "神保町",
        "渋谷",
        "なんば",
    ]

    return any(word in line for word in venue_words)


def is_noise(line):
    if not line:
        return True

    exact_noise = {
        "出演",
        "検索結果",
        "絞り込み検索",
        "詳細検索",
        "クリア",
        "検索",
    }

    if line in exact_noise:
        return True

    prefixes = [
        "先着発売",
        "抽選受付",
        "一般発売",
        "FANY ID",
        "●FANY ID",
        "受付期間：",
    ]

    if any(line.startswith(p) for p in prefixes):
        return True

    if "受付期間：" in line:
        return True

    return False


def parse_search_results(html, performer, search_url):
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    lines = [
        clean(x)
        for x in soup.get_text("\n").splitlines()
        if clean(x)
    ]

    date_indexes = [
        i
        for i, line in enumerate(lines)
        if is_date_line(line)
    ]

    print(
        f"  検索結果内の日付ブロック: {len(date_indexes)}件"
    )

    events = []

    for pos, start in enumerate(date_indexes):

        end = (
            date_indexes[pos + 1]
            if pos + 1 < len(date_indexes)
            else len(lines)
        )

        block = lines[start:end]

        if not block:
            continue

        date_line = block[0]
        date = parse_date(date_line)
        start_time = parse_start_time(date_line)

        # --------------------------------
        # 出演欄位置
        # --------------------------------

        try:
            cast_index = block.index("出演")
        except ValueError:
            cast_index = -1

        if cast_index == -1:
            continue

        # --------------------------------
        # 出演者欄
        # --------------------------------

        cast_lines = []

        for line in block[cast_index + 1:]:

            if (
                line.startswith("先着")
                or line.startswith("抽選")
                or line.startswith("一般発売")
                or line.startswith("FANY ID")
                or line.startswith("●FANY ID")
                or "受付期間：" in line
            ):
                break

            if not is_noise(line):
                cast_lines.append(line)

        cast_text = " ".join(cast_lines)

        # 本当に出演している公演だけ
        if performer["name"] not in cast_text:
            continue

        # --------------------------------
        # 出演より前だけを見る
        # date / title / venue の順
        # --------------------------------

        header_lines = [
            line
            for line in block[1:cast_index]
            if not is_noise(line)
        ]

        if not header_lines:
            continue

        # --------------------------------
        # 会場
        # --------------------------------

        venue = ""

        for line in reversed(header_lines):
            if looks_like_venue(line):
                venue = line
                break

        # --------------------------------
        # タイトル
        # --------------------------------

        title = ""

        for line in header_lines:

            # 会場自身は除外
            if line == venue:
                continue

            # 曜日単体などを除外
            if line in {
                "月", "火", "水",
                "木", "金", "土", "日",
                "祝",
            }:
                continue

            # 短すぎる文字列はタイトル扱いしない
            if len(line) <= 1:
                continue

            title = line
            break

        if not title:
            print(
                f"  タイトル取得失敗: {date}",
                file=sys.stderr
            )
            continue

        event = {
            "performerId": performer["id"],
            "date": date,
            "title": title,
            "venue": venue,
            "startTime": start_time,
            "sourceUrl": search_url,
        }

        events.append(event)

        print(
            f"    {date} / {title} / {venue}"
        )

    # 重複除去
    unique = {}

    for event in events:
        unique[event_key(event)] = event

    return list(unique.values())


def scrape_performer(performer):
    name = performer["name"]

    params = {
        "keywords": name,
        "search_type": "search_string",
    }

    url = SEARCH_URL + "?" + urlencode(params)

    print("")
    print("==============================")
    print(f"scraping {name}")
    print(url)

    try:
        html = fetch(url)
    except Exception as error:
        print(
            f"検索ページ取得失敗: {name}: {error}",
            file=sys.stderr
        )
        return []

    events = parse_search_results(
        html,
        performer,
        url
    )

    print(
        f"  → {name}: {len(events)}件取得"
    )

    return events


def main():

    with open(
        "performers.json",
        encoding="utf-8"
    ) as f:
        config = json.load(f)

    performers = config.get(
        "performers",
        []
    )

    try:
        with open(
            "events.json",
            encoding="utf-8"
        ) as f:
            old_data = json.load(f)
    except Exception:
        old_data = {
            "events": []
        }

    old_events = old_data.get(
        "events",
        []
    )

    old_keys = {
        event_key(event)
        for event in old_events
    }

    all_events = []

    for performer in performers:

        if "fany" not in performer.get(
            "sources",
            []
        ):
            continue

        events = scrape_performer(
            performer
        )

        all_events.extend(events)

        time.sleep(1)

    # --------------------------------
    # 重複削除
    # --------------------------------

    unique = {}

    for event in all_events:
        unique[event_key(event)] = event

    all_events = list(
        unique.values()
    )

    all_events.sort(
        key=lambda e: (
            e.get("date", ""),
            e.get("startTime", ""),
            e.get("title", ""),
            e.get("performerId", ""),
        )
    )

    # --------------------------------
    # 新規公演
    # --------------------------------

    new_events = [
        event
        for event in all_events
        if event_key(event) not in old_keys
    ]

    payload = {
        "syncedAt": (
            datetime.now(timezone.utc)
            .astimezone()
            .strftime("%Y-%m-%d %H:%M:%S %z")
        ),
        "performers": performers,
        "events": all_events,
    }

    with open(
        "events.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            payload,
            f,
            ensure_ascii=False,
            indent=2
        )

    with open(
        "new_events.json",
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            new_events,
            f,
            ensure_ascii=False,
            indent=2
        )   
        if __name__ == "__main__":
    main()
    
