from .common import disjoint, number, require, span, unique


class Scale:
    def __init__(self, segments):
        self.by_camera = {}
        for key, row in sorted(unique(segments).items()):
            lo, hi = span(row['columns'], 'calibrated columns')
            step = number(row['us_per_column'], 'column period')
            require(step > 0, 'column period must be positive')
            self.by_camera.setdefault(row['camera'], []).append(
                (lo, hi, key, number(row['origin_us'], 'origin'), step, number(row['error_us'], 'scale error')))
        for rows in self.by_camera.values():
            disjoint(rows, 'camera scale segments')

    def locate(self, camera, columns):
        lo, hi = columns
        # The columns are inclusive. Never extrapolate through a segment break.
        for left, right, key, origin, step, error in self.by_camera.get(camera, ()):
            if left <= lo <= hi < right:
                return (origin + (lo - left) * step - error, origin + (hi - left) * step + error), key
        return None, None
