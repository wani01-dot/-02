
import json
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests

from scraper import (
    HEADERS,
    PERFORMERS_FILE,
    EVENTS_FILE,
    load_json,
    save_json,
    scrape_fany,
    scrape_tiget,
    scrape_eplus,
    scrape_livepocket,
    sanitize_event_performers,
    is_today_or_future,
    remove_duplicates,
    attach_tracked_performers,
    attach_ticket_sale_keys,
    identity_key,
)

OUTPUT_FILE = "fast_scraper_test_events.json"
REPORT_FILE = "fast_scraper_report.json"

MAX_WORKERS = 3

SOURCE_NAMES = (
    "fany",
    "tiget",
    "eplus",
    "livepocket",
)


def get_events(data):
    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        events = data.get("events", [])
        if isinstance(events, list):
            return events

    return []


def count_by_source(events):
    return {
        source: sum(
            1
            for event in events
            if event.get("source") == source
        )
        for source in SOURCE_NAMES
    }


def count_details(events):
    return {
        "events": len(events),
        "ticketStatus": sum(
            bool(event.get("ticketStatus"))
            for event in events
        ),
        "ticketOptionEvents": sum(
            bool(event.get("ticketOptions"))
            for event in events
        ),
        "ticketOptions": sum(
            len(event.get("ticketOptions") or [])
            for event in events
        ),
        "saleStartAt": sum(
            bool(event.get("saleStartAt"))
            for event in events
        ),
        "ticketOptionSaleStarts": sum(
            bool(option.get("saleStartAt"))
            for event in events
            for option in (
                event.get("ticketOptions") or []
            )
        ),
        "advancePeriods": sum(
            period.get("category") == "advance"
            for event in events
            for period in (
                event.get("salePeriods") or []
            )
        ),
        "firstComePeriods": sum(
            period.get("category") == "first_come"
            for event in events
            for period in (
                event.get("salePeriods") or []
            )
        ),
        "performerDetails": sum(
            bool(event.get("performersText"))
            for event in events
        ),
        "openTimes": sum(
            bool(event.get("openTime"))
            for event in events
        ),
    }


def scrape_one_performer(performer):
    name = performer["name"]
    performer_id = performer["id"]

    sources = performer.get(
        "sources",
        ["fany", "tiget"],
    )

    started = time.monotonic()

    session = requests.Session()
    session.headers.update(HEADERS)

    # キャッシュはスレッドごとに独立。
    # 共有辞書の競合を防ぐ。
    fany_detail_cache = {}

    events = []
    errors = []
    source_times = {}

    try:
        for source in SOURCE_NAMES:
            if source not in sources:
                continue

            source_started = time.monotonic()

            print(
                f"[{name}] {source} 開始",
                flush=True,
            )

            try:
                if source == "fany":
                    result = scrape_fany(
                        session,
                        performer,
                        fany_detail_cache,
                    )

                elif source == "tiget":
                    result = scrape_tiget(
                        session,
                        performer,
                    )

                elif source == "eplus":
                    result = scrape_eplus(
                        session,
                        performer,
                    )

                elif source == "livepocket":
                    result = scrape_livepocket(
                        session,
                        performer,
                    )

                else:
                    result = []

                if not isinstance(result, list):
                    raise TypeError(
                        f"{source} の戻り値がリストではありません"
                    )

                events.extend(result)

                print(
                    f"[{name}] {source}: "
                    f"{len(result)} 件",
                    flush=True,
                )

            except Exception as error:
                message = (
                    f"{name} / {source}: "
                    f"{type(error).__name__}: {error}"
                )

                errors.append(message)

                print(
                    "取得エラー:",
                    message,
                    flush=True,
                )

                traceback.print_exc()

            finally:
                source_times[source] = round(
                    time.monotonic() - source_started,
                    2,
                )

    finally:
        session.close()

    return {
        "performerId": performer_id,
        "name": name,
        "events": events,
        "errors": errors,
        "sourceTimes": source_times,
        "seconds": round(
            time.monotonic() - started,
            2,
        ),
    }


def main():
    print("=" * 50, flush=True)
    print("通常サイト 並列取得テスト", flush=True)
    print("LINE送信なし / 本番データ更新なし", flush=True)
    print("=" * 50, flush=True)

    started = time.monotonic()

    config = load_json(
        PERFORMERS_FILE,
        {"performers": []},
    )

    performers = [
        performer
        for performer in config.get(
            "performers", []
        )
        if performer.get("id")
        and performer.get("name")
    ]

    if not performers:
        raise RuntimeError(
            "performers.json に対象芸人がありません"
        )

    print(
        "対象:",
        " / ".join(
            performer["name"]
            for performer in performers
        ),
        flush=True,
    )

    print(
        "並列数:",
        min(MAX_WORKERS, len(performers)),
        flush=True,
    )

    results = {}

    with ThreadPoolExecutor(
        max_workers=min(
            MAX_WORKERS,
            len(performers),
        )
    ) as executor:

        futures = {
            executor.submit(
                scrape_one_performer,
                performer,
            ): performer
            for performer in performers
        }

        for future in as_completed(futures):
            performer = futures[future]

            try:
                result = future.result()

            except Exception as error:
                result = {
                    "performerId": performer["id"],
                    "name": performer["name"],
                    "events": [],
                    "errors": [
                        f"スレッド異常終了: {error}"
                    ],
                    "sourceTimes": {},
                    "seconds": 0,
                }

                traceback.print_exc()

            results[performer["id"]] = result

            print(
                f"完了: {result['name']} "
                f"{len(result['events'])}件 / "
                f"{result['seconds']}秒",
                flush=True,
            )

    # スレッド完了順ではなく、
    # performers.json の登録順で結合する。
    all_events = []

    for performer in performers:
        result = results[performer["id"]]
        all_events.extend(result["events"])

    # 本番と同じ後処理
    all_events = sanitize_event_performers(
        all_events
    )

    all_events = [
        event
        for event in all_events
        if is_today_or_future(
            event.get("date", "")
        )
    ]

    all_events = remove_duplicates(
        all_events
    )

    attach_tracked_performers(
        all_events
    )

    attach_ticket_sale_keys(
        all_events
    )

    all_events.sort(
        key=lambda event: (
            event.get("date", ""),
            event.get("startTime", ""),
            event.get("performerId", ""),
        )
    )

    elapsed = round(
        time.monotonic() - started,
        2,
    )

    # テスト専用ファイルに保存。
    # events.json は上書きしない。
    save_json(
        OUTPUT_FILE,
        {
            "syncedAt": datetime.now(
                timezone.utc
            ).isoformat(),
            "performers": performers,
            "events": all_events,
        },
    )

    baseline_data = load_json(
        EVENTS_FILE,
        {"events": []},
    )

    baseline_events = get_events(
        baseline_data
    )

    baseline_keys = {
        identity_key(event)
        for event in baseline_events
    }

    fast_keys = {
        identity_key(event)
        for event in all_events
    }

    missing_keys = sorted(
        baseline_keys - fast_keys
    )

    extra_keys = sorted(
        fast_keys - baseline_keys
    )

    errors = [
        error
        for result in results.values()
        for error in result["errors"]
    ]

    report = {
        "elapsedSeconds": elapsed,
        "baseline": {
            "sources": count_by_source(
                baseline_events
            ),
            "details": count_details(
                baseline_events
            ),
        },
        "fast": {
            "sources": count_by_source(
                all_events
            ),
            "details": count_details(
                all_events
            ),
        },
        "performers": [
            {
                "name": results[
                    performer["id"]
                ]["name"],
                "seconds": results[
                    performer["id"]
                ]["seconds"],
                "sourceTimes": results[
                    performer["id"]
                ]["sourceTimes"],
                "errors": results[
                    performer["id"]
                ]["errors"],
            }
            for performer in performers
        ],
        "missingIdentityKeys": missing_keys,
        "extraIdentityKeys": extra_keys,
        "errors": errors,
    }

    save_json(
        REPORT_FILE,
        report,
    )

    print("")
    print("=" * 50)
    print("並列取得テスト結果")
    print("=" * 50)

    print(
        "取得時間:",
        elapsed,
        "秒",
    )

    print("")
    print("サイト別件数")
    print("サイト         既存    並列")

    baseline_counts = count_by_source(
        baseline_events
    )

    fast_counts = count_by_source(
        all_events
    )

    for source in SOURCE_NAMES:
        print(
            f"{source:12s} "
            f"{baseline_counts[source]:5d} "
            f"{fast_counts[source]:7d}"
        )

    print("")
    print("詳細データ比較")

    baseline_details = count_details(
        baseline_events
    )

    fast_details = count_details(
        all_events
    )

    for key in baseline_details:
        print(
            f"{key}: "
            f"{baseline_details[key]} "
            f"→ {fast_details[key]}"
        )

    print("")
    print("出演者別処理時間")

    for performer in performers:
        result = results[
            performer["id"]
        ]

        print(
            result["name"],
            result["seconds"],
            "秒",
        )

        for source, seconds in (
            result["sourceTimes"].items()
        ):
            print(
                f"  {source}: {seconds} 秒"
            )

    print("")
    print(
        "既存にあって並列版にない公演:",
        len(missing_keys),
    )

    print(
        "並列版にあって既存にない公演:",
        len(extra_keys),
    )

    print(
        "取得エラー:",
        len(errors),
    )

    if missing_keys:
        print("")
        print("不足公演キー（先頭20件）")

        for key in missing_keys[:20]:
            print("MISSING:", key)

    if extra_keys:
        print("")
        print("追加公演キー（先頭20件）")

        for key in extra_keys[:20]:
            print("EXTRA:", key)

    if errors:
        print("")
        print("エラー一覧")

        for error in errors:
            print("ERROR:", error)

    print("")
    print(
        "テストデータ:",
        OUTPUT_FILE,
    )
    print(
        "比較レポート:",
        REPORT_FILE,
    )
    print("=" * 50)

    # 取得エラーが発生した場合は
    # テストを失敗扱いにする。
    if errors:
        raise RuntimeError(
            "一部サイトで取得エラーが発生しました"
        )


if __name__ == "__main__":
    main()
