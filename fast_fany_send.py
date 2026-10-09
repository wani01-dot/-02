
import os

from notify_line import (
    load_json,
    save_json,
    send_line,
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

    blocks = build_ticket_blocks(
        unique,
        performer_map,
        load_stream_events(),
    )

    if not SEND_ENABLED:
        for index, block in enumerate(
            blocks,
            start=1,
        ):
            print("")
            print(f"通知プレビュー {index}")
            print(block)

        print("")
        print("LINE送信なし")
        print("通知履歴の変更なし")
        return

    # LINEテキストメッセージの上限を確認
    # 送信できない長文は送信前に停止する
    for block in blocks:
        if len(block) > 5000:
            raise RuntimeError(
                "LINEメッセージが5000文字を超えています"
            )

    # 1公演グループずつ送信する
    # 送信成功後、対応する公演を通知済みに登録
    from notify_line import group_ticket_events

    groups = list(
        group_ticket_events(unique).values()
    )

    if len(groups) != len(blocks):
        raise RuntimeError(
            "通知グループの数が一致しません"
        )

    for group, block in zip(groups, blocks):
        send_line(block)

        for event in group["events"]:
            register_event(
                event,
                source_keys,
                stable_keys,
                loose_keys,
            )

        save_json(
            NOTIFIED_FILE,
            {
                "stableKeys": sorted(stable_keys),
                "looseKeys": sorted(loose_keys),
                "sourceKeys": sorted(source_keys),
            },
        )

        print(
            "LINE送信成功・履歴をローカル保存:",
            len(group["events"]),
            "件",
        )

    print("FANY高速LINE通知処理完了")


if __name__ == "__main__":
    main()
