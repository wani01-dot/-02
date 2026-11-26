import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import acquisition_probe
import notification_outbox
import notification_pipeline
import notify_line
from performer_matching import cast_matches
from theater_cast_review import apply_reviewed_casts

ARTISTS = json.loads(Path("performers.json").read_text())["performers"]


class ConfirmedReviewTest(unittest.TestCase):
    def test_archive_is_corrected_idempotently_without_removing_verified_cast(self):
        data = json.loads(Path("theater_cast_corrections.json").read_text())
        for path, records in data["archivedRows"].items():
            live = json.loads(Path(path).read_text())
            live = live if isinstance(live, list) else live["events"]
            cleaned = apply_reviewed_casts(records, ARTISTS)
            self.assertEqual(cleaned, apply_reviewed_casts(cleaned, ARTISTS))
            self.assertTrue(all(row in live for row in cleaned))
        same_day = [r for r in data["archivedRows"]["theater_events.json"]
                    if r["date"] == "2027-01-27" and r["title"] == "軟水 三遊間 cacao"]
        self.assertEqual([r["performerId"] for r in apply_reviewed_casts(same_day, ARTISTS)], ["nansui"])
        nansui = next(p for p in ARTISTS if p["id"] == "nansui")
        self.assertTrue(cast_matches(["[企画ライブ]軟水", "／三遊間"], nansui))

    def test_legacy_duplicate_evidence_does_not_equal_accepted_delivery(self):
        row = json.loads(Path("theater_events.json").read_text())["events"][0]
        row = {**row, "performerId": "pyuto"}
        new = {**row, "officialEventId": "test123"}
        for keys, expected in (
            ([], "migration_listing_delivery_unconfirmed"),
            ([notify_line.theater_notification_key(row)], "migration_exact_history_key"),
        ):
            with self.subTest(expected=expected):
                store = SimpleNamespace(data={"records": {}, "batches": {}})
                outbox = notification_outbox.Outbox(store, [], ARTISTS, legacy_theater_keys=keys)
                outbox.add([row], migration=True)
                self.assertEqual(outbox.add([new]), [])
                verdict = outbox.records[notification_outbox.record_id(new)]
                self.assertEqual((verdict["status"], verdict["reason"], verdict["sentAt"]),
                                 ("legacy", expected, None))

    def test_fany_failure_keeps_prior_fany_and_notifies_completed_theater(self):
        old = {"source": "fany", "performerId": "pyuto", "date": "2099-01-23",
               "startTime": "18:00", "venue": "会場", "title": "既存公演"}
        theater = {"source": "theater", "theaterId": "roppongi", "performerId": "pyuto",
                   "date": "2099-01-24", "startTime": "20:00", "venue": "六本木",
                   "title": "新しい公演", "performersText": ["ピュート"]}
        store = Mock(data={"records": {}, "batches": {}})
        delivery = Mock(return_value=Mock(status_code=200, headers={}))
        catalogs = Mock()

        def sources(_):
            yield "fany/pyuto", None, None
            yield "theater/roppongi", [theater], None
            delivery.assert_called_once()
            yield "theater/shibuya", [], None

        with (patch.object(notification_pipeline, "read_events", side_effect=[[old], []]),
              patch.object(notify_line, "post_line", delivery)):
            notification_pipeline.run(store, ARTISTS, sources, persist_catalogs=catalogs)
        self.assertEqual(catalogs.call_args.args[0], [old])
        self.assertEqual(catalogs.call_args.args[1][0]["title"], theater["title"])

    def test_other_acts_marker_is_inconclusive(self):
        candidate = {"date": "2027-01-01", "startTime": "17:00", "title": "公演", "performerId": "pyuto"}
        evidence = {"months": ["2027-01"], "official": [{**candidate, "cast": ["サルゴリラ", "／他"]}]}
        self.assertEqual(acquisition_probe.review(candidate, evidence, {p["id"]: p for p in ARTISTS})[0],
                         "cast_partial_unconfirmed")
