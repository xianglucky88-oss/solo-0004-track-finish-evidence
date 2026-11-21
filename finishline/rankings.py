"""Arrival and net-time rankings for heats split into start-firing groups.

A firing record (`starts`) covers only the athletes of its own group. Every
athlete covered by the same firing shares that firing's single unknown offset:

* within one firing the offset cancels, so two athletes are ordered by their
  finish bounds alone, even when their published elapsed bounds overlap;
* between two firings the offsets are independent, so an order is only provable
  when the two net-time bounds are strictly separated. Two athletes can each
  publish a readable range and still be unordered.

Firings are matched by id, never by an equal `error_us`: two groups may share the
same error value and still be unrelated. Directly proven strict orders are
closed transitively before inclusive place ranges are reported, because an order
proven against every admissible offset stays proven through a chain.

An entry without a firing still has finish evidence, so it takes part in every
arrival order its finish bounds prove. Its elapsed time is undefined, so it can
never receive a definite net place: it appears in the net table as an unranked
athlete with an open possible range, and it widens the far end of the other net
ranges just like any qualified athlete whose evidence is unreadable.
"""
from fractions import Fraction
from itertools import combinations

from .common import number, require, scalar, unique

_MISSING = object()


def _field(row, names, label, default=_MISSING):
    for name in names:
        if name in row:
            return row[name]
    if default is not _MISSING:
        return default
    raise ValueError(f'missing {label}: {names[0]}')


def _firing_rows(rows):
    """Accept either a list of firing records or a mapping of id -> record."""
    if isinstance(rows, dict):
        return [dict(record, id=key) for key, record in rows.items()]
    return rows


def read_starts(rows):
    """Normalize firing records to id -> firing time, error and covered athletes.

    A firing may name its group (`athletes`, `entries`, ...) or leave it implicit
    when the entries reference the firing through their own `start` field.
    """
    rows = _firing_rows(rows)
    require(isinstance(rows, list), 'starts must be a list or an id mapping')
    starts = {}
    for key, row in sorted(unique(rows).items()):
        members = _field(row, ('athletes', 'entries', 'covered', 'members'), 'firing athletes', [])
        require(isinstance(members, list) and all(isinstance(a, str) for a in members),
                f'invalid firing athletes: {key}')
        starts[key] = {'time': number(_field(row, ('time_us', 'start_us', 'time'), 'firing time'),
                                      'firing time'),
                       'error': number(row.get('error_us', 0), 'firing error'),
                       'athletes': members}
    return starts


def read_firings(entries, starts):
    """Map every entry to the firing that covers it, or None when none does."""
    firings = {}

    def cover(athlete, ref, origin):
        require(athlete in entries, f'unknown athlete in {origin}: {athlete!r}')
        require(isinstance(ref, str) and ref in starts, f'unknown start firing for {athlete}: {ref!r}')
        require(firings.get(athlete, ref) == ref, f'conflicting start firings for {athlete}')
        firings[athlete] = ref

    for ref, row in sorted(starts.items()):
        for athlete in row['athletes']:
            cover(athlete, ref, 'firing membership')
    for key, entry in sorted(entries.items()):
        ref = entry.get('start', entry.get('start_id', entry.get('start_group')))
        if ref is not None:
            cover(key, ref, 'entry')
    return {key: firings.get(key) for key in entries}


def _closure(nodes, beats, universe):
    """Close strict order edges transitively and return inclusive place bounds.

    `nodes` have their own evidence; `universe` counts every athlete that may
    take a place. Athletes outside `nodes` could be anywhere, so they widen the
    far end of a range without ever proving themselves ahead of anybody.
    """
    reach = {node: set(beats.get(node, ())) for node in nodes}
    changed = True
    while changed:
        changed = False
        for node in nodes:
            for pivot in tuple(reach[node]):
                extra = reach[pivot] - reach[node]
                if extra:
                    reach[node] |= extra
                    changed = True
    bounds = {}
    for node in nodes:
        ahead = sum(node in reach[other] for other in nodes)
        behind = sum(other in reach[node] for other in nodes)
        bounds[node] = (1 + ahead, universe - behind)
    return bounds


def _earlier(a, b, left, right):
    """Return the athlete proven strictly earlier, or None when neither is."""
    if left[a][1] < right[b][0]:
        return a
    if right[b][1] < left[a][0]:
        return b
    return None


def arrival_relations(nodes, finish):
    """Strict arrival order from separated finish bounds; the firing is irrelevant."""
    beats = {node: set() for node in nodes}
    for a, b in combinations(nodes, 2):
        early = _earlier(a, b, finish, finish)
        if early is not None:
            beats[early].add(b if early == a else a)
    return beats


def net_relations(nodes, finish, net, firings):
    """Strict net order, keeping each firing's unknown offset correlated."""
    beats = {node: set() for node in nodes}
    for a, b in combinations(nodes, 2):
        if firings[a] is not None and firings[a] == firings[b]:
            # One shared offset: it cancels, so the finish bounds decide.
            left, right = finish, finish
        else:
            # Independent firings: only separated net bounds are provable.
            left, right = net, net
        early = _earlier(a, b, left, right)
        if early is not None:
            beats[early].add(b if early == a else a)
    return beats


def _calls_by_athlete(calls):
    by_athlete = {}
    for fact in calls:
        key = fact['athlete']
        if key is not None:
            require(key not in by_athlete, f'multiple calls belong to {key}; adjudicate before publishing')
            by_athlete[key] = fact
    return by_athlete


def _row(key, entry, call, finish):
    return {'athlete': key, 'status': entry['status'], 'call': call['id'] if call else None,
            'finish_us': [scalar(v) for v in finish] if finish is not None else None}


def _place(fields, bounds):
    first, last = bounds
    fields.update(place=first if first == last else None, possible_places=[first, last])


def publish_rankings(entries, calls, starts, firings):
    """Publish arrival and net rankings separately for one segmented-start heat."""
    require(all(row['status'] in ('eligible', 'dns', 'dnf', 'dq') for row in entries.values()),
            'unknown entry status')
    by_athlete = _calls_by_athlete(calls)
    qualified = {key for key, row in entries.items() if row['status'] == 'eligible'}

    finish = {key: tuple(Fraction(v) for v in by_athlete[key]['finish_us'])
              for key in by_athlete
              if key in qualified and by_athlete[key]['finish_us'] is not None}

    net = {}
    for key, (lo, hi) in finish.items():
        ref = firings[key]
        if ref is None:
            continue
        time, error = starts[ref]['time'], starts[ref]['error']
        require(hi >= time - error, 'finish precedes its start firing')
        # The true firing lies in [time - error, time + error], so the true
        # elapsed lies in this interval. Elapsed time is also never negative,
        # so clamping the lower bound only tightens a still-valid bound.
        net[key] = (max(Fraction(0), lo - time - error), hi - time + error)

    arrival_nodes, net_nodes = sorted(finish), sorted(net)
    arrival_bounds = _closure(arrival_nodes, arrival_relations(arrival_nodes, finish), len(qualified))
    net_bounds = _closure(net_nodes, net_relations(net_nodes, finish, net, firings), len(qualified))

    arrival_rows, net_rows = [], []
    for key, entry in sorted(entries.items()):
        call = by_athlete.get(key)
        open_range = [1, len(qualified)] if key in qualified else None

        arrival = _row(key, entry, call, finish.get(key))
        if key in arrival_bounds:
            _place(arrival, arrival_bounds[key])
        else:
            arrival.update(place=None, possible_places=open_range)
        arrival_rows.append(arrival)

        row = _row(key, entry, call, finish.get(key))
        row['start'] = firings[key]
        if key in net_bounds:
            row['elapsed_us'] = [scalar(v) for v in net[key]]
            _place(row, net_bounds[key])
        else:
            # Without both a firing and a readable finish the elapsed time is
            # undefined: no elapsed bounds and no definite net place. As a
            # qualified athlete it still widens the others' net ranges.
            row.update(elapsed_us=None, place=None, possible_places=open_range)
        net_rows.append(row)
    return arrival_rows, net_rows
