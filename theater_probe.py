import json
import re
from datetime import datetime, timezone, timedelta

from playwright.sync_api import sync_playwright


OUTPUT_FILE = "theater_probe.json"

JST = timezone(
    timedelta(hours=9)
)


PERFORMERS = [
    {
        "id": "maison",
        "name": "めぞん",
    },
    {
        "id": "pyuto",
        "name": "ピュート",
    },
    {
        "id": "nansui",
        "name": "軟水",
    },
]


THEATERS = [
    {
        "id": "roppongi",
        "name": "六本木",
        "url": "https://roppongi.yoshimoto.co.jp/schedule/",
    },
    {
        "id": "jimbocho",
        "name": "神保町",
        "url": "https://jimbocho-manzaigekijyo.yoshimoto.co.jp/schedule/",
    },
    {
        "id": "shibuya",
        "name": "渋谷",
        "url": "https://shibuya-manzaigekijyo.yoshimoto.co.jp/schedule/",
    },
    {
        "id": "morinomiya",
        "name": "森ノ宮",
        "url": "https://morinomiya-manzaigekijyo.yoshimoto.co.jp/schedule/",
    },
    {
        "id": "manzaigekijyo",
        "name": "よしもと漫才劇場",
        "url": "https://manzaigekijyo.yoshimoto.co.jp/schedule/",
    },
    {
        "id": "makuhari",
        "name": "幕張",
        "url": "https://makuhari.yoshimoto.co.jp/schedule/",
    },
    {
        "id": "dotonbori",
        "name": "道頓堀",
        "url": "https://dotonbori.yoshimoto.co.jp/schedule/",
    },
    {
        "id": "omiya",
        "name": "大宮",
        "url": "https://omiya.yoshimoto.co.jp/schedule/",
    },
    {
        "id": "fukuoka",
        "name": "福岡",
        "url": "https://fukuokagekijyo.yoshimoto.co.jp/schedule/",
    },
    {
        "id": "ngk",
        "name": "なんばグランド花月",
        "url": "https://ngk.yoshimoto.co.jp/schedule/",
    },
]


def clean(text):
    return re.sub(
        r"\s+",
        " ",
        str(text or ""),
    ).strip()


def now_iso():
    return datetime.now(
        timezone.utc
    ).isoformat()


def unique_strings(values):
    result = []
    seen = set()

    for value in values:
        value = clean(
            value
        )

        if not value:
            continue

        if value in seen:
            continue

        seen.add(
            value
        )

        result.append(
            value
        )

    return result


def make_lines(text):
    result = []

    for raw in str(
        text or ""
    ).splitlines():

        line = clean(
            raw
        )

        if line:
            result.append(
                line
            )

    return result


def find_month_labels(page):
    labels = []

    candidates = page.locator(
        "a, button, [role='button'], li, div, span"
    )

    try:
        count = candidates.count()

    except Exception:
        return []

    for index in range(
        min(
            count,
            3000,
        )
    ):
        try:
            text = clean(
                candidates.nth(
                    index
                ).inner_text(
                    timeout=300
                )
            )

        except Exception:
            continue

        if re.fullmatch(
            r"(?:1[0-2]|[1-9])月",
            text,
        ):
            labels.append(
                text
            )

    return unique_strings(
        labels
    )


def get_matching_contexts(
    text,
):
    lines = make_lines(
        text
    )

    matches = []

    for performer in PERFORMERS:
        performer_name = performer[
            "name"
        ]

        for index, line in enumerate(
            lines
        ):
            if (
                performer_name
                not in line
            ):
                continue

            start = max(
                0,
                index - 5,
            )

            end = min(
                len(lines),
                index + 6,
            )

            context_lines = lines[
                start:end
            ]

            matches.append({
                "performerId":
                    performer[
                        "id"
                    ],

                "performerName":
                    performer_name,

                "matchedLine":
                    line,

                "context":
                    context_lines,
            })

    return matches


def click_month(
    page,
    label,
):
    patterns = [
        f"^{re.escape(label)}$",
    ]

    for selector in [
        "a",
        "button",
        "[role='button']",
        "li",
        "div",
        "span",
    ]:
        locator = page.locator(
            selector
        )

        try:
            count = locator.count()

        except Exception:
            continue

        for index in range(
            min(
                count,
                1500,
            )
        ):
            item = locator.nth(
                index
            )

            try:
                text = clean(
                    item.inner_text(
                        timeout=200
                    )
                )

            except Exception:
                continue

            if text != label:
                continue

            try:
                item.scroll_into_view_if_needed(
                    timeout=1000
                )

                item.click(
                    timeout=2500,
                    force=True,
                )

                page.wait_for_timeout(
                    1500
                )

                return True

            except Exception:
                continue

    return False


def scrape_theater(
    browser,
    theater,
):
    print("")
    print(
        "================================"
    )

    print(
        "劇場:",
        theater[
            "name"
        ],
    )

    print(
        theater[
            "url"
        ]
    )

    context = browser.new_context(
        locale="ja-JP",
        timezone_id="Asia/Tokyo",
        user_agent=(
            "Mozilla/5.0 "
            "(iPhone; CPU iPhone OS 18_0 like Mac OS X) "
            "AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) "
            "Version/18.0 Mobile/15E148 Safari/604.1"
        ),
        viewport={
            "width": 390,
            "height": 844,
        },
    )

    page = context.new_page()

    result = {
        "theaterId":
            theater[
                "id"
            ],

        "theaterName":
            theater[
                "name"
            ],

        "url":
            theater[
                "url"
            ],

        "status":
            "",

        "months":
            [],

        "error":
            "",
    }

    try:
        page.goto(
            theater[
                "url"
            ],
            wait_until="domcontentloaded",
            timeout=45000,
        )

        page.wait_for_timeout(
            4000
        )

        result[
            "status"
        ] = "loaded"

        month_labels = (
            find_month_labels(
                page
            )
        )

        print(
            "月候補:",
            month_labels,
        )

        # 月タブが取れない劇場でも
        # 現在表示中ページだけは確認する
        if not month_labels:
            body_text = page.locator(
                "body"
            ).inner_text(
                timeout=10000
            )

            matches = (
                get_matching_contexts(
                    body_text
                )
            )

            result[
                "months"
            ].append({
                "label":
                    "current",

                "clicked":
                    False,

                "matches":
                    matches,
            })

            print(
                "対象芸人一致:",
                len(
                    matches
                ),
                "件",
            )

            return result

        for month_label in month_labels:
            print(
                "確認:",
                month_label,
            )

            clicked = click_month(
                page,
                month_label,
            )

            if not clicked:
                print(
                    "  月タブクリック失敗"
                )

            try:
                page.wait_for_timeout(
                    1000
                )

                body_text = page.locator(
                    "body"
                ).inner_text(
                    timeout=10000
                )

            except Exception:
                body_text = ""

            matches = (
                get_matching_contexts(
                    body_text
                )
            )

            print(
                "  対象芸人一致:",
                len(
                    matches
                ),
                "件",
            )

            result[
                "months"
            ].append({
                "label":
                    month_label,

                "clicked":
                    clicked,

                "matches":
                    matches,
            })

    except Exception as error:
        result[
            "status"
        ] = "error"

        result[
            "error"
        ] = clean(
            error
        )

        print(
            "劇場取得失敗:",
            error,
        )

    finally:
        context.close()

    return result


def main():
    print(
        "================================"
    )

    print(
        "劇場公式スケジュール調査開始"
    )

    print(
        "対象: 10劇場"
    )

    print(
        "出演者: めぞん / ピュート / 軟水"
    )

    print(
        "================================"
    )

    results = []

    with sync_playwright() as playwright:
        browser = (
            playwright.chromium.launch(
                headless=True
            )
        )

        try:
            for theater in THEATERS:
                result = scrape_theater(
                    browser,
                    theater,
                )

                results.append(
                    result
                )

        finally:
            browser.close()

    total_matches = 0

    for theater in results:
        for month in theater.get(
            "months",
            [],
        ):
            total_matches += len(
                month.get(
                    "matches",
                    [],
                )
            )

    output = {
        "checkedAt":
            now_iso(),

        "theaters":
            results,

        "totalMatches":
            total_matches,
    }

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            output,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print("")
    print(
        "================================"
    )

    print(
        "調査完了"
    )

    print(
        "対象芸人一致合計:",
        total_matches,
        "件",
    )

    print(
        "出力:",
        OUTPUT_FILE,
    )

    print(
        "================================"
    )


if __name__ == "__main__":
    main()
