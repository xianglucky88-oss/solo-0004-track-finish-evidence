from .calibration import Scale
from .common import number, unique
from .judging import read_calls, read_lanes
from .places import build_intervals, publish_places
from .qualification import read_qualification

DESCRIPTION = 'Resolve track finish evidence without forcing places from overlapping time bounds.'


def materialize(doc):
    entries = unique(doc['entries'])
    facts = read_calls(doc['calls'], read_lanes(doc['lane_assignments'], entries), Scale(doc['scales']))
    start = number(doc['start_us'], 'start')
    result = {'heat': doc['heat'], 'calls': facts}
    if 'qualification' in doc:
        _, _, intervals = build_intervals(entries, facts, start)
        qualification = read_qualification(doc, entries, facts, intervals)
        groups = {row['id']: list(row['athletes']) for row in doc['qualification']['groups']}
        result['places'] = publish_places(entries, facts, start, groups)
        result['qualification'] = qualification
    else:
        result['places'] = publish_places(entries, facts, start)
    return result
