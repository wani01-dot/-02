import json
import re
from datetime import datetime, timezone
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup


# ==========================================
# ファイル設定
# ==========================================

PERFORMORMERS_FILE = "performers.json"
EVENTS_FILE = "events.json"
NEW_EVENTS_FILE = "new_events.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8",
}


# ==========================================
# 共通処理
# ==========================================

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    except FileNotFoundError:
        return default

    except json.JSONDecodeError:
        print(f"⚠️ {path} のJSON形式がおかしいです")
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


def clean_text(text):
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
        clean_text(event.get("title", "")).lower(),
        clean_text(event.get("venue", "")).lower(),
    ])


def get_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


# ==========================================
# FANY
# ==========================================

FANY_URL = "https://ticket.fany.lol/search/event"

DATE_RE = re.compile(
    r"^(20\d{2})/(\d{1,2})/(\d{1,2})"
)

START_RE = re.compile(
    r"開演\s*(\d{1,2}:\d{2})"
)


def get_fany_lines(html):
    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    lines = []

    for raw in soup.get_text("\n").splitlines():
        text = clean_text(raw)

        if text:
            lines.append(text)

    return lines


def is_sales_line(line):
    keywords = [
        "発売",
        "受付期間",
        "受付中",
        "受付終了",
        "受付前",
        "抽選",
        "先着",
        "FANY ID",
    ]

    return any(
        word in line
        for word in keywords
    )


def find_fany_performers(block):
    try:
        start = block.index("出演")
    except ValueError:
        return ""

    result = []

    for line in block[start + 1:]:

        if is_sales_line(line):
            break

        result.append(line)

    return " ".join(result)


def find_fany_venue(block):
    for line in block:

        if re.search(
            r"（[^）]*(?:都|道|府|県)）",
            line
        ):
            return line

    return ""


def find_fany_title(block):
    noise = {
        "日",
        "月",
        "火",
        "水",
        "木",
        "金",
        "土",
        "出演",
    }

    for line in block[1:]:

        if line in noise:
            continue

        if is_sales_line(line):
            continue

        if re.search(
            r"（[^）]*(?:都|道|府|県)）",
            line
        ):
            continue

        return line

    return "公演名不明"


def scrape_fany(session, performer):
    performer_id = performer["id"]
    performer_name = performer["name"]

    url = (
        FANY_URL
        + "?"
        + urlencode({
            "keywords": performer_name,
            "search_type": "search_string"
        })
    )

    print(f"🔎 FANY：{performer_name}")

    response = session.get(
        url,
        timeout=30
    )

    response.raise_for_status()

    lines = get_fany_lines(
        response.text
    )

    event_starts = []

    for index, line in enumerate(lines):

        if (
            DATE_RE.match(line)
            and "開演" in line
        ):
            event_starts.append(index)

    events = []

    for i, start in enumerate(event_starts):

        if i + 1 < len(event_starts):
            end = event_starts[i + 1]
        else:
            end = len(lines)

        block = lines[start:end]

        if not block:
            continue

        performers_text = (
            find_fany_performers(block)
        )

        if performer_name not in performers_text:
            continue

        date_match = DATE_RE.match(
            block[0]
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

        start_match = START_RE.search(
            block[0]
        )

        start_time = ""

        if start_match:
            start_time = start_match.group(1)

        title = find_fany_title(
            block
        )

        venue = find_fany_venue(
            block
        )

        events.append({
            "performerId": performer_id,
            "date": date,
            "startTime": start_time,
            "title": title,
            "venue": venue,
            "source": "fany",
            "sourceUrl": url,
        })

    print(f"   → {len(events)}件")

    return events


# ==========================================
# TIGET
# ==========================================

TIGET_BASE = "https://tiget.net"
TIGET_SEARCH = "https://tiget.net/events"


def scrape_tiget(session, performer):
    performer_id = performer["id"]
    performer_name = performer["name"]

    print(f"🔎 TIGET：{performer_name}")

    url = (
        TIGET_SEARCH
        + "?"
        + urlencode({
            "q[words]": performer_name
        })
    )

    try:
        response = session.get(
            url,
            timeout=30
        )

        response.raise_for_status()

    except Exception as e:
        print(f"   ⚠️ TIGET取得失敗：{e}")
        return []

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    events = []
    checked_urls = set()

    for link in soup.find_all(
        "a",
        href=True
    ):

        href = link.get("href", "")

        if not re.match(
            r"^/events/\d+",
            href
        ):
            continue

        event_url = urljoin(
            TIGET_BASE,
            href
        )

        if event_url in checked_urls:
            continue

        checked_urls.add(event_url)

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

        detail_text = clean_text(
            detail_soup.get_text(
                " ",
                strip=True
            )
        )

        if performer_name not in detail_text:
            continue

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

        time_match = re.search(
            r"(?:開演|START|start)"
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

        title = ""

        if detail_soup.title:
            title = clean_text(
                detail_soup.title.get_text()
            )

            title = re.sub(
                r"\s*[｜|]\s*TIGET.*$",
                "",
                title
            )

        if not title:
            title = clean_text(
                link.get_text(
                    " ",
                    strip=True
                )
            )

        venue = ""

        venue_match = re.search(
            r"(?:会場|場所)"
            r"\s*[:：]\s*"
            r"(.{1,80}?)"
            r"(?=\s(?:開場|開演|OPEN|START|出演|料金|チケット|$))",
            detail_text,
            re.IGNORECASE
        )

        if venue_match:
            venue = clean_text(
                venue_match.group(1)
            )

        events.append({
            "performerId": performer_id,
            "date": date,
            "startTime": start_time,
            "title": title or "公演名不明",
            "venue": venue,
            "source": "tiget",
            "sourceUrl": event_url,
        })

    print(f"   → {len(events)}件")

    return events


# ==========================================
# LivePocket
# ==========================================

LIVEPOCKET_BASE = "https://livepocket.jp"


def scrape_livepocket(session, performer):
    performer_id = performer["id"]
    performer_name = performer["name"]

    print(
        f"🔎 LivePocket：{performer_name}"
    )

    search_urls = [
        (
            "https://livepocket.jp/event/search?"
            + urlencode({
                "word": performer_name
            })
        ),
        (
            "https://livepocket.jp/e?"
            + urlencode({
                "keyword": performer_name
            })
        ),
    ]

    html = None

    for search_url in search_urls:

        try:
            response = session.get(
                search_url,
                timeout=25
            )

            if (
                response.status_code == 200
                and len(response.text) > 1000
            ):
                html = response.text
                break

        except Exception:
            pass

    if not html:
        print(
            "   ⚠️ LivePocket検索ページ取得失敗"
        )
        return []

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    event_urls = set()

    for link in soup.find_all(
        "a",
        href=True
    ):

        href = link["href"]

        if (
            "/e/" in href
            or "t.livepocket.jp/e/" in href
        ):
            event_urls.add(
                urljoin(
                    LIVEPOCKET_BASE,
                    href
                )
            )

    events = []

    for event_url in event_urls:

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

        detail_text = clean_text(
            detail_soup.get_text(
                " ",
                strip=True
            )
        )

        if performer_name not in detail_text:
            continue

        date_match = re.search(
            r"(20\d{2})年"
            r"(\d{1,2})月"
            r"(\d{1,2})日",
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

        title = ""

        if detail_soup.title:
            title = clean_text(
                detail_soup.title.get_text()
            )

        if not title:
            title = "公演名不明"

        venue = ""

        venue_match = re.search(
            r"(?:会場|場所)"
            r"\s*[:：]\s*"
            r"(.{1,80}?)"
            r"(?=\s(?:開場|開演|出演|料金|チケット|$))",
            detail_text
        )

        if venue_match:
            venue = clean_text(
                venue_match.group(1)
            )

        events.append({
            "performerId": performer_id,
            "date": date,
            "startTime": start_time,
            "title": title,
            "venue": venue,
            "source": "livepocket",
            "sourceUrl": event_url,
        })

    print(f"   → {len(events)}件")

    return events


# ==========================================
# 重複削除
# ==========================================

def remove_duplicates(events):
    result = []
    seen = set()

    for event in events:

        key = event_key(event)

        if key in seen:
            continue

        seen.add(key)
        result.append(event)

    return result


# ==========================================
# メイン
# ==========================================

def main():

    print(
        "================================"
    )

    print(
        "芸人出演情報スクレイピング開始"
    )

    print(
        "================================"
    )

    config = load_json(
        PERFORMORMERS_FILE,
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
            "❌ performers.json に芸人が登録されていません"
        )

        save_json(
            NEW_EVENTS_FILE,
            []
        )

        return

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

    session = get_session()

    all_events = []

    for performer in performers:

        performer_id = performer.get(
            "id",
            ""
        )

        performer_name = performer.get(
            "name",
            ""
        )

        if (
            not performer_id
            or not performer_name
        ):
            continue

        print()
        print(
            f"🎙️ {performer_name}"
        )

        sources = performer.get(
            "sources",
            ["fany"]
        )

        if "fany" in sources:

            try:
                events = scrape_fany(
                    session,
                    performer
                )

                all_events.extend(
                    events
                )

            except Exception as e:
                print(
                    f"   ❌ FANYエラー：{e}"
                )

        if "tiget" in sources:

            try:
                events = scrape_tiget(
                    session,
                    performer
                )

                all_events.extend(
                    events
                )

            except Exception as e:
                print(
                    f"   ❌ TIGETエラー：{e}"
                )

        if "livepocket" in sources:
            try:
                events = scrape_livepocket(
                    session,
                    performer
                )

                all_events.extend(
                    events
                )

            except Exception as e:
                print(
                    f"   ❌ LivePocketエラー：{e}"
                )
