import json
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup


# ==============================
# 基本設定
# ==============================

SEARCH_URL = "https://ticket.fany.lol/search/event"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8",
}


# ==============================
# 共通処理
# ==============================

def clean(text):
    """余計な空白を整理"""
    return re.sub(r"\s+", " ", text or "").strip()


def fetch(url):
    """FANYからHTMLを取得"""
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    # 日本語文字化け対策
    response.encoding = response.apparent_encoding

    return response.text


def event_key(event):
    """
    同じ公演かどうか判定するためのキー
    出演者ごとに別イベントとして管理
    """
    return "|".join([
        event.get("performerId", ""),
        event.get("date", ""),
        event.get("title", ""),
        event.get("venue", ""),
        event.get("startTime", ""),
    ])


# ==============================
# FANY検索結果解析
# ==============================

def parse_search_results(html, performer, search_url):
    """
    FANY検索結果ページから直接、公演情報を取り出す
    """

    soup = BeautifulSoup(html, "html.parser")

    # script/styleなど不要部分を削除
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    raw_text = soup.get_text("\n")

    lines = []

    for line in raw_text.splitlines():
        line = clean(line)

        if line:
            lines.append(line)

    events = []

    # ------------------------------
    # 日付の行を探す
    #
    # 例：
    # 2026/09/04(金)開場 17:15 開演 17:30
    # ------------------------------

    date_pattern = re.compile(
        r"^(20\d{2})/"
        r"(\d{1,2})/"
        r"(\d{1,2})"
    )

    time_pattern = re.compile(
        r"開演\s*(\d{1,2}:\d{2})"
    )

    date_indexes = []

    for i, line in enumerate(lines):
        if date_pattern.search(line):
            date_indexes.append(i)

    print(
        f"  検索結果内の日付ブロック: {len(date_indexes)}件"
    )

    # ------------------------------
    # 1公演ずつ解析
    # ------------------------------

    for position, start_index in enumerate(date_indexes):

        if position + 1 < len(date_indexes):
            end_index = date_indexes[position + 1]
        else:
            end_index = len(lines)

        block = lines[start_index:end_index]

        if not block:
            continue

        full_block = " ".join(block)

        # --------------------------------
        # 本当に出演者として名前があるか
        # --------------------------------

        if performer["name"] not in full_block:
            continue

        # 「出演」がないブロックは除外
        if "出演" not in full_block:
            continue

        # --------------------------------
        # 日付
        # --------------------------------

        match = date_pattern.search(block[0])

        if not match:
            continue

        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))

        date = f"{year:04d}-{month:02d}-{day:02d}"

        # --------------------------------
        # 開演時間
        # --------------------------------

        time_match = time_pattern.search(block[0])

        if time_match:
            start_time = time_match.group(1)
        else:
            start_time = ""

        # --------------------------------
        # 公演タイトル
        # --------------------------------

        title = ""

        # 通常、日付の次の行がタイトル
        for line in block[1:]:

            # 不要な行は飛ばす
            if line in [
                "出演",
                "検索結果",
                "絞り込み検索",
            ]:
                continue

            if line.startswith("先着"):
                continue

            if line.startswith("抽選"):
                continue

            if line.startswith("一般発売"):
                continue

            if line.startswith("FANY ID"):
                continue

            if "受付期間：" in line:
                continue

            title = line
            break

        if not title:
            continue

        # --------------------------------
        # 会場
        # --------------------------------

        venue = ""

        try:
            title_index = block.index(title)
        except ValueError:
            title_index = 1

        # タイトル以降、出演欄より前を探す
        for line in block[title_index + 1:]:

            if line == "出演":
                break

            # 都道府県表記がある行を会場と判断
            if re.search(
                r"（.*?(?:東京都|北海道|大阪府|京都府|.{2,3}県)）",
                line
            ):
                venue = line
                break

        # 会場判定ができなかった場合
        if not venue:

            for line in block[title_index + 1:]:

                if line == "出演":
                    break

                if (
                    "発売" not in line
                    and "受付" not in line
                    and line != title
                ):
                    venue = line
                    break

        # --------------------------------
        # 出演欄を確認
        # --------------------------------

        performer_text = ""

        if "出演" in block:

            cast_index = block.index("出演")

            cast_lines = []

            for line in block[cast_index + 1:]:

                if (
                    line.startswith("先着")
                    or line.startswith("抽選")
                    or line.startswith("一般発売")
                    or line.startswith("FANY ID")
                    or "受付期間：" in line
                ):
                    break

                cast_lines.append(line)

            performer_text = " ".join(cast_lines)

        # 出演欄が取得できた場合、
        # その中に芸人名があるか最終確認
        if performer_text:

            if performer["name"] not in performer_text:
                continue

        # --------------------------------
        # 保存
        # --------------------------------

        event = {
            "performerId": performer["id"],
            "date": date,
            "title": title,
            "venue": venue,
            "startTime": start_time,

            # 詳細URLがFANY側で安定して取れないため
            # 検索結果URLを保存
            "sourceUrl": search_url,
        }

        events.append(event)

    # ------------------------------
    # 重複削除
    # ------------------------------

    unique = {}

    for event in events:
        unique[event_key(event)] = event

    return list(unique.values())


# ==============================
# 出演者ごとの取得
# ==============================

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
            f"検索ページ取得失敗: {name}",
            error,
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


# ==============================
# メイン処理
# ==============================

def main():

    # --------------------------------
    # 出演者設定
    # --------------------------------

    with open(
        "performers.json",
        encoding="utf-8"
    ) as f:

        config = json.load(f)

    performers = config.get(
        "performers",
        []
    )

    # --------------------------------
    # 前回データ
    # --------------------------------

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

    # --------------------------------
    # FANY取得
    # --------------------------------

    all_events = []

    for performer in performers:

        sources = performer.get(
            "sources",
            []
        )

        if "fany" not in sources:
            continue

        events = scrape_performer(
            performer
        )

        all_events.extend(events)

        # FANYへ連続アクセスしすぎない
        time.sleep(1)

    # --------------------------------
    # 全体重複削除
    # --------------------------------

    unique = {}

    for event in all_events:

        unique[
            event_key(event)
        ] = event

    all_events = list(
        unique.values()
    )

    # 日付順に並べる
    all_events.sort(
        key=lambda e: (
            e.get("date", ""),
            e.get("startTime", ""),
            e.get("title", ""),
            e.get("performerId", ""),
        )
    )

    # --------------------------------
    # 新規公演判定
    # --------------------------------

    new_events = []

    for event in all_events:

        if event_key(event) not in old_keys:
            new_events.append(event)

    # --------------------------------
    # events.json を直接更新
    # --------------------------------

    payload = {
        "syncedAt": (
            datetime.now(timezone.utc)
            .astimezone()
            .strftime(
                "%Y-%m-%d %H:%M:%S %z"
            )
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

    # --------------------------------
    # LINE通知用
    # --------------------------------

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

    # --------------------------------
    # ログ
    # --------------------------------

    print("")
    print("==============================")
    print("FANY同期完了")
    print(f"全公演数: {len(all_events)}")
    print(f"新規公演数: {len(new_events)}")

    for performer in performers:

        count = sum(
            1
            for event in all_events
            if event.get("performerId")
            == performer.get("id")
        )

        print(
            f"{performer.get('name')}: {count}件"
        )


if __name__ == "__main__":
    main()
