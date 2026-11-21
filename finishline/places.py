from fractions import Fraction

from .common import require, scalar


def measured_intervals(calls, qualified, start):
    """Closed absolute-time intervals for eligible athletes whose call is fully covered."""
    by_athlete = {}
    for fact in calls:
        key = fact['athlete']
        if key is not None:
            require(key not in by_athlete, f'multiple calls belong to {key}; adjudicate before publishing')
            by_athlete[key] = fact
    intervals = {key: tuple(map(Fraction, fact['finish_us'])) for key, fact in by_athlete.items()
                 if key in qualified and fact['finish_us'] is not None}
    require(all(lo >= start for lo, hi in intervals.values()), 'finish precedes common start')
    return intervals


def place_ranges(intervals, qualified):
    """Possible-place span per eligible athlete under one set of closed time intervals.

    Two closed intervals prove an ordering only when they are strictly separated.
    Eligible athletes without any interval still participate across the full span.
    """
    ranges = {}
    total = len(qualified)
    for key in qualified:
        if key in intervals:
            lo, hi = intervals[key]
            before = sum(b < lo for other, (a, b) in intervals.items() if other != key)
            after = sum(a > hi for other, (a, b) in intervals.items() if other != key)
            ranges[key] = (before + 1, total - after)
        else:
            ranges[key] = (1, total)
    return ranges


def publish_places(entries, calls, start):
    by_athlete = {}
    for fact in calls:
        key = fact['athlete']
        if key is not None:
            require(key not in by_athlete, f'multiple calls belong to {key}; adjudicate before publishing')
            by_athlete[key] = fact
    qualified = {k for k, row in entries.items() if row['status'] == 'eligible'}
    require(all(row['status'] in ('eligible', 'dns', 'dnf', 'dq') for row in entries.values()), 'unknown entry status')
    intervals = measured_intervals(calls, qualified, start)
    spans = place_ranges(intervals, qualified)
    rows = []
    for key, entry in sorted(entries.items()):
        call = by_athlete.get(key)
        base = {'athlete': key, 'status': entry['status'], 'call': call['id'] if call else None,
                'place': None, 'possible_places': None, 'elapsed_us': None}
        if key in intervals:
            lo, hi = intervals[key]
            first, last = spans[key]
            base.update(place=first if first == last else None, possible_places=[first, last],
                        elapsed_us=[scalar(lo - start), scalar(hi - start)])
        elif key in qualified:
            base.update(possible_places=[1, len(qualified)])
        rows.append(base)
    return rows
