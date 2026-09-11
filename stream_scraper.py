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

OUTPUT_FILE = Path(
    "stream_events.json"
)

JST = ZoneInfo(
    "Asia/Tokyo"
)


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

    "Accept-Language": (
        "ja-JP,ja;q=0.9"
    ),
}


# 万一FANY側のページがおかしくなっても
# 無限ループしないための安全装置
MAX_COLLECTION_PAGES = 80


# 一覧ページ間の待機
COLLECTION_DELAY = 0.20


# 商品詳細ページ間の待機
PRODUCT_DELAY = 0.20


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
        str(
            value or ""
        )
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

def resolve_year(
    month,
    day=None
):
    """
    FANY上で年表記がない場合、
    現在日を基準に自然な年を補完する。
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
    例:

    タイトル（9/18 19:00）
    タイトル (9/18 19:00)
    タイトル（9/18　19:00）
    タイトル（9月18日 19:00）
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

            "time": (
                match.group(3)
            ),
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
# FANY一覧
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

        url = absolute_url(
            href.split(
                "?"
            )[0]
        )

        links.add(
            url
        )

    return sorted(
        links
    )


def crawl_all_product_links():
    """
    FANY一覧を1ページずつ進む。

    ページ数表示には依存しない。

    新しい商品URLが
    1件も出なくなった時点で終了する。
    """

    all_links = set()

    previous_page_links = None

    print(
        "一覧ページ巡回開始"
    )

    for page in range(
        1,
        MAX_COLLECTION_PAGES + 1
    ):

        print(
            f"一覧 {page}ページ目"
        )

        try:

            html = fetch_collection_page(
                page
            )

        except Exception as exc:

            print(
                "  一覧取得失敗:",
                exc
            )

            print(
                "  一覧巡回終了"
            )

            break


        page_links = set(
            extract_product_links(
                html
            )
        )


        print(
            "  このページ:",
            len(
                page_links
            ),
            "件"
        )


        # 商品が完全にゼロなら終了
        if not page_links:

            print(
                "  商品がないため終了"
            )

            break


        # FANYが存在しないページを
        # 最終ページへリダイレクトする場合への対策
        if (
            previous_page_links
            is not None
            and
            page_links
            ==
            previous_page_links
        ):

            print(
                "  前ページと同じ内容のため終了"
            )

            break


        new_links = (
            page_links
            -
            all_links
        )


        print(
            "  新規:",
            len(
                new_links
            ),
            "件"
        )


        # URL自体はあるが
        # 全部すでに取得済みなら終了
        if not new_links:

            print(
                "  新しい商品がないため終了"
            )

            break


        all_links.update(
            new_links
        )


        print(
            "  累計:",
            len(
                all_links
            ),
            "件"
        )


        previous_page_links = (
            page_links
        )


        time.sleep(
            COLLECTION_DELAY
        )


    print(
        "一覧巡回完了"
    )

    print(
        "商品URL総数:",
        len(
            all_links
        )
    )


    return sorted(
        all_links
    )


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


def extract_performer_section(
    raw_text
):
    """
    ◆出演者 の次から、
    次の見出しまでを取得する。

    長い正規表現を使わず、
    1行ずつ確認する方式。
    """

    lines = raw_text.splitlines()

    collecting = False

    collected = []

    for raw_line in lines:

        line = clean_text(
            raw_line
        )

        if not line:
            continue


        if not collecting:

            if (
                line == "◆出演者"
                or
                line == "出演者"
                or
                line.startswith(
                    "◆出演者"
                )
            ):

                collecting = True


                remainder = re.sub(
                    r"^◆?\s*出演者\s*",
                    "",
                    line
                )


                if remainder:

                    collected.append(
                        remainder
                    )

            continue


        # 次の項目・見出しに来たら終了
        if (
            line.startswith(
                "◆"
            )
            or
            line.startswith(
                "【"
            )
            or
            line.startswith(
                "＜"
            )
            or
            line.startswith(
                "注意事項"
            )
        ):

            break


        collected.append(
            line
        )


    return clean_text(
        " ".join(
            collected
        )
    )


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
    注意書きに含まれる
    「販売終了」を拾わないようにする。
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

        if len(
            text
        ) > 50:

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

def extract_archive_lines(
    raw_text
):
    """
    本当にアーカイブに関係する行だけ取得する。
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


def extract_archive_text(
    raw_text
):

    lines = extract_archive_lines(
        raw_text
    )

    if not lines:

        return ""

    return " / ".join(
        lines
    )


def extract_archive_end(
    raw_text
):
    """
    アーカイブ関連文の中だけから
    日時を取得する。
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


    performer_text = (
        extract_performer_section(
            raw_text
        )
    )


    performer_ids = (
        performer_ids_from_text(
            performer_text
        )
    )


    # めぞん・ピュート・軟水の
    # どれも出演していない場合は除外
    if not performer_ids:

        return None


    datetime_info = (
        parse_title_datetime(
            title
        )
    )


    if not datetime_info:

        print(
            "  日時取得失敗:",
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
            "  日付不正:",
            title
        )

        return None


    # 過去公演は除外
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

        "date": (
            event_date.isoformat()
        ),

        "startTime": (
            start_time
        ),

        "title": (
            strip_title_datetime(
                title
            )
        ),

        "performerIds": (
            performer_ids
        ),

        "performersText": (
            performer_text
        ),

        "price": (
            price
        ),

        "archive": (
            archive
        ),

        "archiveEnd": (
            archive_end
        ),

        "status": (
            status
            or
            "販売状況不明"
        ),

        "source": (
            "FANYオンラインチケット"
        ),

        "sourceUrl": (
            url
        ),
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


def deduplicate_events(
    events
):

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


    # ---------------------------------
    # FANY一覧を最後まで巡回
    # ---------------------------------

    product_links = (
        crawl_all_product_links()
    )


    print(
        "====================================="
    )

    print(
        "詳細ページ確認開始"
    )

    print(
        "商品URL数:",
        len(
            product_links
        )
    )

    print(
        "====================================="
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
                "  詳細取得失敗:",
                url,
                exc
            )


        time.sleep(
            PRODUCT_DELAY
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

        "events": (
            events
        ),
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
