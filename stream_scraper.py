import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://online-ticket.yoshimoto.co.jp"

LIVE_COLLECTION_URL = (
    "https://online-ticket.yoshimoto.co.jp/collections/live"
)

OUTPUT_FILE = Path("stream_events.json")


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


def parse_title_datetime(title):
    """
    例:
    公演タイトル（9/18　19:00）

    ↓

    {
      month: 9,
      day: 18,
      time: "19:00"
    }
    """

    match = re.search(
        r"[（(]"
        r"\s*(\d{1,2})"
        r"\s*/\s*"
        r"(\d{1,2})"
        r"\s+"
        r"(\d{1,2}:\d{2})"
        r"\s*[）)]",
        title
    )

    if not match:
        return None

    return {
        "month": int(
            match.group(1)
        ),
        "day": int(
            match.group(2)
        ),
        "time": match.group(3),
    }


def resolve_year(month):
    """
    FANY一覧では年が省略されることがあるため、
    現在月から自然な年を補完する。
    """

    now = datetime.now()

    year = now.year

    current_month = now.month

    if (
        current_month >= 10
        and
        month <= 3
    ):
        year += 1

    elif (
        current_month <= 3
        and
        month >= 10
    ):
        year -= 1

    return year


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

        href = a.get(
            "href",
            ""
        )

        if (
            "/collections/live/products/"
            not in href
        ):
            continue

        links.add(
            absolute_url(
                href
            )
        )

    return sorted(
        links
    )


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


def extract_total_pages(html):
    soup = BeautifulSoup(
        html,
        "html.parser"
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


def extract_heading(soup):
    h1 = soup.find(
        "h1"
    )

    if h1:
        return clean_text(
            h1.get_text(
                " ",
                strip=True
            )
        )

    title_tag = soup.find(
        "title"
    )

    if title_tag:
        return clean_text(
            title_tag.get_text(
                " ",
                strip=True
            )
        )

    return ""


def strip_title_datetime(title):
    return clean_text(
        re.sub(
            r"[（(]"
            r"\s*\d{1,2}"
            r"\s*/\s*"
            r"\d{1,2}"
            r"\s+"
            r"\d{1,2}:\d{2}"
            r"\s*[）)]"
            r"\s*$",
            "",
            title
        )
    )


def extract_performer_section(text):
    """
    ◆出演者
    AAA、BBB、CCC
    注意事項

    のような部分だけを抜く。
    """

    patterns = [
        r"◆出演者\s*(.+?)(?=注意事項)",
        r"出演者\s*(.+?)(?=注意事項)",
        r"◆出演者\s*(.+?)(?=◆)",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.S
        )

        if match:

            value = clean_text(
                match.group(1)
            )

            if value:
                return value

    return ""


def extract_price(text):
    patterns = [
        r"¥\s*[\d,]+\s*\(税込\)",
        r"¥\s*[\d,]+",
        r"￥\s*[\d,]+",
        r"[\d,]+\s*円",
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


def extract_archive_text(text):
    """
    公演ページ内に明示されている場合のみ拾う。
    無理に日付を推測しない。
    """

    candidates = []

    keywords = [
        "見逃し配信",
        "見逃し視聴",
        "アーカイブ",
        "視聴期限",
        "販売終了",
    ]

    lines = [
        clean_text(
            line
        )
        for line
        in text.splitlines()
    ]

    for line in lines:

        if not line:
            continue

        if any(
            keyword in line
            for keyword
            in keywords
        ):
            candidates.append(
                line
            )

    if not candidates:
        return ""

    return " / ".join(
        candidates[:3]
    )


def extract_archive_end(text):
    """
    例:
    見逃し視聴 9/20 23:59まで

    のような表記があれば
    YYYY-MM-DD HH:MM
    に変換する。
    """

    patterns = [
        (
            r"(?:見逃し配信|見逃し視聴|視聴期限|アーカイブ)"
            r".{0,40}?"
            r"(\d{1,2})"
            r"/"
            r"(\d{1,2})"
            r"\s*"
            r"(\d{1,2}:\d{2})"
        ),
        (
            r"(\d{1,2})"
            r"月"
            r"(\d{1,2})"
            r"日"
            r".{0,20}?"
            r"(\d{1,2}:\d{2})"
            r".{0,20}?"
            r"(?:まで|終了)"
        ),
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.S
        )

        if not match:
            continue

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
            month
        )

        return (
            f"{year:04d}-"
            f"{month:02d}-"
            f"{day:02d} "
            f"{time_text}"
        )

    return ""


def extract_status(text):
    if "販売終了" in text:
        return "販売終了"

    if "販売中" in text:
        return "販売中"

    return ""


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

    full_text_raw = soup.get_text(
        "\n",
        strip=True
    )

    full_text = clean_text(
        full_text_raw
    )

    performer_text = (
        extract_performer_section(
            full_text
        )
    )

    performer_ids = (
        performer_ids_from_text(
            performer_text
        )
    )

    if not performer_ids:
        return None

    datetime_info = (
        parse_title_datetime(
            title
        )
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
        month
    )

    date = (
        f"{year:04d}-"
        f"{month:02d}-"
        f"{day:02d}"
    )

    price = extract_price(
        full_text
    )

    archive_text = (
        extract_archive_text(
            full_text_raw
        )
    )

    archive_end = (
        extract_archive_end(
            full_text
        )
    )

    status = extract_status(
        full_text
    )

    event_id = re.sub(
        r"[^a-zA-Z0-9]+",
        "-",
        url.rstrip(
            "/"
        ).split(
            "/"
        )[-1]
    ).strip(
        "-"
    )

    return {
        "id": (
            "fany-stream-"
            +
            event_id
        ),

        "date": date,

        "startTime": start_time,

        "title": strip_title_datetime(
            title
        ),

        "performerIds": performer_ids,

        "performersText": performer_text,

        "price": price,

        "archive": archive_text,

        "archiveEnd": archive_end,

        "status": status,

        "source": (
            "FANYオンラインチケット"
        ),

        "sourceUrl": url,
    }


def load_existing():
    if not OUTPUT_FILE.exists():
        return []

    try:
        data = json.loads(
            OUTPUT_FILE.read_text(
                encoding="utf-8"
            )
        )

        if isinstance(
            data,
            list
        ):
            return data

        if isinstance(
            data,
            dict
        ):
            return data.get(
                "events",
                []
            )

    except Exception:
        pass

    return []


def merge_events(
    existing,
    current
):
    """
    URL単位で最新データに置き換える。
    """

    merged = {}

    for event in existing:

        source_url = (
            event.get(
                "sourceUrl",
                ""
            )
        )

        if not source_url:
            continue

        merged[
            source_url
        ] = event

    for event in current:

        source_url = (
            event.get(
                "sourceUrl",
                ""
            )
        )

        if not source_url:
            continue

        merged[
            source_url
        ] = event

    values = list(
        merged.values()
    )

    values.sort(
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

    return values


def main():
    print(
        "FANY配信取得開始"
    )

    first_html = (
        fetch_collection_page(
            1
        )
    )

    total_pages = (
        extract_total_pages(
            first_html
        )
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
            f"一覧 {page}/{total_pages}"
        )

        try:
            html = (
                fetch_collection_page(
                    page
                )
            )

            links = (
                extract_product_links(
                    html
                )
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
            0.3
        )

    print(
        "商品URL数:",
        len(
            product_links
        )
    )

    matched = []

    for index, url in enumerate(
        sorted(
            product_links
        ),
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
            0.25
        )

    existing = load_existing()

    merged = merge_events(
        existing,
        matched
    )

    output = {
        "updatedAt": (
            datetime.now()
            .astimezone()
            .isoformat()
        ),

        "source": (
            "FANY Online Ticket"
        ),

        "events": merged,
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
        "保存完了:",
        OUTPUT_FILE
    )

    print(
        "今回ヒット:",
        len(
            matched
        )
    )

    print(
        "保存件数:",
        len(
            merged
        )
    )


if __name__ == "__main__":
    main()
