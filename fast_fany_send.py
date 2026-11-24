
import json
import os

from notify_line import (
    load_json,
    save_json,
    send_line,
    source_notification_key,
    stable_notification_key,
    loose_notification_key,
    get_ticket_send_events,
    build_line_digest,
    load_stream_events,
)

FAST_EVENTS_FILE = "fast_fany_events.json"
EVENTS_FILE = "events.json"
NOTIFIED_FILE = "notified_events.json"
PERFORMERS_FILE = "performers.json"

# ワークフロー側で明示的に許可するまで送信しない
SEND_ENABLED = (
    os.environ.get("FAST_FANY_SEND", "")
    == "true"
)


def read_events(path, required=False):
    data = load_json(path, None)

    if data is None:
        if required:
            raise RuntimeError(
                f"{path} が見つかりません"
            )
        return []

    if isinstance(data, list):
        events = data
    elif isinstance(data, dict):
        events = data.get("events")
    else:
        events = None

    if not isinstance(events, list):
        raise RuntimeError(
            f"{path} の形式が不正です"
        )

    if not all(
        isinstance(event, dict)
        for event in events
    ):
        raise RuntimeError(
            f"{path} に不正な公演データがあります"
        )

    return events


def event_keys(event):
    return (
        source_notification_key(event),
        stable_notification_key(event),
        loose_notification_key(event),
    )


def register_event(
    event,
    source_keys,
    stable_keys,
    loose_keys,
):
    source_key, stable_key, loose_key = (
        event_keys(event)
    )

    if source_key:
        source_keys.add(source_key)

    stable_keys.add(stable_key)
    loose_keys.add(loose_key)


def main():
    print("================================")
    print("FANY高速LINE通知")
    print(
        "送信モード:",
        "有効" if SEND_ENABLED else "確認のみ",
    )
    print("================================")

    fast_events = read_events(
        FAST_EVENTS_FILE,
        required=True,
    )

    old_events = read_events(
        EVENTS_FILE,
        required=True,
    )

    config = load_json(
        PERFORMERS_FILE,
        {},
    )

    performers = config.get(
        "performers",
        [],
    )

    if not isinstance(performers, list):
        raise RuntimeError(
            "出演者設定が不正です"
        )

    performer_map = {
        performer["id"]: performer
        for performer in performers
        if isinstance(performer, dict)
        and performer.get("id")
    }

    history = load_json(
        NOTIFIED_FILE,
        {},
    )

    if not isinstance(history, dict):
        raise RuntimeError(
            "通知履歴の形式が不正です"
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

    # カレンダーに掲載済みの公演も通知対象外
    for event in old_events:
        register_event(
            event,
            source_keys,
            stable_keys,
            loose_keys,
        )

    candidates = get_ticket_send_events(
        fast_events,
        performer_map,
        stable_keys,
        loose_keys,
        source_keys,
    )

    # 同じ取得結果内での重複を除外
    unique = []
    seen_source = set()
    seen_stable = set()
    seen_loose = set()

    for event in candidates:
        source_key, stable_key, loose_key = (
            event_keys(event)
        )

        if source_key and source_key in seen_source:
            continue

        if stable_key in seen_stable:
            continue

        if loose_key in seen_loose:
            continue

        unique.append(event)

        if source_key:
            seen_source.add(source_key)

        seen_stable.add(stable_key)
        seen_loose.add(loose_key)

    print("FANY取得:", len(fast_events))
    print("既存公演:", len(old_events))
    print("新規候補:", len(unique))

    if not unique:
        print("通知する新着公演はありません")
        return

    message = build_line_digest(unique, [], load_stream_events())
    if not SEND_ENABLED:
        print(json.dumps(message, ensure_ascii=False, indent=2))
        print("LINE送信なし")
        print("通知履歴の変更なし")
        return

    send_line(message)
    for event in unique:
        register_event(event, source_keys, stable_keys, loose_keys)
    save_json(
        NOTIFIED_FILE,
        {
            "stableKeys": sorted(stable_keys),
            "looseKeys": sorted(loose_keys),
            "sourceKeys": sorted(source_keys),
        },
    )

    print("FANY高速LINE通知処理完了")


if __name__ == "__main__":
    main()
