from fractions import Fraction

from .common import require, scalar


def publish_places(entries, calls, start):
    by_athlete = {}
    for fact in calls:
        key = fact['athlete']
        if key is not None:
            require(key not in by_athlete, f'multiple calls belong to {key}; adjudicate before publishing')
            by_athlete[key] = fact
    qualified = {k for k, row in entries.items() if row['status'] == 'eligible'}
    require(all(row['status'] in ('eligible', 'dns', 'dnf', 'dq') for row in entries.values()), 'unknown entry status')
    intervals = {k: tuple(map(Fraction, fact['finish_us'])) for k, fact in by_athlete.items()
                 if k in qualified and fact['finish_us'] is not None}
    require(all(v[0] >= start for v in intervals.values()), 'finish precedes common start')
    rows = []
    for key, entry in sorted(entries.items()):
        call = by_athlete.get(key)
        base = {'athlete': key, 'status': entry['status'], 'call': call['id'] if call else None,
                'place': None, 'possible_places': None, 'elapsed_us': None}
        if key in intervals:
            lo, hi = intervals[key]
            before = sum(b < lo for k, (a, b) in intervals.items() if k != key)
            after = sum(a > hi for k, (a, b) in intervals.items() if k != key)
            first, last = before + 1, len(qualified) - after
            base.update(place=first if first == last else None, possible_places=[first, last],
                        elapsed_us=[scalar(lo - start), scalar(hi - start)])
        elif key in qualified:
            base.update(possible_places=[1, len(qualified)])
        rows.append(base)
    return rows
