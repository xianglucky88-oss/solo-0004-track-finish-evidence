"""Acceptance checks for segmented start firings and the frozen old format."""
import itertools
import json
import random
import unittest
from fractions import Fraction

from finishline.common import encode
from finishline.workflow import materialize


def load(name):
    with open(f'examples/{name}', encoding='utf-8') as handle:
        return json.load(handle)


BASELINE = load('baseline.json')
CHANGED = load('changed.json')
SEGMENTED = load('segmented.json')
MISSING = load('missing-start.json')


def by_athlete(rows):
    return {row['athlete']: row for row in rows}


def sample(doc, result, count=3000, seed=20261121):
    """Draw admissible realizations: one shared offset per firing."""
    starts = {row['id']: (Fraction(row['time_us']), Fraction(row['error_us']))
              for row in doc['starts']}
    finish = {row['athlete']: row['finish_us'] for row in result['arrival_places']
              if row['finish_us'] is not None}
    firing = {row['athlete']: row['start'] for row in result['net_places']}
    rng = random.Random(seed)
    for _ in range(count):
        offsets = {key: rng.uniform(-float(err), float(err))
                   for key, (time, err) in starts.items()}
        arrival = {key: rng.uniform(*map(float, bounds)) for key, bounds in finish.items()}
        net = {}
        for key, bounds in finish.items():
            if firing[key] is not None:
                net[key] = (rng.uniform(*map(float, bounds))
                            - float(starts[firing[key]][0]) - offsets[firing[key]])
        yield arrival, net


def ranks(values):
    return {key: 1 + sum(other < value for other in values.values()) for key, value in values.items()}


class OldFormatTest(unittest.TestCase):
    def test_baseline_places_unchanged(self):
        result = materialize(BASELINE)
        self.assertEqual(set(result), {'heat', 'calls', 'places'})
        places = by_athlete(result['places'])
        self.assertEqual(places['r1']['place'], 1)
        self.assertEqual(places['r4']['place'], 4)
        self.assertEqual(places['r2']['possible_places'], [2, 3])
        self.assertEqual(places['r3']['possible_places'], [2, 3])
        self.assertEqual(places['r5']['possible_places'], None)

    def test_changed_places_unchanged(self):
        places = by_athlete(materialize(CHANGED)['places'])
        self.assertEqual(places['r1']['place'], None)
        self.assertEqual(places['r1']['possible_places'], [1, 2])
        self.assertEqual(places['r4']['possible_places'], [1, 4])

    def test_result_is_byte_stable(self):
        # Frozen bytes captured before segmented starts were added.
        self.assertEqual(
            encode(materialize(BASELINE)),
            '{"calls":[{"assignment":"la1","athlete":"r1","camera":"a","columns":[10,10],'
            '"finish_us":[1197,1203],"id":"call-1","lane":1,"scale":"scale-a1"},'
            '{"assignment":"la2","athlete":"r2","camera":"a","columns":[24,25],'
            '"finish_us":[1337,1353],"id":"call-2","lane":2,"scale":"scale-a1"},'
            '{"assignment":"lb3","athlete":"r3","camera":"b","columns":[20,21],'
            '"finish_us":[1338,1354],"id":"call-3","lane":3,"scale":"scale-b"},'
            '{"assignment":"la4","athlete":"r4","camera":"a","columns":[90,90],'
            '"finish_us":[1997,2003],"id":"call-4","lane":4,"scale":"scale-a2"}],'
            '"heat":"demo-heat","places":[{"athlete":"r1","call":"call-1",'
            '"elapsed_us":[197,203],"place":1,"possible_places":[1,1],"status":"eligible"},'
            '{"athlete":"r2","call":"call-2","elapsed_us":[337,353],"place":null,'
            '"possible_places":[2,3],"status":"eligible"},'
            '{"athlete":"r3","call":"call-3","elapsed_us":[338,354],"place":null,'
            '"possible_places":[2,3],"status":"eligible"},'
            '{"athlete":"r4","call":"call-4","elapsed_us":[997,1003],"place":4,'
            '"possible_places":[4,4],"status":"eligible"},'
            '{"athlete":"r5","call":null,"elapsed_us":null,"place":null,'
            '"possible_places":null,"status":"dns"}]}')


class SegmentedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = materialize(SEGMENTED)
        cls.arrival = by_athlete(cls.result['arrival_places'])
        cls.net = by_athlete(cls.result['net_places'])

    def test_two_tables(self):
        self.assertEqual(set(self.result), {'heat', 'calls', 'arrival_places', 'net_places'})
        self.assertEqual(set(self.arrival), set(self.net))

    def test_firing_coverage(self):
        self.assertEqual(self.net['a1']['start'], 'fire-pack')
        self.assertEqual(self.net['a2']['start'], 'fire-pack')
        self.assertEqual(self.net['a3']['start'], 'fire-pack')
        self.assertNotEqual(self.net['b1']['start'], self.net['c1']['start'])

    def test_first_to_arrive_but_slower_net(self):
        self.assertEqual(self.arrival['x1']['place'], 1)
        self.assertEqual(self.net['x1']['place'], 6)
        for key in ('a1', 'a2', 'a3', 'b1', 'c1'):
            self.assertLess(self.net[key]['elapsed_us'][0], self.net['x1']['elapsed_us'][0])

    def test_shared_firing_orders_overlapping_elapsed(self):
        for key, place in (('a1', 1), ('a2', 2), ('a3', 3)):
            self.assertEqual(self.net[key]['place'], place)
            self.assertEqual(self.net[key]['possible_places'], [place, place])
        # The published elapsed intervals really do overlap pairwise.
        pairs = (('a1', 'a2'), ('a2', 'a3'))
        for first, second in pairs:
            self.assertFalse(self.net[first]['elapsed_us'][1] < self.net[second]['elapsed_us'][0])

    def test_cross_firing_not_provable(self):
        self.assertIsNone(self.net['b1']['place'])
        self.assertIsNone(self.net['c1']['place'])
        self.assertEqual(self.net['b1']['possible_places'], [4, 5])
        self.assertEqual(self.net['c1']['possible_places'], [4, 5])
        # Both have readable bounds, yet neither order is provable.
        b, c = self.net['b1']['elapsed_us'], self.net['c1']['elapsed_us']
        self.assertFalse(b[1] < c[0] or c[1] < b[0])

    def test_definite_places_hold_in_every_realization(self):
        for arrival, net in sample(SEGMENTED, self.result):
            arrival_ranks, net_ranks = ranks(arrival), ranks(net)
            for key, row in self.arrival.items():
                low, high = row['possible_places']
                self.assertTrue(low <= arrival_ranks[key] <= high)
                if row['place'] is not None:
                    self.assertEqual(arrival_ranks[key], row['place'])
            for key, row in self.net.items():
                if row['elapsed_us'] is None:
                    continue
                low, high = row['possible_places']
                self.assertTrue(low <= net_ranks[key] <= high)
                if row['place'] is not None:
                    self.assertEqual(net_ranks[key], row['place'])

    def test_unprovable_pairs_really_swap(self):
        seen = set()
        for arrival, net in sample(SEGMENTED, self.result, count=400):
            seen.add(net['b1'] < net['c1'])
        self.assertEqual(seen, {True, False})


class MissingStartTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = materialize(MISSING)
        cls.arrival = by_athlete(cls.result['arrival_places'])
        cls.net = by_athlete(cls.result['net_places'])

    def test_missing_start_joins_arrival(self):
        self.assertEqual(self.arrival['m1']['place'], 1)
        self.assertEqual(self.arrival['m1']['finish_us'], [1028, 1032])

    def test_missing_start_has_no_definite_net_place(self):
        row = self.net['m1']
        self.assertIsNone(row['start'])
        self.assertIsNone(row['elapsed_us'])
        self.assertIsNone(row['place'])
        self.assertEqual(row['possible_places'], [1, 4])

    def test_shared_firing_order_with_wildcard(self):
        self.assertEqual(self.net['m2']['possible_places'], [1, 3])
        self.assertEqual(self.net['m3']['possible_places'], [2, 4])
        self.assertIsNone(self.net['m4']['place'])
        for arrival, net in sample(MISSING, self.result):
            net_ranks = ranks(net)
            for key, row in self.net.items():
                if row['elapsed_us'] is None:
                    continue
                low, high = row['possible_places']
                self.assertTrue(low <= net_ranks[key] <= high)


class RejectionTest(unittest.TestCase):
    def test_both_start_forms_rejected(self):
        with self.assertRaises(ValueError):
            materialize(dict(BASELINE, starts=MISSING['starts']))

    def test_unknown_firing_rejected(self):
        doc = json.loads(json.dumps(SEGMENTED))
        doc['entries'][0]['start'] = 'fire-nowhere'
        with self.assertRaises(ValueError):
            materialize(doc)

    def test_conflicting_firing_rejected(self):
        doc = json.loads(json.dumps(SEGMENTED))
        doc['entries'][0]['start'] = 'fire-late'
        with self.assertRaises(ValueError):
            materialize(doc)

    def test_unknown_member_rejected(self):
        doc = json.loads(json.dumps(SEGMENTED))
        doc['starts'][0]['athletes'] = ['ghost']
        with self.assertRaises(ValueError):
            materialize(doc)


if __name__ == '__main__':
    unittest.main()
