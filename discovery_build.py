import json
import re
from copy import deepcopy
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


def unique_dicts(
    values,
    key_fields,
):
    result = []
    seen = set()

    for value in values:
        if not isinstance(
            value,
            dict,
        ):
            continue

        key = tuple(
            clean(
                value.get(
                    field,
                    "",
                )
            )
            for field in key_fields
        )

        if key in seen:
            continue

        seen.add(key)

        result.append(
            deepcopy(value)
        )

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
        or not b
    ):
        return 0.0

    if a == b:
        return 1.0

    if (
        len(a) >= 6
        and len(b) >= 6
        and (
            a in b
            or b in a
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

    # =====================================================
    # 出演者
    # =====================================================

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
        and performer_id
        == ticket_performer
    ):
        score += 5

    # =====================================================
    # 開演時間
    # =====================================================

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
        and start_b
        and start_a == start_b
    ):
        score += 4

    # =====================================================
    # 会場
    # =====================================================

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
        and venue_b
    ):
        if venue_a == venue_b:
            score += 4

        elif (
            venue_a in venue_b
            or venue_b in venue_a
        ):
            score += 3

    # =====================================================
    # タイトル
    # =====================================================

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
# チケット情報の共通化
# =========================================================

def normalize_sale_period(
    period,
):
    if not isinstance(
        period,
        dict,
    ):
        return None

    return {
        "category":
            clean(
                period.get(
                    "category",
                    "",
                )
            ),

        "label":
            clean(
                period.get(
                    "label",
                    "",
                )
            ),

        "startAt":
            clean(
                period.get(
                    "startAt",
                    "",
                )
            ),

        "endAt":
            clean(
                period.get(
                    "endAt",
                    "",
                )
            ),
    }


def normalize_ticket_option(
    option,
):
    if not isinstance(
        option,
        dict,
    ):
        return None

    sale_periods = []

    raw_periods = option.get(
        "salePeriods",
        [],
    )

    if isinstance(
        raw_periods,
        list,
    ):
        for period in raw_periods:
            normalized = (
                normalize_sale_period(
                    period
                )
            )

            if normalized:
                sale_periods.append(
                    normalized
                )

    # 古い形式にも対応
    if (
        not sale_periods
        and option.get(
            "saleStartAt"
        )
    ):
        sale_periods.append({
            "category":
                clean(
                    option.get(
                        "saleCategory",
                        "",
                    )
                ),

            "label":
                clean(
                    option.get(
                        "saleLabel",
                        "",
                    )
                ),

            "startAt":
                clean(
                    option.get(
                        "saleStartAt",
                        "",
                    )
                ),

            "endAt":
                clean(
                    option.get(
                        "saleEndAt",
                        "",
                    )
                ),
        })

    sale_periods = unique_dicts(
        sale_periods,
        [
            "category",
            "label",
            "startAt",
            "endAt",
        ],
    )

    return {
        "name":
            clean(
                option.get(
                    "name",
                    "",
                )
            ),

        "type":
            clean(
                option.get(
                    "type",
                    "",
                )
            ),

        "status":
            clean(
                option.get(
                    "status",
                    "",
                )
            ),

        "price":
            clean(
                option.get(
                    "price",
                    "",
                )
            ),

        "remaining":
            option.get(
                "remaining"
            ),

        "remainingText":
            clean(
                option.get(
                    "remainingText",
                    "",
                )
            ),

        "saleStartAt":
            clean(
                option.get(
                    "saleStartAt",
                    "",
                )
            ),

        "saleEndAt":
            clean(
                option.get(
                    "saleEndAt",
                    "",
                )
            ),

        "saleCategory":
            clean(
                option.get(
                    "saleCategory",
                    "",
                )
            ),

        "saleLabel":
            clean(
                option.get(
                    "saleLabel",
                    "",
                )
            ),

        "salePeriods":
            sale_periods,
    }


def get_ticket_sale_periods(
    ticket,
):
    result = []

    raw_periods = ticket.get(
        "salePeriods",
        [],
    )

    if isinstance(
        raw_periods,
        list,
    ):
        for period in raw_periods:
            normalized = (
                normalize_sale_period(
                    period
                )
            )

            if normalized:
                result.append(
                    normalized
                )

    # トップレベルの販売情報
    if (
        ticket.get(
            "saleStartAt"
        )
    ):
        result.append({
            "category":
                clean(
                    ticket.get(
                        "saleCategory",
                        "",
                    )
                ),

            "label":
                clean(
                    ticket.get(
                        "saleLabel",
                        "",
                    )
                ),

            "startAt":
                clean(
                    ticket.get(
                        "saleStartAt",
                        "",
                    )
                ),

            "endAt":
                clean(
                    ticket.get(
                        "saleEndAt",
                        "",
                    )
                ),
        })

    # ticketOptionsの中にも販売期間がある
    options = ticket.get(
        "ticketOptions",
        [],
    )

    if isinstance(
        options,
        list,
    ):
        for option in options:
            normalized_option = (
                normalize_ticket_option(
                    option
                )
            )

            if not normalized_option:
                continue

            result.extend(
                normalized_option.get(
                    "salePeriods",
                    [],
                )
            )

    return unique_dicts(
        result,
        [
            "category",
            "label",
            "startAt",
            "endAt",
        ],
    )


def get_ticket_options(
    ticket,
):
    result = []

    options = ticket.get(
        "ticketOptions",
        [],
    )

    if isinstance(
        options,
        list,
    ):
        for option in options:
            normalized = (
                normalize_ticket_option(
                    option
                )
            )

            if normalized:
                result.append(
                    normalized
                )

    return result


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

        ticket_options = (
            get_ticket_options(
                ticket
            )
        )

        sale_periods = (
            get_ticket_sale_periods(
                ticket
            )
        )

        candidates.append({
            "score":
                score,

            "performerId":
                clean(
                    ticket.get(
                        "performerId",
                        "",
                    )
                ),

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

            "date":
                clean(
                    ticket.get(
                        "date",
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

            "ticketOptions":
                ticket_options,

            "salePeriods":
                sale_periods,

            "saleStartAt":
                clean(
                    ticket.get(
                        "saleStartAt",
                        "",
                    )
                ),

            "saleEndAt":
                clean(
                    ticket.get(
                        "saleEndAt",
                        "",
                    )
                ),

            "saleCategory":
                clean(
                    ticket.get(
                        "saleCategory",
                        "",
                    )
                ),

            "saleLabel":
                clean(
                    ticket.get(
                        "saleLabel",
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

        unique.append(
            candidate
        )

    return unique


# =========================================================
# 発見イベントの共通形式
# =========================================================

def convert_discovered_event(
    event,
    discovery_source,
):
    performers_text = event.get(
        "performersText",
        [],
    )

    if not isinstance(
        performers_text,
        list,
    ):
        performers_text = (
            [
                clean(
                    performers_text
                )
            ]
            if clean(
                performers_text
            )
            else []
        )

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
                or
                event.get(
                    "discoveryUrl",
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
            performers_text,

        "newUntil":
            clean(
                event.get(
                    "newUntil",
                    "",
                )
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

                "performersText":
                    [],

                "newUntil":
                    clean(
                        event.get(
                            "newUntil",
                            "",
                        )
                    ),
            }

        performer_id = clean(
            event.get(
                "performerId",
                "",
            )
        )

        if (
            performer_id
            and performer_id
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
            and source not in grouped[
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
            and url not in grouped[
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

        performers_text = (
            event.get(
                "performersText",
                [],
            )
        )

        if not isinstance(
            performers_text,
            list,
        ):
            performers_text = [
                performers_text
            ]

        grouped[
            key
        ][
            "performersText"
        ] = unique_strings([
            *grouped[
                key
            ][
                "performersText"
            ],
            *performers_text,
        ])

        event_new_until = clean(
            event.get(
                "newUntil",
                "",
            )
        )

        if (
            event_new_until
            and (
                not grouped[
                    key
                ][
                    "newUntil"
                ]
                or event_new_until
                >
                grouped[
                    key
                ][
                    "newUntil"
                ]
            )
        ):
            grouped[
                key
            ][
                "newUntil"
            ] = event_new_until

        if (
            not grouped[
                key
            ].get(
                "openTime"
            )
            and event.get(
                "openTime"
            )
        ):
            grouped[
                key
            ][
                "openTime"
            ] = clean(
                event.get(
                    "openTime"
                )
            )

        if (
            not grouped[
                key
            ].get(
                "venue"
            )
            and event.get(
                "venue"
            )
        ):
            grouped[
                key
            ][
                "venue"
            ] = clean(
                event.get(
                    "venue"
                )
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
            performer_id = clean(
                event.get(
                    "performerId",
                    "",
                )
            )

            tracked = (
                [performer_id]
                if performer_id
                else []
            )

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

        # =================================================
        # 同じ販売URLをまとめる
        # =================================================

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

        # =================================================
        # 公演側へチケット情報を統合
        # =================================================

        combined_options = []
        combined_periods = []

        option_seen = set()
        period_seen = set()

        for match in unique_matches:
            for option in match.get(
                "ticketOptions",
                [],
            ):
                key = (
                    match.get(
                        "source",
                        "",
                    ),
                    clean(
                        option.get(
                            "name",
                            "",
                        )
                    ),
                    clean(
                        option.get(
                            "type",
                            "",
                        )
                    ),
                    clean(
                        option.get(
                            "price",
                            "",
                        )
                    ),
                    clean(
                        option.get(
                            "status",
                            "",
                        )
                    ),
                    clean(
                        option.get(
                            "saleStartAt",
                            "",
                        )
                    ),
                )

                if key in option_seen:
                    continue

                option_seen.add(key)

                combined_options.append({
                    **deepcopy(
                        option
                    ),

                    "source":
                        match.get(
                            "source",
                            "",
                        ),

                    "sourceUrl":
                        match.get(
                            "sourceUrl",
                            "",
                        ),
                })

            for period in match.get(
                "salePeriods",
                [],
            ):
                key = (
                    match.get(
                        "source",
                        "",
                    ),
                    clean(
                        period.get(
                            "category",
                            "",
                        )
                    ),
                    clean(
                        period.get(
                            "label",
                            "",
                        )
                    ),
                    clean(
                        period.get(
                            "startAt",
                            "",
                        )
                    ),
                    clean(
                        period.get(
                            "endAt",
                            "",
                        )
                    ),
                )

                if key in period_seen:
                    continue

                period_seen.add(key)

                combined_periods.append({
                    **deepcopy(
                        period
                    ),

                    "source":
                        match.get(
                            "source",
                            "",
                        ),

                    "sourceUrl":
                        match.get(
                            "sourceUrl",
                            "",
                        ),
                })

        event[
            "ticketMatches"
        ] = unique_matches

        event[
            "ticketListed"
        ] = bool(
            unique_matches
        )

        event[
            "ticketOptions"
        ] = combined_options

        event[
            "salePeriods"
        ] = combined_periods

        # =================================================
        # 代表チケット情報
        # =================================================

        if unique_matches:
            best = unique_matches[0]

            event[
                "status"
            ] = "ticket_listed"

            event[
                "ticketStatus"
            ] = clean(
                best.get(
                    "ticketStatus",
                    "",
                )
            )

            event[
                "source"
            ] = clean(
                best.get(
                    "source",
                    "",
                )
            )

            event[
                "sourceUrl"
            ] = clean(
                best.get(
                    "sourceUrl",
                    "",
                )
            )

            event[
                "saleStartAt"
            ] = clean(
                best.get(
                    "saleStartAt",
                    "",
                )
            )

            event[
                "saleEndAt"
            ] = clean(
                best.get(
                    "saleEndAt",
                    "",
                )
            )

            event[
                "saleCategory"
            ] = clean(
                best.get(
                    "saleCategory",
                    "",
                )
            )

            event[
                "saleLabel"
            ] = clean(
                best.get(
                    "saleLabel",
                    "",
                )
            )

            if (
                not event.get(
                    "openTime"
                )
                and best.get(
                    "openTime"
                )
            ):
                event[
                    "openTime"
                ] = clean(
                    best.get(
                        "openTime"
                    )
                )

        else:
            # =============================================
            # ライブ開催は確認済みだが
            # チケットサイトは未発見
            # =============================================

            event[
                "status"
            ] = "ticket_unlisted"

            event[
                "ticketStatus"
            ] = "チケットサイト公開待ち"

            event[
                "source"
            ] = "discovery"

            event[
                "sourceUrl"
            ] = ""

            event[
                "saleStartAt"
            ] = ""

            event[
                "saleEndAt"
            ] = ""

            event[
                "saleCategory"
            ] = ""

            event[
                "saleLabel"
            ] = ""

        result.append(
            event
        )

    return result


# =========================================================
# EXTRA取得元
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
    # 発見情報を共通形式へ
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
    # 主催者・SNS・その他発見ソース
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

    print(
        "発見公演・重複整理後:",
        len(
            discovered
        ),
        "件",
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

    ticket_option_count = sum(
        len(
            event.get(
                "ticketOptions",
                [],
            )
        )
        for event in discovered
    )

    sale_period_count = sum(
        len(
            event.get(
                "salePeriods",
                [],
            )
        )
        for event in discovered
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

        "ticketOptionCount":
            ticket_option_count,

        "salePeriodCount":
            sale_period_count,

        "events":
            discovered,
    }

    save_json(
        OUTPUT_FILE,
        output,
    )

    # =====================================================
    # ログ
    # =====================================================

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
        "チケット情報あり:",
        listed_count,
        "件",
    )

    print(
        "チケット公開待ち:",
        unlisted_count,
        "件",
    )

    print(
        "取得券種:",
        ticket_option_count,
        "件",
    )

    print(
        "取得販売期間:",
        sale_period_count,
        "件",
    )

    print("")

    for event in discovered:
        if event.get(
            "ticketListed"
        ):
            status = "🎫"

        else:
            status = "🕐"

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

        if event.get(
            "ticketListed"
        ):
            for match in event.get(
                "ticketMatches",
                [],
            ):
                print(
                    "   └",
                    match.get(
                        "source",
                        ""
                    ),
                    match.get(
                        "ticketStatus",
                        ""
                    ),
                )

        else:
            print(
                "   └ チケットサイト公開待ち"
            )

    print("")
    print(
        "保存:",
        OUTPUT_FILE,
    )

    print(
        "================================"
    )


if __name__ == "__main__":
    main()
