"""Render the production job audit for the Actions Summary page."""
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from acquisition_summary import ARTISTS, SOURCES, cell, records

JST = timezone(timedelta(hours=9))
SOURCE_LABELS = {
    **SOURCES,
    **{f"{source}/{pid}": f"{label}・{name}"
       for source, label in {"tiget": "TIGET", "eplus": "イープラス", "livepocket": "LivePocket"}.items()
       for pid, name in ARTISTS.items()},
}


def when(value):
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(value).astimezone(JST).strftime("%m/%d %H:%M:%S")
    except (ValueError, TypeError):
        return "—"


def seconds(value):
    return f"{value:.2f}秒" if isinstance(value, (int, float)) else "—"


def metric(value):
    return str(value) if value is not None else "—"


def render_summary(log):
    starts, fetched, decisions, deliveries = {}, {}, {}, {}
    timing, usage = {}, {}
    for row in records(log):
        kind = row.get("type")
        source = row.get("source")
        if kind == "run_timing":
            timing = row
        elif kind == "source_started" and source:
            starts[source] = row
        elif kind == "source_result" and source:
            fetched[source] = row
        elif kind == "source_decision" and source:
            decisions[source] = row
        elif kind in ("line_result", "line_quota_deferred"):
            deliveries[row["retryKey"]] = row
        elif kind == "line_usage":
            usage = row

    schedule_interval = timing.get("scheduleIntervalSeconds")
    interval = (f"定期実行の作成間隔 **{seconds(schedule_interval)}**" if schedule_interval is not None
                else f"同期処理の開始間隔 **{seconds(timing.get('pipelineIntervalSeconds'))}**")
    report = [
        "## 本番同期の状況",
        "",
        f"実行作成 **{when(timing.get('createdAt'))}** ／ 実行開始まで **{seconds(timing.get('queueSeconds'))}**"
        f" ／ {interval}（JST）",
        "",
        "### LINE月間利用量",
        "",
    ]
    if usage and not usage.get("error"):
        report.extend([
            "| 対象月 | 消費通数 | 無料枠上限 | 実効上限 | 残り | 自動送信残枠 |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
            "| " + " | ".join(cell(metric(usage.get(key))) for key in
                              ("month", "consumed", "freeCap", "effectiveCap", "freeRemaining", "automaticRemaining")) + " |",
            "",
            "消費通数はLINE APIの取得時点の値。自動送信残枠は手動用の留保と送信予約を反映。",
        ])
    else:
        report.append(f"利用量未確認（{cell(usage.get('error') or '取得記録なし')}）。")
    report.extend(["", "### 取得元別", "",
                   "| 取得元 | 状態 | 件数 | 取得 | 新着 |",
                   "| --- | --- | ---: | ---: | ---: |"])
    for source, label in SOURCE_LABELS.items():
        fetch = fetched.get(source, {})
        status = ("失敗" if fetch.get("failures") else "成功") if fetch else (
            "完了記録なし" if source in starts else "未確認")
        if fetch.get("error"):
            error = fetch["error"].splitlines()[0].partition(" for url: ")[0][:100]
            status += f"・{error}"
        report.append(f"| {cell(label)} | {cell(status)} | {metric(fetch.get('events'))} | "
                      f"{seconds(fetch.get('seconds'))} | {metric(decisions.get(source, {}).get('newShows'))} |")
    report.extend(["", "<details><summary>取得開始・完了・新着判定の時刻（JST）</summary>", "",
                   "| 取得元 | 開始 | 完了 | 判定 |", "| --- | --- | --- | --- |"])
    for source, label in SOURCE_LABELS.items():
        if source in starts or source in fetched or source in decisions:
            started = starts.get(source, fetched.get(source, {})).get("startedAt")
            report.append(f"| {cell(label)} | {when(started)} | {when(fetched.get(source, {}).get('completedAt'))}"
                          f" | {when(decisions.get(source, {}).get('decidedAt'))} |")
    report.extend(["", "</details>", "", "### LINE API", ""])
    if deliveries:
        report.extend(["| 取得元 | 結果 | 受理（JST） | 取得完了→受理 |",
                       "| --- | --- | --- | ---: |"])
        for row in deliveries.values():
            if row["type"] == "line_quota_deferred":
                status = "保留"
            elif row.get("status") == "accepted":
                status = "受理済み・受理時刻不明" if row.get("httpStatus") == 409 else "受理"
            else:
                status = f"失敗 ({metric(row.get('httpStatus'))})"
            label = SOURCE_LABELS.get(row.get("source"), "再試行・手動")
            report.append(f"| {cell(label)} | {cell(status)} | {when(row.get('sentAt'))} | "
                          f"{seconds(row.get('completionToAcceptanceSeconds'))} |")
    else:
        report.append("この実行に送信結果の記録はありません。")
    report.extend(["", "受理はLINE APIの応答時刻で、端末への着信時刻は確認できません。", ""])
    return "\n".join(report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    path = parser.parse_args().log
    if path.is_file():
        with path.open(encoding="utf-8") as log:
            print(render_summary(log))
    else:
        print(render_summary(()))


if __name__ == "__main__":
    main()
