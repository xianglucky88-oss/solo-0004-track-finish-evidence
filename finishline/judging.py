from .common import disjoint, integer, require, scalar, span, unique


def read_lanes(rows, entries):
    lanes = {}
    for key, row in sorted(unique(rows).items()):
        require(row['athlete'] in entries, f'unknown athlete in lane assignment: {key}')
        lane = integer(row['lane'], 'lane', 1)
        lanes.setdefault((row['camera'], lane), []).append((*span(row['columns'], 'lane columns'), key, row['athlete']))
    for rows in lanes.values():
        disjoint(rows, 'lane assignments')
    return lanes


def read_calls(rows, lanes, scale):
    facts = []
    for key, row in sorted(unique(rows).items()):
        a, b = row['columns']
        lo, hi = integer(a, 'first column', 0), integer(b, 'last column', 0)
        require(lo <= hi, 'reversed adjudication columns')
        camera, lane = row['camera'], integer(row['lane'], 'lane', 1)
        identity = next(((key, athlete) for x, y, key, athlete in lanes.get((camera, lane), ()) if x <= lo <= hi < y), None)
        bounds, segment, timebase = scale.locate(camera, (lo, hi))
        facts.append({'id': key, 'camera': camera, 'lane': lane, 'columns': [lo, hi],
                      'athlete': identity[1] if identity else None, 'assignment': identity[0] if identity else None,
                      'scale': segment, 'timebase': timebase,
                      'finish_us': [scalar(v) for v in bounds] if bounds else None})
    return facts
