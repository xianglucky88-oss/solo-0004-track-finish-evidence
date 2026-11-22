"""Qualification round slot resolution.

Automatic slots are filled first inside each group; the remaining eligible
athletes then compete for at-large (cross-group) slots ordered by net finish
time.  Athletes whose times are anchored to incomparable time bases never share
an at-large pool.

Finish evidence is a closed time interval per athlete, so a strict order is
only provable when two closed intervals are strictly separated.  The provable
relations form a partial order; every linear extension of that order is one
admissible ranking interpretation.  Automatic and at-large slots are resolved
jointly inside each interpretation — never by fixing automatic slots first and
ranking the leftovers under a separate explanation.
"""
from .common import integer, require

SCENARIO_LIMIT = 50_000


def read_qualification(doc, entries, calls, intervals):
    """Validate the qualification block and resolve it into per-athlete outcomes."""
    config = doc['qualification']
    require(isinstance(config, dict), 'qualification must be an object')
    groups_doc = config['groups']
    pools_doc = config['at_large_pools']
    require(isinstance(groups_doc, list) and groups_doc, 'qualification.groups must be a non-empty list')
    require(isinstance(pools_doc, list) and pools_doc, 'qualification.at_large_pools must be a non-empty list')

    eligible = {key for key, row in entries.items() if row['status'] == 'eligible'}
    groups, automatic = {}, {}
    for row in groups_doc:
        name = row['id']
        require(isinstance(name, str) and bool(name.strip()) and name not in groups,
                f'invalid or duplicate group id: {name!r}')
        members = row['athletes']
        require(isinstance(members, list) and members, f'group {name} has no athletes')
        require(all(isinstance(a, str) and a in eligible for a in members),
                f'group {name} references an unknown or non-eligible athlete')
        require(len(members) == len(set(members)), f'group {name} lists an athlete twice')
        groups[name] = list(members)
        automatic[name] = integer(row['automatic_slots'], 'automatic_slots', 0)
        require(automatic[name] <= len(members), f'group {name} awards more automatic slots than members')
    grouped = {athlete for members in groups.values() for athlete in members}
    require(grouped == eligible, 'every eligible athlete must belong to exactly one qualification group')

    timebase_of = _timebases(calls, eligible)
    pools, at_large = {}, {}
    covered = set()
    for row in pools_doc:
        name = row['id']
        require(isinstance(name, str) and bool(name.strip()) and name not in pools,
                f'invalid or duplicate at-large pool id: {name!r}')
        members = row['groups']
        require(isinstance(members, list) and members, f'pool {name} has no groups')
        require(all(isinstance(g, str) and g in groups for g in members),
                f'pool {name} references an unknown group')
        require(len(members) == len(set(members)), f'pool {name} lists a group twice')
        pool_groups = set(members)
        require(not (pool_groups & covered), f'a group may feed only one at-large pool: {name}')
        covered |= pool_groups
        bases = set()
        for group in members:
            for athlete in groups[group]:
                base = timebase_of[athlete]
                if base is not None:  # unreadable finishes carry no comparable time
                    bases.add(base)
        require(len(bases) <= 1, f'pool {name} mixes incomparable time bases')
        pools[name] = list(members)
        at_large[name] = integer(row['at_large_slots'], 'at_large_slots', 0)
    require(covered == set(groups), 'every qualification group must feed one at-large pool')

    return resolve(groups, automatic, pools, at_large, intervals, timebase_of)


def _timebases(calls, eligible):
    timebase_of = {}
    for fact in calls:
        athlete = fact['athlete']
        if athlete in eligible and fact['finish_us'] is not None:
            base = fact['timebase']
            seen = timebase_of.setdefault(athlete, base)
            require(seen == base, f'athlete {athlete} has calls on incomparable time bases')
    # An athlete without a readable finish interval carries no comparable time.
    for athlete in eligible:
        timebase_of.setdefault(athlete, None)
    return timebase_of


def _partial_order(members, intervals):
    """Edges athlete -> athlete meaning the former is provably faster."""
    members = list(members)
    edges = {a: set() for a in members}
    for i, a in enumerate(members):
        for b in members[i + 1:]:
            ia, ib = intervals.get(a), intervals.get(b)
            if ia is not None and ib is not None:
                if ia[1] < ib[0]:
                    edges[a].add(b)
                elif ib[1] < ia[0]:
                    edges[b].add(a)
            # A missing interval compares to nobody: it can land anywhere.
    return edges


def _linear_extensions(members, edges):
    """All topological orders of the provable partial order (deterministic order)."""
    indegree = {a: 0 for a in members}
    for a, outs in edges.items():
        for b in outs:
            indegree[b] += 1
    orders, current = [], []

    def extend(remaining, indeg):
        if not remaining:
            orders.append(tuple(current))
            return
        for a in sorted(remaining):
            if indeg[a] == 0:
                current.append(a)
                next_remaining = remaining - {a}
                next_indeg = dict(indeg)
                for b in edges[a]:
                    next_indeg[b] -= 1
                extend(next_remaining, next_indeg)
                current.pop()

    extend(set(members), indegree)
    return orders


def _count_linear_extensions(members, edges):
    """Number of topological orders, memoized over the remaining-athlete mask."""
    index = {a: i for i, a in enumerate(members)}
    preds = [0] * len(members)
    for a, outs in edges.items():
        for b in outs:
            preds[index[b]] |= 1 << index[a]
    full = (1 << len(members)) - 1
    cache = {}

    def count(mask):
        if mask == full:
            return 1
        if mask not in cache:
            total = 0
            for i, _ in enumerate(members):
                bit = 1 << i
                if not (mask & bit) and (preds[i] & ~mask) == 0:
                    total += count(mask | bit)
                    if total > SCENARIO_LIMIT:
                        return total
            cache[mask] = total
        return cache[mask]

    return count(0)


def resolve(groups, automatic, pools, at_large, intervals, timebase_of):
    # The provable relations inside a pool form one partial order; its linear
    # extensions are exactly the admissible ranking interpretations.  Automatic
    # and at-large slots are assigned jointly inside each interpretation.
    athlete_outcomes = {a: {'slots': set()}
                        for members in groups.values() for a in members}
    pool_summaries = []
    for pool, pool_groups in pools.items():
        pool_members = [a for g in pool_groups for a in groups[g]]
        edges = _partial_order(pool_members, intervals)
        # Count admissible interleavings before materializing them; cross-group
        # freedom can explode even when every group order is fixed.
        require(_count_linear_extensions(pool_members, edges) <= SCENARIO_LIMIT,
                f'too many undetermined rankings in pool {pool}; adjudicate before resolving slots')
        pool_orders = _linear_extensions(pool_members, edges)
        slot_cap = at_large[pool]
        valid = 0
        for order in pool_orders:
            # The pool partial order contains every within-group edge, so each
            # pool order projects onto a valid order of each member group.
            valid += 1
            automatic_winners = set()
            for group in pool_groups:
                group_order = [a for a in order if a in groups[group]]
                automatic_winners.update(group_order[:automatic[group]])
            remainder = [a for a in order if a not in automatic_winners]
            at_large_winners = set(remainder[:slot_cap])
            for a in pool_members:
                outcome = athlete_outcomes[a]
                if a in automatic_winners:
                    outcome['slots'].add('automatic')
                elif a in at_large_winners:
                    outcome['slots'].add('at_large')
                else:
                    outcome['slots'].add('none')
        pool_summaries.append({
            'pool': pool,
            'timebase': next(iter({timebase_of[a] for a in pool_members
                                   if timebase_of[a] is not None}), None),
            'groups': list(pool_groups), 'at_large_slots': slot_cap,
            'eligible_athletes': sorted(pool_members), 'scenarios': valid})

    rows = []
    for athlete in sorted(athlete_outcomes):
        outcome = athlete_outcomes[athlete]
        slots = outcome['slots']
        qualified_ways = slots & {'automatic', 'at_large'}
        if not qualified_ways:
            decision, slot = 'no_slot', None
        elif 'none' in slots:
            decision, slot = 'review', None
        elif qualified_ways == {'automatic'}:
            decision, slot = 'qualified', 'automatic'
        elif qualified_ways == {'at_large'}:
            decision, slot = 'qualified', 'at_large'
        else:
            # Always qualified, but the group boundary and at-large backfill
            # interact, so the slot source is not fixed under one explanation.
            decision, slot = 'qualified', 'undetermined'
        rows.append({'athlete': athlete, 'decision': decision, 'slot': slot,
                     'possible_slots': sorted(slots),
                     'timebase': timebase_of[athlete],
                     'readable_finish': athlete in intervals})
    return {'pools': pool_summaries, 'athletes': rows}
