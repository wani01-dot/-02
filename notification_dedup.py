"""Cross-source duplicate checks for FANY/ticket sites and theater schedules.

Only match within the same performer, date, and start time; title similarity
is required to avoid suppressing different shows at the same venue.
"""
import re
import unicodedata
from difflib import SequenceMatcher


def normalized_title(value):
    value = unicodedata.normalize('NFKC', str(value or '')).casefold()
    value = re.sub(r'[\s\W_]+', '', value, flags=re.UNICODE)
    return value


def performer_ids(event):
    ids = [event.get('performerId')]
    for key in ('trackedPerformers', 'performerIds'):
        extra = event.get(key, [])
        if isinstance(extra, list):
            ids.extend(extra)
    return {str(x) for x in ids if x}


def same_show(a, b):
    if not (performer_ids(a) & performer_ids(b)):
        return False
    if not a.get('date') or a.get('date') != b.get('date'):
        return False
    start_a = str(a.get('startTime') or '').strip()
    start_b = str(b.get('startTime') or '').strip()
    if not start_a or not start_b or start_a != start_b:
        return False
    x, y = normalized_title(a.get('title')), normalized_title(b.get('title'))
    if len(x) < 5 or len(y) < 5:
        return False
    if x == y:
        return True
    if min(len(x), len(y)) >= 9 and (x in y or y in x):
        return True
    return SequenceMatcher(None, x, y).ratio() >= 0.84


def matches_any(event, others):
    return any(same_show(event, other) for other in others)
