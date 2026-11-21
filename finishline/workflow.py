from .calibration import Scale
from .common import number, require, unique
from .judging import read_calls, read_lanes
from .places import publish_places
from .rankings import publish_rankings, read_firings, read_starts

DESCRIPTION = 'Resolve track finish evidence without forcing places from overlapping time bounds.'


def materialize(doc):
    entries = unique(doc['entries'])
    facts = read_calls(doc['calls'], read_lanes(doc['lane_assignments'], entries), Scale(doc['scales']))
    if 'start_us' in doc:
        # A heat with one common firing keeps the frozen single-ranking result.
        require('starts' not in doc, 'bundle must use either start_us or starts, not both')
        result = {'heat': doc['heat'], 'calls': facts,
                  'places': publish_places(entries, facts, number(doc['start_us'], 'start'))}
    else:
        require('starts' in doc, 'bundle needs start_us or starts')
        starts = read_starts(doc['starts'])
        arrival, net = publish_rankings(entries, facts, starts, read_firings(entries, starts))
        result = {'heat': doc['heat'], 'calls': facts,
                  'arrival_places': arrival, 'net_places': net}
    return result
