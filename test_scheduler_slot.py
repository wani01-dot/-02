import json
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import notification_pipeline
from scheduler_slot import claim_slot
from sync_summary import render_summary


class SchedulerSlotTest(unittest.TestCase):
    def setUp(self):
        self.store = SimpleNamespace(data={}, save=Mock())

    def test_external_and_native_share_the_same_slot_then_native_covers_outage(self):
        self.assertTrue(claim_slot(self.store, "2026-11-27T12:00:04Z", "2026-11-27T12:00:40Z")[0])
        self.assertFalse(claim_slot(self.store, "2026-11-27T12:04:02Z", "2026-11-27T12:05:02Z")[0])
        self.assertTrue(claim_slot(self.store, "2026-11-27T12:09:03Z", "2026-11-27T12:09:40Z")[0])
        self.assertFalse(claim_slot(self.store, "2026-11-27T12:01:00Z", "2026-11-27T12:10:00Z")[0])
        self.assertEqual(self.store.save.call_count, 2)

    def test_missing_api_timestamp_falls_back_to_current_utc_slot(self):
        claimed, label = claim_slot(self.store, "", "2026-11-27T21:02:00+09:00")
        self.assertTrue(claimed)
        self.assertEqual(label, "2026-11-27T12:00:00+00:00")

    def test_duplicate_does_not_load_or_acquire_or_notify_or_read_quota(self):
        claim_slot(self.store, "2026-11-27T12:00:01Z", "2026-11-27T12:00:10Z")
        with (
            patch.dict("os.environ", {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main",
                                      "GITHUB_EVENT_NAME": "schedule", "RUN_CREATED_AT": "2026-11-27T12:04:02Z"},
                       clear=True),
            patch.object(notification_pipeline, "GitState", return_value=self.store),
            patch.object(notification_pipeline, "run") as run,
            patch.object(notification_pipeline, "LineQuota") as quota,
        ):
            notification_pipeline.main()
        run.assert_not_called()
        quota.assert_not_called()

    def test_losing_remote_compare_and_swap_aborts_before_collection(self):
        self.store.save.side_effect = subprocess.CalledProcessError(1, "git push")
        with (
            patch.dict("os.environ", {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main",
                                      "EXTERNAL_SCHEDULER": "true", "RUN_CREATED_AT": "2026-11-27T12:00:00Z"},
                       clear=True),
            patch.object(notification_pipeline, "GitState", return_value=self.store),
            patch.object(notification_pipeline, "run") as run,
        ):
            with self.assertRaises(subprocess.CalledProcessError):
                notification_pipeline.main()
        run.assert_not_called()

    def test_external_tick_rejects_manual_resend_inputs(self):
        with (
            patch.dict("os.environ", {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main",
                                      "EXTERNAL_SCHEDULER": "true", "LINE_REQUEUE_CONFIRM": "true"}, clear=True),
            patch.object(notification_pipeline, "GitState") as state,
        ):
            with self.assertRaisesRegex(ValueError, "manual resend"):
                notification_pipeline.main()
        state.assert_not_called()

    def test_duplicate_is_visible_in_summary(self):
        log = [json.dumps({"type": "scheduler_slot", "status": "skipped", "slot": "2026-11-27T12:00:00Z"})]
        self.assertIn("11/27 21:00:00 JST の5分枠は処理済み", render_summary(log))
