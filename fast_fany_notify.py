
import json

from notify_line import (
    load_json,
    source_notification_key,
    stable_notification_key,
    loose_notification_key,
    get_ticket_send_events,
    build_ticket_blocks,
    load_stream_events,
)

FAST_EVENTS_FILE = "fast_fany_events.json"
EVENTS_FILE = "events.json"
NOTIFIED_FILE = "notified_events.json"
PERFORMERS_FILE = "performers.json"


def main():
    print("================================")
    print("FANY高速通知 判定テスト")
    print("LINE送信なし")
    print("================================")

    # 高速取得結果
    fast_data = load_json(
        FAST_EVENTS_FILE,
        None,
    )

    if not isinstance(fast_data, dict):
        raise RuntimeError(
            "高速取得データがありません"
        )

    fast_events = fast_data.get("events")

    if not isinstance(fast_events, list):
        raise RuntimeError(
            "高速取得データの形式が不正です"
        )

    # 既存カレンダー
    calendar_data = load_json(
        EVENTS_FILE,
        {"events": []},
    )

    if isinstance(calendar_data, list):
        old_events = calendar_data
    elif isinstance(calendar_data, dict):
        old_events = calendar_data.get(
            "events",
            [],
        )
    else:
        raise RuntimeError(
            "既存カレンダーの形式が不正です"
        )

    if not isinstance(old_events, list):
        raise RuntimeError(
            "既存公演データの形式が不正です"
        )

    # 通知履歴
    history = load_json(
        NOTIFIED_FILE,
        {},
    )

    stable_keys = set(
        history.get("stableKeys", [])
    )

    loose_keys = set(
        history.get("looseKeys", [])
    )

    source_keys = set(
        history.get("sourceKeys", [])
    )

    # カレンダー掲載済み公演も除外
    for event in old_events:
        if not isinstance(event, dict):
            continue

        stable_keys.add(
            stable_notification_key(event)
        )

        loose_keys.add(
            loose_notification_key(event)
        )

        source_key = source_notification_key(
            event
        )

        if source_key:
            source_keys.add(source_key)

    # 出演者設定
    config = load_json(
        PERFORMERS_FILE,
        {"performers": []},
    )

    performer_map = {
        performer["id"]: performer
        for performer in config.get(
            "performers",
            [],
        )
        if performer.get("id")
    }

    # 通知候補の判定
    candidates = get_ticket_send_events(
        fast_events,
        performer_map,
        stable_keys,
        loose_keys,
        source_keys,
    )

    # 同じ取得結果内での重複も除外
    unique = []
    seen_sources = set()
    seen_stable = set()
    seen_loose = set()

    for event in candidates:
        source_key = source_notification_key(
            event
        )
        stable_key = stable_notification_key(
            event
        )
        loose_key = loose_notification_key(
            event
        )

        if (
            source_key
            and source_key in seen_sources
        ):
            continue

        if stable_key in seen_stable:
            continue

        if loose_key in seen_loose:
            continue

        unique.append(event)

        if source_key:
            seen_sources.add(source_key)

        seen_stable.add(stable_key)
        seen_loose.add(loose_key)

    print(
        "FANY取得公演:",
        len(fast_events),
        "件",
    )

    print(
        "既存カレンダー:",
        len(old_events),
        "件",
    )

    print(
        "新規通知候補:",
        len(unique),
        "件",
    )

    # 既存のLINE表示形式でプレビュー
    blocks = build_ticket_blocks(
        unique,
        performer_map,
        load_stream_events(),
    )

    for index, block in enumerate(
        blocks,
        start=1,
    ):
        print("")
        print(
            "通知プレビュー",
            index,
        )
        print(block)

    print("")
    print("================================")
    print("判定テスト完了")
    print("LINE送信なし")
    print("通知履歴の変更なし")
    print("================================")


if __name__ == "__main__":
    main()
