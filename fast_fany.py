
import json
import time
import requests

from scraper import (
    HEADERS,
    scrape_fany,
    remove_duplicates,
    is_today_or_future,
)


PERFORMERS_FILE = "performers.json"
OUTPUT_FILE = "fast_fany_events.json"


def main():
    started = time.monotonic()

    with open(
        PERFORMERS_FILE,
        "r",
        encoding="utf-8",
    ) as file:
        config = json.load(file)

    performers = config.get(
        "performers",
        [],
    )

    session = requests.Session()
    session.headers.update(HEADERS)

    detail_cache = {}
    events = []

    for performer in performers:
        if not performer.get("name"):
            continue

        if "fany" not in performer.get(
            "sources",
            [],
        ):
            continue

        print(
            "FANY取得開始:",
            performer["name"],
            flush=True,
        )

        performer_started = time.monotonic()

        performer_events = scrape_fany(
            session,
            performer,
            detail_cache,
        )

        events.extend(performer_events)

        print(
            "FANY取得完了:",
            performer["name"],
            len(performer_events),
            "件",
            round(
                time.monotonic()
                - performer_started,
                1,
            ),
            "秒",
            flush=True,
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

    print(
        "FANY合計:",
        len(events),
        "件",
    )

    print(
        "取得時間:",
        round(
            time.monotonic() - started,
            1,
        ),
        "秒",
    )

    print(
        "LINE送信なし。取得テスト完了。",
    )


if __name__ == "__main__":
    main()
