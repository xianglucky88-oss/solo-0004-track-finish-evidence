from .arbitration import build_report, read_arbitrations
from .calibration import Scale
from .common import number, unique
from .judging import read_calls, read_lanes
from .places import measured_intervals, place_ranges, publish_places

DESCRIPTION = 'Resolve track finish evidence without forcing places from overlapping time bounds.'


def materialize(doc):
    start = number(doc['start_us'], 'start')
    entries = unique(doc['entries'])
    facts = read_calls(doc['calls'], read_lanes(doc['lane_assignments'], entries), Scale(doc['scales']))
    result = {'heat': doc['heat'], 'calls': facts, 'places': publish_places(entries, facts, start)}
    prepared = read_arbitrations(doc, entries, facts, start)
    if prepared is not None:
        qualified = {key for key, row in entries.items() if row['status'] == 'eligible'}
        intervals = measured_intervals(facts, qualified, start)
        result['arbitration'] = build_report(prepared, intervals, place_ranges(intervals, qualified), qualified, start)
    return result
