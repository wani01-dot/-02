
import json
import time
import requests

from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)

from scraper import (
    HEADERS,
    scrape_fany,
    remove_duplicates,
    is_today_or_future,
)


PERFORMERS_FILE = "performers.json"
OUTPUT_FILE = "fast_fany_events.json"

# 同時取得する芸人の最大数
MAX_WORKERS = 3


# ==========================================
# 芸人1組のFANY取得
# ==========================================

def scrape_one_performer(performer):
    name = performer.get("name", "")

    started = time.monotonic()

    print(
        "FANY取得開始:",
        name,
        flush=True,
    )

    # 各スレッドで独立したSessionを使用
    session = requests.Session()
    session.headers.update(HEADERS)

    # 各スレッドで独立したキャッシュを使用
    detail_cache = {}

    try:
        events = scrape_fany(
            session,
            performer,
            detail_cache,
        )

        elapsed = round(
            time.monotonic() - started,
            1,
        )

        print(
            "FANY取得完了:",
            name,
            len(events),
            "件",
            elapsed,
            "秒",
            flush=True,
        )

        return {
            "name": name,
            "events": events,
            "elapsed": elapsed,
        }

    finally:
        session.close()


# ==========================================
# MAIN
# ==========================================

def main():
    started = time.monotonic()

    print(
        "================================",
        flush=True,
    )
    print(
        "FANY 並列取得テスト開始",
        flush=True,
    )
    print(
        "================================",
        flush=True,
    )

    with open(
        PERFORMERS_FILE,
        "r",
        encoding="utf-8",
    ) as file:
        config = json.load(file)

    performers = [
        performer
        for performer in config.get(
            "performers",
            [],
        )
        if (
            performer.get("name")
            and "fany" in performer.get(
                "sources",
                [],
            )
        )
    ]

    if not performers:
        raise RuntimeError(
            "FANY取得対象の芸人がいません"
        )

    print(
        "取得対象:",
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

    results = []
    failures = []

    # ======================================
    # 3組を同時に取得
    # ======================================

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
                results.append(result)

            except Exception as error:
                name = performer.get(
                    "name",
                    "不明",
                )

                failures.append(name)

                print(
                    "FANY取得失敗:",
                    name,
                    repr(error),
                    flush=True,
                )

    # ======================================
    # 取得結果をまとめる
    # ======================================

    events = []

    for result in results:
        events.extend(
            result["events"]
        )

    events = remove_duplicates(
        events
    )

    events = [
        event
        for event in events
        if is_today_or_future(
            event.get("date", "")
        )
    ]

    # ======================================
    # 一部でも失敗したら保存しない
    # ======================================

    if failures:
        print(
            "取得失敗:",
            " / ".join(failures),
            flush=True,
        )

        raise RuntimeError(
            "一部のFANY取得に失敗しました"
        )

    # ======================================
    # JSON保存
    # ======================================

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            {
                "events": events,
            },
            file,
            ensure_ascii=False,
            indent=2,
        )

    # ======================================
    # 結果表示
    # ======================================

    print(
        "",
        flush=True,
    )

    print(
        "================================",
        flush=True,
    )

    print(
        "FANY 並列取得結果",
        flush=True,
    )

    for performer in performers:
        name = performer["name"]

        result = next(
            (
                item
                for item in results
                if item["name"] == name
            ),
            None,
        )

        if result:
            print(
                name,
                len(result["events"]),
                "件",
                result["elapsed"],
                "秒",
                flush=True,
            )

    print(
        "--------------------------------",
        flush=True,
    )

    print(
        "FANY合計:",
        len(events),
        "件",
        flush=True,
    )

    print(
        "取得時間:",
        round(
            time.monotonic() - started,
            1,
        ),
        "秒",
        flush=True,
    )

    print(
        "LINE送信なし。取得テスト完了。",
        flush=True,
    )

    print(
        "================================",
        flush=True,
    )


if __name__ == "__main__":
    main()
