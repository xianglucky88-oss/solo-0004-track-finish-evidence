from .calibration import Scale
from .common import number, unique
from .judging import read_calls, read_lanes
from .places import publish_places

DESCRIPTION = 'Resolve track finish evidence without forcing places from overlapping time bounds.'


def materialize(doc):
    entries = unique(doc['entries'])
    facts = read_calls(doc['calls'], read_lanes(doc['lane_assignments'], entries), Scale(doc['scales']))
    return {'heat': doc['heat'], 'calls': facts, 'places': publish_places(entries, facts, number(doc['start_us'], 'start'))}
