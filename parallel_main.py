"""Parallel production entrypoint. Keeps scraper.py and its public functions unchanged."""

import scraper as core
from parallel_scraper_helper import scrape_all_parallel


def main():
    print('=' * 48, flush=True)
    print('出演情報取得開始（芸人別並列版）', flush=True)
    print('FANY + TIGET + イープラス + LivePocket', flush=True)
    print('既存の通知判定・48時間NEW・販売情報を維持', flush=True)
    print('=' * 48, flush=True)

    config = core.load_json(core.PERFORMERS_FILE, {'performers': []})
    performers = config.get('performers', [])
    old_data = core.load_json(core.EVENTS_FILE, {'events': []})
    old_events = old_data if isinstance(old_data, list) else old_data.get('events', [])

    notified = core.load_json(core.NOTIFIED_FILE, {})
    stable_keys = set(notified.get('stableKeys', []))
    loose_keys = set(notified.get('looseKeys', []))
    source_keys = set(notified.get('sourceKeys', []))

    # Existing events are treated as notified, exactly as in scraper.py.
    for event in old_events:
        stable_keys.add(core.stable_notification_key(event))
        loose_keys.add(core.loose_notification_key(event))
        source_key = core.source_notification_key(event)
        if source_key:
            source_keys.add(source_key)

    # No file is modified until every worker completes without a reported error.
    all_events = scrape_all_parallel(
        performers,
        core.HEADERS,
        {
            'fany': core.scrape_fany,
            'tiget': core.scrape_tiget,
            'eplus': core.scrape_eplus,
            'livepocket': core.scrape_livepocket,
        },
    )

    all_events = core.sanitize_event_performers(all_events)
    all_events = [e for e in all_events if core.is_today_or_future(e.get('date', ''))]
    all_events = core.remove_duplicates(all_events)

    new_events = []
    for event in all_events:
        source_key = core.source_notification_key(event)
        stable_key = core.stable_notification_key(event)
        loose_key = core.loose_notification_key(event)
        if source_key and source_key in source_keys:
            continue
        if stable_key in stable_keys or loose_key in loose_keys:
            continue
        new_events.append(event)

    core.apply_discovery_metadata(all_events, old_events, new_events)
    core.attach_tracked_performers(all_events)
    core.attach_ticket_sale_keys(all_events)
    all_events.sort(key=lambda e: (e.get('date', ''), e.get('startTime', ''), e.get('performerId', '')))

    output = {
        'syncedAt': core.now_iso(),
        'performers': performers,
        'events': all_events,
    }
    history = {
        'stableKeys': sorted(stable_keys),
        'looseKeys': sorted(loose_keys),
        'sourceKeys': sorted(source_keys),
    }

    # Match the original scraper's output files and JSON shapes.
    core.save_json(core.EVENTS_FILE, output)
    core.save_json(core.NEW_EVENTS_FILE, new_events)
    core.save_json(core.NOTIFIED_FILE, history)

    print('\n' + '=' * 48)
    print('並列版取得結果')
    print('現在の公演数:', len(all_events))
    for source in ('fany', 'tiget', 'eplus', 'livepocket'):
        print(source + ':', sum(e.get('source') == source for e in all_events), '件')
    print('販売状況取得:', sum(bool(e.get('ticketStatus')) for e in all_events), '件')
    print('販売枠取得公演:', sum(bool(e.get('ticketOptions')) for e in all_events), '件')
    print('販売枠合計:', sum(len(e.get('ticketOptions', [])) for e in all_events), '件')
    print('公演代表の販売開始日時:', sum(bool(e.get('saleStartAt')) for e in all_events), '件')
    print('券種別販売開始日時:', core.count_ticket_option_sale_starts(all_events), '件')
    print('先行販売期間:', core.count_sale_periods(all_events, 'advance'), '件')
    print('先着販売期間:', core.count_sale_periods(all_events, 'first_come'), '件')
    print('出演者詳細取得:', sum(bool(e.get('performersText')) for e in all_events), '件')
    print('開場時間取得:', sum(bool(e.get('openTime')) for e in all_events), '件')
    print('48時間NEW:', sum(bool(e.get('newUntil')) for e in all_events), '件')
    print('本当の新規公演:', len(new_events), '件')
    for event in new_events:
        print('NEW:', event.get('performerId'), event.get('date'), event.get('title'), event.get('sourceUrl'))
    print('=' * 48, flush=True)


if __name__ == '__main__':
    main()
