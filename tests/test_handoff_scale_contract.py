"""Pre-upgrade contract tests for the finish-line evidence pipeline.

These tests are deliberately *not* derived by running the production code and
freezing its output.  The expected results in ``tests/expected/`` were computed
by hand from the raw columns, the half-open scale segments, and the lane
assignments.  The derivation for the paired fixtures is repeated below so a
reviewer can re-check it without touching ``finishline/``.

Coordinate model (from PROJECT_SPEC.md):

* a scale segment and a lane assignment cover the *half-open* pixel columns
  ``[start, end)``;
* an adjudication call covers the *inclusive* columns ``[first, last]``, so it
  is only readable when one single segment satisfies
  ``start <= first <= last < end``;
* a call resolves to an athlete only when one single lane assignment for the
  *same camera and lane* satisfies ``start <= first <= last < end``;
* a finish time is ``origin + (column - start) * period``, widened by +-error.

Hand computation for the fixtures
---------------------------------

Scales (camera a):  scale-a1 ``[0,80)``  origin 1100, period 10, error 3
                    scale-a2 ``[86,150)`` origin 2000, period 10, error 3
        (camera b):  scale-b1 ``[0,100)`` origin 1100, period 12, error 2

Identity handoff (camera a, lane 2): la2-old covers ``[0,12)`` -> r6;
la2 covers ``[12,150)`` -> r2.  The handoff sits at column 12, while the scale
break sits between 80 and 86, so the two boundaries do not coincide and a call
can be calibrated without being identified, or identified without being
calibrated, depending on where it falls.

Selected calls, camera a unless noted:

    call-r1         [10,10] -> 1100+10*10=1200 -+3         = [1197,1203]
    call-r6-old     [5,5]   -> 1100+5*10=1150 -+3          = [1147,1153]
    call-r2 aligned [12,14] -> lo 1100+12*10=1220-3=1217; hi 1100+14*10=1240+3=1243
    call-r2 straddle[10,14] -> lo 1100+10*10=1200-3=1197; hi 1243          (same scale, identity lost)
    call-r3 (cam b) [20,21] -> 1100+20*12=1340-2=1338 ; 1100+21*12=1352+2=1354
    call-a-edge-lo  [79,79] -> 1100+79*10=1890 -+3         = [1887,1893]  (scale-a1)
    call-a-edge-hi  [86,86] -> 2000+0 -+3                  = [1997,2003]  (scale-a2)
    call-a-gap      [80,80] -> column 80 is in neither segment          -> None
    call-a-break    [79,86] -> spans the break, never covered           -> None
    call-r4-gap     [83,84] -> inside the break                         -> no time (identity r4 kept)
    call-b-lane2    [30,30] -> camera b lane 2 has *no* assignment      -> time, no athlete

Expected places are then the interval arithmetic from ``places.py`` rendered
by hand: for an eligible athlete with a readable finish interval [lo, hi] the
possible places are ``[1 + #{other hi < lo}, #qualified - #{other lo > hi}]``;
an eligible athlete with no readable time spans ``[1, #qualified]``.

Aligned (times 1147/1197/1217/1338 + r4 unknown):
    r6 [1,2]  r1 [2,3]  r2 [3,4]  r3 [4,5]  r4 [1,5]
Straddled (r2 loses identity, so its 1197 lower bound leaves the pool; only
r1 1197, r3 1338, r6 1147 remain readable and 5 athletes are qualified):
    r6 [1,3]  r1 [2,4]  r3 [3,5]  r2 [1,5]  r4 [1,5]

The two fixtures differ *only* in the columns of ``call-r2``: aligned keeps it
inside ``la2`` (time and identity), straddled starts two columns earlier so the
call straddles the identity handoff with ``la2-old`` and loses identity while
keeping the same scale and a readable time.
"""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from finishline.cli import main as cli_main
from finishline.common import encode
from finishline.workflow import materialize

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / 'tests' / 'fixtures'
EXPECTED = ROOT / 'tests' / 'expected'


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def run_cli(argv):
    status = cli_main(argv)
    return status


class PairedFixtureTest(unittest.TestCase):
    def setUp(self):
        self.aligned = read_json(FIXTURES / 'handoff_aligned.json')
        self.straddled = read_json(FIXTURES / 'handoff_straddled.json')
        self.expected_aligned = read_json(EXPECTED / 'handoff_aligned.json')
        self.expected_straddled = read_json(EXPECTED / 'handoff_straddled.json')

    def test_pair_is_a_controlled_single_difference(self):
        """The pair must differ only in call-r2 columns, or it proves nothing."""
        a = json.loads(json.dumps(self.aligned))
        b = json.loads(json.dumps(self.straddled))
        for doc in (a, b):
            doc['calls'] = [c for c in doc['calls'] if c['id'] != 'call-r2']
        self.assertEqual(a, b)

        a2 = next(c for c in self.aligned['calls'] if c['id'] == 'call-r2')
        b2 = next(c for c in self.straddled['calls'] if c['id'] == 'call-r2')
        self.assertEqual(a2['columns'], [12, 14])
        self.assertEqual(b2['columns'], [10, 14])

    def test_aligned_matches_hand_computed_oracle(self):
        self.assertEqual(materialize(self.aligned), self.expected_aligned)

    def test_straddled_matches_hand_computed_oracle(self):
        self.assertEqual(materialize(self.straddled), self.expected_straddled)

    # --- the three fact classes -------------------------------------------
    def _call(self, result, call_id):
        return next(c for c in result['calls'] if c['id'] == call_id)

    def _place(self, result, athlete):
        return next(p for p in result['places'] if p['athlete'] == athlete)

    def test_both_time_and_identity(self):
        result = materialize(self.aligned)
        call = self._call(result, 'call-r2')
        self.assertEqual(call['athlete'], 'r2')
        self.assertEqual(call['assignment'], 'la2')
        self.assertEqual(call['finish_us'], [1217, 1243])
        place = self._place(result, 'r2')
        self.assertEqual(place['elapsed_us'], [217, 243])
        self.assertIsNone(place['place'])
        self.assertEqual(place['possible_places'], [3, 4])

    def test_identity_side_of_handoff_is_still_resolved(self):
        """The old side of the camera-a lane-2 handoff must bind r6, not r2."""
        result = materialize(self.aligned)
        call = self._call(result, 'call-r6-old')
        self.assertEqual(call['athlete'], 'r6')
        self.assertEqual(call['assignment'], 'la2-old')
        self.assertEqual(call['finish_us'], [1147, 1153])
        self.assertEqual(self._place(result, 'r6')['possible_places'], [1, 2])

    def test_time_without_identity(self):
        result = materialize(self.straddled)
        call = self._call(result, 'call-r2')
        self.assertIsNone(call['athlete'])
        self.assertIsNone(call['assignment'])
        self.assertEqual(call['finish_us'], [1197, 1243])  # time is still read
        place = self._place(result, 'r2')
        self.assertIsNone(place['call'])
        self.assertIsNone(place['elapsed_us'])
        # The unjudged athlete must NOT be dropped or narrowed.
        self.assertEqual(place['possible_places'], [1, 5])

    def test_identity_without_time(self):
        result = materialize(self.aligned)
        call = self._call(result, 'call-r4-gap')
        self.assertEqual(call['athlete'], 'r4')      # identity survives
        self.assertEqual(call['assignment'], 'la4')
        self.assertIsNone(call['finish_us'])         # no time outside the gap
        place = self._place(result, 'r4')
        self.assertEqual(place['call'], 'call-r4-gap')
        self.assertEqual(place['possible_places'], [1, 5])

    def test_place_consequences_flip_between_pair(self):
        """Losing identity on call-r2 widens r2 and shifts r1/r3/r6's intervals."""
        aligned = materialize(self.aligned)
        straddled = materialize(self.straddled)
        self.assertEqual(self._place(aligned, 'r2')['possible_places'], [3, 4])
        self.assertEqual(self._place(straddled, 'r2')['possible_places'], [1, 5])
        self.assertEqual(self._place(aligned, 'r1')['possible_places'], [2, 3])
        self.assertEqual(self._place(straddled, 'r1')['possible_places'], [2, 4])
        self.assertEqual(self._place(aligned, 'r3')['possible_places'], [4, 5])
        self.assertEqual(self._place(straddled, 'r3')['possible_places'], [3, 5])
        self.assertEqual(self._place(aligned, 'r6')['possible_places'], [1, 2])
        self.assertEqual(self._place(straddled, 'r6')['possible_places'], [1, 3])

    # --- the three named regressions --------------------------------------
    def test_no_cross_segment_interpolation(self):
        result = materialize(self.aligned)
        # A call that spans the break is never covered by one segment.
        self.assertIsNone(self._call(result, 'call-a-break')['finish_us'])
        self.assertIsNone(self._call(result, 'call-a-break')['scale'])
        # A column inside the break is not snapped onto either neighbour.
        self.assertIsNone(self._call(result, 'call-a-gap')['finish_us'])
        self.assertIsNone(self._call(result, 'call-a-gap')['scale'])
        # The boundary columns resolve to *different* segments, proving the
        # break is real: interpolation across it would yield one continuous
        # value instead of these two disjoint windows.
        lo = self._call(result, 'call-a-edge-lo')
        hi = self._call(result, 'call-a-edge-hi')
        self.assertEqual(lo['scale'], 'scale-a1')
        self.assertEqual(hi['scale'], 'scale-a2')
        self.assertEqual(lo['finish_us'], [1887, 1893])
        self.assertEqual(hi['finish_us'], [1997, 2003])
        # The windows are far apart; a linear/nearest extrapolation would put
        # column 80 or 83 inside a plausible finish time.
        self.assertGreater(hi['finish_us'][0], lo['finish_us'][1] + 100)

    def test_lane_number_alone_never_binds_identity(self):
        result = materialize(self.aligned)
        # camera b lane 2 exists only as lane 2 on camera a (r2); the time must
        # still be published without an athlete name.
        cross_camera = self._call(result, 'call-b-lane2')
        self.assertIsNone(cross_camera['athlete'])
        self.assertEqual(cross_camera['finish_us'], [1458, 1462])
        # camera b lane 1 is r3, not r1 (camera a lane 1). Lane number matching
        # would swap them.
        self.assertEqual(self._call(result, 'call-r3')['athlete'], 'r3')
        self.assertEqual(self._call(result, 'call-r1')['athlete'], 'r1')
        # The lane-2 handoff must bind by columns, not by lane number: the
        # aligned call leans on la2, while the old-side call leans on la2-old.
        self.assertEqual(self._call(result, 'call-r2')['assignment'], 'la2')
        self.assertEqual(self._call(result, 'call-r6-old')['assignment'], 'la2-old')

    def test_unjudged_athlete_stays_in_positions(self):
        for doc in (self.aligned, self.straddled):
            result = materialize(doc)
            qualified = [p['athlete'] for p in result['places'] if p['status'] == 'eligible']
            self.assertEqual(len(qualified), 5)
            for name in ('r4',):
                place = self._place(result, name)
                self.assertIsNone(place['elapsed_us'])
                self.assertEqual(place['possible_places'], [1, len(qualified)])
            # A dns athlete is still listed, but outside the placing pool.
            dns = self._place(result, 'r5')
            self.assertEqual(dns['status'], 'dns')
            self.assertIsNone(dns['possible_places'])

    def test_no_place_is_forced_inside_overlapping_bounds(self):
        result = materialize(self.aligned)
        for place in result['places']:
            if place['possible_places'] and place['possible_places'][0] != place['possible_places'][1]:
                self.assertIsNone(place['place'])


class PublishReplayTest(unittest.TestCase):
    def setUp(self):
        self.aligned = FIXTURES / 'handoff_aligned.json'
        self.straddled = FIXTURES / 'handoff_straddled.json'
        self.tmp = tempfile.TemporaryDirectory()
        self.archive = Path(self.tmp.name) / 'ledger.sqlite'

    def tearDown(self):
        self.tmp.cleanup()

    def test_publish_show_source_replay_roundtrip(self):
        _capture(['publish', str(self.aligned), str(self.archive), 'a'])
        _capture(['publish', str(self.straddled), str(self.archive), 'b'])

        expected_a = materialize(read_json(self.aligned))
        expected_b = materialize(read_json(self.straddled))

        # show must return the published result, unchanged on reread
        self.assertEqual(_capture(['show', str(self.archive), 'a']), encode(expected_a))
        self.assertEqual(_capture(['show', str(self.archive), 'b']), encode(expected_b))
        # source must return the frozen input, unchanged on reread
        self.assertEqual(_capture(['source', str(self.archive), 'a']), encode(read_json(self.aligned)))
        # replay recomputes from the frozen source and matches the stored result
        _capture(['replay', str(self.archive), 'a'])
        _capture(['replay', str(self.archive), 'b'])

    def test_publish_is_immutable_per_edition(self):
        _capture(['publish', str(self.aligned), str(self.archive), 'a'])
        self.assertEqual(run_cli(['publish', str(self.straddled), str(self.archive), 'a']), 2)

    def test_archived_result_carries_both_fact_classes(self):
        _capture(['publish', str(self.straddled), str(self.archive), 'b'])
        result = json.loads(_capture(['show', str(self.archive), 'b']))
        by_id = {c['id']: c for c in result['calls']}
        # time without identity
        self.assertEqual(by_id['call-r2']['finish_us'], [1197, 1243])
        self.assertIsNone(by_id['call-r2']['athlete'])
        # identity without time survives the archive round trip too
        self.assertEqual(by_id['call-r4-gap']['athlete'], 'r4')
        self.assertIsNone(by_id['call-r4-gap']['finish_us'])

    def test_archive_tamper_is_detected(self):
        _capture(['publish', str(self.aligned), str(self.archive), 'a'])
        with sqlite3.connect(self.archive) as db:
            db.execute("UPDATE editions SET result=replace(result,'\"r2\"','\"r3\"') WHERE name='a'")
        self.assertEqual(run_cli(['show', str(self.archive), 'a']), 2)


def _capture(argv):
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        status = cli_main(argv)
    if status != 0:
        raise AssertionError(f'command failed with status {status}: {argv}')
    return buf.getvalue().strip()


if __name__ == '__main__':
    unittest.main()
