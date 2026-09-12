"""第三问覆盖补扫几何优化：保留完整清除证书和原控制流程。

唯一策略变化是证书补扫选点，利用缺口集合的包围圆将测站向当前位置
投影；所有新点仍按同样的单元半对角修正逐项核验覆盖收益。
"""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import numpy as np

_COMPLETE_PATH = Path(__file__).with_name("baseline_complete.py")
_spec = importlib.util.spec_from_file_location("_q3_complete_for_efficient", _COMPLETE_PATH)
if _spec is None:
    raise ImportError(f"不能加载完整清除控制器: {_COMPLETE_PATH}")
_complete = importlib.util.module_from_spec(_spec)
exec(compile(_COMPLETE_PATH.read_bytes(), str(_COMPLETE_PATH), "exec"), _complete.__dict__)


def _enclosing_circle(points):
    """固定随机顺序的增量包围圆；最终以全部输入点重新扩大半径。

    即使近共线浮点情形产生非最小圆，最后的最大距离核验也使圆保持
    保守包围性。该函数只处理公开无信号证书的网格点。
    """
    points = np.asarray(points, dtype=float)
    if len(points) == 0:
        return np.zeros(2), 0.0
    order = np.random.default_rng(714025).permutation(len(points))
    p = points[order]
    cx, cy, r2 = float(p[0, 0]), float(p[0, 1]), 0.0

    def outside(q, x, y, radius_squared):
        return (float(q[0]) - x) ** 2 + (float(q[1]) - y) ** 2 > radius_squared + 1e-7

    for i in range(1, len(p)):
        if not outside(p[i], cx, cy, r2):
            continue
        ax, ay = map(float, p[i])
        cx, cy, r2 = ax, ay, 0.0
        for j in range(i):
            if not outside(p[j], cx, cy, r2):
                continue
            bx, by = map(float, p[j])
            cx, cy = (ax + bx) / 2.0, (ay + by) / 2.0
            r2 = (ax - cx) ** 2 + (ay - cy) ** 2
            for k in range(j):
                if not outside(p[k], cx, cy, r2):
                    continue
                dx, dy = map(float, p[k])
                ux, uy = bx - ax, by - ay
                vx, vy = dx - ax, dy - ay
                det = 2.0 * (ux * vy - uy * vx)
                if abs(det) < 1e-10:
                    pairs = ((ax, ay, bx, by), (ax, ay, dx, dy), (bx, by, dx, dy))
                    qa, qb, qc, qd = max(pairs, key=lambda q: (q[0] - q[2]) ** 2 + (q[1] - q[3]) ** 2)
                    cx, cy = (qa + qc) / 2.0, (qb + qd) / 2.0
                    r2 = max((ax - cx) ** 2 + (ay - cy) ** 2,
                             (bx - cx) ** 2 + (by - cy) ** 2,
                             (dx - cx) ** 2 + (dy - cy) ** 2)
                else:
                    uu, vv = ux * ux + uy * uy, vx * vx + vy * vy
                    cx = ax + (vy * uu - uy * vv) / det
                    cy = ay + (ux * vv - vx * uu) / det
                    r2 = (ax - cx) ** 2 + (ay - cy) ** 2
    center = np.array([cx, cy], dtype=float)
    radius = float(np.max(np.linalg.norm(points - center, axis=1)))
    return center, radius + 1e-7


class EfficientCoverageCertificate(_complete.ContinuousCoverageCertificate):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.projected_probe_count = 0
        self.compared_probe_count = 0

    def _nearest_cluster_probe(self, current, cluster):
        if len(cluster) == 0:
            return None
        center, radius = _enclosing_circle(cluster)
        allowed = self.safe_radius - radius - 1e-5
        if allowed < 0:
            return None
        delta = np.asarray(current, dtype=float) - center
        distance = float(np.linalg.norm(delta))
        if distance <= allowed:
            point = np.asarray(current, dtype=float).copy()
        else:
            point = center + delta * (allowed / max(distance, 1e-15))
        norm = float(np.linalg.norm(point))
        if norm > self.radius - 1e-6:
            point *= (self.radius - 1e-6) / norm
        # 投影回圆域后再复核，不能把可行性建立在近似计算上。
        if np.all(np.sum((cluster - point) ** 2, axis=1) <= self._safe_r2):
            return point
        return None

    def best_probe(self, current, channels, max_candidates=240):
        channels = list(channels)
        remaining = self.centers[self.unresolved(channels)]
        if len(remaining) == 0:
            return None
        current = np.asarray(current, dtype=float)
        original = super().best_probe(current, channels, max_candidates=max_candidates)
        # 先保留完整策略实际选点。额外候选仅来自同一组尚未排除单元。
        if len(remaining) > 144:
            pool = remaining[np.linspace(0, len(remaining) - 1, 144, dtype=int)]
        else:
            pool = remaining.copy()
        angles = np.linspace(0.0, 2.0 * math.pi, 24, endpoint=False)
        ring = np.column_stack((np.cos(angles), np.sin(angles))) * 1450.0
        seeds = np.vstack((original[None, :], np.mean(remaining, axis=0)[None, :], pool, ring))
        norms = np.linalg.norm(seeds, axis=1)
        outside = norms > self.radius - 1e-6
        seeds[outside] *= ((self.radius - 1e-6) / norms[outside])[:, None]
        seed_masks = np.sum((seeds[:, None, :] - remaining[None, :, :]) ** 2, axis=2) <= self._safe_r2
        gains = np.count_nonzero(seed_masks, axis=1)
        travels = np.linalg.norm(seeds - current, axis=1)
        costs = travels / 5.0 + 6.0 * len(channels)
        scores = gains / np.maximum(1.0, costs)
        # 基线推荐点、收益最高与单位费用收益最高的少数簇做包围圆优化。
        selected = set([0])
        selected.update(map(int, np.argsort(scores)[-7:]))
        selected.update(map(int, np.argsort(gains)[-4:]))
        extra = []
        whole = self._nearest_cluster_probe(current, remaining)
        if whole is not None:
            extra.append(whole)
        for index in sorted(selected):
            point = self._nearest_cluster_probe(current, remaining[seed_masks[index]])
            if point is not None:
                extra.append(point)
        # 单元级最近可测点，能够处理狭小的圆周缺口且无需走到边界中心。
        delta = current - pool
        distance = np.linalg.norm(delta, axis=1)
        radii = self.safe_radius - 1e-5
        projected = pool + delta * np.minimum(1.0, radii / np.maximum(distance, 1e-12))[:, None]
        candidates = np.vstack((seeds, projected, np.asarray(extra).reshape(-1, 2)))
        norms = np.linalg.norm(candidates, axis=1)
        outside = norms > self.radius - 1e-6
        candidates[outside] *= ((self.radius - 1e-6) / norms[outside])[:, None]
        # 不对坐标取整，以免抹去沿保证接收圆内缩的数值裕量。
        best = None
        finish = None
        for point in candidates:
            gain = int(np.count_nonzero(np.sum((remaining - point) ** 2, axis=1) <= self._safe_r2))
            if gain == 0:
                continue
            travel = float(np.linalg.norm(point - current))
            cost = travel / 5.0 + 6.0 * len(channels)
            if gain == len(remaining) and (finish is None or travel < finish[0]):
                finish = (travel, point.copy())
            record = (gain / max(1.0, cost), gain, -travel, point.copy())
            if best is None or record[:3] > best[:3]:
                best = record
        chosen = finish[1] if finish is not None else best[3]
        self.compared_probe_count += 1
        if float(np.linalg.norm(chosen - original)) > 1e-5:
            self.projected_probe_count += 1
        return chosen

    def summary(self, channels):
        result = super().summary(channels)
        result.update({
            "probe_selection": "original_candidates_plus_nearest_certified_cluster_projections",
            "compared_probe_count": self.compared_probe_count,
            "changed_probe_count": self.projected_probe_count,
        })
        return result


class Q3ParticleController(_complete.Q3ParticleController):
    def __init__(self, client):
        super().__init__(client)
        self.certificate = EfficientCoverageCertificate()


def run_q3_particle(client):
    return Q3ParticleController(client).run()
