"""指定したX投稿を、アカウント・芸人名を検証してx_posts.jsonへ登録。"""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ACCOUNTS = Path("x_accounts.json")
POSTS = Path("x_posts.json")
TARGETS = {
    "めぞん": ["めぞん", "吉野おいなり君", "原一刻"],
    "ピュート": ["ピュート", "竹内智也"],
    "軟水": ["軟水", "大川内聡", "つるまる"],
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--text", required=True)
    parser.add_argument("--date", default="")
    args = parser.parse_args()
    url = args.url.strip()
    parsed = urlparse(url)
    match = re.fullmatch(r"/([A-Za-z0-9_]+)/status/(\d+)/?", parsed.path)
    if parsed.scheme != "https" or parsed.hostname not in ("x.com", "www.x.com", "twitter.com", "www.twitter.com") or not match:
        raise ValueError("Xの投稿URLを入力してね（https://x.com/アカウント/status/数字）")
    account, post_id = match.groups()
    allowed = json.loads(ACCOUNTS.read_text(encoding="utf-8"))
    allowed = allowed if isinstance(allowed, list) else allowed.get("accounts", [])
    if account.lower() not in [str(a).lower() for a in allowed]:
        raise ValueError(f"監視対象外のアカウント: @{account}")
    body = args.text.strip()
    if not body or len(body) > 5000:
        raise ValueError("本文は1〜5000文字で入力してね")
    groups = [name for name, terms in TARGETS.items() if any(term in body for term in terms)]
    if re.search(r"(?:ピュート.{0,8}ポイント|ポイント.{0,8}ピュート)", body) and "ピュート" not in groups:
        groups.append("ピュート")
    if not groups:
        raise ValueError("本文に対象の芸人名が見つからないため登録しません")
    if args.date.strip():
        try:
            stamp = datetime.fromisoformat(args.date.strip().replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise ValueError("投稿日時は 2026-10-26T12:00:00+09:00 の形式で入力してね") from exc
    else:
        # 投稿日が不明なときは登録時刻を投稿日時と偽らない
        stamp = None
    canonical = f"https://x.com/{account}/status/{post_id}"
    items = json.loads(POSTS.read_text(encoding="utf-8")) if POSTS.exists() else []
    if not isinstance(items, list):
        raise ValueError("x_posts.jsonの形式が不正です")
    def identity(row):
        m = re.search(r"/status/(\d+)", str(row.get("url", row.get("post_url", ""))))
        return m.group(1) if m else None
    if any(identity(row) == post_id for row in items if isinstance(row, dict)):
        print(f"登録済み: {canonical}")
        return
    entry = {"url": canonical, "text": body}
    if stamp is not None:
        entry["created_at"] = stamp.isoformat()
    items.append(entry)
    POSTS.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"登録完了: {canonical} / 該当: {', '.join(groups)} / 合計{len(items)}件")

if __name__ == "__main__":
    main()
