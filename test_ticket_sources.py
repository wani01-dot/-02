import unittest
from unittest.mock import Mock, patch

import requests
from bs4 import BeautifulSoup

import notification_pipeline as pipeline
import scraper

PERSON = {"id": "nansui", "name": "軟水", "sources": ["fany"]}


class TicketSourcesTest(unittest.TestCase):
    def test_tiget_uses_only_labelled_fields_and_preserves_performer_names(self):
        html = """<html><body>1999年1月1日 開演12:00 別の出演者：めぞん
        <h1 class="pg-event__header__title">公式公演名</h1>
        <dl class="pg-event__detail__section"><dt>開催日</dt><dd>2099年1月2日</dd></dl>
        <dl class="pg-event__detail__section"><dt>会場</dt><dd>テストホール</dd></dl>
        <dl class="pg-event__detail__section"><dt>出演者</dt><dd><a>軟 水</a> / <a>ﾋﾟｭｰﾄ</a></dd></dl>
        <dl class="pg-event__detail__section"><dt>開場 18:00 / 開演 18:30</dt><dd>チケット</dd></dl>
        </body></html>"""
        session = Mock()
        session.get.side_effect = [Mock(text='<a href="/events/123">正しい公演名</a>'), Mock(text=html)]
        event, = scraper.scrape_tiget(session, PERSON)
        self.assertEqual((event["date"], event["startTime"], event["venue"]),
                         ("2099-01-02", "18:30", "テストホール"))
        self.assertEqual(event["title"], "公式公演名")
        self.assertEqual(event["performersText"], ["軟 水", "ﾋﾟｭｰﾄ"])
        self.assertEqual(scraper.tiget_detail_fields(BeautifulSoup("<html>旧形式</html>", "html.parser")), None)

    def test_fany_cooldown_only_skips_denied_performer_and_leaves_theater_running(self):
        state = {}
        response = requests.Response()
        response.status_code = 403
        with (patch.object(pipeline, "THEATERS", [{"id": "roppongi"}]),
              patch.object(pipeline, "fetch_theater", return_value=[]) as theater,
              patch.object(pipeline, "fetch_ticket", side_effect=requests.HTTPError(response=response)) as fetch,
              patch.object(pipeline, "timestamp", return_value="2026-11-28T00:00:00+00:00")):
            first = list(pipeline.completed_sources([PERSON], fany_state=state))
            second = list(pipeline.completed_sources([PERSON], fany_state=state))
        self.assertIn(("fany/nansui", None, None), first)
        self.assertEqual([row[0] for row in second], ["theater/roppongi"])
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(theater.call_count, 2)
        self.assertEqual(state["fany/nansui"], "2026-11-28T06:00:00+00:00")

    def test_updating_tiget_title_merges_same_official_show_without_resetting_history(self):
        old = {"source": "tiget", "sourceUrl": "https://tiget.net/events/123", "performerId": "nansui",
               "date": "2099-01-02", "startTime": "18:30", "venue": "ホール",
               "title": "検索カードの長いタイトル", "firstSeenAt": "2026-11-27T00:00:00Z"}
        new = {**old, "title": "公式公演名"}
        other = {**new, "startTime": "21:00"}
        merged = pipeline.merge_catalog([old], [new, other], {})
        self.assertEqual([(e["title"], e["startTime"], e["firstSeenAt"]) for e in merged],
                         [("公式公演名", "18:30", old["firstSeenAt"]), ("公式公演名", "21:00", old["firstSeenAt"])])
