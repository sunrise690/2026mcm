"""闭圆盘上的连续覆盖检查，以及经检查的残余覆盖测站投影。"""
from itertools import combinations
import math

import numpy as np
from scipy.optimize import minimize
from scipy.spatial import ConvexHull, QhullError

DOMAIN_RADIUS = 1800.0
RECEIVE_RADIUS = 1000.0
MARGIN = 0.02
PLANNING_RADIUS = 995.0


def critical_points(stations, radius=DOMAIN_RADIUS):
    """列举受限最近点 Voronoi 单元的顶点和圆弧极值，允许冗余点。

    每个单元内，距离平方是凸函数；边上最大值在端点，圆弧上
    最大值在端点或测站的径向反点。全枚举避免 Qhull 共线退化。
    """
    sites = np.unique(np.asarray(stations, dtype=float).reshape(-1, 2), axis=0) / radius
    if not len(sites):
        return np.array([[radius, 0.0]])
    points = [np.zeros(2), np.array([1.0, 0.0]), np.array([-1.0, 0.0])]
    norm = np.linalg.norm(sites, axis=1)
    points.extend(-sites[norm > 1e-14] / norm[norm > 1e-14, None])
    for i, j in combinations(range(len(sites)), 2):
        normal = sites[j] - sites[i]
        nn = float(normal @ normal)
        if nn < 1e-26:
            continue
        rhs = float((sites[j] @ sites[j] - sites[i] @ sites[i]) / 2.0)
        midpoint = normal * (rhs / nn)
        h2 = 1.0 - float(midpoint @ midpoint)
        if h2 >= -1e-12:
            side = np.array([-normal[1], normal[0]]) * math.sqrt(max(0.0, h2) / nn)
            points.extend((midpoint + side, midpoint - side))
    triples = np.array(list(combinations(range(len(sites)), 3)), dtype=int)
    if len(triples):
        a = sites[triples[:, 0]]
        u = sites[triples[:, 1]] - a
        v = sites[triples[:, 2]] - a
        det = u[:, 0] * v[:, 1] - u[:, 1] * v[:, 0]
        good = np.abs(det) > 1e-12
        a, u, v, det = a[good], u[good], v[good], det[good]
        uu, vv = np.sum(u * u, axis=1) / 2, np.sum(v * v, axis=1) / 2
        offset = np.column_stack((uu * v[:, 1] - vv * u[:, 1],
                                  vv * u[:, 0] - uu * v[:, 0])) / det[:, None]
        center = a + offset
        points.extend(center[np.sum(center * center, axis=1) <= 1.0 + 1e-11])
    pts = np.asarray(points, dtype=float)
    # 投影只纠正圆周交点的浮点舍入，不把圆外三角形中心当作域内候选。
    n = np.linalg.norm(pts, axis=1)
    pts *= np.minimum(1.0, 1.0 / np.maximum(n, 1e-30))[:, None]
    return pts * radius


def covering_radius(stations, radius=DOMAIN_RADIUS):
    sites = np.asarray(stations, dtype=float).reshape(-1, 2)
    if not len(sites):
        return float('inf'), np.array([radius, 0.0])
    pts = critical_points(sites, radius)
    nearest2 = np.min(np.sum((pts[:, None, :] - sites[None, :, :]) ** 2, axis=2), axis=1)
    index = int(np.argmax(nearest2))
    return float(np.sqrt(nearest2[index])), pts[index].copy()


def verify_cells(stations, radius=DOMAIN_RADIUS, receive_radius=RECEIVE_RADIUS,
                 max_depth=19):
    """独立充分证书：递归闭方格的距离上界，保留所有圆周相交单元。"""
    sites = np.asarray(stations, float).reshape(-1, 2)
    if not len(sites):
        return False, 0
    centers = np.zeros((1, 2))
    half = float(radius)
    checked = 0
    for _ in range(max_depth + 1):
        nearest_origin = np.maximum(np.abs(centers) - half, 0.0)
        centers = centers[np.sum(nearest_origin ** 2, axis=1) <= radius ** 2 + 1e-8]
        if not len(centers):
            return True, checked
        checked += len(centers)
        distance = np.sqrt(np.min(np.sum((centers[:, None, :] - sites[None, :, :]) ** 2, axis=2), axis=1))
        unresolved = distance + math.sqrt(2) * half > receive_radius - 1e-6
        centers = centers[unresolved]
        if not len(centers):
            return True, checked
        if len(centers) > 100000:
            return False, checked
        half /= 2
        offsets = half * np.array([[-1, -1], [-1, 1], [1, -1], [1, 1]])
        centers = (centers[:, None, :] + offsets).reshape(-1, 2)
    return False, checked


class DiskCertificate:
    """证书仅吸收逐频道已接受的 no_signal；不依赖源数或空间先验。"""
    def __init__(self, radius=DOMAIN_RADIUS, receive_radius=RECEIVE_RADIUS):
        self.radius = float(radius)
        self.receive_radius = float(receive_radius)
        self.stations = {ch: [] for ch in range(1, 21)}
        self._cache = {}

    def add_no_signal(self, point, channel):
        point = np.asarray(point, dtype=float)
        if point.shape != (2,) or not np.all(np.isfinite(point)):
            raise ValueError('测站必须是有限二维坐标')
        if channel not in self.stations:
            raise ValueError('非法频道')
        p = (float(point[0]), float(point[1]))
        if p not in self.stations[channel]:
            self.stations[channel].append(p)

    def report(self, channels):
        records = {}
        for ch in channels:
            key = tuple(sorted(self.stations[ch]))
            if key not in self._cache:
                value, point = covering_radius(key, self.radius)
                possible = value <= self.receive_radius - MARGIN
                checked, cells = verify_cells(key, self.radius, self.receive_radius) if possible else (False, 0)
                self._cache[key] = {
                    'covering_radius_m': value if math.isfinite(value) else None,
                    'witness': point.tolist(),
                    'station_count': len(key),
                    'covered': bool(possible and checked),
                    'independent_closed_cells_checked': cells,
                }
            records[str(ch)] = self._cache[key]
        return {'method': 'clipped_voronoi_candidates_plus_independent_adaptive_closed_cells',
                'domain_radius_m': self.radius, 'receive_radius_m': self.receive_radius,
                'safety_margin_m': MARGIN, 'channels': records,
                'complete': all(row['covered'] for row in records.values())}


class ResidualPlanner:
    """网格提出覆盖簇，凸透镜投影缩短绕行，连续检查修补新产生的缺口。"""
    def __init__(self, spacing=100.0):
        axis = np.arange(-DOMAIN_RADIUS, DOMAIN_RADIUS + spacing / 2, spacing)
        xx, yy = np.meshgrid(axis, axis)
        grid = np.column_stack((xx.ravel(), yy.ravel()))
        grid = grid[np.sum(grid * grid, axis=1) < DOMAIN_RADIUS ** 2]
        angle = np.linspace(0, 2 * np.pi, 240, endpoint=False)
        ring = DOMAIN_RADIUS * np.column_stack((np.cos(angle), np.sin(angle)))
        self.grid = np.vstack((grid, ring))
        self.calls = 0
        self.exchange_steps = 0

    @staticmethod
    def _remaining(sites, points):
        if not len(sites):
            return points
        d2 = np.min(np.sum((points[:, None, :] - sites[None, :, :]) ** 2, axis=2), axis=1)
        return points[d2 > (RECEIVE_RADIUS - MARGIN) ** 2]

    @staticmethod
    def _hull(points):
        if len(points) > 3:
            try:
                return points[ConvexHull(points).vertices]
            except QhullError:
                pass
        return points

    def project_cluster(self, points, start, end=None):
        """约束 ||q-w||<=r 的交集是凸集；最终逐点验证求解可行性。"""
        points = np.asarray(points, dtype=float).reshape(-1, 2)
        if not len(points):
            return None
        support = self._hull(points) / 1000.0
        a = np.asarray(start, float) / 1000.0
        b = None if end is None else np.asarray(end, float) / 1000.0
        r = PLANNING_RADIUS / 1000.0

        def objective(x):
            if b is None:
                delta = x - a
                return float(delta @ delta), 2 * delta
            da, db = x - a, x - b
            na, nb = max(float(np.linalg.norm(da)), 1e-10), max(float(np.linalg.norm(db)), 1e-10)
            return na + nb, da / na + db / nb

        def constraint(x):
            return r * r - np.sum((x - support) ** 2, axis=1)

        result = minimize(objective, support.mean(axis=0), jac=True, method='SLSQP',
                          constraints={'type': 'ineq', 'fun': constraint,
                                       'jac': lambda x: -2 * (x - support)},
                          options={'maxiter': 75, 'ftol': 1e-10})
        q = result.x * 1000.0
        if np.all(np.isfinite(q)) and np.max(np.linalg.norm(points - q, axis=1)) <= RECEIVE_RADIUS - MARGIN:
            return q
        return None

    def one_station(self, sites, start, end=None):
        sites = np.asarray(sites, float).reshape(-1, 2)
        radius, witness = covering_radius(sites)
        if radius <= RECEIVE_RADIUS - MARGIN:
            return None
        remaining = self._remaining(sites, np.vstack((self.grid, critical_points(sites))))
        remaining = self._hull(remaining)
        for _ in range(14):
            q = self.project_cluster(remaining, start, end)
            if q is None:
                return None
            radius, witness = covering_radius(np.vstack((sites, q)))
            if radius <= RECEIVE_RADIUS - MARGIN:
                return q
            remaining = self._hull(np.vstack((remaining, witness)))
            self.exchange_steps += 1
        return None

    def propose(self, sites, start, end=None, scan_seconds=48.0):
        sites = np.asarray(sites, float).reshape(-1, 2)
        self.calls += 1
        radius, witness = covering_radius(sites)
        if radius <= RECEIVE_RADIUS - MARGIN:
            return None
        whole = self.one_station(sites, start, end)
        if whole is not None:
            return whole
        remaining = self._remaining(sites, np.vstack((self.grid, critical_points(sites), witness)))
        indices = np.linspace(0, len(remaining) - 1, min(40, len(remaining)), dtype=int)
        seeds = np.vstack((remaining[indices], remaining.mean(axis=0), witness))
        a = np.asarray(start, float)
        b = None if end is None else np.asarray(end, float)

        def cost(q):
            travel = float(np.linalg.norm(q - a))
            if b is not None:
                travel += float(np.linalg.norm(q - b) - np.linalg.norm(a - b))
            return max(0.0, travel) / 5.0 + scan_seconds

        masks = np.sum((seeds[:, None, :] - remaining[None, :, :]) ** 2, axis=2) <= PLANNING_RADIUS ** 2
        gain = masks.sum(axis=1)
        order = np.argsort(gain / np.array([cost(q) for q in seeds]))[-5:]
        candidates = list(seeds[order])
        for i in order:
            q = self.project_cluster(remaining[masks[i]], a, b)
            if q is not None:
                candidates.append(q)
        # 每个非空缺口至少有自身作为可覆盖测站，提供严格的推进回退。
        return max(candidates, key=lambda q: (
            int(np.count_nonzero(np.sum((remaining - q) ** 2, axis=1) <= (RECEIVE_RADIUS - MARGIN) ** 2)) / cost(q),
            -cost(q))).copy()
