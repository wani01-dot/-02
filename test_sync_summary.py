import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import line_quota
import notification_outbox
import notification_pipeline
import notify_line
from sync_summary import render_summary


class SyncSummaryTest(unittest.TestCase):
    def test_summary_keeps_failed_and_unfinished_sources_and_409_without_inventing_time(self):
        rows = [
            {"type": "source_started", "source": "theater/roppongi", "startedAt": "2026-11-27T00:00:00Z"},
            {"type": "source_result", "source": "fany/maison", "failures": 1, "error": "403 for url: https://example.org"},
            {"type": "line_result", "retryKey": "abc", "source": "tiget/pyuto", "status": "accepted", "httpStatus": 409},
            {"type": "line_usage", "month": "2026-11", "freeCap": 200, "effectiveCap": 200,
             "consumed": 42, "freeRemaining": 158, "automaticRemaining": 147},
        ]
        result = render_summary(map(json.dumps, rows))
        self.assertIn("| 六本木 | 完了記録なし", result)
        self.assertIn("| FANY・めぞん | 失敗・403 |", result)
        self.assertIn("| TIGET・ピュート | 受理済み・受理時刻不明 | — | — |", result)
        self.assertIn("| 2026-11 | 42 | 200 | 200 | 158 | 147 |", result)
        self.assertIn("11/27 09:00:00", result)

    def test_reports_creation_interval_separately_from_runner_wait(self):
        store = SimpleNamespace(data={"lastScheduledCreatedAt": "2026-11-26T12:00:00Z"})
        with (patch.dict("os.environ", {"GITHUB_EVENT_NAME": "schedule",
                                       "RUN_CREATED_AT": "2026-11-26T17:00:00Z",
                                       "RUN_STARTED_AT": "2026-11-26T17:00:04Z"}),
              patch.object(notification_pipeline, "audit") as audit):
            notification_pipeline.log_run_timing(store)
        self.assertEqual(audit.call_args.kwargs["queueSeconds"], 4)
        self.assertEqual(audit.call_args.kwargs["scheduleIntervalSeconds"], 18000)

    def test_quota_info_is_observable_without_a_send_and_without_destination(self):
        quota = line_quota.LineQuota(SimpleNamespace(data={}))
        quota.read = Mock(side_effect=[{"type": "limited", "value": 200}, {"totalUsage": 57}])
        with (patch.object(notify_line, "post_line") as send,
              patch.object(line_quota, "audit") as audit):
            quota.audit_usage()
        send.assert_not_called()
        self.assertEqual(audit.call_args.kwargs["consumed"], 57)
        self.assertEqual(audit.call_args.kwargs["freeRemaining"], 143)
        self.assertNotIn("destination", audit.call_args.kwargs)

    def test_batch_logs_acceptance_duration_and_keeps_existing_message_format(self):
        store = SimpleNamespace(data={"records": {}, "batches": {}}, save=Mock())
        outbox = notification_outbox.Outbox(store, [], [{"id": "pyuto", "notify": True}])
        event = {"source": "tiget", "performerId": "pyuto", "date": "2099-01-01",
                 "startTime": "19:00", "title": "公演", "venue": "会場"}
        with patch.object(notification_outbox, "audit") as audit:
            key = outbox.stage(outbox.add([event]), source_label="tiget/pyuto",
                               source_completed_at="2026-11-27T00:00:00Z",
                               source_decided_at="2026-11-27T00:00:01Z")
            with (patch.object(notify_line, "post_line", return_value=Mock(status_code=200, headers={})) as send,
                  patch.object(notification_outbox, "timestamp", return_value="2026-11-27T00:00:03Z")):
                self.assertTrue(outbox.send(key))
        self.assertEqual(send.call_args.args[0]["type"], "flex")
        self.assertEqual(audit.call_args.kwargs["completionToAcceptanceSeconds"], 3)
        self.assertEqual(audit.call_args.kwargs["decisionToAcceptanceSeconds"], 2)
