import hashlib
import json
import re
import time

from datetime import datetime, date, timedelta
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

CACHE_FILE = Path(
    "stream_cache.json"
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


session = requests.Session()

session.headers.update(
    HEADERS
)


# 一覧巡回の安全上限
MAX_COLLECTION_PAGES = 80


# 一覧ページ間の待機
COLLECTION_DELAY = 0.25


# 詳細ページ間の待機
PRODUCT_DELAY = 0.35


# 対象外商品は7日後に再確認
NON_MATCH_CACHE_DAYS = 7


# 対象商品は12時間ごとに再確認
MATCH_CACHE_HOURS = 12


# 期限切れになった対象外商品を
# 1回の実行で再確認する最大件数
MAX_STALE_NON_MATCH_RECHECKS = 20


# 429などの再試行待機
RETRY_WAIT_SECONDS = [
    5,
    15,
    30,
    60,
]


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


def now_jst():

    return datetime.now(
        JST
    )


def today_jst():

    return now_jst().date()


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
# HTTP
# =========================================================

def get_with_retry(
    url,
    timeout=30
):

    attempts = (
        len(
            RETRY_WAIT_SECONDS
        )
        +
        1
    )


    for attempt in range(
        attempts
    ):

        try:

            response = session.get(
                url,
                timeout=timeout
            )

        except requests.RequestException as exc:

            if (
                attempt
                >=
                attempts - 1
            ):

                raise


            wait = RETRY_WAIT_SECONDS[
                min(
                    attempt,
                    len(
                        RETRY_WAIT_SECONDS
                    ) - 1
                )
            ]


            print(
                "  通信エラー:",
                exc
            )

            print(
                f"  {wait}秒待って再試行"
            )


            time.sleep(
                wait
            )

            continue


        if (
            response.status_code
            ==
            429
        ):

            if (
                attempt
                >=
                attempts - 1
            ):

                response.raise_for_status()


            wait = RETRY_WAIT_SECONDS[
                min(
                    attempt,
                    len(
                        RETRY_WAIT_SECONDS
                    ) - 1
                )
            ]


            retry_after = (
                response.headers.get(
                    "Retry-After"
                )
            )


            if retry_after:

                try:

                    wait = max(
                        wait,
                        int(
                            retry_after
                        )
                    )

                except ValueError:

                    pass


            print(
                "  429 Too Many Requests"
            )

            print(
                f"  {wait}秒待って再試行"
            )


            time.sleep(
                wait
            )

            continue


        if (
            response.status_code
            >=
            500
        ):

            if (
                attempt
                >=
                attempts - 1
            ):

                response.raise_for_status()


            wait = RETRY_WAIT_SECONDS[
                min(
                    attempt,
                    len(
                        RETRY_WAIT_SECONDS
                    ) - 1
                )
            ]


            print(
                "  サーバーエラー:",
                response.status_code
            )

            print(
                f"  {wait}秒待って再試行"
            )


            time.sleep(
                wait
            )

            continue


        response.raise_for_status()

        return response


    raise RuntimeError(
        "HTTP取得に失敗しました"
    )


# =========================================================
# キャッシュ
# =========================================================

def load_cache():

    if not CACHE_FILE.exists():

        return {
            "version": 1,
            "items": {},
        }


    try:

        data = json.loads(
            CACHE_FILE.read_text(
                encoding="utf-8"
            )
        )

    except Exception as exc:

        print(
            "キャッシュ読込失敗:",
            exc
        )

        return {
            "version": 1,
            "items": {},
        }


    if not isinstance(
        data,
        dict
    ):

        return {
            "version": 1,
            "items": {},
        }


    if not isinstance(
        data.get(
            "items"
        ),
        dict
    ):

        data[
            "items"
        ] = {}


    return data


def parse_iso_datetime(
    value
):

    if not value:

        return None


    try:

        dt = datetime.fromisoformat(
            value
        )

    except Exception:

        return None


    if dt.tzinfo is None:

        dt = dt.replace(
            tzinfo=JST
        )


    return dt.astimezone(
        JST
    )


def cache_is_fresh(
    item
):

    checked_at = parse_iso_datetime(
        item.get(
            "checkedAt",
            ""
        )
    )


    if not checked_at:

        return False


    matched = bool(
        item.get(
            "matched",
            False
        )
    )


    if matched:

        expires_at = (
            checked_at
            +
            timedelta(
                hours=MATCH_CACHE_HOURS
            )
        )

    else:

        expires_at = (
            checked_at
            +
            timedelta(
                days=NON_MATCH_CACHE_DAYS
            )
        )


    return (
        now_jst()
        <
        expires_at
    )


def save_cache(
    cache
):

    cache[
        "version"
    ] = 1


    cache[
        "updatedAt"
    ] = (
        now_jst()
        .isoformat()
    )


    CACHE_FILE.write_text(
        json.dumps(
            cache,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


# =========================================================
# 年
# =========================================================

def resolve_year(
    month,
    day=None
):

    now = now_jst()

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

def parse_title_datetime(
    title
):

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


def strip_title_datetime(
    title
):

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

def fetch_collection_page(
    page
):

    url = (
        f"{LIVE_COLLECTION_URL}"
        f"?page={page}"
    )


    response = get_with_retry(
        url
    )


    return response.text


def extract_product_links(
    html
):

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


def crawl_all_product_links():

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


        if not page_links:

            print(
                "  商品がないため終了"
            )

            break


        if (
            previous_page_links
            is not None
            and
            page_links
            ==
            previous_page_links
        ):

            print(
                "  前ページと同じため終了"
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
# 詳細
# =========================================================

def extract_heading(
    soup
):

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


        if (
            line.startswith(
                "◆"
            )
            or
            line.startswith(
                "
