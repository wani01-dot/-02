import json
import os
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests

import notification_outbox as state
import notification_pipeline as pipeline
import livepocket_scraper
import notify_line as line
import scraper
import theater_scraper as theater
from performer_matching import cast_matches

PERFORMERS = [{"id": pid, "name": name, "notify": True}
              for pid, name in zip(("maison", "pyuto", "nansui"), ("めぞん", "ピュート", "軟水"))]


def show(**fields):
    return {"source": "theater", "theaterId": "roppongi", "performerId": "pyuto",
            "date": "2099-01-21", "startTime": "21:00",
            "title": "新ネタピュートライブ", "venue": theater.THEATERS[0]["venue"], **fields}


def row(eid, title, cast, opened, started, day="2027/01/21", **fields):
    return {"id": eid, "name": title, "memberHtml": cast, "date": day,
            "dateTime1": opened, "dateTime2": started, "dateTime3": "22:15",
            "url1": "https://ticket.fany.lol/reception/123/456", **fields}


class Store:
    def __init__(self):
        self.data = {"records": {}, "batches": {}, "lastScheduledAt": None}
        self.saved = None
        self.fail = False

    def save(self):
        if self.fail:
            raise OSError("simulated state push failure")
        self.saved = deepcopy(self.data)


class TheaterTest(unittest.TestCase):
    def test_roppongi_and_adjacent_rows_never_share_cast(self):
        rows = [
            row("1", "ダイタク×9番街レトロコントライブ「待ってろ！自動車学校」",
                "ダイタク／9番街レトロ", "19:00", "19:15"),
            row("2", "新ネタ<br>ピュートライブ", "ピュート<br>ゲスト：ビューティフルトーキョーマンズ／狛犬／あなたとネ",
                "20:45", "21:00", url2="https://example.org/stream", price3="1,000円"),
            row("3", "ピュートという文字がタイトルにある", "", "21:00", "21:15"),
            row("4", "その後の公演", "ダイタク", "21:30", "21:45"),
            row("5", "同日の別公演", "MC：メゾン／ゲスト：軟 水", "22:00", "22:15"),
            row("6", "翌日公演", "ﾋﾟｭｰﾄ", "20:45", "21:00", day="2027/01/22"),
            row("7", "翌月公演", "軟水", "20:45", "21:00", day="2027/02/01"),
        ]
        results = theater.parse_month(theater.THEATERS[0], 2027, 1, rows, PERFORMERS)
        self.assertEqual([(e["officialEventId"], e["performerId"]) for e in results],
                         [("2", "pyuto"), ("5", "maison"), ("5", "nansui"), ("6", "pyuto")])
        first = results[0]
        self.assertEqual((first["title"], first["openTime"], first["startTime"], first["endTime"]),
                         ("新ネタ ピュートライブ", "20:45", "21:00", "22:15"))
        self.assertTrue(first["hasStreaming"])
        self.assertTrue(first["sourceUrl"].endswith("?id=2"))
        self.assertNotIn("ダイタク", "/".join(first["performersText"]))

    def test_empty_feed_and_each_theater_failure(self):
        for venue in theater.THEATERS:
            with self.subTest(venue=venue["id"]):
                venue_id = venue.get("feedId", venue["id"])
                response = Mock(url=theater.FEED + "?theater=" + venue_id +
                                "&venue=01&date_from=20270101&date_to=20270131", ok=True)
                response.json.return_value = []
                self.assertEqual(theater.feed_rows(response, venue), [])
                response.ok = False
                with self.assertRaises(RuntimeError):
                    theater.feed_rows(response, venue)
                response.ok = True
                response.url = theater.FEED + "?theater=wrong"
                with self.assertRaises(ValueError):
                    theater.feed_rows(response, venue)

    def test_month_switch_mismatch_fails_before_parsing(self):
        page = Mock()
        response = Mock(url=theater.FEED + "?theater=roppongi&venue=01&date_from=20270101&date_to=20270131", ok=True)
        response.json.return_value = []
        context = page.expect_response.return_value
        context.__enter__ = Mock(return_value=SimpleNamespace(value=response))
        context.__exit__ = Mock(return_value=False)
        tabs = Mock()
        tabs.evaluate_all.return_value = [[2027, 1]]
        active = Mock()
        active.evaluate.return_value = [2026, 12]
        marker = Mock()
        marker.input_value.return_value = "roppongi"
        venue = Mock(input_value=Mock(return_value="01"))
        locators = {"#theater": marker, "#venue": venue, ".calendar-month a[data-y][data-m]": tabs,
                    ".calendar-month a.active": active}
        page.locator.side_effect = lambda selector: locators.get(selector, Mock())
        with patch.object(theater, "parse_month") as parse:
            with self.assertRaisesRegex(ValueError, "Month switch failed"):
                theater.scrape_theater(Mock(new_page=Mock(return_value=page)), theater.THEATERS[0], PERFORMERS)
            parse.assert_not_called()
        page.close.assert_called_once()

    def test_cast_normalization_and_explicit_individual_alias(self):
        for cast, performer in zip(("ゲスト:メ ゾ ン", "MC：ﾋﾟｭｰﾄ", "出演：軟　水"), PERFORMERS):
            self.assertTrue(cast_matches(cast, performer))
            self.assertFalse(cast_matches(cast + "研究会", performer))
        self.assertTrue(cast_matches("MC：登録した個人名", {**PERFORMERS[0], "aliases": ["登録した個人名"]}))
        self.assertFalse(cast_matches("個人名（めぞん）", PERFORMERS[0]))
        self.assertTrue(cast_matches("ゲスト：原一刻", PERFORMERS[0]))
        self.assertTrue(cast_matches("ポイント（ピュート）", PERFORMERS[1]))
        self.assertTrue(cast_matches("司会：大川内聡", PERFORMERS[2]))
        self.assertFalse(cast_matches("ポイント", PERFORMERS[1]))

    def test_fany_reception_parent_cannot_include_another_show(self):
        page = """<div><div><p>2027/01/21</p><p>出演</p><p>ピュート</p>
        <a href="/reception/12/34">A</a><a href="/reception/56/78">B</a></div></div>"""
        self.assertEqual(scraper.find_reception_candidates(page), [])


    def test_fany_reception_separates_two_cards_on_same_day(self):
        response = Mock(text="""
            <div><p>2027/01/21</p><p>対象外</p><p>開演19:15</p>
            <p>出演</p><p>ダイタク</p><a href="/reception/12/34">購入</a></div>
            <div><p>2027/01/21</p><p>新ネタピュートライブ</p><p>開演21:00</p>
            <p>出演</p><p>ピュート</p><a href="/reception/56/78">購入</a></div>
        """)
        session = Mock()
        session.get.return_value = response
        with patch.object(scraper, "is_today_or_future", return_value=True):
            _, events = scraper.request_fany_range(session, PERFORMERS[1], date(2027, 1, 21), date(2027, 1, 21))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["performersText"], ["ピュート"])
        self.assertTrue(events[0]["sourceUrl"].endswith("/reception/56/78"))

    def test_livepocket_failed_http_does_not_infer_cast_from_title(self):
        session = Mock()
        session.get.side_effect = requests.Timeout()
        result = livepocket_scraper.scrape_livepocket_detail(
            session, PERFORMERS[1], "https://livepocket.jp/e/example"
        )
        self.assertIsNone(result)

    def test_transient_theater_failure_retries_without_returning_empty(self):
        manager = Mock()
        manager.__enter__ = Mock(return_value=Mock())
        manager.__exit__ = Mock(return_value=False)
        with (patch.object(theater, "sync_playwright", return_value=manager),
              patch.object(theater, "scrape_theater", side_effect=[RuntimeError("temporary"), []]) as scrape,
              patch.object(theater.time, "sleep")):
            self.assertEqual(theater.fetch_theater(theater.THEATERS[0], PERFORMERS), [])
            self.assertEqual(scrape.call_count, 2)


class GitStateTest(unittest.TestCase):
    def test_concurrent_writers_cannot_publish_two_different_new_states(self):
        previous = Path.cwd()
        with TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                state.git("init", "--bare", "remote.git")
                state.git("init", "checkout")
                os.chdir("checkout")
                state.git("config", "user.name", "Mock Bot")
                state.git("config", "user.email", "bot@example.invalid")
                state.git("remote", "add", "origin", "../remote.git")
                first = state.GitState()
                stale = state.GitState()
                first.data["lastScheduledAt"] = "first writer"
                first.save()
                stale.data["lastScheduledAt"] = "stale writer"
                with self.assertRaises(Exception):
                    stale.save()
                self.assertEqual(state.GitState().data["lastScheduledAt"], "first writer")
            finally:
                os.chdir(previous)


class DeliveryTest(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.box = state.Outbox(self.store, [], PERFORMERS)
        self.enterContext(patch.object(line, "LINE_TOKEN", "mock-token"))
        self.enterContext(patch.object(line, "LINE_TO", "mock-user"))

    def test_cross_source_duplicate_but_separate_times_titles_and_venues(self):
        a = show(officialEventId="123")
        fany = show(source="fany", sourceUrl="https://ticket.fany.lol/reception/55/99",
                    venue="YOSHIMOTO ROPPONGI THEATER")
        self.assertEqual(state.duplicate_reason(a, fany), "show_and_cast")
        self.assertEqual(state.duplicate_reason(a, {**a, "title": "公式による改題"}), "official_id")
        for other in ({**fany, "startTime": "19:15"}, {**fany, "title": "別の公演"},
                      {**fany, "venue": "別会場"}):
            self.assertFalse(state.duplicate_reason(a, other))
        self.assertEqual(len(self.box.add([a, fany])), 1)
        self.assertEqual(self.box.records[state.record_id(fany)]["status"], "duplicate")

    def test_retry_uses_persisted_body_and_key(self):
        key = self.box.stage(self.box.add([show()]))
        with patch.object(state.requests, "post", side_effect=[
            requests.Timeout(), Mock(status_code=200, headers={"x-line-request-id": "ok"}),
        ]) as post:
            self.assertFalse(self.box.send(key))
            self.assertEqual(self.store.saved["records"][state.record_id(show())]["status"], "failed")
            self.assertTrue(self.box.retry())
            self.assertEqual(post.call_args_list[0], post.call_args_list[1])
        self.assertEqual(self.box.records[state.record_id(show())]["status"], "accepted")

    def test_save_failure_before_and_after_api_acceptance(self):
        key = self.box.stage(self.box.add([show()]))
        self.store.fail = True
        with patch.object(state.requests, "post") as post:
            with self.assertRaises(OSError):
                self.box.send(key)
            post.assert_not_called()
        self.store.fail = False

        def accepted(*args, **kwargs):
            self.store.fail = True
            return Mock(status_code=200, headers={"x-line-request-id": "original"})

        with patch.object(state.requests, "post", side_effect=accepted) as first:
            with self.assertRaises(OSError):
                self.box.send(key)
        self.store.data = self.store.saved
        self.store.fail = False
        recovered = state.Outbox(self.store, [], PERFORMERS)
        with patch.object(state.requests, "post", return_value=Mock(
            status_code=409, headers={"x-line-accepted-request-id": "original"}
        )) as second:
            self.assertTrue(recovered.retry())
        self.assertEqual(first.call_args, second.call_args)

    def test_expired_ambiguous_attempt_never_sends_again(self):
        key = self.box.stage(self.box.add([show()]))
        self.box.batches[key]["firstAttemptAt"] = "2000-01-01T00:00:00+00:00"
        with patch.object(state.requests, "post") as post:
            self.assertFalse(self.box.send(key))
            post.assert_not_called()
        self.assertEqual(self.box.batches[key]["status"], "reconciliation_required")

    def test_migration_keeps_legacy_evidence_separate_and_requeue_has_preview(self):
        old = show()
        self.assertEqual(self.box.add([old], migration=True), [])
        self.assertEqual(self.box.add([show()]), [])
        with patch.object(state.requests, "post") as post:
            self.box.requeue_confirmed_unsent(state.record_id(old), "audit test evidence")
            post.assert_not_called()
        self.assertEqual(self.box.records[state.record_id(old)]["status"], "legacy")

    def test_502_new_shows_one_digest_with_detail_audit(self):
        events = [show(title=f"新着 {i}") for i in range(502)]
        key = self.box.stage(self.box.add(events))
        payload = self.box.batches[key]["message"]
        self.assertIn("502 公演", payload["altText"])
        self.assertEqual(sum(r["inDigestDetails"] for r in self.box.records.values()), 6)
        self.assertLess(len(json.dumps(payload["contents"], ensure_ascii=False).encode()), 30_000)

    def test_pipeline_sends_completed_theater_while_ticket_is_still_waiting(self):
        release = threading.Event()
        ticket_finished = threading.Event()

        def ticket(source, performer):
            if source != "fany":
                if not release.wait(3):
                    raise AssertionError("Theater push must release other-ticket worker")
                ticket_finished.set()
            return []

        venue = theater.THEATERS[0]
        performers = [{**PERFORMERS[1], "sources": ["fany", "tiget"]}]
        catalog = Mock()

        def accept(*args, **kwargs):
            self.assertFalse(ticket_finished.is_set())
            release.set()
            return Mock(status_code=200, headers={})

        with (patch.object(pipeline, "THEATERS", [venue]),
              patch.object(pipeline, "fetch_ticket", side_effect=ticket),
              patch.object(pipeline, "fetch_theater", return_value=[show()]),
              patch.object(pipeline, "read_events", return_value=[]),
              patch.object(line, "load_stream_events", return_value=[]),
              patch.object(state.requests, "post", side_effect=accept) as post):
            pipeline.run(self.store, performers, pipeline.completed_sources, persist_catalogs=catalog)
        post.assert_called_once()
        self.assertTrue(ticket_finished.is_set())
        self.assertEqual(catalog.call_args.args[1][0]["title"], show()["title"])

    def test_fany_result_is_processed_before_blocking_other_source(self):
        release = threading.Event()

        def ticket(source, performer):
            if source == "fany":
                return [show(source="fany", sourceUrl="https://ticket.fany.lol/reception/22/33")]
            if not release.wait(3):
                raise AssertionError("FANY should send before other-ticket completion")
            return []

        performers = [{**PERFORMERS[1], "sources": ["fany", "tiget"]}]

        def accept(*args, **kwargs):
            release.set()
            return Mock(status_code=200, headers={})

        with (patch.object(pipeline, "THEATERS", [theater.THEATERS[0]]),
              patch.object(pipeline, "fetch_ticket", side_effect=ticket),
              patch.object(pipeline, "fetch_theater", return_value=[]),
              patch.object(pipeline, "read_events", return_value=[]),
              patch.object(line, "load_stream_events", return_value=[]),
              patch.object(state.requests, "post", side_effect=accept) as post):
            pipeline.run(self.store, performers, pipeline.completed_sources, persist_catalogs=Mock())
        post.assert_called_once()
        self.assertTrue(release.is_set())

    def test_all_theaters_fail_and_existing_catalog_survives(self):
        old = show()
        sources = Mock(return_value=[(f"theater/{t['id']}", None, None) for t in theater.THEATERS])
        catalog = Mock()
        with (patch.object(pipeline, "read_events", side_effect=[[], [old]]),
              patch.object(line, "load_stream_events", return_value=[]),
              patch.object(state.requests, "post") as post):
            with self.assertRaisesRegex(RuntimeError, "全劇場取得失敗"):
                pipeline.run(self.store, PERFORMERS, sources, persist_catalogs=catalog)
        post.assert_not_called()
        catalog.assert_called_once_with([], [old])


if __name__ == "__main__":
    unittest.main()
