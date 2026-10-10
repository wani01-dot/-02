"""Parallel performer scraping for scraper.py.

Each performer gets an independent requests.Session and FANY detail cache.
The original performer order is preserved in the returned event list.
"""

import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests


MAX_WORKERS = 3
SOURCE_NAMES = ("fany", "tiget", "eplus", "livepocket")


def scrape_all_parallel(performers, headers, scrapers):
    valid = [p for p in performers if p.get("name") and p.get("id")]
    if not valid:
        raise RuntimeError("取得対象の芸人がありません")

    def scrape_one(performer):
        name = performer["name"]
        sources = performer.get("sources", ["fany", "tiget"])
        session = requests.Session()
        session.headers.update(headers)
        cache = {}
        events = []
        errors = []
        timings = {}
        started = time.monotonic()

        try:
            for source in SOURCE_NAMES:
                if source not in sources:
                    continue
                began = time.monotonic()
                print(f"[{name}] {source} 開始", flush=True)
                try:
                    if source == "fany":
                        result = scrapers[source](session, performer, cache)
                    else:
                        result = scrapers[source](session, performer)
                    if not isinstance(result, list):
                        raise TypeError(f"{source} の戻り値がリストではありません")
                    events.extend(result)
                    print(f"[{name}] {source}: {len(result)} 件", flush=True)
                except Exception as exc:
                    message = f"{name} / {source}: {type(exc).__name__}: {exc}"
                    errors.append(message)
                    print(f"取得エラー: {message}", flush=True)
                    traceback.print_exc()
                finally:
                    timings[source] = round(time.monotonic() - began, 2)
        finally:
            session.close()

        return {
            "events": events,
            "errors": errors,
            "timings": timings,
            "seconds": round(time.monotonic() - started, 2),
        }

    results = {}
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(valid))) as executor:
        futures = {executor.submit(scrape_one, p): p for p in valid}
        for future in as_completed(futures):
            performer = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {
                    "events": [],
                    "errors": [f"{performer['name']} / スレッド異常: {exc}"],
                    "timings": {},
                    "seconds": 0,
                }
                traceback.print_exc()
            results[performer["id"]] = result
            print(f"完了: {performer['name']} {len(result['events'])}件 / {result['seconds']}秒", flush=True)

    errors = [err for p in valid for err in results[p["id"]]["errors"]]
    if errors:
        raise RuntimeError("並列取得でエラーが発生したため、既存データを維持します:\n" + "\n".join(errors))

    all_events = []
    for performer in valid:
        all_events.extend(results[performer["id"]]["events"])
    return all_events
