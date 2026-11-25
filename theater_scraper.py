"""Read each theater's published schedule with the official page's browser request."""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from performer_matching import cast_matches
from notify_line import normalize_title

JST = timezone(timedelta(hours=9))
OUTPUT_FILE = "theater_events.json"
FEED = "https://feed-api.yoshimoto.co.jp/fany/theater/v1"

THEATERS = [
    {
        "id": "roppongi",
        "name": "六本木",
        "venue": "よしもと六本木シアター",
        "url": "https://roppongi.yoshimoto.co.jp/schedule/",
    },
    {
        "id": "jimbocho",
        "feedId": "jimbocho_manzaigekijyo",
        "name": "神保町",
        "venue": "神保町よしもと漫才劇場",
        "url": "https://jimbocho-manzaigekijyo.yoshimoto.co.jp/schedule/",
    },
    {
        "id": "shibuya",
        "feedId": "shibuya_manzaigekijyo",
        "name": "渋谷",
        "venue": "渋谷よしもと漫才劇場",
        "url": "https://shibuya-manzaigekijyo.yoshimoto.co.jp/schedule/",
    },
    {
        "id": "morinomiya",
        "feedId": "morinomiya_manzaigekijyo",
        "name": "森ノ宮",
        "venue": "森ノ宮よしもと漫才劇場",
        "url": "https://morinomiya-manzaigekijyo.yoshimoto.co.jp/schedule/",
    },
    {
        "id": "manzaigekijyo",
        "name": "よしもと漫才劇場",
        "venue": "よしもと漫才劇場",
        "url": "https://manzaigekijyo.yoshimoto.co.jp/schedule/",
    },
    {
        "id": "makuhari",
        "name": "幕張",
        "venue": "よしもと幕張イオンモール劇場",
        "url": "https://makuhari.yoshimoto.co.jp/schedule/",
    },
    {
        "id": "dotonbori",
        "name": "道頓堀",
        "venue": "Yogibo META VALLEY",
        "url": "https://dotonbori.yoshimoto.co.jp/schedule/",
    },
    {
        "id": "omiya",
        "name": "大宮",
        "venue": "大宮ラクーンよしもと劇場",
        "url": "https://omiya.yoshimoto.co.jp/schedule/",
    },
    {
        "id": "fukuoka",
        "feedId": "fukuokagekijyo",
        "name": "福岡",
        "venue": "よしもと福岡 大和証券劇場",
        "url": "https://fukuokagekijyo.yoshimoto.co.jp/schedule/",
    },
    {
        "id": "ngk",
        "name": "なんばグランド花月",
        "venue": "なんばグランド花月",
        "url": "https://ngk.yoshimoto.co.jp/schedule/",
    },
]


def make_theater_source_key(event):
    return "|".join((
        "theater", event["theaterId"], event["performerId"], event["date"],
        event["startTime"], normalize_title(event["title"]),
    ))


def plain(value, separator=" "):
    return BeautifulSoup(str(value or ""), "html.parser").get_text(separator, strip=True)


def cast_lines(value):
    soup = BeautifulSoup(str(value or ""), "html.parser")
    for tag in soup.select("br"):
        tag.replace_with("\n")
    for tag in soup.select("a, li, p, div"):
        tag.append("\n")
    return [line.strip() for line in soup.get_text().splitlines() if line.strip()]


def time_field(value):
    value = str(value or "")
    if value == "00:00":
        return ""
    return value if re.fullmatch(r"\d{1,2}:\d{2}", value) else ""


def parse_month(theater, year, month, rows, performers):
    events = []
    for row in rows:
        if row["date"][:7] != f"{year}/{month:02d}":
            continue
        event_date = date.fromisoformat(row["date"].replace("/", "-"))
        cast = cast_lines(row.get("memberHtml")) or cast_lines(row.get("member"))
        matches = [p["id"] for p in performers if cast_matches(cast, p)]
        event_id = str(row["id"])
        if not cast:
            print(f"出演者確認待ち: theater/{theater['id']}/{event_id} {event_date}", flush=True)
        for pid in matches:
            event = {
                "performerId": pid,
                "trackedPerformers": matches,
                "officialEventId": event_id,
                "date": event_date.isoformat(),
                "openTime": time_field(row.get("dateTime1")),
                "startTime": time_field(row.get("dateTime2")),
                "endTime": ("" if str(row.get("notice") or "").startswith("【終演時間非表示】")
                            else time_field(row.get("dateTime3"))),
                "title": plain(row.get("name")),
                "venue": theater["venue"],
                "source": "theater",
                "sourceUrl": theater["url"] + "?" + urlencode({"id": event_id}),
                "theaterId": theater["id"],
                "theaterName": theater["name"],
                "ticketUrl": public_url(row.get("url1")),
                "streamingUrl": public_url(row.get("url2")),
                "ticketStatus": "",
                "ticketNotice": plain(row.get("notice")),
                "ticketOptions": [],
                "salePeriods": [],
                "performersText": cast,
                "publishedVia": "theater",
                "hasStreaming": bool(row.get("price3") or public_url(row.get("url2"))),
                "streamingPrice": plain(row.get("price3")),
                "advancePrice": plain(row.get("price1")),
                "doorPrice": plain(row.get("price2")),
            }
            if not event["title"]:
                raise ValueError(f"Missing event title: {event_id}")
            event["theaterSourceKey"] = make_theater_source_key(event)
            events.append(event)
    return events


def public_url(value):
    value = str(value or "").strip()
    parts = urlsplit(value)
    return value if parts.scheme in ("https", "http") and parts.netloc else ""


def feed_rows(response, theater):
    parts = urlsplit(response.url)
    params = parse_qs(parts.query)
    if params.get("theater") != [theater.get("feedId", theater["id"])]:
        raise ValueError(f"Unexpected theater in schedule response: {params.get('theater')}")
    if params.get("venue") != ["01"]:
        raise ValueError(f"Unexpected venue in schedule response: {params.get('venue')}")
    if not response.ok:
        raise RuntimeError(f"Schedule feed HTTP {response.status}")
    try:
        first_day, last_day = [datetime.strptime(params[key][0], "%Y%m%d").date()
                               for key in ("date_from", "date_to")]
    except (KeyError, ValueError, IndexError) as error:
        raise ValueError("Missing or malformed schedule range") from error
    if first_day > last_day:
        raise ValueError("Invalid schedule range")
    rows = response.json()
    if not isinstance(rows, list):
        raise ValueError("Unexpected schedule feed shape")
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or not re.fullmatch(r"[A-Za-z0-9_-]+", str(row.get("id") or "")):
            raise ValueError("Invalid schedule event ID")
        event_date = date.fromisoformat(row["date"].replace("/", "-"))
        if not first_day <= event_date <= last_day:
            raise ValueError(f"Schedule event outside requested range: {event_date}")
        item = str(row["id"]), event_date
        if item in seen:
            raise ValueError(f"Duplicate schedule event {item}")
        seen.add(item)
    return rows


def scrape_theater(browser, theater, performers):
    page = browser.new_page(locale="ja-JP", timezone_id="Asia/Tokyo")
    try:
        def is_feed(response):
            return response.url.split("?", 1)[0] == FEED and response.request.method == "GET"

        with page.expect_response(is_feed, timeout=18_000) as response:
            navigation = page.goto(theater["url"], wait_until="domcontentloaded", timeout=18_000)
            if not navigation or not navigation.ok:
                raise RuntimeError("Schedule page navigation failed")
        rows = feed_rows(response.value, theater)
        if (page.locator("#theater").input_value() != theater.get("feedId", theater["id"])
                or page.locator("#venue").input_value() != "01"):
            raise ValueError("Schedule page theater or venue mismatch")
        tabs = page.locator(".calendar-month a[data-y][data-m]")
        tabs.first.wait_for(timeout=5_000)
        months = tabs.evaluate_all("tabs => tabs.map(a => [Number(a.dataset.y), Number(a.dataset.m)])")
        if len({tuple(m) for m in months}) != len(months):
            raise ValueError("Duplicate month tabs")
        expected = {(int(r["date"][:4]), int(r["date"][5:7])) for r in rows}
        if expected - {tuple(m) for m in months}:
            raise ValueError("Schedule feed contains dates outside available month tabs")
        events = []
        for year, month in months:
            date(year, month, 1)
            tab = page.locator(f'.calendar-month a[data-y="{year}"][data-m="{month}"]')
            tab.click(timeout=3_000)
            actual = page.locator(".calendar-month a.active").evaluate(
                "a => [Number(a.dataset.y), Number(a.dataset.m)]", timeout=3_000
            )
            if actual != [year, month]:
                raise ValueError(f"Month switch failed: {year}/{month}: {actual}")
            rendered = page.locator(".schedule .schedule-time[id]").evaluate_all(
                """nodes => nodes.map(node => [
                    node.id.slice(8),
                    node.closest('.schedule-block')?.id.slice(8)
                ])"""
            )
            for row_id, day in rendered:
                if not day or not day.startswith(f"{year}-{month:02d}-"):
                    raise ValueError(f"Schedule content month mismatch: {day}")
            expected_rows = sorted(
                (str(r["id"]), r["date"].replace("/", "-")) for r in rows
                if r["date"][:7] == f"{year}/{month:02d}"
            )
            if sorted(map(tuple, rendered)) != expected_rows:
                raise ValueError(f"Rendered schedule does not match feed: {year}/{month}")
            events.extend(parse_month(theater, year, month, rows, performers))
        return events
    finally:
        page.close()


def fetch_theater(theater, performers):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for attempt in range(2):
                try:
                    return scrape_theater(browser, theater, performers)
                except Exception as error:
                    if attempt:
                        raise
                    print(f"劇場再試行: {theater['id']} {error}", flush=True)
                    time.sleep(1)
        finally:
            browser.close()


def main():
    performers = json.loads(Path("performers.json").read_text())["performers"]
    results = []
    with ThreadPoolExecutor(max_workers=3) as workers:
        futures = {workers.submit(fetch_theater, theater, performers): theater for theater in THEATERS}
        for future in as_completed(futures):
            theater = futures[future]
            try:
                events = future.result()
                results.append(events)
                print(f"劇場完了: {theater['id']} {len(events)}件")
            except Exception as error:
                print(f"劇場取得失敗: {theater['id']} {error}")
    if not results:
        raise RuntimeError("全劇場取得失敗")
    path = Path(OUTPUT_FILE)
    previous = json.loads(path.read_text()) if path.exists() else {"events": []}
    old = previous if isinstance(previous, list) else previous["events"]
    merged = {make_theater_source_key(event): event for event in old}
    for events in results:
        merged.update({make_theater_source_key(event): event for event in events})
    path.write_text(json.dumps({"syncedAt": datetime.now(JST).isoformat(),
                                "events": list(merged.values())}, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
