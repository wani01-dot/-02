"""Durable, single-writer notification outbox. Production persists it before each push."""
import json
import os
import re
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import requests

import notify_line as line
from performer_matching import normalized_name

STATE_REF = "refs/heads/line-notification-state"
STATE_FILE = "notification-outbox.json"
RETRY_WINDOW = timedelta(hours=24)
VENUE_ALIASES = {
    "六本木": "よしもと六本木シアター",
    "yoshimotoroppongitheater": "よしもと六本木シアター",
    "よしもと六本木シアター(東京都)": "よしもと六本木シアター",
}
EVENT_PATHS = {
    "fany": r"^/reception/(\d+/\d+)(?:/|$)",
    "tiget": r"^/events/(\d+)(?:/|$)",
    "eplus": r"^/sf/detail/([^/]+)",
    "livepocket": r"^/e/([^/]+)",
}


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def audit(kind, **fields):
    print(json.dumps({"type": kind, "at": timestamp(), **fields}, ensure_ascii=False), flush=True)


def canonical_venue(event):
    venue = normalized_name(str(event.get("venue") or ""))
    return normalized_name(VENUE_ALIASES.get(venue, venue))


def official_id(event):
    source = event.get("source", "")
    eid = event.get("officialEventId")
    if eid and source == "theater":
        return f"theater/{event.get('theaterId')}/{eid}"
    pattern = EVENT_PATHS.get(source)
    match = re.match(pattern, urlsplit(event.get("sourceUrl") or "").path) if pattern else None
    return f"{source}/{match[1]}" if match else ""


def signature(event):
    start = event.get("startTime") or ""
    if re.fullmatch(r"\d:\d\d", start):
        start = "0" + start
    return (event.get("date") or "", start, canonical_venue(event),
            normalized_name(str(event.get("title") or "")))


def duplicate_reason(a, b):
    left, right = signature(a), signature(b)
    aid, bid = official_id(a), official_id(b)
    if a.get("source") == b.get("source") and aid and bid and aid != bid:
        return ""
    if left != right or not all(left):
        # A scoped official ID may survive a title edit. Date, start time and venue
        # must still match so distinct performances and venues stay distinct.
        if not (aid and aid == bid and left[:3] == right[:3] and all(left[:3])):
            return ""
        return "official_id"
    if not set(line.event_performer_ids(a)).intersection(line.event_performer_ids(b)):
        # Same official event represents one show even when discovered by another cast search.
        if not aid or aid != bid:
            return ""
    return "official_id" if aid and aid == bid else "show_and_cast"


def record_id(event):
    key = (event.get("source"), official_id(event), signature(event),
           event.get("performerId"))
    return json.dumps(key, ensure_ascii=False, separators=(",", ":"))


def git(*args, input=None):
    return subprocess.check_output(["git", *args], input=input, text=True).strip()


class GitState:
    """A fast-forward push is the compare-and-swap barrier before external delivery."""

    def __init__(self):
        heads = git("ls-remote", "--heads", "origin", STATE_REF)
        self.parent = heads.split()[0] if heads else None
        if self.parent:
            git("fetch", "--no-tags", "origin", STATE_REF)
            if git("rev-parse", "FETCH_HEAD") != self.parent:
                raise RuntimeError("Notification state changed while loading")
            self.data = json.loads(git("show", f"{self.parent}:{STATE_FILE}"))
            self.blob = git("rev-parse", f"{self.parent}:{STATE_FILE}")
        else:
            self.data = {"records": {}, "batches": {}, "lastScheduledAt": None}
            self.blob = None

    def save(self):
        blob = git("hash-object", "-w", "--stdin", input=json.dumps(self.data, ensure_ascii=False))
        if blob == self.blob:
            return
        tree = git("mktree", input=f"100644 blob {blob}\t{STATE_FILE}\n")
        parents = ["-p", self.parent] if self.parent else []
        commit = git("commit-tree", tree, *parents, "-m", "Persist LINE notification state")
        git("push", "origin", f"{commit}:{STATE_REF}")
        self.parent = commit
        self.blob = blob


class Outbox:
    def __init__(self, store, stream_events, performers, *, legacy_ticket_keys=(), legacy_theater_keys=()):
        self.store = store
        self.records = store.data["records"]
        self.batches = store.data["batches"]
        self.stream_events = stream_events
        self.legacy_ticket_keys = set(legacy_ticket_keys)
        self.legacy_theater_keys = set(legacy_theater_keys)
        self.notify_ids = {p["id"] for p in performers if p.get("notify")}

    def add(self, events, *, migration=False, acquired_at=None):
        # Use a date/time/venue index to avoid comparing each event with the entire history.
        by_slot = {}
        known_official_ids = set()
        for key, record in self.records.items():
            if record["status"] != "duplicate":
                by_slot.setdefault(signature(record["event"])[:3], []).append(key)
                if record.get("officialId") and record["reason"] != "migration_exact_history_key":
                    known_official_ids.add(record["officialId"])
        new = []
        for event in events:
            if event.get("performerId") not in self.notify_ids:
                continue
            key = record_id(event)
            if key in self.records:
                continue
            slot = signature(event)[:3]
            match, reason = next(
                ((other, why) for other in by_slot.get(slot, ())
                 if (why := duplicate_reason(event, self.records[other]["event"]))),
                (None, ""),
            )
            acquired = event.get("firstSeenAt") if migration else (acquired_at or timestamp())
            eid = official_id(event)
            if event.get("source") == "theater":
                previously_indexed = line.theater_notification_key(event) in self.legacy_theater_keys
            else:
                previously_indexed = (
                    bool(eid) and eid not in known_official_ids
                    and line.source_notification_key(event) in self.legacy_ticket_keys
                )
            if migration:
                status, decision = "legacy", "migration_existing_listing"
            elif match and self.records[match]["status"] == "legacy":
                prior = self.records[match]
                prior_event = prior["event"]
                history_key = (line.theater_notification_key(prior_event) in self.legacy_theater_keys
                               if prior_event.get("source") == "theater"
                               else line.source_notification_key(prior_event) in self.legacy_ticket_keys)
                status = "legacy"
                decision = ("migration_exact_history_key" if previously_indexed or history_key
                            else "migration_listing_delivery_unconfirmed")
            elif match:
                status, decision = "duplicate", reason
                if match in new:
                    anchor = self.records[match]["event"]
                    anchor["trackedPerformers"] = sorted(
                        set(line.event_performer_ids(anchor)) | set(line.event_performer_ids(event))
                    )
            elif previously_indexed:
                status, decision = "legacy", "migration_exact_history_key"
            elif not all(signature(event)) or event["date"] < datetime.now(line.JST).date().isoformat():
                status, decision = "acquired", "past_or_incomplete"
            else:
                status, decision = "pending", "new_show"
                new.append(key)
            self.records[key] = {
                "event": dict(event), "source": event.get("source"),
                "officialId": eid or None, "firstAcquiredAt": acquired,
                "decidedAt": timestamp(), "status": status, "reason": decision,
                "duplicateOf": match, "duplicateReason": reason or None,
                "sentAt": None, "lineResponse": None, "inDigestDetails": None,
            }
            if status != "duplicate":
                by_slot.setdefault(slot, []).append(key)
                if eid and not previously_indexed:
                    known_official_ids.add(eid)
            if not migration:
                audit("event_decision", key=key, **{
                    k: v for k, v in self.records[key].items() if k != "event"
                })
        return new

    def stage(self, keys):
        if not keys:
            return
        events = [self.records[key]["event"] for key in keys]
        displayed = set()
        # Existing styling, ordering and counts remain in the shared builder.
        message = line.build_line_digest(
            [], [], self.stream_events, displayed=displayed,
            groups=[{"event": event, "events": [event]} for event in events],
        )
        retry_key = str(uuid.uuid4())
        self.batches[retry_key] = {
            "keys": keys, "message": message, "createdAt": timestamp(),
            "firstAttemptAt": None, "status": "pending",
        }
        for key in keys:
            self.records[key]["inDigestDetails"] = id(self.records[key]["event"]) in displayed
        return retry_key

    def send(self, retry_key):
        batch = self.batches[retry_key]
        if batch["status"] not in ("pending", "failed"):
            return
        first_attempt = batch["firstAttemptAt"]
        if first_attempt and datetime.now(timezone.utc) - datetime.fromisoformat(first_attempt) >= RETRY_WINDOW:
            if batch.get("definitivelyRejected"):
                replacement = str(uuid.uuid4())
                self.batches[replacement] = {**batch, "firstAttemptAt": None, "status": "pending"}
                del self.batches[retry_key]
                return self.send(replacement)
            batch["status"] = "reconciliation_required"
            self.store.save()
            audit("retry_window_expired", retryKey=retry_key, keys=batch["keys"])
            return False
        previously_unresolved = first_attempt is not None and not batch.get("definitivelyRejected")
        batch["firstAttemptAt"] = first_attempt or timestamp()
        batch["definitivelyRejected"] = False
        # Persist the exact payload and key before making the request, including on crash recovery.
        self.store.save()
        outcome = {"httpStatus": None, "requestId": None}
        try:
            response = line.post_line(batch["message"], retry_key=retry_key, timeout=15)
            accepted_id = response.headers.get("x-line-accepted-request-id")
            outcome = {
                "httpStatus": response.status_code,
                "requestId": accepted_id or response.headers.get("x-line-request-id"),
            }
            success = response.status_code == 200 or (response.status_code == 409 and bool(accepted_id))
        except (requests.RequestException, RuntimeError) as error:
            success = False
            outcome["error"] = type(error).__name__
        sent_at = timestamp() if success else None
        if success and outcome["httpStatus"] == 409:
            sent_at = None  # Exact time of the earlier accepted request is unknown.
        batch["status"] = "accepted" if success else "failed"
        batch["definitivelyRejected"] = (
            not success and not previously_unresolved
            and outcome["httpStatus"] in {400, 401, 403, 404, 413, 422, 429}
        )
        if success:
            del batch["message"]
        for key in batch["keys"]:
            record = self.records[key]
            record.update(status=batch["status"], sentAt=sent_at, lineResponse=outcome,
                          lastAttemptAt=timestamp())
        audit("line_result", retryKey=retry_key, keys=batch["keys"], status=batch["status"],
              sentAt=sent_at, detailKeys=[key for key in batch["keys"]
                                         if self.records[key]["inDigestDetails"]], **outcome)
        self.store.save()
        return success

    def retry(self):
        results = [self.send(key) for key in list(self.batches)
                   if self.batches[key]["status"] in ("pending", "failed")]
        return all(results)


    def requeue_confirmed_unsent(self, key, evidence, *, confirm=False):
        record = self.records[key]
        event = record["event"]
        if record["status"] != "legacy" or not all(signature(event)):
            raise ValueError("Only complete migrated records can be manually requeued")
        if event["date"] < datetime.now(line.JST).date().isoformat():
            raise ValueError("Cannot requeue a past performance")
        if not evidence.strip():
            raise ValueError("An operator must provide evidence that no notification was sent")
        known_delivery = {"accepted", "pending", "failed"}
        if any(other["status"] in known_delivery and duplicate_reason(event, other["event"])
               for other in self.records.values()):
            raise ValueError("A matching delivery is already recorded or pending")
        audit("manual_requeue_review", key=key, evidence=evidence, confirmed=confirm)
        if not confirm:
            return
        record.update(status="pending", reason="operator_verified_unsent",
                      decidedAt=timestamp(), evidence=evidence)
        if not self.send(self.stage([key])):
            raise RuntimeError("Manual requeue remains pending")
