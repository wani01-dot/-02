import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from livepocket_scraper import _shared_detail, _detail_cache, _detail_lock


class DetailCacheTests(unittest.TestCase):
    def setUp(self):
        with _detail_lock:
            _detail_cache.clear()

    def test_concurrent_requests_share_html(self):
        entered = Event()
        release = Event()
        calls = []

        def loader():
            calls.append(1)
            entered.set()
            if not release.wait(5):
                raise RuntimeError("test timed out")
            return "<html>cast</html>"

        with ThreadPoolExecutor(max_workers=3) as pool:
            first = pool.submit(_shared_detail, ("browser", "url"), loader)
            try:
                self.assertTrue(entered.wait(5))
                others = [pool.submit(_shared_detail, ("browser", "url"), loader) for _ in range(2)]
            finally:
                release.set()
            self.assertEqual([f.result(timeout=5) for f in [first, *others]], ["<html>cast</html>"] * 3)
        self.assertEqual(len(calls), 1)

    def test_failure_can_be_retried(self):
        key = ("http", "url")
        with self.assertRaises(RuntimeError):
            _shared_detail(key, lambda: "")
        self.assertEqual(_shared_detail(key, lambda: "ok"), "ok")

    def test_http_and_browser_are_separate(self):
        self.assertEqual(_shared_detail(("http", "url"), lambda: "static"), "static")
        self.assertEqual(_shared_detail(("browser", "url"), lambda: "rendered"), "rendered")


if __name__ == "__main__":
    unittest.main()
