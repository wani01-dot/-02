import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import acquisition_probe as probe
import notification_outbox
import notification_pipeline
import notify_line


class AcquisitionProbeTest(unittest.TestCase):
    def setUp(self):
        self.performer = {"id": "pyuto", "name": "ピュート", "notify": True}
        self.venue = probe.THEATERS[0]
        self.candidate = {"theaterId": self.venue["id"], "date": "2099-01-21",
                          "startTime": "19:15", "title": "候補公演", "performerId": "pyuto"}
        self.official = {**self.candidate, "officialEventId": "123", "cast": ["ダイタク"]}

    def test_exact_match_requires_official_cast_review(self):
        performers = {"pyuto": self.performer}
        def outcome(rows):
            return probe.review(self.candidate, {"months": ["2099-01"], "official": rows}, performers)[0]

        self.assertEqual(outcome([self.official]), "cast_differs_review_required")
        self.assertEqual(outcome([{**self.official, "cast": ["ﾋﾟｭｰﾄ"]}]), "official_cast_matches")
        self.assertEqual(outcome([{**self.official, "cast": []}]), "cast_unpublished")
        self.assertEqual(outcome([{**self.official, "startTime": "21:00"}]), "not_found")
        self.assertEqual(outcome([self.official, self.official]), "ambiguous")
        self.assertEqual(probe.review(self.candidate, None, performers)[0], "source_unavailable")

    def test_source_counts_and_read_only_path(self):
        event = {**self.candidate, "source": "theater", "officialEventId": "123",
                 "venue": self.venue["venue"], "performersText": ["ピュート"]}
        metadata = {"months": ["2099-01"], "official": [self.official]}
        log = io.StringIO()
        with (patch.object(probe, "THEATERS", [self.venue]),
              patch.object(probe, "theater_result", return_value=([event], metadata)),
              patch.object(probe, "fany_result", side_effect=RuntimeError("403")),
              patch.object(notify_line, "post_line") as post,
              patch.object(notification_outbox.GitState, "save") as save,
              patch.object(notification_pipeline, "publish_catalogs") as publish,
              redirect_stdout(log)):
            self.assertFalse(probe.probe([self.performer], [self.candidate], [], [], []))
        for forbidden in (post, save, publish):
            forbidden.assert_not_called()
        records = [json.loads(line) for line in log.getvalue().splitlines()]
        summary = records[-1]
        self.assertEqual(summary["failures"], ["fany/pyuto"])
        self.assertEqual(summary["hypotheticalBatches"], {"fany": 0, "theater": 1})
        result = next(r for r in records if r["type"] == "probe_source_result" and r["status"] == "success")
        self.assertEqual((result["officialShowCount"], result["counts"], result["targetMonths"]),
                         (1, {"pyuto": 1}, ["2099-01"]))
        self.assertGreaterEqual(result["elapsedToDecisionSeconds"], result["acquisitionSeconds"] - 0.001)
