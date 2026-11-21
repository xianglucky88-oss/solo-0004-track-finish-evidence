from .common import disjoint, number, require, span, unique


class Scale:
    def __init__(self, segments):
        self.by_camera = {}
        self.cameras = set()
        for key, row in sorted(unique(segments).items()):
            lo, hi = span(row['columns'], 'calibrated columns')
            step = number(row['us_per_column'], 'column period')
            require(step > 0, 'column period must be positive')
            camera = row['camera']
            self.cameras.add(camera)
            self.by_camera.setdefault(camera, []).append(
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


def read_offsets(rows, scale):
    """Parse verification evidence bounding one unknown offset per camera."""
    offsets = {}
    for key, row in sorted(unique(rows).items()):
        camera = row['camera']
        require(camera in scale.cameras, f'camera offset evidence names unknown camera: {key}')
        lower = number(row['min_offset_us'], 'camera offset lower bound', minimum=None)
        upper = number(row['max_offset_us'], 'camera offset upper bound', minimum=None)
        require(lower <= upper, f'camera offset bounds reversed: {key}')
        require(camera not in offsets, f'duplicate camera offset evidence for camera {camera}')
        offsets[camera] = (lower, upper)
    return offsets
