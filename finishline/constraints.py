"""Exact feasibility for shared camera offsets and per-call timing uncertainty.

Every variable is one unknown real: either a camera zero-point offset or an
athlete's actual finish instant.  A constraint ``target - source <= w`` is
stored as an edge ``(source, target, w)``; Bellman-Ford relaxes
``dist[target] <= dist[source] + w`` and declares infeasibility on a negative
cycle.  Strict orderings need ``target - source < 0``; they are encoded
lexicographically as weight ``(0, -1)`` against a symbolic positive
infinitesimal, so no epsilon guess is introduced and all arithmetic stays
exact rational arithmetic.
"""
from .common import require


def _key(weight):
    return weight if isinstance(weight, tuple) else (weight, 0)


class DifferenceSystem:
    def __init__(self):
        self.nodes = set()
        self.edges = []

    def var(self, name):
        require(name not in self.nodes, f'duplicate constraint variable: {name}')
        self.nodes.add(name)
        return name

    def le(self, target, source, bound=0):
        """Record ``target - source <= bound`` as edge source -> target."""
        self.nodes.update((source, target))
        self.edges.append((source, target, _key(bound)))

    def strict_edge(self, target, source):
        """Edge enforcing strict ``target - source < 0``."""
        self.nodes.update((source, target))
        return (source, target, (0, -1))

    def feasible(self, extra=()):
        dist = {node: (0, 0) for node in self.nodes}
        edges = self.edges + list(extra)
        for _ in range(len(self.nodes)):
            changed = False
            for source, target, weight in edges:
                candidate = (dist[source][0] + weight[0], dist[source][1] + weight[1])
                if candidate < dist[target]:
                    dist[target] = candidate
                    changed = True
            if not changed:
                return True
        return False


def build_finish_system(intervals, offsets, start=None):
    """Build the joint constraint graph for one heat.

    ``intervals`` maps an athlete to (low, high, camera) where low/high already
    include the legacy scale error.  A located call reads
    ``tau = nominal + delta_camera + eta`` with ``eta`` in
    ``[low-nominal, high-nominal]``, equivalently ``low <= tau - delta <= high``;
    the camera's single unknown zero-point offset is bounded by ``offsets``.
    Cameras absent from ``offsets`` keep an unconstrained historical offset,
    which is equivalent to pinning their absolute reading bounds
    ``low <= tau <= high``.  When ``start`` is supplied, the common start adds
    the absolute floor ``tau >= start`` that no offset can violate.
    """
    system = DifferenceSystem()
    athlete_var = {}
    for athlete in sorted(intervals):
        athlete_var[athlete] = system.var(f't:{athlete}')
    offset_var = {}
    for camera in sorted(offsets):
        offset_var[camera] = system.var(f'd:{camera}')
        lower, upper = offsets[camera]
        system.le(offset_var[camera], 'zero', upper)   # delta - 0 <= upper
        system.le('zero', offset_var[camera], -lower)  # 0 - delta <= -lower
    system.nodes.add('zero')
    for athlete, (low, high, camera) in intervals.items():
        tau = athlete_var[athlete]
        if camera in offset_var:
            delta = offset_var[camera]
            # low <= tau - delta <= high couples every call sharing the camera
            # through one delta, while delta's own bounds supply the anchor.
            # The common start is an absolute floor the offset cannot erase.
            if start is not None:
                system.le('zero', tau, -start)         # 0 - tau <= -start
            system.le(tau, delta, high)                # tau - delta <= high
            system.le(delta, tau, -low)                # delta - tau <= -low
        else:
            # Historical camera without offset evidence: an unconstrained
            # offset is equivalent to pinning the absolute reading bounds.
            system.le(tau, 'zero', high)               # tau <= high
            system.le('zero', tau, -low)               # tau >= low (>= start)
    return system, athlete_var
