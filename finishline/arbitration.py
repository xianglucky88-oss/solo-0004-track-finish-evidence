"""Arbitration over challenged calls.

A protest targets exactly one athlete. The arbitrator never deletes the whole
uncertainty chain: for each challenged call they publish a closed set of
allowed readings (the measured interval may be retained, or replaced by exact
alternative intervals) and pairs of alternatives that cannot be chosen
together. A protest's free text is evidence context only, never a measurement.

An interpretation picks one allowed option per challenged call, excluding
incompatible pairs. Official places are externally citable only when they are
identical in every compatible interpretation.
"""
from itertools import product

from .common import number, require, scalar, unique
from .places import place_ranges

# A hard cap keeps local enumeration explicit instead of exploding silently.
MAX_INTERPRETATIONS = 10000


def _option_row(option, start):
    oid = option['id']
    require(isinstance(oid, str) and bool(oid.strip()), 'arbitration option id must be a non-blank string')
    retain = option.get('retain')
    interval = option.get('finish_us')
    if retain is True:
        require(interval is None, f'option {oid} cannot both retain and replace the measurement')
        return oid, None
    if retain is False or retain is None:
        require(isinstance(interval, list) and len(interval) == 2,
                f'option {oid} must give finish_us [lo, hi] or retain: true')
        lo, hi = number(interval[0], 'arbitration finish bound'), number(interval[1], 'arbitration finish bound')
        require(lo <= hi, f'option {oid} has reversed finish bounds')
        require(lo >= start, f'option {oid} precedes common start')
        return oid, (lo, hi)
    raise ValueError(f'option {oid} retain must be true or false')


def read_arbitrations(doc, entries, calls, start):
    """Validate the arbitration block and resolve it against materialized calls."""
    block = doc.get('arbitrations')
    if block is None:
        return None
    require(isinstance(block, list) and block, 'arbitrations must be a non-empty list')
    call_index = unique(calls)
    qualified = {key for key, row in entries.items() if row['status'] == 'eligible'}

    challenges = []
    seen_calls = set()
    all_options = set()
    conflicts = []
    for index, row in enumerate(block):
        require(isinstance(row, dict), f'arbitration {index} must be an object')
        call_id = row['call']
        require(call_id in call_index, f'unknown call in arbitration: {call_id}')
        require(call_id not in seen_calls, f'duplicate arbitration for call: {call_id}')
        seen_calls.add(call_id)
        fact = call_index[call_id]
        athlete = fact['athlete']
        require(athlete is not None and athlete in qualified,
                f'arbitration {call_id} does not target an eligible athlete')
        statement = row.get('protest_text')
        require(isinstance(statement, str) and bool(statement.strip()),
                f'arbitration {call_id} needs a protest_text record (context, never a measurement)')
        options = row.get('options')
        require(isinstance(options, list) and options, f'arbitration {call_id} needs allowed options')
        parsed = {}
        for option in options:
            require(isinstance(option, dict), f'arbitration {call_id} option must be an object')
            oid, bounds = _option_row(option, start)
            require(oid not in parsed and oid not in all_options, f'duplicate option id: {oid}')
            if bounds is None:
                require(fact['finish_us'] is not None,
                        f'option {oid} retains a call with no fully covered measurement')
            parsed[oid] = bounds
            all_options.add(oid)
        challenges.append({'call': call_id, 'athlete': athlete, 'protest_text': statement,
                           'options': parsed, 'fact': fact})
        for pair in row.get('conflicts', []):
            require(isinstance(pair, list) and len(pair) == 2, f'arbitration {call_id} conflict must be a pair')
            conflicts.append((pair[0], pair[1]))

    validated = []
    for a, b in conflicts:
        require(a != b, 'a conflict pair needs two distinct options')
        require(a in all_options and b in all_options, f'conflict references unknown option: {a}/{b}')
        validated.append((a, b))
    return {'challenges': challenges, 'conflicts': validated}


def _combo_intervals(base_intervals, challenges, choices):
    intervals = dict(base_intervals)
    for challenge, oid in zip(challenges, choices):
        bounds = challenge['options'][oid]
        if bounds is None:
            bounds = base_intervals[challenge['athlete']]
        intervals[challenge['athlete']] = bounds
    return intervals


def _encode_interval(bounds, start):
    return [scalar(bounds[0] - start), scalar(bounds[1] - start)]


def build_report(prepared, base_intervals, spans, qualified, start):
    """Enumerate compatible interpretations and classify every eligible athlete."""
    challenges = prepared['challenges']
    conflict_pairs = {tuple(sorted(pair)) for pair in prepared['conflicts']}
    option_ids = [sorted(item['options']) for item in challenges]
    total_combos = 1
    for ids in option_ids:
        total_combos *= len(ids)
    require(total_combos <= MAX_INTERPRETATIONS, 'too many arbitration interpretations to enumerate locally')

    interpretations = []
    # Robust spans come only from compatible interpretations; seeding them with the
    # baseline span would wrongly re-inject unmeasured full-span uncertainty even when
    # the arbitrator has published structured alternatives for that call.
    robust = {key: set() for key in qualified}
    for numbering, choices in enumerate(product(*option_ids), start=1):
        chosen = set(choices)
        if any(a in chosen and b in chosen for a, b in conflict_pairs):
            continue
        intervals = _combo_intervals(base_intervals, challenges, choices)
        case = place_ranges(intervals, qualified)
        for key in qualified:
            robust[key].add(case[key][0])
            robust[key].add(case[key][1])
        interpretations.append({
            'id': f'i{numbering:02d}',
            'options': {item['call']: oid for item, oid in zip(challenges, choices)},
            'places': {key: list(case[key]) for key in sorted(case)},
        })
    require(interpretations, 'every arbitration interpretation is excluded by conflicts')

    outcomes = {}
    for key in sorted(qualified):
        base_lo, base_hi = spans[key]
        robust_lo, robust_hi = min(robust[key]), max(robust[key])
        base_fixed = base_lo == base_hi
        citable = robust_lo == robust_hi
        if citable:
            classification = 'citable'
        elif base_fixed:
            classification = 'challengeable'
        elif (robust_lo, robust_hi) == (base_lo, base_hi):
            classification = 'stable_undecidable'
        else:
            classification = 'previously_undecidable_widened'
        outcomes[key] = {
            'base_possible_places': [base_lo, base_hi],
            'arbitration_possible_places': [robust_lo, robust_hi],
            'citable_place': robust_lo if citable else None,
            'classification': classification,
            'affected': (robust_lo, robust_hi) != (base_lo, base_hi),
        }

    affected_athletes = [key for key, row in outcomes.items() if row['affected']]
    citable_places = sorted(row['citable_place'] for row in outcomes.values() if row['citable_place'] is not None)
    challenged_athletes = [item['athlete'] for item in challenges]
    challengeable_places = sorted({outcomes[key]['base_possible_places'][0]
                                   for key in affected_athletes
                                   if outcomes[key]['classification'] == 'challengeable'})
    previously_undecidable = [[row['base_possible_places'][0], row['base_possible_places'][1]]
                              for key, row in outcomes.items()
                              if row['classification'] in ('previously_undecidable_widened', 'stable_undecidable')]
    previously_undecidable.sort()
    if affected_athletes:
        affected_place_range = [min(outcomes[key]['arbitration_possible_places'][0] for key in affected_athletes),
                                max(outcomes[key]['arbitration_possible_places'][1] for key in affected_athletes)]
    else:
        affected_place_range = None

    return {
        'challenged_athletes': challenged_athletes,
        'protests': [{'call': item['call'], 'athlete': item['athlete'], 'protest_text': item['protest_text']}
                     for item in challenges],
        'allowed_options': [
            {'call': item['call'], 'athlete': item['athlete'],
             'options': [
                 {'id': oid,
                  'retain': bounds is None,
                  'finish_elapsed_us': (_encode_interval(bounds, start) if bounds is not None else
                                        _encode_interval(base_intervals[item['athlete']], start))}
                 for oid, bounds in sorted(item['options'].items())]}
            for item in challenges],
        'conflicts': [[a, b] for a, b in sorted(conflict_pairs)],
        'interpretation_count': len(interpretations),
        'interpretations': interpretations,
        'citable_places': citable_places,
        'affected_athletes': affected_athletes,
        'affected_place_range': affected_place_range,
        'challengeable_places': challengeable_places,
        'previously_undecidable_ranges': previously_undecidable,
        'athlete_outcomes': outcomes,
    }
