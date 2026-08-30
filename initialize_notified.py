import json
import re


EVENTS_FILE = "events.json"
NOTIFIED_FILE = "notified_events.json"


def load_json(path, default):
    try:
        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:
            return json.load(f)

    except (
        FileNotFoundError,
        json.JSONDecodeError
    ):
        return default


def save_json(path, data):
    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:
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
    text = clean(
        text
    ).lower()

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
        text = text.replace(
            char,
            ""
        )

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
        event.get(
            "performerId",
            ""
        ),
        event.get(
            "date",
            ""
        ),
        event.get(
            "startTime",
            ""
        ),
        normalize_venue(
            event.get(
                "venue",
                ""
            )
        ),
    ])


def loose_notification_key(event):
    return "|".join([
        event.get(
            "performerId",
            ""
        ),
        event.get(
            "date",
            ""
        ),
        normalize_venue(
            event.get(
                "venue",
                ""
            )
        ),
        normalize_title(
            event.get(
                "title",
                ""
            )
        ),
    ])


def main():
    data = load_json(
        EVENTS_FILE,
        {
            "events": []
        }
    )

    if isinstance(
        data,
        list
    ):
        events = data
    else:
        events = data.get(
            "events",
            []
        )

    stable_keys = set()
    loose_keys = set()

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

    output = {
        "stableKeys":
            sorted(
                stable_keys
            ),

        "looseKeys":
            sorted(
                loose_keys
            ),
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


if __name__ == "__main__":
    main()
