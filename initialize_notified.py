import json
import re


EVENTS_FILE = "events.json"
NOTIFIED_FILE = "notified_events.json"


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


def clean(text):
    return re.sub(
        r"\s+",
        " ",
        str(text or "")
    ).strip()


def normalize_title(text):
    text = clean(text).lower()

    for char in [
        " ",
        "　",
        "「",
        "」",
        "『",
        "』",
        "【",
        "】",
        "・",
        "！",
        "!",
        "？",
        "?",
        "：",
        ":",
        "〜",
        "～",
    ]:
        text = text.replace(char, "")

    return text


def normalize_venue(text):
    return (
        clean(text)
        .lower()
        .replace(" ", "")
        .replace("　", "")
    )


def stable_notification_key(event):
    return "|".join([
        event.get("performerId", ""),
        event.get("date", ""),
        event.get("startTime", ""),
        normalize_venue(
            event.get("venue", "")
        ),
    ])


def loose_notification_key(event):
    return "|".join([
        event.get("performerId", ""),
        event.get("date", ""),
        normalize_venue(
            event.get("venue", "")
        ),
        normalize_title(
            event.get("title", "")
        ),
    ])


def source_notification_key(event):
    source = event.get(
        "source",
        ""
    )

    performer_id = event.get(
        "performerId",
        ""
    )

    url = event.get(
        "sourceUrl",
        ""
    )

    if source == "tiget":
        match = re.search(
            r"/events/(\d+)",
            url
        )

        if match:
            return (
                "tiget|"
                + performer_id
                + "|"
                + match.group(1)
            )

    if source == "fany":
        match = re.search(
            r"/reception/(\d+)/(\d+)",
            url
        )

        if match:
            return (
                "fany|"
                + performer_id
                + "|"
                + match.group(1)
                + "|"
                + match.group(2)
            )

    return ""


def main():
    data = load_json(
        EVENTS_FILE,
        {
            "events": []
        }
    )

    if isinstance(data, list):
        events = data
    else:
        events = data.get(
            "events",
            []
        )

    old_notified = load_json(
        NOTIFIED_FILE,
        {}
    )

    stable_keys = set(
        old_notified.get(
            "stableKeys",
            []
        )
    )

    loose_keys = set(
        old_notified.get(
            "looseKeys",
            []
        )
    )

    source_keys = set(
        old_notified.get(
            "sourceKeys",
            []
        )
    )

    for event in events:
        stable_keys.add(
            stable_notification_key(
                event
            )
        )

        loose_keys.add(
            loose_notification_key(
                event
            )
        )

        source_key = (
            source_notification_key(
                event
            )
        )

        if source_key:
            source_keys.add(
                source_key
            )

    output = {
        "stableKeys":
            sorted(stable_keys),

        "looseKeys":
            sorted(loose_keys),

        "sourceKeys":
            sorted(source_keys),
    }

    save_json(
        NOTIFIED_FILE,
        output
    )

    print(
        "通知済み初期化完了"
    )

    print(
        "登録公演数:",
        len(events)
    )

    print(
        "stableKeys:",
        len(stable_keys)
    )

    print(
        "looseKeys:",
        len(loose_keys)
    )

    print(
        "sourceKeys:",
        len(source_keys)
    )


if __name__ == "__main__":
    main()
