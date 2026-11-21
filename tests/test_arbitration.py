"""Acceptance tests for arbitration-aware places.

Run from the repository root with:  python3 -I -m unittest discover -s tests -v
"""
import copy
import sys
import unittest
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finishline.common import decode, encode  # noqa: E402
from finishline.workflow import materialize  # noqa: E402

EXAMPLES = {
    name: decode(open(path, encoding='utf-8').read())
    for name, path in (
        ('baseline', 'examples/baseline.json'),
        ('changed', 'examples/changed.json'),
        ('protest', 'examples/protest.json'),
        ('conflict', 'examples/arbitration_conflict.json'),
        ('invalid', 'examples/invalid_arbitration.json'),
    )
}


class BaselineContract(unittest.TestCase):
    def test_independent_check_values(self):
        rows = {row['athlete']: row for row in materialize(EXAMPLES['baseline'])['places']}
        self.assertEqual(rows['r1']['place'], 1)
        self.assertEqual(rows['r4']['place'], 4)
        self.assertEqual(rows['r2']['possible_places'], [2, 3])
        self.assertEqual(rows['r3']['possible_places'], [2, 3])
        self.assertIsNone(rows['r5']['possible_places'])

    def test_bundles_without_arbitrations_have_no_arbitration_block(self):
        for name in ('baseline', 'changed'):
            self.assertNotIn('arbitration', materialize(EXAMPLES[name]))

    def test_broken_scale_segment_removes_every_certain_place(self):
        rows = {row['athlete']: row for row in materialize(EXAMPLES['changed'])['places']}
        self.assertIsNone(rows['r1']['place'])
        self.assertEqual(rows['r1']['possible_places'], [1, 2])
        self.assertEqual(rows['r4']['possible_places'], [1, 4])

    def test_replay_is_deterministic(self):
        self.assertEqual(encode(materialize(EXAMPLES['protest'])),
                         encode(materialize(copy.deepcopy(EXAMPLES['protest']))))


class SingleProtestAcceptance(unittest.TestCase):
    def setUp(self):
        self.report = materialize(EXAMPLES['protest'])['arbitration']
        self.outcomes = self.report['athlete_outcomes']

    def test_only_r2_is_challenged_but_chain_is_not_deleted(self):
        self.assertEqual(self.report['challenged_athletes'], ['r2'])
        self.assertEqual(self.report['interpretation_count'], 3)
        # The two alternative readings are still part of the compatible set.
        chosen = {tuple(sorted(i['options'].items())) for i in self.report['interpretations']}
        self.assertEqual(len(chosen), 3)

    def test_adjacent_non_protester_r1_is_affected(self):
        r1 = self.outcomes['r1']
        self.assertTrue(r1['affected'])
        self.assertEqual(r1['base_possible_places'], [1, 1])
        self.assertEqual(r1['arbitration_possible_places'], [1, 2])
        self.assertEqual(r1['classification'], 'challengeable')
        self.assertIsNone(r1['citable_place'])

    def test_farther_runner_r4_is_provably_stable(self):
        r4 = self.outcomes['r4']
        self.assertFalse(r4['affected'])
        self.assertEqual(r4['base_possible_places'], [4, 4])
        self.assertEqual(r4['arbitration_possible_places'], [4, 4])
        self.assertEqual(r4['classification'], 'citable')
        self.assertEqual(r4['citable_place'], 4)
        for interpretation in self.report['interpretations']:
            self.assertEqual(interpretation['places']['r4'], [4, 4])

    def test_only_robust_places_are_open_for_external_citation(self):
        self.assertEqual(self.report['citable_places'], [4])
        # r1's official first place from the pre-arbitration result is withdrawn.
        self.assertEqual(self.report['challengeable_places'], [1])

    def test_distinguish_challengeable_from_already_undecidable(self):
        # r2 was already undecidable; its span widened, it is not a lost certain place.
        self.assertEqual(self.outcomes['r2']['classification'], 'previously_undecidable_widened')
        # r3 was already undecidable and remains exactly so: no new protest effect.
        self.assertEqual(self.outcomes['r3']['classification'], 'stable_undecidable')
        self.assertFalse(self.outcomes['r3']['affected'])
        self.assertEqual(self.report['previously_undecidable_ranges'], [[2, 3], [2, 3]])

    def test_affected_athletes_and_place_ranges(self):
        self.assertEqual(self.report['affected_athletes'], ['r1', 'r2'])
        self.assertEqual(self.report['affected_place_range'], [1, 3])

    def test_protest_text_is_archived_but_never_measured(self):
        statement = self.report['protests'][0]['protest_text']
        self.assertIn('不携带任何读值', statement)
        # Every numerical range in the report must originate from an explicit option
        # or the original measurement; the early/late alternatives are 1150..1160 / 1450..1460.
        option_map = {opt['id']: opt for opt in self.report['allowed_options'][0]['options']}
        self.assertEqual(option_map['opt-early-call-2']['finish_elapsed_us'], [150, 160])
        self.assertEqual(option_map['opt-late-call-2']['finish_elapsed_us'], [450, 460])
        # No option interval may come from parsing the free-text statement.
        self.assertNotIn('1150', statement)

    def test_retain_option_keeps_original_measurement(self):
        option_map = {opt['id']: opt for opt in self.report['allowed_options'][0]['options']}
        retained = option_map['opt-retain-call-2']
        self.assertTrue(retained['retain'])
        self.assertEqual(retained['finish_elapsed_us'], [337, 353])
        retain_case = next(i for i in self.report['interpretations']
                           if i['options']['call-2'] == 'opt-retain-call-2')
        self.assertEqual(retain_case['places']['r2'], [2, 3])


class ConflictExclusion(unittest.TestCase):
    def test_incompatible_pair_is_never_adopted_together(self):
        report = materialize(EXAMPLES['conflict'])['arbitration']
        self.assertEqual(report['conflicts'], [['opt2-early', 'opt3-early']])
        self.assertEqual(report['interpretation_count'], 3)  # 2x2 minus one incompatible pair
        for interpretation in report['interpretations']:
            self.assertFalse(interpretation['options']['call-2'] == 'opt2-early'
                             and interpretation['options']['call-3'] == 'opt3-early')
        # Even with two protests, r4 remains the sole citable place.
        self.assertEqual(report['citable_places'], [4])


class RejectedArbitrations(unittest.TestCase):
    def test_unknown_conflict_option_is_rejected(self):
        with self.assertRaises(ValueError):
            materialize(EXAMPLES['invalid'])

    def _bundle(self, **override):
        doc = copy.deepcopy(EXAMPLES['protest'])
        arb = doc['arbitrations'][0]
        for key, value in override.items():
            arb[key] = value
        return doc

    def test_unknown_call_rejected(self):
        with self.assertRaises(ValueError):
            materialize(self._bundle(call='call-nope'))

    def test_duplicate_arbitration_rejected(self):
        doc = copy.deepcopy(EXAMPLES['protest'])
        doc['arbitrations'].append(copy.deepcopy(doc['arbitrations'][0]))
        with self.assertRaises(ValueError):
            materialize(doc)

    def test_duplicate_option_id_rejected(self):
        doc = copy.deepcopy(EXAMPLES['protest'])
        options = doc['arbitrations'][0]['options']
        options[1]['id'] = options[0]['id']
        with self.assertRaises(ValueError):
            materialize(doc)

    def test_reversed_bounds_rejected(self):
        with self.assertRaises(ValueError):
            materialize(self._bundle(options=[
                {'id': 'o1', 'retain': True},
                {'id': 'o2', 'finish_us': [1300, 1200]},
            ]))

    def test_option_before_common_start_rejected(self):
        with self.assertRaises(ValueError):
            materialize(self._bundle(options=[
                {'id': 'o1', 'retain': True},
                {'id': 'o2', 'finish_us': [900, 950]},
            ]))

    def test_retain_on_uncovered_call_rejected(self):
        doc = copy.deepcopy(EXAMPLES['changed'])
        doc['arbitrations'] = [{
            'call': 'call-4',
            'protest_text': '文字不作为读值。',
            'options': [{'id': 'o-retain', 'retain': True}],
            'conflicts': [],
        }]
        with self.assertRaises(ValueError):
            materialize(doc)

    def test_missing_protest_text_rejected(self):
        with self.assertRaises(ValueError):
            materialize(self._bundle(protest_text='   '))

    def test_all_conflicting_combinations_rejected(self):
        doc = copy.deepcopy(EXAMPLES['conflict'])
        # One single option per call, declared incompatible: no interpretation survives.
        doc['arbitrations'][0]['options'] = [{'id': 'only-a', 'retain': True}]
        doc['arbitrations'][1]['options'] = [{'id': 'only-b', 'retain': True}]
        doc['arbitrations'][1]['conflicts'] = [['only-a', 'only-b']]
        with self.assertRaises(ValueError):
            materialize(doc)

    def test_conflict_pair_needs_distinct_options(self):
        doc = copy.deepcopy(EXAMPLES['protest'])
        doc['arbitrations'][0]['conflicts'] = [['opt-early-call-2', 'opt-early-call-2']]
        with self.assertRaises(ValueError):
            materialize(doc)


class FractionAndUnmeasuredSemantics(unittest.TestCase):
    def test_exact_fraction_string_option_is_accepted(self):
        doc = copy.deepcopy(EXAMPLES['protest'])
        doc['arbitrations'][0]['options'][1]['finish_us'] = ['1150/1', '2321/2']
        report = materialize(doc)['arbitration']
        option = next(o for o in report['allowed_options'][0]['options']
                      if o['id'] == 'opt-early-call-2')
        self.assertEqual(option['finish_elapsed_us'], [150, '321/2'])
        self.assertEqual(Fraction('321/2'), Fraction(2321, 2) - 1000)

    def test_replacement_option_reintroduces_unmeasured_athlete(self):
        doc = copy.deepcopy(EXAMPLES['changed'])
        doc['arbitrations'] = [{
            'call': 'call-4',
            'protest_text': '文字不作为读值；替代读值由仲裁员结构化给出。',
            'options': [
                {'id': 'o-retain-impossible', 'finish_us': [2100, 2110]},
                {'id': 'o-even-later', 'finish_us': [2200, 2210]},
            ],
            'conflicts': [],
        }]
        report = materialize(doc)['arbitration']
        # r4 stays last under both alternatives, but r1/r2/r3 keep the changed-bundle uncertainty.
        for interpretation in report['interpretations']:
            self.assertEqual(interpretation['places']['r4'], [4, 4])
        # The unmeasured athlete re-enters with a stable last place; r1 was already strictly
        # separated from the r2/r3 cluster and stays citable too, while r2/r3 do not.
        self.assertEqual(report['citable_places'], [1, 4])
        self.assertEqual(report['athlete_outcomes']['r4']['arbitration_possible_places'], [4, 4])
        self.assertTrue(report['athlete_outcomes']['r4']['affected'])
        self.assertIsNone(report['athlete_outcomes']['r2']['citable_place'])


if __name__ == '__main__':
    unittest.main()
