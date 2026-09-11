import hashlib
import json
import re
import time

from datetime import datetime, date
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


# =========================================================
# 基本設定
# =========================================================

BASE_URL = "https://online-ticket.yoshimoto.co.jp"

LIVE_COLLECTION_URL = (
    "https://online-ticket.yoshimoto.co.jp/collections/live"
)

OUTPUT_FILE = Path("stream_events.json")

JST = ZoneInfo("Asia/Tokyo")


TRACKED_PERFORMERS = {
    "maison": [
        "めぞん",
    ],
    "pyuto": [
        "ピュート",
    ],
    "nansui": [
        "軟水",
    ],
}


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


session = requests.Session()

session.headers.update(
    HEADERS
)


# =========================================================
# 共通
# =========================================================

def clean_text(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or "")
    ).strip()


def absolute_url(url):
    return urljoin(
        BASE_URL,
        url
    )


def today_jst():
    return datetime.now(
        JST
    ).date()


def performer_ids_from_text(text):
    found = []

    normalized = clean_text(
        text
    )

    for performer_id, aliases in TRACKED_PERFORMERS.items():

        for alias in aliases:

            if alias in normalized:

                found.append(
                    performer_id
                )

                break

    return found


# =========================================================
# 年の補完
# =========================================================

def resolve_year(month, day=None):
    """
    FANY上で年表記がない場合に、
    現在日を基準として自然な年を補う。
    """

    now = datetime.now(
        JST
    )

    year = now.year

    if (
        now.month >= 10
        and
        month <= 3
    ):
        year += 1

    elif (
        now.month <= 3
        and
        month >= 10
    ):
        year -= 1

    return year


# =========================================================
# 日時
# =========================================================

def parse_title_datetime(title):
    """
    以下のようなパターンを対象にする。

    タイトル（9/18 19:00）
    タイトル (9/18 19:00)
    タイトル（9/18　19:00）
    """

    patterns = [
        (
            r"[（(]"
            r"\s*(\d{1,2})"
            r"\s*/\s*"
            r"(\d{1,2})"
            r"\s+"
            r"(\d{1,2}:\d{2})"
            r"\s*[）)]"
        ),
        (
            r"[（(]"
            r"\s*(\d{1,2})"
            r"月"
            r"(\d{1,2})"
            r"日"
            r".{0,12}?"
            r"(\d{1,2}:\d{2})"
            r"\s*[）)]"
        ),
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            title
        )

        if not match:
            continue

        return {
            "month": int(
                match.group(1)
            ),
            "day": int(
                match.group(2)
            ),
            "time": match.group(3),
        }

    return None


def strip_title_datetime(title):
    patterns = [
        (
            r"\s*[（(]"
            r"\s*\d{1,2}"
            r"\s*/\s*"
            r"\d{1,2}"
            r"\s+"
            r"\d{1,2}:\d{2}"
            r"\s*[）)]"
            r"\s*$"
        ),
        (
            r"\s*[（(]"
            r"\s*\d{1,2}"
            r"月"
            r"\d{1,2}"
            r"日"
            r".{0,12}?"
            r"\d{1,2}:\d{2}"
            r"\s*[）)]"
            r"\s*$"
        ),
    ]

    value = title

    for pattern in patterns:

        value = re.sub(
            pattern,
            "",
            value
        )

    return clean_text(
        value
    )


# =========================================================
# 一覧
# =========================================================

def fetch_collection_page(page):
    url = (
        f"{LIVE_COLLECTION_URL}"
        f"?page={page}"
    )

    response = session.get(
        url,
        timeout=30
    )

    response.raise_for_status()

    return response.text


def extract_product_links(html):
    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    links = set()

    for a in soup.find_all(
        "a",
        href=True
    ):

        href = clean_text(
            a.get(
                "href",
                ""
            )
        )

        if not href:
            continue

        if (
            "/collections/live/products/"
            not in href
        ):
            continue

        links.add(
            absolute_url(
                href.split(
                    "?"
                )[0]
            )
        )

    return sorted(
        links
    )


def extract_total_pages(html):
    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    page_numbers = []

    for a in soup.find_all(
        "a",
        href=True
    ):

        href = a.get(
            "href",
            ""
        )

        match = re.search(
            r"[?&]page=(\d+)",
            href
        )

        if match:

            page_numbers.append(
                int(
                    match.group(1)
                )
            )

    if page_numbers:
        return max(
            page_numbers
        )

    text = clean_text(
        soup.get_text(
            " ",
            strip=True
        )
    )

    match = re.search(
        r"(\d+)\s*/\s*(\d+)\s*ページ",
        text
    )

    if match:
        return int(
            match.group(2)
        )

    return 1


# =========================================================
# 詳細ページ
# =========================================================

def extract_heading(soup):
    h1 = soup.find(
        "h1"
    )

    if h1:

        value = clean_text(
            h1.get_text(
                " ",
                strip=True
            )
        )

        if value:
            return value

    title_tag = soup.find(
        "title"
    )

    if title_tag:

        value = clean_text(
            title_tag.get_text(
                " ",
                strip=True
            )
        )

        value = re.sub(
            r"\s*[|｜].*$",
            "",
            value
        )

        return clean_text(
            value
        )

    return ""


def extract_performer_section(raw_text):
    """
    ◆出演者 から次の見出しまでを取得する。
    """

    patterns = [
        (
            r"◆\s*出演者"
            r"\s*(.+?)"
            r"(?=\n\s*◆|\n\s*
