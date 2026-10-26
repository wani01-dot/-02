"""劇場先行通知。通常チケットの新着を含めず、既存のLINE通知処理を再利用する。"""
import json
import os
import tempfile
from pathlib import Path

import notify_line


def main():
    if not os.environ.get("LINE_CHANNEL_ACCESS_TOKEN") or not os.environ.get("LINE_TO"):
        raise RuntimeError("LINE通知の設定がありません")

    path = Path("theater_events.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    events = data if isinstance(data, list) else data.get("events")
    if not isinstance(events, list):
        raise ValueError("劇場イベントデータが不正です")
    if not events:
        # 劇場取得失敗と正常な0件を区別できないため、0件なら通知しない
        print("劇場取得0件。先行通知を安全のためスキップ")
        return

    # 一時的な空の新着ファイルを参照させ、劇場新着だけ通知する。
    # 元のnew_events.jsonは変更しない。
    with tempfile.TemporaryDirectory() as tempdir:
        blank = Path(tempdir) / "new_events.json"
        blank.write_text("[]", encoding="utf-8")
        original = notify_line.NEW_EVENTS_FILE
        try:
            notify_line.NEW_EVENTS_FILE = str(blank)
            notify_line.main()
        finally:
            notify_line.NEW_EVENTS_FILE = original

    print("劇場の先行通知判定完了")


if __name__ == "__main__":
    main()
