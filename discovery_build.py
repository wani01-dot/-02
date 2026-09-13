import json
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher


THEATER_EVENTS_FILE = "theater_events.json"
TICKET_EVENTS_FILE = "events.json"
EXTRA_DISCOVERY_FILE = "extra_discovery_events.json"
OUTPUT_FILE = "discovered_events.json"


# =========================================================
# JSON
# =========================================================

def load_json(path, default):
    try:
        with open(
            path,
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(file)

    except (
        FileNotFoundError,
        json.JSONDecodeError,
    ):
        return default


def save_json(path, data):
    with open(
        path,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )


# =========================================================
# 共通
# =========================================================

def clean(text):
    return re.sub(
        r"\s+",
        " ",
        str(text or ""),
    ).strip()


def normalize_title(text):
    text = clean(text).lower()

    remove_chars = [
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
        "(",
        ")",
        "（",
        "）",
        "―",
        "-",
        "ー",
    ]

    for char in remove_chars:
        text = text.replace(
            char,
            "",
        )

    return text


def normalize_venue(text):
    text = clean(text).lower()

    remove_words = [
        " ",
        "　",
        "（東京都）",
        "（大阪府）",
        "（福岡県）",
        "（千葉県）",
        "（埼玉県）",
    ]

    for word in remove_words:
        text = text.replace(
            word,
            "",
        )

    return text


def now_iso():
    return datetime.now(
        timezone.utc
    ).isoformat()


def unique_strings(values):
    result = []

    for value in values:
        value = clean(value)

        if not value:
            continue

        if value in result:
            continue

        result.append(value)

    return result


# =========================================================
# イベント配列取得
# =========================================================

def extract_events(data):
    if isinstance(
        data,
        list,
    ):
        return data

    if isinstance(
        data,
        dict,
    ):
        events = data.get(
            "events",
            [],
        )

        if isinstance(
            events,
            list,
        ):
            return events

    return []


# =========================================================
# タイトル類似度
# =========================================================

def title_similarity(
    title_a,
    title_b,
):
    a = normalize_title(
        title_a
    )

    b = normalize_title(
        title_b
    )

    if (
        not a
        or
        not b
    ):
        return 0.0

    if a == b:
        return 1.0

    if (
        len(a) >= 6
        and
        len(b) >= 6
        and
        (
            a in b
            or
            b in a
        )
    ):
        return 0.92

    return SequenceMatcher(
        None,
        a,
        b,
    ).ratio()


# =========================================================
# 同一公演スコア
# =========================================================

def match_score(
    discovered,
    ticket,
):
    score = 0

    # 日付一致は必須
    if (
        clean(
            discovered.get(
                "date"
            )
        )
        !=
        clean(
            ticket.get(
                "date"
            )
        )
    ):
        return 0

    score += 5


    # 出演者
    performer_id = clean(
        discovered.get(
            "performerId",
            "",
        )
    )

    ticket_performer = clean(
        ticket.get(
            "performerId",
            "",
        )
    )

    if (
        performer_id
        and
        performer_id
        ==
        ticket_performer
    ):
        score += 5


    # 開演時間
    start_a = clean(
        discovered.get(
            "startTime",
            "",
        )
    )

    start_b = clean(
        ticket.get(
            "startTime",
            "",
        )
    )

    if (
        start_a
        and
        start_b
        and
        start_a == start_b
    ):
        score += 4


    # 会場
    venue_a = normalize_venue(
        discovered.get(
            "venue",
            "",
        )
    )

    venue_b = normalize_venue(
        ticket.get(
            "venue",
            "",
        )
    )

    if (
        venue_a
        and
        venue_b
    ):
        if venue_a == venue_b:
            score += 4

        elif (
            venue_a in venue_b
            or
            venue_b in venue_a
        ):
            score += 3


    # タイトル
    similarity = title_similarity(
        discovered.get(
            "title",
            "",
        ),
        ticket.get(
            "title",
            "",
        ),
    )

    if similarity >= 0.90:
        score += 6

    elif similarity >= 0.75:
        score += 4

    elif similarity >= 0.55:
        score += 2


    return score


# =========================================================
# 最適チケット候補
# =========================================================

def find_ticket_matches(
    event,
    ticket_events,
):
    candidates = []

    for ticket in ticket_events:
        score = match_score(
            event,
            ticket,
        )

        if score < 10:
            continue

        candidates.append({
            "score":
                score,

            "source":
                clean(
                    ticket.get(
                        "source",
                        "",
                    )
                ),

            "sourceUrl":
                clean(
                    ticket.get(
                        "sourceUrl",
                        "",
                    )
                ),

            "title":
                clean(
                    ticket.get(
                        "title",
                        "",
                    )
                ),

            "venue":
                clean(
                    ticket.get(
                        "venue",
                        "",
                    )
                ),

            "openTime":
                clean(
                    ticket.get(
                        "openTime",
                        "",
                    )
                ),

            "startTime":
                clean(
                    ticket.get(
                        "startTime",
                        "",
                    )
                ),

            "ticketStatus":
                clean(
                    ticket.get(
                        "ticketStatus",
                        "",
                    )
                ),
        })


    candidates.sort(
        key=lambda item:
            item.get(
                "score",
                0,
            ),
        reverse=True,
    )


    unique = []
    seen = set()

    for candidate in candidates:
        key = (
            candidate.get(
                "source",
                "",
            )
            +
            "|"
            +
            candidate.get(
                "sourceUrl",
                "",
            )
        )

        if key in seen:
            continue

        seen.add(key)
        unique.append(candidate)

    return unique


# =========================================================
# 発見イベントの共通形式
# =========================================================

def convert_discovered_event(
    event,
    discovery_source,
):
    return {
        "performerId":
            clean(
                event.get(
                    "performerId",
                    "",
                )
            ),

        "date":
            clean(
                event.get(
                    "date",
                    "",
                )
            ),

        "openTime":
            clean(
                event.get(
                    "openTime",
                    "",
                )
            ),

        "startTime":
            clean(
                event.get(
                    "startTime",
                    "",
                )
            ),

        "title":
            clean(
                event.get(
                    "title",
                    "",
                )
            ),

        "venue":
            clean(
                event.get(
                    "venue",
                    "",
                )
            ),

        "discoverySource":
            discovery_source,

        "discoveryUrl":
            clean(
                event.get(
                    "sourceUrl",
                    "",
                )
            ),

        "theaterId":
            clean(
                event.get(
                    "theaterId",
                    "",
                )
            ),

        "theaterName":
            clean(
                event.get(
                    "theaterName",
                    "",
                )
            ),

        "performersText":
            event.get(
                "performersText",
                [],
            ),
    }


# =========================================================
# 同じ発見公演をまとめる
# =========================================================

def discovery_group_key(
    event,
):
    return "|".join([
        clean(
            event.get(
                "date",
                "",
            )
        ),

        clean(
            event.get(
                "startTime",
                "",
            )
        ),

        normalize_title(
            event.get(
                "title",
                "",
            )
        ),

        normalize_venue(
            event.get(
                "venue",
                "",
            )
        ),
    ])


def group_discovered_events(
    events,
):
    grouped = {}

    for event in events:
        key = discovery_group_key(
            event
        )

        if key not in grouped:
            grouped[key] = {
                **event,

                "trackedPerformers":
                    [],

                "discoverySources":
                    [],

                "discoveryUrls":
                    [],
            }

        performer_id = clean(
            event.get(
                "performerId",
                "",
            )
        )

        if (
            performer_id
            and
            performer_id
            not in grouped[
                key
            ][
                "trackedPerformers"
            ]
        ):
            grouped[
                key
            ][
                "trackedPerformers"
            ].append(
                performer_id
            )

        source = clean(
            event.get(
                "discoverySource",
                "",
            )
        )

        if (
            source
            and
            source not in grouped[
                key
            ][
                "discoverySources"
            ]
        ):
            grouped[
                key
            ][
                "discoverySources"
            ].append(
                source
            )

        url = clean(
            event.get(
                "discoveryUrl",
                "",
            )
        )

        if (
            url
            and
            url not in grouped[
                key
            ][
                "discoveryUrls"
            ]
        ):
            grouped[
                key
            ][
                "discoveryUrls"
            ].append(
                url
            )

    return list(
        grouped.values()
    )


# =========================================================
# チケット照合
# =========================================================

def attach_ticket_status(
    events,
    ticket_events,
):
    result = []

    for event in events:
        all_matches = []

        tracked = event.get(
            "trackedPerformers",
            [],
        )

        if not tracked:
            tracked = [
                clean(
                    event.get(
                        "performerId",
                        "",
                    )
                )
            ]

        for performer_id in tracked:
            temp_event = dict(
                event
            )

            temp_event[
                "performerId"
            ] = performer_id

            matches = find_ticket_matches(
                temp_event,
                ticket_events,
            )

            all_matches.extend(
                matches
            )

        unique_matches = []
        seen = set()

        for match in all_matches:
            key = (
                match.get(
                    "source",
                    "",
                )
                +
                "|"
                +
                match.get(
                    "sourceUrl",
                    "",
                )
            )

            if key in seen:
                continue

            seen.add(key)

            unique_matches.append(
                match
            )

        unique_matches.sort(
            key=lambda item:
                item.get(
                    "score",
                    0,
                ),
            reverse=True,
        )

        event[
            "ticketMatches"
        ] = unique_matches

        event[
            "ticketListed"
        ] = bool(
            unique_matches
        )

        if unique_matches:
            event[
                "status"
            ] = "ticket_listed"

        else:
            event[
                "status"
            ] = "ticket_unlisted"

        result.append(
            event
        )

    return result


# =========================================================
# EXTRA取得元
#
# 後から主催者公式・SNSスクレイパーが
# ここへデータを流し込める
# =========================================================

def load_extra_discovery_events():
    data = load_json(
        EXTRA_DISCOVERY_FILE,
        [],
    )

    events = extract_events(
        data
    )

    result = []

    for event in events:
        source = (
            clean(
                event.get(
                    "discoverySource",
                    "",
                )
            )
            or
            clean(
                event.get(
                    "source",
                    "",
                )
            )
            or
            "official"
        )

        result.append(
            convert_discovered_event(
                event,
                source,
            )
        )

    return result


# =========================================================
# MAIN
# =========================================================

def main():
    print(
        "================================"
    )

    print(
        "ライブ発見レーダー構築開始"
    )

    print(
        "================================"
    )


    # =====================================================
    # 劇場公式
    # =====================================================

    theater_data = load_json(
        THEATER_EVENTS_FILE,
        {
            "events":
                []
        },
    )

    theater_events = extract_events(
        theater_data
    )

    print(
        "劇場公式:",
        len(
            theater_events
        ),
        "件",
    )


    # =====================================================
    # チケットサイト
    # =====================================================

    ticket_data = load_json(
        TICKET_EVENTS_FILE,
        [],
    )

    ticket_events = extract_events(
        ticket_data
    )

    print(
        "チケットサイト:",
        len(
            ticket_events
        ),
        "件",
    )


    # =====================================================
    # 発見情報を共通形式に
    # =====================================================

    discovered = []

    for event in theater_events:
        discovered.append(
            convert_discovered_event(
                event,
                "theater",
            )
        )


    # =====================================================
    # 将来の主催者/SNS取得分
    # =====================================================

    extra_events = (
        load_extra_discovery_events()
    )

    discovered.extend(
        extra_events
    )

    print(
        "追加発見ソース:",
        len(
            extra_events
        ),
        "件",
    )


    # =====================================================
    # 同一公演をまとめる
    # =====================================================

    discovered = (
        group_discovered_events(
            discovered
        )
    )


    # =====================================================
    # チケットサイト照合
    # =====================================================

    discovered = (
        attach_ticket_status(
            discovered,
            ticket_events,
        )
    )


    # =====================================================
    # 並び替え
    # =====================================================

    discovered.sort(
        key=lambda event: (
            event.get(
                "date",
                ""
            ),

            event.get(
                "startTime",
                ""
            ),

            event.get(
                "title",
                ""
            ),
        )
    )


    # =====================================================
    # 集計
    # =====================================================

    listed_count = sum(
        1
        for event in discovered
        if event.get(
            "ticketListed"
        )
    )

    unlisted_count = (
        len(
            discovered
        )
        -
        listed_count
    )


    output = {
        "syncedAt":
            now_iso(),

        "total":
            len(
                discovered
            ),

        "ticketListedCount":
            listed_count,

        "ticketUnlistedCount":
            unlisted_count,

        "events":
            discovered,
    }


    save_json(
        OUTPUT_FILE,
        output,
    )


    print("")
    print(
        "================================"
    )

    print(
        "発見公演:",
        len(
            discovered
        ),
        "件",
    )

    print(
        "チケット公開済み:",
        listed_count,
        "件",
    )

    print(
        "チケット未掲載:",
        unlisted_count,
        "件",
    )


    for event in discovered:
        status = (
            "🟢"
            if event.get(
                "ticketListed"
            )
            else
            "🟠"
        )

        print(
            status,
            event.get(
                "date"
            ),
            event.get(
                "startTime"
            ),
            event.get(
                "title"
            ),
            "/",
            ",".join(
                event.get(
                    "trackedPerformers",
                    [],
                )
            ),
        )


    print(
        "保存:",
        OUTPUT_FILE,
    )

    print(
        "================================"
    )


if __name__ == "__main__":
    main()
