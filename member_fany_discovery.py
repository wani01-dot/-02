"""個人出演レーダー: 既存の公開収集データを個人名で再検査する。
FANYへのアクセスやLINE通知は行わない。
"""
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

SOURCES = [Path("events.json"), Path("discovered_events.json")]
OUTPUT = Path("member_discovery_events.json")
OFFICIAL_PROFILES = {
    "maison": ("https://profile.yoshimoto.co.jp/talent/detail?id=8835", ["吉野おいなり君", "めぞん吉野", "めぞん 吉野", "原一刻", "めぞん原"]),
    "nansui": ("https://profile.yoshimoto.co.jp/talent/detail?id=8902", ["大川内聡", "軟水大川内", "軟水 大川内", "つるまる", "軟水つるまる"]),
    "pyuto": ("https://profile.yoshimoto.co.jp/talent/detail?id=8773", ["ピュートポイント", "ピュート ポイント", "ポイント（ピュート）", "竹内智也", "ピュート竹内", "ピュート 竹内"]),
}
# 「ポイント」だけでは一般語と衝突するので対象にしない。

def load_events(path):
    if not path.exists():
        raise FileNotFoundError(f"{path} が見つかりません")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("events"), list):
        raise ValueError(f"{path} の events 配列が不正です")
    return data["events"]

def actor_text(event):
    fields = ("performersText", "performers", "cast", "castText", "出演者")
    texts = []
    for field in fields:
        val = event.get(field)
        if isinstance(val, list):
            texts.extend(str(x) for x in val if x)
        elif isinstance(val, str):
            texts.append(val)
    return " / ".join(texts)

def normalize(value):
    return re.sub(r"[\s　・/／()（）]+", "", str(value or "")).casefold()

def matches(text, aliases):
    normalized = normalize(text)
    return [name for name in aliases if normalize(name) in normalized]

def main():
    try:
        sources = [(p, load_events(p)) for p in SOURCES]
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"入力エラー。既存データは維持: {exc}", file=sys.stderr)
        return 1

    today = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
    result = {}
    inspected = 0
    for path, events in sources:
        for event in events:
            if not isinstance(event, dict):
                continue
            inspected += 1
            date = str(event.get("date", ""))
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) or date < today:
                continue
            text = actor_text(event)
            if not text:
                continue
            for group, (_, aliases) in OFFICIAL_PROFILES.items():
                names = matches(text, aliases)
                if not names:
                    continue
                copied = dict(event)
                copied["performerId"] = group
                copied["discoverySource"] = "member-from-existing-sources"
                copied["matchedMemberNames"] = names
                key = (group, date, str(event.get("startTime", "")),
                       normalize(event.get("title", "")), normalize(event.get("venue", "")))
                # 既存の発見データにある情報を優先
                if key not in result or path.name == "discovered_events.json":
                    result[key] = copied

    if not result:
        print(f"有効な個人出演の新規候補0件（{inspected}件を検査）。既存データは変更しません。")
        return 0

    output = {"syncedAt": datetime.now(timezone.utc).isoformat(),
              "source": "existing-events-only", "events": list(result.values())}
    temp = OUTPUT.with_suffix(".json.tmp")
    temp.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(OUTPUT)
    print(f"既存公演 {inspected}件から、個人出演候補 {len(result)}件を抽出。")
    print("注意: 外部サイトの新規発見ではありません。")
    return 0

if __name__ == "__main__":
    sys.exit(main())
