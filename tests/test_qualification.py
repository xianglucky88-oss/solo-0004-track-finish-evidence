"""Exhaustive checks for qualification slot resolution.

Run with: PYTHONPATH=. python3 -P -m unittest tests.test_qualification -v
The synthetic bundles live under tests/fixtures, never next to this file.
"""
import unittest
from fractions import Fraction
from pathlib import Path

from finishline.common import decode
from finishline.qualification import _linear_extensions, _partial_order, resolve
from finishline.workflow import materialize

FIXTURE = Path('tests/fixtures/qualification.json')
LEGACY = Path('examples/baseline.json')


def load(path):
    return decode(path.read_text(encoding='utf-8'))


def intervals(spec):
    return {k: tuple(Fraction(v) for v in pair) for k, pair in spec.items()}


class PartialOrderTests(unittest.TestCase):
    def test_strictly_separated_intervals_prove_order(self):
        iv = intervals({'a': [1, 2], 'b': [3, 4]})  # closed intervals, gap -> a before b
        edges = _partial_order(['a', 'b'], iv)
        self.assertEqual(edges, {'a': {'b'}, 'b': set()})

    def test_touching_intervals_stay_incomparable(self):
        iv = intervals({'a': [1, 3], 'b': [3, 5]})  # share endpoint 3 -> order unprovable
        self.assertEqual(_partial_order(['a', 'b'], iv), {'a': set(), 'b': set()})

    def test_missing_interval_compares_to_nobody(self):
        iv = intervals({'a': [1, 2]})  # b absent
        self.assertEqual(_partial_order(['a', 'b'], iv), {'a': set(), 'b': set()})

    def test_linear_extensions_of_chain(self):
        edges = {'a': {'b'}, 'b': {'c'}, 'c': set()}
        self.assertEqual(_linear_extensions(['a', 'b', 'c'], edges), [('a', 'b', 'c')])

    def test_linear_extensions_of_free_set(self):
        edges = {k: set() for k in 'abc'}
        self.assertEqual(len(_linear_extensions(list('abc'), edges)), 6)


class ResolutionTests(unittest.TestCase):
    def _resolve(self, groups, automatic, pools, at_large, iv):
        timebase_of = {a: 'tb' for members in groups.values() for a in members}
        return resolve(groups, automatic, pools, at_large, intervals(iv), timebase_of)

    def _outcomes(self, result):
        return {row['athlete']: row for row in result['athletes']}

    def test_acceptance_always_qualified_but_source_undetermined(self):
        # g1: a vs x overlap at the automatic boundary; y provably last.
        # g2: b provably first, z last. One at-large slot across the pool.
        groups = {'g1': ['a', 'x', 'y'], 'g2': ['b', 'z']}
        iv = {'a': [240, 260], 'x': [250, 270], 'y': [900, 920],
              'b': [340, 360], 'z': [500, 520]}
        result = self._resolve(groups, {'g1': 1, 'g2': 1},
                               {'p': ['g1', 'g2']}, {'p': 1}, iv)
        out = self._outcomes(result)
        # x (and a) advance in every interpretation, but automatic vs at-large
        # depends on the same joint explanation — the source must stay open.
        for athlete in ('a', 'x'):
            self.assertEqual(out[athlete]['decision'], 'qualified')
            self.assertEqual(out[athlete]['slot'], 'undetermined')
            self.assertEqual(set(out[athlete]['possible_slots']), {'automatic', 'at_large'})
        self.assertEqual(out['b']['slot'], 'automatic')
        self.assertEqual(out['y']['decision'], 'no_slot')
        self.assertEqual(out['z']['decision'], 'no_slot')
        self.assertEqual(result['pools'][0]['scenarios'], 2)

    def test_joint_assignment_never_double_allocates(self):
        # In every interpretation exactly automatic + at-large slots are handed out.
        groups = {'g1': ['a', 'x', 'y'], 'g2': ['b', 'z']}
        iv = {'a': [240, 260], 'x': [250, 270], 'y': [900, 920],
              'b': [340, 360], 'z': [500, 520]}
        result = self._resolve(groups, {'g1': 1, 'g2': 1},
                               {'p': ['g1', 'g2']}, {'p': 1}, iv)
        qualified = [r for r in result['athletes'] if r['decision'] == 'qualified']
        self.assertEqual(len(qualified), 3)  # 2 automatic + 1 at-large

    def test_unreadable_finish_forces_review_when_slots_scarce(self):
        groups = {'g': ['p1', 'p2']}
        result = resolve(groups, {'g': 1}, {'p': ['g']}, {'p': 0},
                         intervals({'p2': [10, 20]}), {'p1': None, 'p2': 'tb'})
        out = self._outcomes(result)
        self.assertEqual(out['p1']['decision'], 'review')
        self.assertEqual(set(out['p1']['possible_slots']), {'automatic', 'none'})
        self.assertFalse(out['p1']['readable_finish'])
        self.assertEqual(out['p2']['decision'], 'review')

    def test_review_when_qualified_only_in_some_interpretations(self):
        # Three overlapping athletes, two slots: nobody is guaranteed anything.
        groups = {'g': ['a', 'b', 'c']}
        iv = {'a': [1, 5], 'b': [2, 6], 'c': [3, 7]}
        result = self._resolve(groups, {'g': 1}, {'p': ['g']}, {'p': 1}, iv)
        for row in result['athletes']:
            self.assertEqual(row['decision'], 'review')
            self.assertIn('none', row['possible_slots'])

    def test_deterministic_at_large_ordering(self):
        groups = {'g1': ['a'], 'g2': ['b'], 'g3': ['c']}
        iv = {'a': [10, 10], 'b': [20, 20], 'c': [30, 30]}
        result = self._resolve(groups, {g: 0 for g in groups},
                               {'p': ['g1', 'g2', 'g3']}, {'p': 2}, iv)
        out = self._outcomes(result)
        self.assertEqual(out['a']['slot'], 'at_large')
        self.assertEqual(out['b']['slot'], 'at_large')
        self.assertEqual(out['c']['decision'], 'no_slot')

    def test_cross_group_overlap_forces_review(self):
        # No automatic slots; the at-large decision spans two groups whose
        # finish intervals overlap, so neither order is provable.
        groups = {'g1': ['g'], 'g2': ['h']}
        iv = {'g': [10, 20], 'h': [15, 25]}
        result = self._resolve(groups, {'g1': 0, 'g2': 0},
                               {'p': ['g1', 'g2']}, {'p': 1}, iv)
        self.assertEqual(result['pools'][0]['scenarios'], 2)
        for row in result['athletes']:
            self.assertEqual(row['decision'], 'review')

    def test_three_group_interleavings_keep_group_orders(self):
        groups = {'g1': ['i', 'j'], 'g2': ['g'], 'g3': ['h']}
        iv = {'i': [10, 20], 'j': [15, 25], 'g': [30, 31], 'h': [40, 41]}
        result = self._resolve(groups, {'g1': 1, 'g2': 0, 'g3': 0},
                               {'p': ['g1', 'g2', 'g3']}, {'p': 1}, iv)
        self.assertEqual(result['pools'][0]['scenarios'], 2)
        out = self._outcomes(result)
        self.assertEqual(out['i']['slot'], 'undetermined')
        self.assertEqual(out['j']['slot'], 'undetermined')
        self.assertEqual(out['g']['decision'], 'no_slot')

    def test_scenario_guard(self):
        groups = {'g': [f'e{i}' for i in range(9)]}
        with self.assertRaises(ValueError):
            resolve(groups, {'g': 1}, {'p': ['g']}, {'p': 1}, {},
                    {f'e{i}': None for i in range(9)})

    def test_pool_guard_counts_cross_group_interleavings(self):
        # Two internally-fixed chains with no cross-group edges: the only
        # freedom is how the chains interleave, C(2n, n) interpretations.
        from finishline.qualification import _count_linear_extensions
        size = 8
        members = [f'a{i}' for i in range(size)] + [f'b{i}' for i in range(size)]
        edges = {a: set() for a in members}
        for seq in ('a', 'b'):
            for i in range(size - 1):
                edges[f'{seq}{i}'].add(f'{seq}{i + 1}')
        import math
        self.assertEqual(_count_linear_extensions(members, edges),
                         math.comb(2 * size, size))
        big = 10
        members_big = [f'a{i}' for i in range(big)] + [f'b{i}' for i in range(big)]
        edges_big = {a: set() for a in members_big}
        for seq in ('a', 'b'):
            for i in range(big - 1):
                edges_big[f'{seq}{i}'].add(f'{seq}{i + 1}')
        self.assertGreater(_count_linear_extensions(members_big, edges_big), 50_000)


class ValidationTests(unittest.TestCase):
    def _expect_error(self, mutate):
        doc = load(FIXTURE)
        mutate(doc)
        with self.assertRaises(ValueError):
            materialize(doc)

    def test_mixed_timebases_rejected(self):
        def mutate(doc):
            doc['qualification']['at_large_pools'] = [
                {'id': 'bad', 'groups': ['gp', 'gm'], 'at_large_slots': 2}]
        self._expect_error(mutate)

    def test_group_in_two_pools_rejected(self):
        def mutate(doc):
            doc['qualification']['at_large_pools'] = [
                {'id': 'p1', 'groups': ['gp'], 'at_large_slots': 0},
                {'id': 'p2', 'groups': ['gp', 'gm'], 'at_large_slots': 1}]
        self._expect_error(mutate)

    def test_missing_athlete_from_groups_rejected(self):
        def mutate(doc):
            doc['qualification']['groups'][0]['athletes'] = ['p1']
        self._expect_error(mutate)

    def test_too_many_automatic_slots_rejected(self):
        def mutate(doc):
            doc['qualification']['groups'][0]['automatic_slots'] = 9
        self._expect_error(mutate)

    def test_camera_mixing_timebases_rejected(self):
        def mutate(doc):
            # Camera p's two segments start under one timebase; splitting them
            # makes the calibration itself incomparable and must be refused.
            doc['scales'][0]['timebase'] = 'tb-other'
        self._expect_error(mutate)


class FixtureTests(unittest.TestCase):
    def test_acceptance_fixture_pipeline(self):
        doc = load(FIXTURE)
        result = materialize(doc)
        out = {row['athlete']: row for row in result['qualification']['athletes']}
        self.assertEqual(out['p1']['decision'], 'qualified')
        # Original group results remain independently readable.
        places = {row['athlete']: row for row in result['places']}
        self.assertEqual(places['p1']['group'], 'gp')
        self.assertEqual(places['p2']['possible_places'], [2, 2])

    def test_legacy_bundle_without_qualification_still_publishes(self):
        doc = load(LEGACY)
        result = materialize(doc)
        self.assertNotIn('qualification', result)
        self.assertEqual({r['athlete']: r['place'] for r in result['places']}['r1'], 1)


if __name__ == '__main__':
    unittest.main()
