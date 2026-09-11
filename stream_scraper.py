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
            r"(?=\n\s*◆|\n\s*【|\n\s*＜|\n\s*注意事項|\Z)"
        ),
        (
            r"出演者"
            r"\s*(.+?)"
            r"(?=\n\s*◆|\n\s*【|\n\s*＜|\n\s*注意事項|\Z)"
        ),
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            raw_text,
            re.S
        )

        if not match:
            continue

        value = clean_text(
            match.group(1)
        )

        if value:
            return value

    return ""


# =========================================================
# 価格
# =========================================================

def extract_price(text):
    patterns = [
        r"¥\s*[\d,]+\s*[（(]?税込[）)]?",
        r"￥\s*[\d,]+\s*[（(]?税込[）)]?",
        r"¥\s*[\d,]+",
        r"￥\s*[\d,]+",
        r"[\d,]+\s*円\s*[（(]?税込[）)]?",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text
        )

        if match:

            return clean_text(
                match.group(0)
            )

    return ""


# =========================================================
# 販売状態
# =========================================================

def extract_status(soup):
    """
    ページ全体にある注意文の「販売終了」を
    誤判定しないようにする。

    完全一致に近い表示だけを見る。
    """

    sold_words = {
        "販売終了",
        "販売終了しました",
        "受付終了",
        "受付終了しました",
    }

    sale_words = {
        "販売中",
        "購入する",
        "チケットを購入",
        "購入はこちら",
    }

    visible_texts = []

    for tag in soup.find_all(
        [
            "button",
            "a",
            "span",
            "div",
        ]
    ):

        text = clean_text(
            tag.get_text(
                " ",
                strip=True
            )
        )

        if not text:
            continue

        if len(text) > 50:
            continue

        visible_texts.append(
            text
        )

    for text in visible_texts:

        if text in sold_words:
            return "販売終了"

    for text in visible_texts:

        if text in sale_words:
            return "販売中"

    return ""


# =========================================================
# アーカイブ
# =========================================================

def extract_archive_lines(raw_text):
    """
    アーカイブに本当に関係する文だけを取得。

    「商品が販売終了になった場合」など、
    注意事項は除外する。
    """

    useful_keywords = [
        "見逃し配信",
        "見逃し視聴",
        "アーカイブ配信",
        "アーカイブ視聴",
        "視聴期限",
        "視聴期間",
        "見逃し期間",
    ]

    bad_keywords = [
        "商品が販売終了",
        "販売終了になった場合",
        "予告なく",
        "変更となる場合",
        "視聴できない場合",
        "注意事項",
    ]

    result = []

    for line in raw_text.splitlines():

        line = clean_text(
            line
        )

        if not line:
            continue

        if not any(
            keyword in line
            for keyword
            in useful_keywords
        ):
            continue

        if any(
            keyword in line
            for keyword
            in bad_keywords
        ):
            continue

        if line not in result:

            result.append(
                line
            )

    return result[:4]


def extract_archive_text(raw_text):
    lines = extract_archive_lines(
        raw_text
    )

    if not lines:
        return ""

    return " / ".join(
        lines
    )


def extract_archive_end(raw_text):
    """
    アーカイブ関連行の中だけから期限を探す。
    """

    lines = extract_archive_lines(
        raw_text
    )

    archive_text = " ".join(
        lines
    )

    if not archive_text:
        return ""

    patterns = [
        (
            r"(\d{1,2})"
            r"\s*/\s*"
            r"(\d{1,2})"
            r"\s*"
            r"(\d{1,2}:\d{2})"
        ),
        (
            r"(\d{1,2})"
            r"月"
            r"(\d{1,2})"
            r"日"
            r".{0,15}?"
            r"(\d{1,2}:\d{2})"
        ),
    ]

    matches = []

    for pattern in patterns:

        for match in re.finditer(
            pattern,
            archive_text,
            re.S
        ):

            month = int(
                match.group(1)
            )

            day = int(
                match.group(2)
            )

            time_text = (
                match.group(3)
            )

            year = resolve_year(
                month,
                day
            )

            try:

                dt = datetime.strptime(
                    (
                        f"{year:04d}-"
                        f"{month:02d}-"
                        f"{day:02d} "
                        f"{time_text}"
                    ),
                    "%Y-%m-%d %H:%M"
                )

                matches.append(
                    dt
                )

            except ValueError:
                continue

    if not matches:
        return ""

    latest = max(
        matches
    )

    return latest.strftime(
        "%Y-%m-%d %H:%M"
    )


# =========================================================
# ID
# =========================================================

def make_event_id(url):
    digest = hashlib.sha1(
        url.encode(
            "utf-8"
        )
    ).hexdigest()[:14]

    return (
        "fany-stream-"
        +
        digest
    )


# =========================================================
# 公演1件
# =========================================================

def scrape_product(url):
    response = session.get(
        url,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    title = extract_heading(
        soup
    )

    if not title:
        return None

    raw_text = soup.get_text(
        "\n",
        strip=True
    )

    full_text = clean_text(
        raw_text
    )

    performer_text = extract_performer_section(
        raw_text
    )

    performer_ids = performer_ids_from_text(
        performer_text
    )

    # 出演者欄から3組のどれも見つからなければ除外
    if not performer_ids:
        return None

    datetime_info = parse_title_datetime(
        title
    )

    if not datetime_info:

        print(
            "日時取得失敗:",
            title
        )

        return None

    month = datetime_info[
        "month"
    ]

    day = datetime_info[
        "day"
    ]

    start_time = datetime_info[
        "time"
    ]

    year = resolve_year(
        month,
        day
    )

    try:

        event_date = date(
            year,
            month,
            day
        )

    except ValueError:

        print(
            "日付不正:",
            title
        )

        return None

    # 過去公演は保存しない
    if event_date < today_jst():

        print(
            "  SKIP 過去:",
            event_date,
            title
        )

        return None

    status = extract_status(
        soup
    )

    # 明確に販売終了なら除外
    if status == "販売終了":

        print(
            "  SKIP 販売終了:",
            title
        )

        return None

    price = extract_price(
        full_text
    )

    archive = extract_archive_text(
        raw_text
    )

    archive_end = extract_archive_end(
        raw_text
    )

    return {
        "id": make_event_id(
            url
        ),

        "date": event_date.isoformat(),

        "startTime": start_time,

        "title": strip_title_datetime(
            title
        ),

        "performerIds": performer_ids,

        "performersText": performer_text,

        "price": price,

        "archive": archive,

        "archiveEnd": archive_end,

        "status": (
            status
            or
            "販売状況不明"
        ),

        "source": (
            "FANYオンラインチケット"
        ),

        "sourceUrl": url,
    }


# =========================================================
# 保存
# =========================================================

def sort_events(events):
    return sorted(
        events,
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
                "title",
                ""
            ),
        )
    )


def deduplicate_events(events):
    result = {}

    for event in events:

        source_url = event.get(
            "sourceUrl",
            ""
        )

        if not source_url:
            continue

        result[
            source_url
        ] = event

    return sort_events(
        list(
            result.values()
        )
    )


# =========================================================
# メイン
# =========================================================

def main():
    print(
        "====================================="
    )

    print(
        "FANY配信取得開始"
    )

    print(
        "今日:",
        today_jst()
    )

    print(
        "対象:",
        " / ".join(
            [
                "めぞん",
                "ピュート",
                "軟水",
            ]
        )
    )

    print(
        "====================================="
    )

    first_html = fetch_collection_page(
        1
    )

    total_pages = extract_total_pages(
        first_html
    )

    print(
        "一覧ページ数:",
        total_pages
    )

    product_links = set(
        extract_product_links(
            first_html
        )
    )

    for page in range(
        2,
        total_pages + 1
    ):

        print(
            f"一覧 "
            f"{page}/"
            f"{total_pages}"
        )

        try:

            html = fetch_collection_page(
                page
            )

            links = extract_product_links(
                html
            )

            product_links.update(
                links
            )

        except Exception as exc:

            print(
                "一覧取得失敗:",
                page,
                exc
            )

        time.sleep(
            0.2
        )

    product_links = sorted(
        product_links
    )

    print(
        "商品URL数:",
        len(
            product_links
        )
    )

    matched = []

    for index, url in enumerate(
        product_links,
        start=1
    ):

        print(
            f"詳細 "
            f"{index}/"
            f"{len(product_links)}"
        )

        try:

            event = scrape_product(
                url
            )

            if event:

                matched.append(
                    event
                )

                print(
                    "  HIT:",
                    event[
                        "date"
                    ],
                    event[
                        "startTime"
                    ],
                    event[
                        "title"
                    ],
                    event[
                        "performerIds"
                    ]
                )

        except Exception as exc:

            print(
                "詳細取得失敗:",
                url,
                exc
            )

        time.sleep(
            0.2
        )

    events = deduplicate_events(
        matched
    )

    output = {
        "updatedAt": (
            datetime.now(
                JST
            )
            .isoformat()
        ),

        "source": (
            "FANY Online Ticket"
        ),

        "events": events,
    }

    OUTPUT_FILE.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print(
        "====================================="
    )

    print(
        "保存完了:",
        OUTPUT_FILE
    )

    print(
        "保存件数:",
        len(
            events
        )
    )

    for performer_id in [
        "maison",
        "pyuto",
        "nansui",
    ]:

        count = sum(
            1
            for event in events
            if performer_id
            in event.get(
                "performerIds",
                []
            )
        )

        print(
            performer_id,
            ":",
            count,
            "件"
        )

    print(
        "====================================="
    )


if __name__ == "__main__":
    main()
