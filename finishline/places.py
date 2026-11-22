from fractions import Fraction

from .common import require, scalar


def build_intervals(entries, calls, start):
    """Finish intervals (elapsed microseconds) for eligible athletes with a readable call."""
    by_athlete = {}
    for fact in calls:
        key = fact['athlete']
        if key is not None:
            require(key not in by_athlete, f'multiple calls belong to {key}; adjudicate before publishing')
            by_athlete[key] = fact
    require(all(row['status'] in ('eligible', 'dns', 'dnf', 'dq') for row in entries.values()),
            'unknown entry status')
    qualified = {k for k, row in entries.items() if row['status'] == 'eligible'}
    intervals = {}
    for key in qualified:
        fact = by_athlete.get(key)
        if fact is not None and fact['finish_us'] is not None:
            lo, hi = map(Fraction, fact['finish_us'])
            require(lo >= start, 'finish precedes common start')
            intervals[key] = (lo - start, hi - start)
    return by_athlete, qualified, intervals


def rank_ranges(members, intervals):
    """Best/worst achievable rank (1-based) for each member under closed interval uncertainty."""
    ranges = {}
    for key in members:
        if key in intervals:
            lo, hi = intervals[key]
            before = sum(b < lo for other, (a, b) in intervals.items() if other in members and other != key)
            after = sum(a > hi for other, (a, b) in intervals.items() if other in members and other != key)
            size = len(members)
            ranges[key] = (before + 1, size - after)
        else:
            ranges[key] = (1, len(members))
    return ranges


def publish_places(entries, calls, start, groups=None):
    """Per-group places. Without groups every eligible entry shares one anonymous group."""
    by_athlete, qualified, intervals = build_intervals(entries, calls, start)
    if groups is None:
        groups = {'_default': sorted(qualified)}
    membership = {athlete: group for group, members in groups.items() for athlete in members}
    group_ranges = {group: rank_ranges(set(members), intervals) for group, members in groups.items()}
    rows = []
    for key, entry in sorted(entries.items()):
        call = by_athlete.get(key)
        base = {'athlete': key, 'status': entry['status'], 'call': call['id'] if call else None,
                'group': membership.get(key), 'place': None, 'possible_places': None,
                'elapsed_us': None}
        if key in qualified:
            first, last = group_ranges[membership[key]][key]
            base.update(place=first if first == last else None,
                        possible_places=[first, last],
                        elapsed_us=[scalar(intervals[key][0]), scalar(intervals[key][1])]
                        if key in intervals else None)
        rows.append(base)
    return rows
