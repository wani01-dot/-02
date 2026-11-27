"""Collect independently, serialize notification decisions and publish merged catalogs."""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import notify_line as line
from line_quota import LineQuota
import scraper
from scheduler_slot import claim_slot
from performer_matching import cast_matches
from notification_outbox import GitState, Outbox, audit, elapsed_seconds, git, official_id, record_id, signature, timestamp
from theater_cast_review import apply_reviewed_casts
from theater_scraper import THEATERS, fetch_theater, make_theater_source_key

SOURCES = {"fany": scraper.scrape_fany, "tiget": scraper.scrape_tiget,
           "eplus": scraper.scrape_eplus, "livepocket": scraper.scrape_livepocket}
CATALOGS = ("events.json", "theater_events.json")


def read_events(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data if isinstance(data, list) else data["events"]


def fetch_ticket(source, performer):
    with requests.Session() as session:
        session.headers.update(scraper.HEADERS)
        session.mount("https://", HTTPAdapter(max_retries=Retry(
            total=1, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods={"GET"}, respect_retry_after_header=False,
        )))
        args = (session, performer, {}) if source == "fany" else (session, performer)
        return SOURCES[source](*args)


def timed(label, fetch, *args):
    started = time.monotonic()
    started_at = timestamp()
    audit("source_started", source=label, startedAt=started_at)
    try:
        events = fetch(*args)
    except Exception as error:
        # Details aid diagnosis, but requests and Playwright errors must never expose credentials.
        audit("source_result", source=label, successes=0, failures=1,
              startedAt=started_at, completedAt=timestamp(),
              seconds=round(time.monotonic() - started, 2), error=str(error))
        raise
    completed_at = timestamp()
    audit("source_result", source=label, successes=1, failures=0, startedAt=started_at,
          completedAt=completed_at, events=len(events), seconds=round(time.monotonic() - started, 2))
    return events, completed_at


def completed_sources(performers):
    with (ThreadPoolExecutor(max_workers=3) as theaters,
          ThreadPoolExecutor(max_workers=3) as fany,
          ThreadPoolExecutor(max_workers=3) as tickets):
        pending = {}
        for theater in THEATERS:
            label = f"theater/{theater['id']}"
            pending[theaters.submit(timed, label, fetch_theater, theater, performers)] = label
        for source in SOURCES:
            pool = fany if source == "fany" else tickets
            for performer in performers:
                if source not in performer.get("sources", ["fany", "tiget"]):
                    continue
                label = f"{source}/{performer['id']}"
                pending[pool.submit(timed, label, fetch_ticket, source, performer)] = label
        for future in as_completed(pending):
            label = pending[future]
            try:
                events, acquired_at = future.result()
            except Exception:
                yield label, None, None
            else:
                yield label, events, acquired_at


def catalog_key(event):
    if event["source"] == "theater":
        base = make_theater_source_key(event)
    else:
        base = event["source"], event["performerId"], signature(event)
    return base, official_id(event)


def merge_catalog(old, new, discovered):
    merged = list(old)
    positions = {catalog_key(event): index for index, event in enumerate(merged)}
    for event in new:
        key = catalog_key(event)
        index = positions.get(key)
        if index is None:
            index = positions.pop((key[0], ""), len(merged)) if key[1] else len(merged)
            positions[key] = index
        previous = merged[index] if index < len(merged) else {}
        updated = {**previous, **event}
        first_seen = discovered.get(record_id(event))
        if first_seen:
            updated["firstSeenAt"] = updated.get("firstSeenAt") or first_seen
            until = datetime.fromisoformat(first_seen) + timedelta(hours=scraper.NEW_HOURS)
            updated["newUntil"] = updated.get("newUntil") or until.isoformat()
        if index == len(merged):
            merged.append(updated)
        else:
            merged[index] = updated
    return merged


def log_run_timing(store):
    event = os.environ.get("GITHUB_EVENT_NAME")
    created = os.environ.get("RUN_CREATED_AT") or None
    runner_started = os.environ.get("RUN_STARTED_AT") or None
    observed = timestamp()
    previous = store.data.get("lastScheduledCreatedAt")
    previous_observed = store.data.get("lastScheduledAt")
    audit("run_timing", trigger=event, createdAt=created, runStartedAt=runner_started,
          queueSeconds=elapsed_seconds(created, runner_started),
          scheduleIntervalSeconds=elapsed_seconds(previous, created) if event == "schedule" else None,
          pipelineIntervalSeconds=elapsed_seconds(previous_observed, observed) if event == "schedule" else None)
    if event == "schedule":
        store.data["lastScheduledAt"] = observed
        if created:
            store.data["lastScheduledCreatedAt"] = created


def run(store, performers, sources, *, persist_catalogs, quota=None):
    tickets, theaters = (read_events(path) for path in CATALOGS)
    theaters = apply_reviewed_casts(theaters, performers)
    stream_events = line.load_stream_events()
    ticket_history = line.load_json("notified_events.json", {})
    theater_history = line.load_json("theater_notified_events.json", {})
    outbox = Outbox(store, stream_events, performers,
                    legacy_ticket_keys=ticket_history.get("sourceKeys", []),
                    legacy_theater_keys=theater_history.get("theaterKeys", []), quota=quota)
    if not store.data.get("migrationComplete"):
        # Existing listings may have been delivered by older code. Import as
        # legacy evidence without calling them API-confirmed deliveries.
        outbox.add(tickets + theaters, migration=True)
        store.data["migrationComplete"] = True
    log_run_timing(store)
    store.save()
    retry_keys = [key for key, batch in outbox.batches.items()
                  if batch["status"] in ("pending", "failed")]
    delivery_ok = True
    # Recover source data staged before a previous runner stopped after delivery.
    catalog_keys = {catalog_key(event) for event in tickets + theaters}
    recovered = [
        r for r in outbox.records.values()
        if r["reason"] != "migration_existing_listing" and catalog_key(r["event"]) not in catalog_keys
    ]
    new_tickets = [r["event"] for r in recovered if r["source"] != "theater"]
    new_theaters = [r["event"] for r in recovered if r["source"] == "theater"]
    discovered = {
        record_id(r["event"]): r["firstAcquiredAt"] for r in outbox.records.values()
        if r["reason"] in ("new_show", "operator_verified_unsent")
    }
    theater_success = 0
    for label, events, acquired_at in sources(performers):
        if events is None:
            continue
        if label.startswith("theater/"):
            theater_success += 1
            events = apply_reviewed_casts(events, performers)
            new_theaters.extend(events)
        else:
            for event in events:
                event["trackedPerformers"] = [
                    p["id"] for p in performers if cast_matches(event.get("performersText"), p)
                ]
            new_tickets.extend(events)
        keys = outbox.add(events, acquired_at=acquired_at)
        decided_at = timestamp()
        audit("source_decision", source=label, completedAt=acquired_at, decidedAt=decided_at,
              decisionSeconds=elapsed_seconds(acquired_at, decided_at), newShows=len(keys))
        discovered.update({key: outbox.records[key]["firstAcquiredAt"] for key in keys})
        if keys:
            delivery_ok = bool(outbox.send(outbox.stage(keys, source_label=label, source_completed_at=acquired_at,
                                                      source_decided_at=decided_at))) and delivery_ok
    store.save()
    persist_catalogs(
        merge_catalog(tickets, new_tickets, discovered),
        apply_reviewed_casts(merge_catalog(theaters, new_theaters, discovered), performers),
    )
    for key in retry_keys:
        delivery_ok = bool(outbox.send(key)) and delivery_ok
    if not theater_success:
        raise RuntimeError("全劇場取得失敗。既存の劇場データを保持しました")
    if not delivery_ok:
        raise RuntimeError("一部のLINE通知を保留しました。outboxを参照してください")


def publish_catalogs(tickets, theaters):
    for path, events in zip(CATALOGS, (tickets, theaters)):
        current = read_events(path)
        if events == current:
            continue
        data = json.loads(Path(path).read_text())
        metadata = data if isinstance(data, dict) else {}
        metadata.update(syncedAt=timestamp(), events=events)
        Path(path).write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    if not git("status", "--porcelain", "--", *CATALOGS):
        return
    git("add", "--", *CATALOGS)
    git("commit", "-m", "Update confirmed ticket and theater events")
    for attempt in range(3):
        git("fetch", "--no-tags", "origin", "main")
        git("rebase", "FETCH_HEAD")
        try:
            git("push", "origin", "HEAD:refs/heads/main")
            return
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2)


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_REF") != "refs/heads/main":
        raise RuntimeError("Production entry point runs only on the main Actions workflow")
    external = os.environ.get("EXTERNAL_SCHEDULER") == "true"
    key = os.environ.get("LINE_REQUEUE_RECORD", "")
    if external and (key or os.environ.get("LINE_REQUEUE_EVIDENCE")
                     or os.environ.get("LINE_REQUEUE_CONFIRM") == "true"):
        raise ValueError("External scheduler runs cannot request a manual resend")
    store = GitState()
    if external or os.environ.get("GITHUB_EVENT_NAME") == "schedule":
        observed_at = os.environ.get("SCHEDULER_OBSERVED_AT") or timestamp()
        started, slot = claim_slot(store, os.environ.get("RUN_CREATED_AT"), observed_at)
        audit("scheduler_slot", status="claimed" if started else "skipped",
              trigger="external" if external else "github", slot=slot)
        if not started:
            output = os.environ.get("GITHUB_OUTPUT")
            if output:
                with Path(output).open("a", encoding="utf-8") as target:
                    target.write("skipped=true\n")
            return
    performers = json.loads(Path("performers.json").read_text())["performers"]
    if key:
        outbox = Outbox(store, line.load_stream_events(), performers, quota=LineQuota(store))
        outbox.requeue_confirmed_unsent(
            key, os.environ.get("LINE_REQUEUE_EVIDENCE", ""),
            confirm=os.environ.get("LINE_REQUEUE_CONFIRM") == "true",
        )
        return
    quota = LineQuota(store)
    try:
        run(store, performers, completed_sources, persist_catalogs=publish_catalogs, quota=quota)
    finally:
        quota.audit_usage()


if __name__ == "__main__":
    main()
