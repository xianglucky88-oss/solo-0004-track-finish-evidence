from .calibration import Scale, read_offsets
from .common import number, require, unique
from .constraints import build_finish_system
from .judging import read_calls, read_lanes
from .ordering import check_relations, read_relations
from .places import publish_places, qualified_intervals

DESCRIPTION = 'Resolve track finish evidence without forcing places from overlapping time bounds.'


def materialize(doc):
    entries = unique(doc['entries'])
    scale = Scale(doc['scales'])
    lanes = read_lanes(doc['lane_assignments'], entries)
    facts = read_calls(doc['calls'], lanes, scale)
    offsets = read_offsets(doc['camera_offsets'], scale) if 'camera_offsets' in doc else {}
    used_cameras = {fact['camera'] for fact in facts if fact['finish_us'] is not None}
    if offsets:
        missing = sorted(used_cameras - offsets.keys())
        require(not missing, f'camera offset evidence missing for camera(s): {", ".join(missing)}')
    start = number(doc['start_us'], 'start')
    result = {'heat': doc['heat'], 'calls': facts,
              'places': publish_places(entries, facts, start, offsets)}
    if 'proposed_orderings' in doc:
        _, _, intervals = qualified_intervals(entries, facts, start)
        system, node = build_finish_system(intervals, offsets, start)
        relations = read_relations(doc['proposed_orderings'], entries)
        result['order_checks'] = check_relations(relations, system, node)
    return result
