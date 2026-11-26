"""Run the production readers and dry-run classification without writing repository state."""
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

import notify_line as line
import scraper
from notification_outbox import Outbox, audit, official_id, record_id, timestamp
from notification_pipeline import fetch_ticket, read_events
from performer_matching import cast_matches, normalized_name
from theater_scraper import THEATERS, cast_lines, fetch_theater, plain, time_field

REVIEW_FILE = Path("docs/theater-review-candidates.json")


def theater_result(theater, performers):
    metadata = {}

    def observe(months, rows):
        metadata["months"] = [f"{y}-{m:02d}" for y, m in months]
        metadata["official"] = [
            {
                "officialEventId": str(row["id"]),
                "date": row["date"].replace("/", "-"),
                "startTime": time_field(row.get("dateTime2")),
                "title": plain(row.get("name")),
                "cast": cast_lines(row.get("memberHtml")) or cast_lines(row.get("member")),
                "url": theater["url"] + "?" + urlencode({"id": row["id"]}),
            }
            for row in rows
        ]

    events = fetch_theater(theater, performers, observe=observe)
    return events, metadata


def fany_result(performer):
    return fetch_ticket("fany", performer), {
        "months": [begin.isoformat()[:7] for begin, _ in scraper.build_month_ranges()],
        "official": None,
    }


def collect(task, *args):
    started = timestamp()
    start = time.monotonic()
    try:
        events, metadata = task(*args)
        error = None
    except Exception as exc:
        events, metadata, error = None, {}, str(exc)
    return started, timestamp(), round(time.monotonic() - start, 3), events, metadata, error


def review(candidate, evidence, performers):
    if evidence is None:
        return "source_unavailable", []
    matches = [
        row for row in evidence["official"]
        if row["date"] == candidate["date"] and row["startTime"] == candidate["startTime"]
        and normalized_name(row["title"]) == normalized_name(candidate["title"])
    ]
    if not matches:
        month = candidate["date"][:7]
        return ("not_found" if month in evidence["months"] else "outside_verified_months"), matches
    if len(matches) != 1:
        return "ambiguous", matches
    if not matches[0]["cast"]:
        return "cast_unpublished", matches
    if cast_matches(matches[0]["cast"], performers[candidate["performerId"]]):
        return "official_cast_matches", matches
    if any(normalized_name(field.strip("／ /")) in {"他", "ほか"} for field in matches[0]["cast"]):
        return "cast_partial_unconfirmed", matches
    # A reviewer must confirm the visible official cast is complete before correction.
    return "cast_differs_review_required", matches


ROPPONGI_CASES = (
    ("19:15", "ダイタク×9番街レトロコントライブ「待ってろ！自動車学校」", False),
    ("21:00", "新ネタピュートライブ", True),
)


def check_roppongi(evidence, events, performers):
    for start, title, expected in ROPPONGI_CASES:
        candidate = {"date": "2027-01-21", "startTime": start, "title": title,
                     "performerId": "pyuto"}
        verdict, matches = review(candidate, evidence, performers)
        acceptable = "official_cast_matches" if expected else "cast_differs_review_required"
        event_id = matches[0]["officialEventId"] if len(matches) == 1 else None
        included = any(e.get("officialEventId") == event_id and e["date"] == candidate["date"]
                       and e["startTime"] == start and e["performerId"] == "pyuto" for e in events)
        if verdict == acceptable:
            result = "確認済み" if included == expected else "抽出結果が公式出演欄と不一致"
        elif verdict in ("official_cast_matches", "cast_differs_review_required"):
            result = "公式出演欄が従来の想定と異なる"
        else:
            result = "未確認"
        audit("probe_roppongi_check", startTime=start, title=title, status=result,
              officialEventId=event_id, verdict=verdict, included=included, official=matches)


def probe(performers, candidates, baseline, ticket_keys, theater_keys):
    state = SimpleNamespace(data={"records": {}, "batches": {}})
    dry_run = Outbox(state, [], performers,
                     legacy_ticket_keys=ticket_keys, legacy_theater_keys=theater_keys)
    dry_run.add(baseline, migration=True)
    indexed = {p["id"]: p for p in performers}
    evidence = {}
    roppongi_events = []
    failures = []
    new_batches = {"fany": 0, "theater": 0}
    decisions = {}
    with ThreadPoolExecutor(max_workers=3) as theaters, ThreadPoolExecutor(max_workers=3) as fany:
        jobs = {
            theaters.submit(collect, theater_result, venue, performers): f"theater/{venue['id']}"
            for venue in THEATERS
        }
        jobs.update({
            fany.submit(collect, fany_result, p): f"fany/{p['id']}" for p in performers
        })
        for future in as_completed(jobs):
            source = jobs[future]
            began, completed, seconds, events, metadata, error = future.result()
            kind, identifier = source.split("/")
            if error is not None:
                failures.append(source)
                audit("probe_source_result", source=source, status="failed", startedAt=began,
                      completedAt=completed, acquisitionSeconds=seconds, error=error,
                      plannedMonths=[d.isoformat()[:7] for d, _ in scraper.build_month_ranges()]
                      if kind == "fany" else None)
                continue

            decision_started = time.monotonic()
            if kind == "theater":
                evidence[identifier] = metadata
                if identifier == "roppongi":
                    roppongi_events = events
            else:
                for event in events:
                    event["trackedPerformers"] = [
                        p["id"] for p in performers if cast_matches(event.get("performersText"), p)
                    ]
            keys = dry_run.add(events, acquired_at=completed)
            new_batches[kind] += bool(keys)
            for event in events:
                record = dry_run.records.get(record_id(event))
                reason = record["reason"] if record else "not_targeted"
                decisions[reason] = decisions.get(reason, 0) + 1
            decided = timestamp()
            elapsed = datetime.fromisoformat(decided) - datetime.fromisoformat(began)
            audit("probe_source_result", source=source, status="success", startedAt=began,
                  completedAt=completed, acquisitionSeconds=seconds, decidedAt=decided,
                  decisionSeconds=round(time.monotonic() - decision_started, 3),
                  elapsedToDecisionSeconds=round(elapsed.total_seconds(), 3),
                  targetMonths=metadata["months"],
                  officialShowCount=len(metadata["official"]) if metadata["official"] is not None else None,
                  trackedShowCount=len({(e["date"], e["startTime"], e["title"], official_id(e)) for e in events}),
                  counts={pid: sum(1 for e in events if e["performerId"] == pid) for pid in indexed},
                  hypotheticalNewShows=len(keys))
            for row in metadata["official"] or []:
                audit("probe_official_show", source=source, **row)
            for event in events:
                audit("probe_show", source=source, officialEventId=official_id(event) or None,
                      date=event["date"], startTime=event["startTime"], title=event["title"],
                      cast=event.get("performersText"), url=event.get("sourceUrl"))
    check_roppongi(evidence.get("roppongi"), roppongi_events, indexed)
    for candidate in candidates:
        status, matches = review(candidate, evidence.get(candidate["theaterId"]), indexed)
        audit("probe_review", status=status, stored=candidate, official=matches)
    audit("probe_summary", failures=failures, hypotheticalBatches=new_batches,
          sourcesTotal=len(THEATERS) + len(performers), reviewRecords=len(candidates), decisions=decisions,
          reviewShows=len({(c["theaterId"], c["date"], c["startTime"], c["title"]) for c in candidates}))
    return not failures


def main():
    performers = json.loads(Path("performers.json").read_text())["performers"]
    candidates = json.loads(REVIEW_FILE.read_text())
    ok = probe(performers, candidates, read_events("events.json") + read_events("theater_events.json"),
               line.load_json("notified_events.json", {}).get("sourceKeys", []),
               line.load_json("theater_notified_events.json", {}).get("theaterKeys", []))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
