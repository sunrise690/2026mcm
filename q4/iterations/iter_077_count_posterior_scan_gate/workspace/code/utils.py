"""计算几何、统计与仿真公共函数。"""
from params import *
from pathlib import Path
import json
import math
import platform
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def set_all_seeds(seed):
    np.random.seed(seed)


def write_json(path, data):
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def runtime_meta(seed, run_id):
    return {"seed": int(seed), "run_id": run_id, "python": platform.python_version(), "numpy": np.__version__}


def unit_vector_deg(angle):
    angle_rad = math.radians(angle % 360.0)
    return np.array([math.cos(angle_rad), math.sin(angle_rad)], dtype=float)


def bearing_deg(origin, target):
    delta = np.asarray(target, float) - np.asarray(origin, float)
    return math.degrees(math.atan2(delta[1], delta[0])) % 360.0


def angular_error_deg(a, b):
    return (a - b + 180.0) % 360.0 - 180.0


def clip_halfplane(poly, normal, offset, tol=GEOM_TOL_M):
    """保留 normal dot x <= offset 的闭半平面。"""
    if len(poly) == 0:
        return poly
    output = []
    cyclic = np.vstack([poly[1:], poly[:1]])
    for point_a, point_b in zip(poly, cyclic):
        value_a = float(np.dot(normal, point_a) - offset)
        value_b = float(np.dot(normal, point_b) - offset)
        inside_a, inside_b = value_a <= tol, value_b <= tol
        if inside_a:
            output.append(point_a)
        if inside_a != inside_b:
            fraction = value_a / (value_a - value_b)
            output.append(point_a + fraction * (point_b - point_a))
    return np.asarray(output, dtype=float)


def regular_polygon(center, radius, sides, outer_bound=False):
    shift = math.pi / sides if outer_bound else 0.0
    polygon_radius = radius / math.cos(math.pi / sides) if outer_bound else radius
    angles = np.linspace(0.0, 2.0 * math.pi, sides, endpoint=False) + shift
    return np.column_stack([center[0] + polygon_radius * np.cos(angles), center[1] + polygon_radius * np.sin(angles)])


def intersect_convex(subject, clipper):
    poly = np.asarray(subject, float)
    clip = np.asarray(clipper, float)
    for point_a, point_b in zip(clip, np.vstack([clip[1:], clip[:1]])):
        edge = point_b - point_a
        normal = np.array([edge[1], -edge[0]])
        poly = clip_halfplane(poly, normal, float(np.dot(normal, point_a)))
        if len(poly) == 0:
            break
    return poly


def bearing_wedge(poly, sensor, measured_deg, error_deg=BEARING_ERROR_BOUND_DEG):
    """用两个角界半平面和前向半平面执行 set_membership intersect。"""
    sensor = np.asarray(sensor, float)
    low = unit_vector_deg(measured_deg - error_deg)
    high = unit_vector_deg(measured_deg + error_deg)
    center = unit_vector_deg(measured_deg)
    normal_low = np.array([low[1], -low[0]])
    normal_high = np.array([-high[1], high[0]])
    poly = clip_halfplane(poly, normal_low, float(np.dot(normal_low, sensor)))
    poly = clip_halfplane(poly, normal_high, float(np.dot(normal_high, sensor)))
    return clip_halfplane(poly, -center, float(np.dot(-center, sensor)))


def convex_hull(points):
    points = sorted(set(map(tuple, np.asarray(points, float))))
    if len(points) <= 1:
        return np.asarray(points, float)

    def cross(origin, point_a, point_b):
        return (point_a[0] - origin[0]) * (point_b[1] - origin[1]) - (point_a[1] - origin[1]) * (point_b[0] - origin[0])

    lower = []
    for point in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return np.asarray(lower[:-1] + upper[:-1], float)


def rotating_calipers(poly):
    """以对踵点旋转卡壳计算凸多边形直径。"""
    points = convex_hull(poly)
    size = len(points)
    if size < 2:
        return 0.0, [0, 0]
    if size == 2:
        return float(np.linalg.norm(points[1] - points[0])), [0, 1]
    opposite = 1
    best_distance, best_pair = -1.0, (0, 1)
    for index in range(size):
        next_index = (index + 1) % size
        while True:
            next_opposite = (opposite + 1) % size
            current_area = abs(np.cross(points[next_index] - points[index], points[opposite] - points[index]))
            next_area = abs(np.cross(points[next_index] - points[index], points[next_opposite] - points[index]))
            if next_area > current_area + GEOM_TOL_M:
                opposite = next_opposite
            else:
                break
        for candidate in (opposite, (opposite + 1) % size):
            distance = float(np.linalg.norm(points[index] - points[candidate]))
            if distance > best_distance:
                best_distance, best_pair = distance, (index, candidate)
    return best_distance, list(best_pair)


def _circle_two(point_a, point_b):
    center = (point_a + point_b) / 2.0
    return center, float(np.linalg.norm(point_a - center))


def _circle_three(point_a, point_b, point_c):
    denominator = 2.0 * np.cross(point_b - point_a, point_c - point_a)
    if abs(denominator) < GEOM_TOL_M:
        return None
    aa, bb, cc = np.dot(point_a, point_a), np.dot(point_b, point_b), np.dot(point_c, point_c)
    center = np.array([(aa * (point_b[1] - point_c[1]) + bb * (point_c[1] - point_a[1]) + cc * (point_a[1] - point_b[1])) / denominator,
                       (aa * (point_c[0] - point_b[0]) + bb * (point_a[0] - point_c[0]) + cc * (point_b[0] - point_a[0])) / denominator])
    return center, float(np.linalg.norm(point_a - center))


def minimum_enclosing_circle(points):
    """按字典序增量枚举至多三点支撑圆。"""
    points = np.asarray(sorted(map(tuple, np.asarray(points, float))), float)
    if len(points) == 0:
        return np.zeros(2), 0.0
    center, radius = points[0].copy(), 0.0
    for first, point_a in enumerate(points):
        if np.linalg.norm(point_a - center) <= radius + GEOM_TOL_M:
            continue
        center, radius = point_a.copy(), 0.0
        for second in range(first):
            point_b = points[second]
            if np.linalg.norm(point_b - center) <= radius + GEOM_TOL_M:
                continue
            center, radius = _circle_two(point_a, point_b)
            for third in range(second):
                point_c = points[third]
                if np.linalg.norm(point_c - center) <= radius + GEOM_TOL_M:
                    continue
                circle = _circle_three(point_a, point_b, point_c)
                if circle is not None:
                    center, radius = circle
    return np.asarray(center), float(radius)


def bootstrap(cases, seed, replicates=BOOTSTRAP_REPLICATES):
    rng = np.random.default_rng(seed)
    values = np.array([[case["cleared_count"], case["source_count"], case["virtual_time_s"]] for case in cases], float)
    samples = []
    for _ in range(replicates):
        totals = values[rng.integers(0, len(values), len(values))].sum(axis=0)
        samples.append([totals[0] / totals[1], totals[2] / totals[0]])
    interval = np.quantile(np.asarray(samples), [0.025, 0.975], axis=0)
    totals = values.sum(axis=0)
    return {"clear_ratio": totals[0] / totals[1], "average_clear_time_s": totals[2] / totals[0],
            "clear_ratio_ci95": interval[:, 0].tolist(), "average_clear_time_ci95_s": interval[:, 1].tolist(),
            "bootstrap_replicates": replicates, "resample_unit": "case"}


def validate_constraints(results, constraints):
    violations = []
    for key, (lower, upper, description) in constraints.items():
        values = np.atleast_1d(results.get(key, np.nan)).astype(float).ravel()
        invalid = values[(~np.isfinite(values)) | (values < lower) | (values > upper)]
        for value in invalid[:5]:
            violations.append(f"{description}: {value} not in [{lower},{upper}]")
    print(f"[constraints] PASS={not violations} n_violations={len(violations)}")
    for violation in violations[:5]:
        print("  " + violation)
    return not violations
