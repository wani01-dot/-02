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


MAX_COLLECTION_PAGES = 80

COLLECTION_DELAY = 0.25

PRODUCT_DELAY = 0.35


# 対象外だった商品は
# 7日後にもう一度確認
NON_MATCH_CACHE_DAYS = 7


# 対象ライブは
# 12時間ごとに再確認
MATCH_CACHE_HOURS = 12


# 429再試行待機時間
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


        if response.status_code == 429:

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


            retry_after = response.headers.get(
                "Retry-After"
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


def parse_iso_datetime(value):

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

def extract_price(
    text
):

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

def extract_status(
    soup
):

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

def make_event_id(
    url
):

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
# 商品1件
# =========================================================

def scrape_product(
    url
):

    response = get_with_retry(
        url
    )


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

        return None


    if event_date < today_jst():

        return None


    status = extract_status(
        soup
    )


    if status == "販売終了":

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

def sort_events(
    events
):

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
        "====================================="
    )


    cache = load_cache()

    cache_items = cache[
        "items"
    ]


    product_links = (
        crawl_all_product_links()
    )


    print(
        "キャッシュ登録数:",
        len(
            cache_items
        )
    )


    previous_events = {}


    if OUTPUT_FILE.exists():

        try:

            old_data = json.loads(
                OUTPUT_FILE.read_text(
                    encoding="utf-8"
                )
            )


            for event in old_data.get(
                "events",
                []
            ):

                url = event.get(
                    "sourceUrl"
                )


                if url:

                    previous_events[
                        url
                    ] = event


        except Exception as exc:

            print(
                "旧イベント読込失敗:",
                exc
            )


    events_by_url = dict(
        previous_events
    )


    checked_count = 0

    cache_skip_count = 0

    hit_count = 0


    current_url_set = set(
        product_links
    )


    for index, url in enumerate(
        product_links,
        start=1
    ):

        cached = cache_items.get(
            url
        )


        if (
            cached
            and
            cache_is_fresh(
                cached
            )
        ):

            cache_skip_count += 1


            if cached.get(
                "matched"
            ):

                cached_event = cached.get(
                    "event"
                )


                if isinstance(
                    cached_event,
                    dict
                ):

                    event_date = cached_event.get(
                        "date",
                        ""
                    )


                    if (
                        event_date
                        >=
                        today_jst().isoformat()
                    ):

                        events_by_url[
                            url
                        ] = cached_event


            continue


        checked_count += 1


        print(
            f"詳細確認 "
            f"{index}/"
            f"{len(product_links)}"
        )


        try:

            event = scrape_product(
                url
            )


            cache_items[
                url
            ] = {
                "checkedAt": (
                    now_jst()
                    .isoformat()
                ),

                "matched": bool(
                    event
                ),

                "event": event,
            }


            if event:

                events_by_url[
                    url
                ] = event

                hit_count += 1


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
                    ]
                )


            else:

                events_by_url.pop(
                    url,
                    None
                )


        except Exception as exc:

            print(
                "  詳細取得失敗:",
                url,
                exc
            )


        # 途中で止まっても
        # キャッシュが残るように一定間隔で保存
        if (
            checked_count
            %
            50
            ==
            0
        ):

            save_cache(
                cache
            )


        time.sleep(
            PRODUCT_DELAY
        )


    # FANY一覧から消えたURLを
    # 表示対象から外す
    for url in list(
        events_by_url.keys()
    ):

        if url not in current_url_set:

            events_by_url.pop(
                url,
                None
            )


    # 過去イベントも削除
    today_text = (
        today_jst()
        .isoformat()
    )


    events = []


    for event in events_by_url.values():

        if (
            event.get(
                "date",
                ""
            )
            <
            today_text
        ):

            continue


        events.append(
            event
        )


    events = deduplicate_events(
        events
    )


    output = {
        "updatedAt": (
            now_jst()
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


    save_cache(
        cache
    )


    print(
        "====================================="
    )

    print(
        "商品URL数:",
        len(
            product_links
        )
    )

    print(
        "今回詳細確認:",
        checked_count,
        "件"
    )

    print(
        "キャッシュ省略:",
        cache_skip_count,
        "件"
    )

    print(
        "今回HIT:",
        hit_count,
        "件"
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
