from .common import disjoint, number, require, span, unique


class Scale:
    def __init__(self, segments):
        self.by_camera = {}
        for key, row in sorted(unique(segments).items()):
            lo, hi = span(row['columns'], 'calibrated columns')
            step = number(row['us_per_column'], 'column period')
            require(step > 0, 'column period must be positive')
            timebase = row.get('timebase')
            require(timebase is None or (isinstance(timebase, str) and bool(timebase.strip())),
                    f'invalid scale timebase: {timebase!r}')
            self.by_camera.setdefault(row['camera'], []).append(
                (lo, hi, key, number(row['origin_us'], 'origin'), step,
                 number(row['error_us'], 'scale error'), timebase))
        for camera, rows in self.by_camera.items():
            disjoint(rows, 'camera scale segments')
            bases = {row[6] for row in rows}
            require(len(bases) == 1, f'camera {camera} mixes incomparable time bases')

    def locate(self, camera, columns):
        lo, hi = columns
        # The columns are inclusive. Never extrapolate through a segment break.
        for left, right, key, origin, step, error, timebase in self.by_camera.get(camera, ()):
            if left <= lo <= hi < right:
                return (origin + (lo - left) * step - error, origin + (hi - left) * step + error), key, timebase
        return None, None, None
