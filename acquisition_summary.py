"""Render a compact Actions job summary from the read-only acquisition log."""
import argparse
import html
import json
from collections import Counter
from pathlib import Path


ARTISTS = {"maison": "めぞん", "pyuto": "ピュート", "nansui": "軟水"}
SOURCES = {
    **{f"fany/{pid}": f"FANY・{name}" for pid, name in ARTISTS.items()},
    "theater/roppongi": "六本木",
    "theater/jimbocho": "神保町",
    "theater/shibuya": "渋谷",
    "theater/morinomiya": "森ノ宮",
    "theater/manzaigekijyo": "よしもと漫才劇場",
    "theater/makuhari": "幕張",
    "theater/dotonbori": "道頓堀",
    "theater/omiya": "大宮",
    "theater/fukuoka": "福岡",
    "theater/ngk": "なんばグランド花月",
}
REVIEWS = {
    "official_cast_matches": "公式出演欄に一致",
    "cast_differs_review_required": "出演欄に差異・要確認",
    "cast_partial_unconfirmed": "出演欄に「他」・維持",
    "cast_unpublished": "出演欄を確認できず",
    "not_found": "一致する公演なし・維持",
    "outside_verified_months": "確認対象月の外・維持",
    "ambiguous": "候補が複数・維持",
    "source_unavailable": "公式取得失敗・維持",
}


def records(lines):
    for line in lines:
        if not line.startswith("{"):
            continue
        try:
            result = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(result, dict):
            yield result


def cell(value):
    escaped = html.escape(" ".join(str(value).split()))
    return escaped.replace("|", "&#124;").replace("`", "&#96;")


def render_summary(lines):
    results = {}
    reviews = Counter()
    roppongi = []
    decisions = {}
    for row in records(lines):
        if row.get("type") == "probe_source_result":
            results[row["source"]] = row
        elif row.get("type") == "probe_review":
            reviews[row["status"]] += 1
        elif row.get("type") == "probe_summary":
            decisions = row.get("decisions", {})
        elif row.get("type") == "probe_roppongi_check":
            roppongi.append(row)

    sources = dict(SOURCES)
    labels = {"tiget": "TIGET", "eplus": "イープラス", "livepocket": "LivePocket"}
    for source in labels:
        for pid, name in ARTISTS.items():
            key = f"{source}/{pid}"
            if key in results:
                sources[key] = f"{labels[source]}・{name}"

    succeeded = sum(results.get(source, {}).get("status") == "success" for source in sources)
    failed = sum(results.get(source, {}).get("status") == "failed" for source in sources)
    report = [
        "## 公演取得テスト",
        "",
        f"成功 **{succeeded}** ／ 失敗 **{failed}** ／ 未実行・未確認 **{len(sources) - succeeded - failed}**",
        "",
        "| 取得元 | 成否 | 取得件数 | 秒 | エラー理由 |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    counts = []
    for source, label in sources.items():
        row = results.get(source, {})
        status = row.get("status")
        seconds = row.get("acquisitionSeconds")
        count = row.get("trackedShowCount")
        official = row.get("officialShowCount")
        count_text = f"{count} / {official}" if official is not None else count
        error = row.get("error")
        if error:
            error = str(error).splitlines()[0].partition(" for url: ")[0][:160]
        status_text = {"success": "成功", "failed": "失敗"}.get(status, "未確認")
        report.append(
            f"| {cell(label)} | {status_text} | "
            f"{count_text if count_text is not None else '—'} | "
            f"{f'{seconds:.2f}' if isinstance(seconds, (int, float)) else '—'} | "
            f"{cell(error) if error else '—'} |"
        )
        if status == "success":
            counts.append((label, row.get("counts", {})))
    report.extend(["", "劇場の件数は「対象3組の公演数 / 公式掲載総数」。チケットサイトは対象の公演数。"])
    if counts:
        report.extend(["", "### 出演者別件数", "",
                       "| 取得元 | めぞん | ピュート | 軟水 |", "| --- | ---: | ---: | ---: |"])
        for label, by_artist in counts:
            report.append(f"| {cell(label)} | " + " | ".join(str(by_artist.get(pid, 0)) for pid in ARTISTS) + " |")
    if roppongi:
        report.extend(["", "### 六本木 2027/01/21", "",
                       "| 開演 | 照合結果 | 公式公演ID |", "| --- | --- | --- |"])
        for row in roppongi:
            report.append(f"| {cell(row['startTime'])} | {cell(row['status'])} | {cell(row.get('officialEventId') or '—')} |")
    if decisions:
        report.extend(["", "### 新着判定", "", "| 判定理由 | レコード数 |", "| --- | ---: |"])
        labels = {"migration_exact_history_key": "旧履歴キーあり（LINE着信未証明）",
                  "migration_listing_delivery_unconfirmed": "既存掲載あり・送信未確認",
                  "new_show": "新着候補"}
        for reason, count in sorted(decisions.items()):
            report.append(f"| {cell(labels.get(reason, reason))} | {count} |")
    if reviews:
        report.extend(["", "### 残り12公演の照合", "", "| 照合結果 | 出演者レコード数 |", "| --- | ---: |"])
        for status, count in sorted(reviews.items()):
            report.append(f"| {cell(REVIEWS.get(status, status))} | {count} |")
    report.extend(["", "公演ID・出演者欄・エラー詳細は実行ログと成果物 **acquisition-probe** を参照。", ""])
    return "\n".join(report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    args = parser.parse_args()
    if args.log.exists():
        with args.log.open(encoding="utf-8") as log:
            print(render_summary(log))
    else:
        print(render_summary(()))


if __name__ == "__main__":
    main()
