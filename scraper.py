import json
import re
from datetime import datetime, timezone
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup


# =========================================================
# 基本設定
# =========================================================

PERFORMERS_FILE = "performers.json"
EVENTS_FILE = "events.json"
NEW_EVENTS_FILE = "new_events.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.7",
}


# =========================================================
# 共通処理
# =========================================================

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    except FileNotFoundError:
        return default

    except json.JSONDecodeError:
        print(f"⚠️ {path} のJSON形式がおかしいため初期値を使用します")
        return
