"""Acceptance checks for shared camera zero-point offsets.

Run from the repository root with an isolated interpreter so untrusted data
directories can never shadow the standard library::

    python3 -I tests/acceptance.py

The script recomputes every expectation from the synthetic example bundles;
it never edits the immutable SQLite editions.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from finishline.common import decode, encode  # noqa: E402
from finishline.workflow import materialize  # noqa: E402


def load(name):
    return decode((ROOT / 'examples' / name).read_text(encoding='utf-8'))


def places_by_athlete(result):
    return {row['athlete']: row for row in result['places']}


def relations_by_id(result):
    return {row['id']: row for row in result['order_checks']['relations']}


def check(condition, label):
    if not condition:
        raise AssertionError(label)
    print(f'  ok - {label}')


def test_legacy_outputs_unchanged():
    print('legacy bundles keep their historical results')
    expected = {
        'baseline.json': {
            'r1': (1, [1, 1]), 'r2': (None, [2, 3]), 'r3': (None, [2, 3]),
            'r4': (4, [4, 4]), 'r5': (None, None)},
        'changed.json': {
            'r1': (None, [1, 2]), 'r2': (None, [2, 4]), 'r3': (None, [2, 4]),
            'r4': (None, [1, 4]), 'r5': (None, None)},
    }
    for name, wants in expected.items():
        result = materialize(load(name))
        check('order_checks' not in result, f'{name}: no order_checks section without input')
        for athlete, (place, possible) in wants.items():
            row = places_by_athlete(result)[athlete]
            check(row['place'] is place and row['possible_places'] == possible,
                  f'{name}: {athlete} place={place} possible={possible}')


def test_same_camera_offset_is_shared():
    print('same-camera calls share one offset and keep provable order')
    result = materialize(load('shared_offsets.json'))
    rows = places_by_athlete(result)
    check(rows['r1']['possible_places'][0] <= 2 <= rows['r1']['possible_places'][1],
          'r1 possible places reflect joint feasible region')
    check(rows['r2']['place'] is None or rows['r2']['possible_places'][0] >= 2,
          'r2 cannot inherit an independently widened r1 interval')
    rels = relations_by_id(result)
    check(rels['ord-same-camera']['proven'] is True,
          'same-camera r1 before r2 is proven (offset cancels)')
    check(rels['ord-same-camera-reversed']['individually_possible'] is False,
          'reversed same-camera relation is impossible on its own')
    check(rels['ord-same-camera-reversed']['in_conflict'] is True,
          'impossible relation is reported in the conflict core')
    check(rels['ord-proven-cross']['proven'] is True,
          'a cross-camera relation can still be proven when bounds force it')


def test_individually_feasible_cycle_conflicts_jointly():
    print('each pair feasible alone, but the cycle needs one shared offset set')
    result = materialize(load('camera_cycle.json'))
    oc = result['order_checks']
    check(oc['all_hold'] is False, 'three-edge cycle cannot hold jointly')
    check(len(oc['conflict_ids']) == 3,
          'minimal conflict core names all three cycle relations')
    for row in oc['relations']:
        check(row['individually_possible'] is True, f"{row['id']} feasible alone")
        check(row['proven'] is False, f"{row['id']} not forced on its own")
        check(row['in_conflict'] is True, f"{row['id']} appears in the joint conflict")
    # Every athlete still gets a real possible-place range rather than a forced rank.
    for row in result['places']:
        check(row['possible_places'] == [1, 3], f"{row['athlete']} possible places [1,3]")


def test_minimal_core_drops_independent_failure():
    print('minimal core excludes relations not needed to keep infeasibility')
    doc = load('shared_offsets.json')
    doc['proposed_orderings'] = [r for r in doc['proposed_orderings']
                                 if r['id'] != 'ord-same-camera-reversed']
    oc = materialize(doc)['order_checks']
    wanted = {'ord-cycle-r3-r4', 'ord-cycle-r4-r5', 'ord-cycle-r5-r3'}
    check(oc['all_hold'] is False, 'cycle remains infeasible without the bad relation')
    check(set(oc['conflict_ids']) == wanted, 'core is exactly the three cycle edges')
    check(all(r['individually_possible'] for r in oc['relations']),
          'every remaining relation is individually feasible')


def test_cli_rejects_invalid_bundles():
    print('invalid input exits with status 2 without publishing')
    env = dict(__import__('os').environ)
    env['PYTHONPATH'] = str(ROOT)
    proc = subprocess.run([sys.executable, '-m', 'finishline', 'preview',
                           str(ROOT / 'examples' / 'invalid.json')],
                          cwd=ROOT, capture_output=True, text=True, env=env)
    check(proc.returncode == 2, 'invalid.json rejected with exit status 2')
    check(proc.stdout == '', 'no result payload on validation failure')


def main():
    tests = [test_legacy_outputs_unchanged,
             test_same_camera_offset_is_shared,
             test_individually_feasible_cycle_conflicts_jointly,
             test_minimal_core_drops_independent_failure,
             test_cli_rejects_invalid_bundles]
    for test in tests:
        test()
    print('\nall acceptance checks passed')


if __name__ == '__main__':
    main()
