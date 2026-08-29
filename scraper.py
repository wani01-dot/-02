import json
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup


# =========================================================
# 基本設定
# =========================================================

SEARCH_URL = "https://ticket.fany.lol/search/event"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/18.0 "
        "Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8",
}


# =========================================================
# 共通処理
# =========================================================

def clean(text):
    """空白や改行を整理する"""
    return re.sub(r"\s+", " ", text or "").strip()


def fetch(url):
    """FANYのHTMLを取得する"""

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    response.encoding = response.apparent_encoding

    return response.text


def event_key(event):
    """
    前回データとの比較に使うキー。
    同じ出演者・日時・タイトル・会場なら同じ公演扱い。
    """

    return "|".join([
        event.get("performerId", ""),
        event.get("date", ""),
        event.get("startTime", ""),
        event.get("title", ""),
        event.get("venue", ""),
    ])


# =========================================================
# 日付関連
# =========================================================

def is_date_line(line):
    """
    例:
    2026/09/05(土)
    2026/09/05(土) 開場 10:30 開演 11:00
    """

    return bool(
        re.search(
            r"^20\d{2}/\d{1,2}/\d{1,2}",
            line
        )
    )


def parse_date(line):

    match = re.search(
        r"^(20\d{2})/(\d{1,2})/(\d{1,2})",
        line,
    )

    if not match:
        return ""

    year = int(match.group(1))
    month = int(match.group(2))
    day = int(match.group(3))

    return f"{year:04d}-{month:02d}-{day:02d}"


def parse_start_time(line):

    match = re.search(
        r"開演\s*(\d{1,2}:\d{2})",
        line,
    )

    if not match:
        return ""

    return match.group(1)


# =========================================================
# 不要テキスト判定
# =========================================================

def is_noise(line):

    if not line:
        return True

    exact_noise = {
        "出演",
        "検索",
        "検索結果",
        "絞り込み検索",
        "詳細検索",
        "クリア",
        "月",
        "火",
        "水",
        "木",
        "金",
        "土",
        "日",
        "祝",
    }

    if line in exact_noise:
        return True

    bad_prefixes = [
        "先着",
        "抽選",
        "一般発売",
        "FANY ID",
        "●FANY ID",
        "受付期間",
        "販売期間",
        "発売開始",
    ]

    if any(
        line.startswith(prefix)
        for prefix in bad_prefixes
    ):
        return True

    if "受付期間：" in line:
        return True

    return False


# =========================================================
# 会場判定
# =========================================================

def looks_like_venue(line):

    # 都道府県表記があるもの
    if re.search(
        r"（(?:東京都|北海道|大阪府|京都府|.{2,3}県)）",
        line,
    ):
        return True

    venue_words = [
        "劇場",
        "ホール",
        "シアター",
        "THEATER",
        "ルミネ",
        "神保町",
        "幕張",
        "森ノ宮",
        "よしもと漫才劇場",
        "なんばグランド花月",
        "渋谷よしもと",
    ]

    return any(
        word in line
        for word in venue_words
    )


# =========================================================
# FANY検索結果解析
# =========================================================

def parse_search_results(
    html,
    performer,
    search_url,
):

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    # JSやCSSは消す
    for tag in soup(
        ["script", "style", "noscript"]
    ):
        tag.decompose()

    raw_text = soup.get_text("\n")

    lines = []

    for raw_line in raw_text.splitlines():

        line = clean(raw_line)

        if line:
            lines.append(line)

    # ---------------------------------------------
    # 日付の開始位置を全部探す
    # ---------------------------------------------

    date_indexes = []

    for index, line in enumerate(lines):

        if is_date_line(line):
            date_indexes.append(index)

    print(
        f"  検索結果内の日付ブロック: "
        f"{len(date_indexes)}件"
    )

    events = []

    # ---------------------------------------------
    # 日付ごとにブロックを分割
    # ---------------------------------------------

    for position, start_index in enumerate(
        date_indexes
    ):

        if position + 1 < len(date_indexes):
            end_index = date_indexes[
                position + 1
            ]
        else:
            end_index = len(lines)

        block = lines[
            start_index:end_index
        ]

        if not block:
            continue

        date_line = block[0]

        date = parse_date(
            date_line
        )

        start_time = parse_start_time(
            date_line
        )

        # -----------------------------------------
        # 「出演」の位置を探す
        # -----------------------------------------

        try:
            cast_index = block.index(
                "出演"
            )
        except ValueError:
            continue

        # -----------------------------------------
        # 出演者一覧を作る
        # -----------------------------------------

        cast_lines = []

        for line in block[
            cast_index + 1:
        ]:

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

        cast_text = " ".join(
            cast_lines
        )

        # 本当に出演者欄に名前があるか確認
        if performer["name"] not in cast_text:
            continue

        # -----------------------------------------
        # 出演欄より前
        #
        # 日付
        # 公演タイトル
        # 会場
        # 出演
        #
        # を想定
        # -----------------------------------------

        header_lines = []

        for line in block[
            1:cast_index
        ]:

            if not is_noise(line):
                header_lines.append(line)

        if not header_lines:
            continue

        # -----------------------------------------
        # 会場を探す
        # -----------------------------------------

        venue = ""

        for line in reversed(
            header_lines
        ):

            if looks_like_venue(line):

                venue = line
                break

        # -----------------------------------------
        # タイトルを探す
        # -----------------------------------------

        title = ""

        for line in header_lines:

            if line == venue:
                continue

            if is_noise(line):
                continue

            if len(line) <= 1:
                continue

            # 時刻だけなどを除外
            if re.fullmatch(
                r"\d{1,2}:\d{2}",
                line
            ):
                continue

            title = line
            break

        if not title:
            print(
                f"  タイトル取得失敗: "
                f"{date}",
                file=sys.stderr,
            )
            continue

        event
