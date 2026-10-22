"""FANYで個人名を検索する補助レーダー。LINE送信は行わない。"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
import requests
import scraper

OUTPUT = Path("member_discovery_events.json")
# 一般的すぎる単独の姓・名は検索しない
# 吉本興業公式プロフィールに基づく所属。検索語は本人名の明確な表記のみ。
# 「ポイント」は一般語だがFANYの出演者検索結果として照合する。
OFFICIAL_PROFILES = {
    "maison": {"url": "https://profile.yoshimoto.co.jp/talent/detail?id=8835", "members": ["吉野おいなり君", "原一刻"]},
    "nansui": {"url": "https://profile.yoshimoto.co.jp/talent/detail?id=8902", "members": ["大川内聡", "つるまる"]},
    "pyuto": {"url": "https://profile.yoshimoto.co.jp/talent/detail?id=8773", "members": ["ポイント", "竹内智也"]},
}
TARGETS = {group: data["members"] for group, data in OFFICIAL_PROFILES.items()}


def main():
    session = requests.Session()
    session.headers.update(scraper.HEADERS)
    collected = []
    success = 0
    failures = []
    for performer_id, names in TARGETS.items():
        for name in names:
            try:
                performer = {"id": performer_id, "name": name}
                found = scraper.scrape_fany(session, performer, {})
                # 出演者名に検索語が存在する場合を優先し、
                # 公演名だけの偶然の一致を避ける
                for event in found:
                    event["performerId"] = performer_id
                    event["discoverySource"] = "fany-member"
                    collected.append(event)
                success += 1
                print(f"{name}: {len(found)}件", flush=True)
            except Exception as exc:
                failures.append(f"{name}: {type(exc).__name__}: {exc}")
                print(f"検索失敗 {failures[-1]}", file=sys.stderr, flush=True)

    # 全検索失敗の場合は既存データを消さない
    if success == 0:
        raise RuntimeError("個人名検索が全て失敗。既存ファイルは維持します")

    # 全件ゼロ件はサイト側の一時的な不調の可能性があるため、既存データを維持。
    if not collected and OUTPUT.exists():
        print("検索結果0件。既存の個人出演データを維持します")
        return

    # 一部失敗時も既存の有効な情報を維持する
    if failures and OUTPUT.exists():
        old = json.loads(OUTPUT.read_text(encoding="utf-8"))
        collected.extend(old.get("events", []))

    # 公演名と日時が同じものだけ集約。別名表記は後段の既存処理で統合
    unique = {}
    for e in collected:
        key = (e.get("performerId"), e.get("date"), e.get("startTime"), e.get("title"), e.get("sourceUrl"))
        unique[key] = e

    result = {"syncedAt": datetime.now(timezone.utc).isoformat(), "events": list(unique.values())}
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\\n", encoding="utf-8")
    print(f"個人名検索: {len(unique)}件、成功 {success}、失敗 {len(failures)}")

if __name__ == "__main__":
    main()
