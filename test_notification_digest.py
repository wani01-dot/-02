import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import requests

import fast_fany_send
import notify_line as line


def event(title, performer="maison", **fields):
    return {
        "performerId": performer,
        "title": title,
        "date": "2026-12-05",
        "startTime": "19:00",
        "venue": "テスト劇場",
        "source": "fany",
        **fields,
    }


class DigestTest(unittest.TestCase):
    def test_large_digest_counts_prioritizes_sales_and_shows_streaming(self):
        now = datetime(2026, 11, 24, 10, tzinfo=line.JST)
        upcoming = event(
            "先行受付ライブ",
            trackedPerformers=["maison", "pyuto"],
            ticketOptions=[{
                "salePeriods": [{"label": "先行", "startAt": "2026-11-25T01:00:00Z"}],
            }],
        )
        stream = event("配信ライブ", "nansui", hasStreaming=True, ticketStatus="販売中")
        others = [event(f"公演 {i} " + "長" * 150) for i in range(500)]
        message = line.build_line_digest([stream, *others, upcoming], [], [], now=now)
        bubble = message["contents"]
        texts = [item["text"] for item in bubble["body"]["contents"] if item["type"] == "text"]
        buttons = [item["action"] for item in bubble["footer"]["contents"]]
        self.assertEqual(message["type"], "flex")
        self.assertIn("新着 502 公演", message["altText"])
        self.assertEqual(texts[1], upcoming["title"])
        self.assertIn("発売間近 11/25 10:00（先行）", texts)
        self.assertIn("販売中", texts)
        self.assertIn("📡 配信あり", texts)
        self.assertIn("ほか 496件はカレンダーへ", texts)
        self.assertEqual([button["label"] for button in buttons[:3]],
                         ["🔴めぞん 501件", "🟡ピュート 1件", "🔵軟水 1件"])
        self.assertEqual([button["uri"].split("=")[-1] for button in buttons],
                         ["maison", "pyuto", "nansui", "all"])
        self.assertLess(len(json.dumps(bubble, ensure_ascii=False).encode()), 30_000)

    def test_sale_fallback_and_empty_digest(self):
        now = datetime(2026, 11, 24, 10, tzinfo=line.JST)
        self.assertIsNone(line.build_line_digest([], [], []))
        self.assertEqual(
            line.digest_sale([{"saleStartAt": "2026-11-20", "saleEndAt": "2026-11-27"}], now),
            (None, "受付期間中"),
        )
        self.assertEqual(
            line.digest_sale([{"saleStartAt": "invalid", "saleEndAt": "2026-11-23"}], now),
            (None, "受付期間終了"),
        )

    def test_standard_history_updates_only_on_success_and_prevents_resend(self):
        ticket = event("合同ライブのお知らせ")
        duplicate = {**ticket, "source": "theater", "theaterId": "test"}
        theater = event("独演会のお知らせ", "nansui", source="theater", theaterId="test")
        self.check_delivery(line.main, [ticket], [duplicate, theater], 2)

    def test_fast_fany_history_updates_only_on_success_and_prevents_resend(self):
        with patch.object(fast_fany_send, "SEND_ENABLED", True):
            self.check_delivery(fast_fany_send.main, [event("FANY高速通知ライブ")], [], 1)

    def check_delivery(self, entry_point, tickets, theaters, expected_count):
        files = {
            "new_events.json": tickets,
            "fast_fany_events.json": {"events": tickets},
            "events.json": {"events": []},
            "theater_events.json": {"events": theaters},
            "stream_events.json": [],
            "performers.json": {"performers": [
                {"id": "maison", "notify": True}, {"id": "nansui", "notify": True},
            ]},
            "notified_events.json": {"stableKeys": ["existing"]},
            "theater_notified_events.json": {"theaterKeys": ["existing"]},
        }
        histories = ("notified_events.json", "theater_notified_events.json")
        cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            os.chdir(directory)
            try:
                for path, value in files.items():
                    Path(path).write_text(json.dumps(value), encoding="utf-8")
                original = {path: Path(path).read_bytes() for path in files}
                with (
                    patch.object(line, "LINE_TOKEN", "mock-token"),
                    patch.object(line, "LINE_TO", "mock-destination"),
                    patch.object(line.requests, "post") as post,
                ):
                    post.return_value = Mock(status_code=500, ok=False, text="test failure")
                    post.return_value.raise_for_status.side_effect = requests.HTTPError("test failure")
                    with self.assertRaises(requests.HTTPError):
                        entry_point()
                    for path in histories:
                        self.assertEqual(Path(path).read_bytes(), original[path])
                    post.reset_mock()
                    post.return_value = Mock(status_code=200, ok=True)
                    entry_point()
                    post.assert_called_once()
                    messages = post.call_args.kwargs["json"]["messages"]
                    self.assertEqual(len(messages), 1)
                    self.assertIn(f"新着 {expected_count} 公演", messages[0]["altText"])
                    for path in histories:
                        self.assertIn("existing", Path(path).read_text(encoding="utf-8"))
                    self.assertIn(line.stable_notification_key(tickets[0]),
                                  line.load_json(histories[0], {})["stableKeys"])
                    for theater in theaters:
                        self.assertIn(line.theater_notification_key(theater),
                                      line.load_json(histories[1], {})["theaterKeys"])
                    post.reset_mock()
                    entry_point()
                    post.assert_not_called()
                for path in files.keys() - set(histories):
                    self.assertEqual(Path(path).read_bytes(), original[path])
            finally:
                os.chdir(cwd)
