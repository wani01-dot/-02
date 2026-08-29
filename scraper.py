import json
import re
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup


# ==========================================
# 設定
# ==========================================

PERFORMERS_FILE = "performers.json"
NEW_EVENTS_FILE = "new_events.json"

FANY_URL = "https://ticket.fany.lol/search/event"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) "
        "Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
}


# ==========================================
# JSON
# ==========================================

def load_json(path, default):
    try:
        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:
            return json.load(f)

    except (
        FileNotFoundError,
        json.JSONDecodeError
    ):
        return default


def save_json(path, data):
    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


# ==========================================
# 文字整理
# ==========================================

def clean(text):
    return re.sub(
        r"\s+",
        " ",
        text or ""
    ).strip()


# ==========================================
# FANY取得
# ==========================================

def get_fany_lines(
    session,
    performer_name
):

    search_url = (
        FANY_URL
        + "?"
        + urlencode({
            "keywords":
                performer_name,
            "search_type":
                "search_string"
        })
    )

    print("")
    print(
        "================================"
    )

    print(
        f"FANY検索：{performer_name}"
    )

    print(
        f"URL：{search_url}"
    )

    response = session.get(
        search_url,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    lines = []

    for raw in soup.get_text(
        "\n"
    ).splitlines():

        line = clean(raw)

        if line:
            lines.append(line)

    print(
        f"全テキスト行数：{len(lines)}"
    )

    return lines


# ==========================================
# 公演ブロック抽出
# ==========================================

DATE_RE = re.compile(
    r"^(20\d{2})/"
    r"(\d{1,2})/"
    r"(\d{1,2})"
)


def find_event_blocks(
    lines,
    performer_name
):

    indexes = []

    for index, line in enumerate(
        lines
    ):

        if DATE_RE.match(line):
            indexes.append(index)

    print(
        f"日付行候補：{len(indexes)}件"
    )

    blocks = []

    for number, start in enumerate(
        indexes
    ):

        if number + 1 < len(indexes):
            end = indexes[number + 1]
        else:
            end = len(lines)

        block = lines[
            start:end
        ]

        whole_text = " ".join(
            block
        )

        # 対象芸人が入っている公演だけ
        if (
            performer_name
            not in whole_text
        ):
            continue

        blocks.append(
            block
        )

    print(
        f"{performer_name}を含むブロック："
        f"{len(blocks)}件"
    )

    return blocks


# ==========================================
# デバッグ表示
# ==========================================

def print_debug_blocks(
    performer_name,
    blocks
):

    print("")
    print(
        "################################"
    )

    print(
        f"{performer_name} 公演デバッグ"
    )

    print(
        "################################"
    )

    # 多すぎるとログが読めないので
    # 最初の3公演だけ詳しく表示
    for block_number, block in enumerate(
        blocks[:3],
        start=1
    ):

        print("")
        print(
            "================================"
        )

        print(
            f"公演ブロック {block_number}"
        )

        print(
            "================================"
        )

        # 最大40行
        for line_number, line in enumerate(
            block[:40]
        ):

            print(
                f"[{line_number:02d}] "
                f"{repr(line)}"
            )

        print(
            "================================"
        )


# ==========================================
# 特に怪しい行を検索
# ==========================================

def print_interesting_lines(
    performer_name,
    lines
):

    print("")
    print(
        "----- 時刻を含む行 -----"
    )

    time_count = 0

    for index, line in enumerate(
        lines
    ):

        if re.search(
            r"\d{1,2}:\d{2}",
            line
        ):

            print(
                f"[{index}] "
                f"{repr(line)}"
            )

            time_count += 1

            if time_count >= 20:
                break

    print("")
    print(
        "----- 「開演」を含む行 -----"
    )

    count = 0

    for index, line in enumerate(
        lines
    ):

        if "開演" in line:

            print(
                f"[{index}] "
                f"{repr(line)}"
            )

            count += 1

            if count >= 20:
                break

    print("")
    print(
        "----- 「出演」を含む行 -----"
    )

    count = 0

    for index, line in enumerate(
        lines
    ):

        if "出演" in line:

            print(
                f"[{index}] "
                f"{repr(line)}"
            )

            count += 1

            if count >= 20:
                break


# ==========================================
# メイン
# ==========================================

def main():

    print(
        "================================"
    )

    print(
        "FANY解析デバッグ開始"
    )

    print(
        "================================"
    )

    config = load_json(
        PERFORMERS_FILE,
        {
            "performers": []
        }
    )

    performers = config.get(
        "performers",
        []
    )

    if not performers:

        print(
            "performers.jsonに"
            "芸人が登録されていません"
        )

        save_json(
            NEW_EVENTS_FILE,
            []
        )

        return


    session = requests.Session()

    session.headers.update(
        HEADERS
    )


    for performer in performers:

        performer_name = (
            performer.get(
                "name",
                ""
            )
        )

        if not performer_name:
            continue

        try:

            lines = get_fany_lines(
                session,
                performer_name
            )

            blocks = find_event_blocks(
                lines,
                performer_name
            )

            print_debug_blocks(
                performer_name,
                blocks
            )

            print_interesting_lines(
                performer_name,
                lines
            )

        except Exception as error:

            print(
                f"FANY取得エラー："
                f"{performer_name}"
            )

            print(
                repr(error)
            )


    # ======================================
    # LINE通知を止める
    # ======================================

    save_json(
        NEW_EVENTS_FILE,
        []
    )


    print("")
    print(
        "================================"
    )

    print(
        "デバッグ終了"
    )

    print(
        "events.jsonは変更していません"
    )

    print(
        "LINE通知も発生しません"
    )

    print(
        "================================"
    )


# ==========================================
# 実行
# ==========================================

if __name__ == "__main__":
    main()
