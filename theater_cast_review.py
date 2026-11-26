"""Apply narrowly scoped corrections backed by the official theater feed."""
import json
from functools import lru_cache
from pathlib import Path

from performer_matching import cast_matches, normalized_name


def key(event):
    return (
        event.get("theaterId"), event.get("date"), event.get("startTime"),
        normalized_name(event.get("title") or ""),
    )


@lru_cache(maxsize=1)
def reviewed_casts():
    path = Path(__file__).with_name("theater_cast_corrections.json")
    return {key(row): row for row in json.loads(path.read_text(encoding="utf-8"))["shows"]}


def apply_reviewed_casts(events, performers):
    indexed = {p["id"]: p for p in performers}
    reviews = reviewed_casts()
    result = []
    for event in events:
        official = reviews.get(key(event))
        pure_theater = (event.get("source") == "theater" or
                        set(event.get("discoverySources") or ()) == {"theater"})
        if official is None or not pure_theater:
            result.append(event)
            continue
        fields = event.get("performersText") or []
        if isinstance(fields, str):
            fields = [fields]
        excluded = {
            pid for pid in official["excludedPerformers"]
            if not (str(event.get("officialEventId")) == official["officialEventId"]
                    and pid in indexed and cast_matches(fields, indexed[pid]))
        }
        primary = event.get("performerId")
        if primary in excluded:
            # Grouped discovery rows can also cover a different, valid performer.
            retained = [pid for pid in (event.get("trackedPerformers") or []) if pid not in excluded]
            if event.get("source") == "theater" or not retained:
                continue
            event = {**event, "performerId": retained[0]}
        bad_lines = {normalized_name(title) for title in official["adjacentTitles"]}
        cleaned = [field for field in fields if normalized_name(field) not in bad_lines]
        ids = event.get("trackedPerformers")
        filtered = [pid for pid in ids if pid not in excluded] if isinstance(ids, list) else ids
        if filtered != ids or cleaned != fields:
            event = {**event, "performersText": cleaned}
            if filtered != ids:
                event["trackedPerformers"] = filtered
        result.append(event)
    return result
