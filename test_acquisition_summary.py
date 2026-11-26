import json
import unittest

from acquisition_summary import SOURCES, render_summary
from theater_scraper import THEATERS


class SummaryTest(unittest.TestCase):
    def test_expected_sources_and_failure_rows(self):
        self.assertEqual(set(SOURCES), {
            "fany/maison", "fany/pyuto", "fany/nansui",
            *[f"theater/{venue['id']}" for venue in THEATERS],
        })
        data = [
            {"type": "probe_source_result", "source": "fany/maison", "status": "failed",
             "acquisitionSeconds": 0.128, "error": "HTTP 403 | <example>\nstack trace"},
            {"type": "probe_source_result", "source": "theater/roppongi", "status": "success",
             "trackedShowCount": 0, "officialShowCount": 42, "acquisitionSeconds": 2,
             "counts": {"maison": 0, "pyuto": 0, "nansui": 0}},
            {"type": "probe_review", "status": "source_unavailable"},
        ]
        summary = render_summary(["{invalid JSON", *map(json.dumps, data)])
        self.assertIn("成功 **1** ／ 失敗 **1** ／ 未実行・未確認 **11**", summary)
        self.assertIn("| FANY・めぞん | 失敗 | — | 0.13 | HTTP 403 &#124; &lt;example&gt; |", summary)
        self.assertIn("| 六本木 | 成功 | 0 / 42 | 2.00 | — |", summary)
        self.assertIn("| 六本木 | 0 | 0 | 0 |", summary)
        self.assertIn("| 公式取得失敗・維持 | 1 |", summary)

    def test_missing_log_is_not_counted_as_success(self):
        self.assertIn("未実行・未確認 **13**", render_summary([]))
