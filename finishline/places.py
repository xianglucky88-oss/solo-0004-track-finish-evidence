from fractions import Fraction

from .common import require, scalar
from .constraints import build_finish_system


def qualified_intervals(entries, calls, start):
    """Collect one located finish interval per eligible athlete."""
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
    for key, fact in by_athlete.items():
        if key in qualified and fact['finish_us'] is not None:
            lo, hi = map(Fraction, fact['finish_us'])
            require(lo >= start, 'finish precedes common start')
            intervals[key] = (lo, hi, fact['camera'])
    return by_athlete, qualified, intervals


def publish_places(entries, calls, start, offsets):
    by_athlete, qualified, intervals = qualified_intervals(entries, calls, start)
    system, node = build_finish_system(intervals, offsets, start)

    def can_be_before(a, b):
        # True when some feasible assignment has athlete a finishing strictly
        # before athlete b under the single shared set of camera offsets:
        # strict tau_a - tau_b < 0, edge source=b -> target=a.
        return system.feasible((system.strict_edge(node[a], node[b]),))

    located = set(intervals)
    rows = []
    for key, entry in sorted(entries.items()):
        call = by_athlete.get(key)
        base = {'athlete': key, 'status': entry['status'], 'call': call['id'] if call else None,
                'place': None, 'possible_places': None, 'elapsed_us': None}
        if key in intervals:
            lo, hi, _ = intervals[key]
            # Evaluated over the joint feasible region of one shared offset per
            # camera plus the legacy per-call scale error (never widened per
            # athlete in isolation).  A finish is proven ahead/behind only when
            # the strict ordering holds in every feasible assignment; two
            # athletes whose only joint possibility is a tie prove neither
            # side, matching the legacy strictly-separated interval rule.
            proven_ahead = proven_behind = 0
            for other in located:
                if other == key:
                    continue
                key_first = can_be_before(key, other)
                other_first = can_be_before(other, key)
                if other_first and not key_first:
                    proven_ahead += 1
                elif key_first and not other_first:
                    proven_behind += 1
            first = proven_ahead + 1
            last = len(qualified) - proven_behind
            require(first <= last, f'incoherent place bounds for {key}')
            base.update(place=first if first == last else None, possible_places=[first, last],
                        elapsed_us=[scalar(lo - start), scalar(hi - start)])
        elif key in qualified:
            base.update(possible_places=[1, len(qualified)])
        rows.append(base)
    return rows
