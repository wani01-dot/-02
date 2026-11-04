"""TicketDive artist/search discovery. Only confirmed event pages are stored.

Failure-safe: never replace the last successful cache with an empty/partial crawl.
"""
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = 'https://ticketdive.com'
SOURCES = [
    'https://ticketdive.com/artist/JMVCHy5NpmIxdL7Erlbv',
    'https://ticketdive.com/artist/nhAsXH2rnZI0MMDHvuza',
    'https://ticketdive.com/artist/xiqDN7AtBDkbTAIKrVFS',
    'https://ticketdive.com/search?q=%E3%83%94%E3%83%A5%E3%83%BC%E3%83%88',
]
OUTPUT = Path('ticketdive_events.json')
IDS = {'めぞん': 'maison', 'ピュート': 'pyuto', '軟水': 'nansui'}
MEMBERS = {'吉野おいなり君': 'maison', '原一刻': 'maison', '竹内智也': 'pyuto', 'ポイント': 'pyuto', 'つるまる': 'nansui', 'がまの助': 'nansui'}
SESSION = requests.Session()
SESSION.headers.update({'User-Agent': 'Mozilla/5.0 (compatible; WaraiCalendar/1.0; public event discovery)'})


def fetch(url):
    r = SESSION.get(url, timeout=18)
    r.raise_for_status()
    return BeautifulSoup(r.text, 'html.parser')


def clean(text):
    return re.sub(r'\s+', ' ', text or '').strip()


def event_links(soup):
    found = set()
    for a in soup.select('a[href]'):
        url = urljoin(BASE, a['href']).split('#')[0].split('?')[0]
        parsed = urlparse(url)
        if parsed.hostname == 'ticketdive.com' and re.fullmatch(r'/event/[^/]+', parsed.path):
            found.add(url)
    return found


def field(text, label, end_labels):
    pattern = re.escape(label) + r'\s*(.*?)\s*(?=' + '|'.join(map(re.escape, end_labels)) + r'|$)'
    m = re.search(pattern, text, re.S)
    return clean(m.group(1)) if m else ''


def parse_event(url, soup):
    # Text separated by newlines to avoid mixing performers with ticket prices.
    lines = [clean(s) for s in soup.stripped_strings]
    title = ''
    for node in soup.select('h1'):
        title = clean(node.get_text(' ', strip=True))
        if title:
            break
    if not title:
        title = clean(soup.title.get_text(' ', strip=True).split('|')[0]) if soup.title else ''
    text = '\n'.join(lines)
    flat = clean(soup.get_text(' ', strip=True))
    m = re.search(r'公演日時\s*(20\d{2})/(\d{1,2})/(\d{1,2})', flat)
    if not m or not title:
        return []
    when = date(*map(int, m.groups()))
    if when < date.today() - timedelta(days=3) or when > date.today() + timedelta(days=400):
        return []
    # Only accept a single-date event; multiple-day listings need separate sessions.
    header = flat.split('TICKET INFO', 1)[0]
    if re.search(r'公演日時[^\n]*[〜～]', header):
        return []
    open_match = re.search(r'開場時刻\s*(\d{1,2}:\d{2})', header)
    start_match = re.search(r'開演時刻\s*(\d{1,2}:\d{2})', header)
    venue_match = re.search(r'会場\s*(.+?)(?=\s*出演|$)', header)
    # Extract the dedicated '出演' section before ticket info.
    cast_match = re.search(r'出演\s*(.+?)$', header)
    cast = clean(cast_match.group(1)) if cast_match else ''
    if not cast:
        return []
    names = [clean(x) for x in re.split(r'\s*/\s*|\s*／\s*', cast) if clean(x)]
    ids = set()
    for name in names:
        for group, pid in IDS.items():
            if name == group or name.startswith(group + '（'):
                ids.add(pid)
        for member, pid in MEMBERS.items():
            if name == member or name.startswith(member + '（'):
                ids.add(pid)
    if not ids:
        return []
    if not start_match or not venue_match:
        return []
    common = {
        'date': when.isoformat(), 'openTime': open_match.group(1) if open_match else '',
        'startTime': start_match.group(1), 'title': title, 'venue': clean(venue_match.group(1)),
        'performersText': names, 'sourceUrl': url, 'discoverySource': 'ticketdive-official',
    }
    return [{**common, 'performerId': pid} for pid in sorted(ids)]


def main():
    old = {'events': []}
    if OUTPUT.exists():
        try:
            old = json.loads(OUTPUT.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            pass
    old_events = old.get('events', []) if isinstance(old, dict) else []
    links = set()
    succeeded = 0
    for url in SOURCES:
        try:
            soup = fetch(url)
            new = event_links(soup)
            print(f'SOURCE {url}: {len(new)} event links')
            links.update(new)
            succeeded += 1
        except requests.RequestException as exc:
            print(f'WARN source fetch failed: {url}: {exc}', file=sys.stderr)
    # Retry older known event pages, so intermittent source failures do not drop events.
    links.update(e.get('sourceUrl', '') for e in old_events if e.get('sourceUrl', '').startswith(BASE + '/event/'))
    new_events = []
    successful_urls = set()
    for url in sorted(links):
        try:
            entries = parse_event(url, fetch(url))
            new_events.extend(entries)
            successful_urls.add(url)
        except (requests.RequestException, ValueError) as exc:
            print(f'WARN event fetch failed: {url}: {exc}', file=sys.stderr)
    # Retain cached records on failed requests; remove expired events only.
    keys = {(e['sourceUrl'], e['performerId']) for e in new_events}
    for e in old_events:
        if (e.get('sourceUrl'), e.get('performerId')) not in keys and e.get('sourceUrl') not in successful_urls:
            if e.get('date', '') >= (date.today() - timedelta(days=3)).isoformat():
                new_events.append(e)
    # No successful source read means keep cache and report, not erase.
    if succeeded == 0 and not successful_urls:
        print('WARN all TicketDive sources unavailable; cache preserved')
        return
    new_events.sort(key=lambda e: (e['date'], e['startTime'], e['title'], e['performerId']))
    OUTPUT.write_text(json.dumps({'events': new_events}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'TicketDive events: {len(new_events)}; sources succeeded: {succeeded}/{len(SOURCES)}')


if __name__ == '__main__':
    main()
