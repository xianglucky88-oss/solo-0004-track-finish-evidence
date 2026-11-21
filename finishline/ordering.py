"""Check proposed relative orderings against one shared set of camera offsets."""
from .common import require, unique


def read_relations(rows, entries):
    relations = []
    for key, row in sorted(unique(rows).items()):
        before, after = row['before'], row['after']
        require(before != after, f'ordering relation relates an athlete to itself: {key}')
        require(before in entries and after in entries, f'ordering relation names unknown athlete: {key}')
        relations.append({'id': key, 'before': before, 'after': after})
    return relations


def check_relations(relations, system, node):
    """Decide whether every proposed ordering holds under one offset assignment.

    A relation is individually possible if its strict finish ordering is
    feasible, and proven when the reverse ordering is infeasible.  When the
    full set is impossible, a minimal irreducible core names the conflicting
    relations: each pair may work alone, yet no single camera offset
    assignment satisfies them together.
    """
    for relation in relations:
        for role in ('before', 'after'):
            require(relation[role] in node, f'ordering relation {relation["id"]} lacks located finish evidence')
    results = []
    edges = {}
    for relation in relations:
        # "before" finishes strictly first: tau_before - tau_after < 0,
        # edge source=after -> target=before.
        edge = system.strict_edge(node[relation['before']], node[relation['after']])
        edges[relation['id']] = edge
        possible = system.feasible((edge,))
        reverse = system.strict_edge(node[relation['after']], node[relation['before']])
        results.append({'id': relation['id'], 'before': relation['before'], 'after': relation['after'],
                        'individually_possible': possible,
                        'proven': not system.feasible((reverse,)),
                        'in_conflict': False})
    by_id = {row['id']: row for row in results}
    jointly_possible = system.feasible(tuple(edges.values()))
    conflict_ids = []
    if not jointly_possible:
        # Minimal unsat core: greedily drop relations that are not needed to
        # preserve infeasibility, then confirm every remaining one is needed.
        core = list(edges)
        for candidate in list(core):
            remaining = [edges[k] for k in core if k != candidate]
            if not system.feasible(tuple(remaining)):
                core.remove(candidate)
        conflict_ids = core
        for key in conflict_ids:
            by_id[key]['in_conflict'] = True
    return {'all_hold': jointly_possible,
            'conflict_ids': conflict_ids,
            'relations': results}
