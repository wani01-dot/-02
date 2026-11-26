import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests

import line_quota
import notification_outbox
import notify_line


class LineQuotaTest(unittest.TestCase):
    def setUp(self):
        self.persist = Mock()
        self.store = SimpleNamespace(data={"records": {}, "batches": {}}, save=self.persist)
        self.quota = line_quota.LineQuota(self.store)

    def test_reservation_persists_across_runs_and_retry_uses_same_reservation(self):
        self.quota.limits = Mock(return_value=(200, 184, 3))
        one, two, three = {}, {}, {}
        self.assertEqual(self.quota.reserve(one), (True, None))
        self.assertEqual(self.quota.reserve(one), (True, None))
        self.assertEqual(self.quota.reserve(two), (True, None))
        new_runner = line_quota.LineQuota(self.store)
        new_runner.limits = Mock(return_value=(200, 185, 3))
        self.assertEqual(new_runner.reserve(three), (False, "monthly_budget"))
        self.assertEqual(new_runner.reserve(one), (True, None))
        self.assertEqual(self.store.data["lineQuota"]["projectedUsage"], 190)

    def test_probe_quota_without_assuming_group_has_one_recipient(self):
        self.quota.read = Mock(side_effect=[{"type": "limited", "value": 5000},
                                          {"totalUsage": 170}, {"count": 5}])
        with patch.object(notify_line, "LINE_TO", "Cmock-test-group"):
            self.assertEqual(self.quota.limits(), (200, 170, 5))
        self.assertEqual(self.quota.read.call_args.args[0], "/group/Cmock-test-group/members/count")

    def test_quota_when_unavailable_keeps_pending_batch_and_never_pushes(self):
        row = {"source": "fany", "performerId": "pyuto", "date": "2099-01-01",
               "startTime": "19:00", "venue": "会場", "title": "公演"}
        self.quota.limits = Mock(side_effect=requests.Timeout)
        box = notification_outbox.Outbox(
            self.store, [], [{"id": "pyuto", "notify": True}], quota=self.quota,
        )
        key = box.stage(box.add([row]))
        with patch.object(notify_line, "post_line") as post:
            self.assertTrue(box.send(key))
            self.assertTrue(box.send(key))
        post.assert_not_called()
        self.persist.assert_called()
        self.quota.limits.assert_called_once()
        self.assertEqual(box.batches[key]["status"], "pending")
        self.assertIsNone(box.batches[key]["firstAttemptAt"])

    def test_quota_depletion_does_not_prevent_catalog_publication(self):
        import notification_pipeline as pipeline
        self.quota.limits = Mock(return_value=(200, 190, 1))
        old = {"source": "fany", "performerId": "pyuto", "date": "2099-01-01",
               "startTime": "18:00", "venue": "会場", "title": "既存"}
        new = {"source": "theater", "theaterId": "roppongi", "performerId": "pyuto",
               "date": "2099-01-02", "startTime": "19:00", "venue": "六本木",
               "title": "新着", "performersText": ["ピュート"]}
        sources = lambda _: iter([("fany/pyuto", None, None), ("theater/roppongi", [new], None)])
        publish = Mock()
        with (patch.object(pipeline, "read_events", side_effect=[[old], []]),
              patch.object(notify_line, "post_line") as post):
            pipeline.run(self.store, [{"id": "pyuto", "notify": True}], sources,
                         persist_catalogs=publish, quota=self.quota)
        post.assert_not_called()
        self.assertEqual(publish.call_args.args[0], [old])
        self.assertEqual(publish.call_args.args[1][0]["title"], "新着")
        self.assertEqual(len(self.store.data["batches"]), 1)

    def test_legacy_writer_is_blocked_before_reading_or_sending_on_actions(self):
        for workflow in ("sync.yml", "theater-probe.yml"):
            with (self.subTest(workflow=workflow),
                  patch.dict("os.environ", {"GITHUB_ACTIONS": "true",
                             "GITHUB_WORKFLOW_REF": f"user/repo/.github/workflows/{workflow}@refs/heads/main"}),
                  patch.object(notify_line, "load_json") as load,
                  patch.object(notify_line, "post_line") as post):
                with self.assertRaisesRegex(RuntimeError, "旧通知経路"):
                    notify_line.main()
                load.assert_not_called()
                post.assert_not_called()
