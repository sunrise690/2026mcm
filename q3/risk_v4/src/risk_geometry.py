"""仅由公共阴性测站计算漏源风险上界，并按剩余概率质量选择短程补扫。"""
import math

import numpy as np
from scipy.optimize import minimize

REGION = 1800.0
RMIN = 1000.0
RMAX = 1500.0
# 外圆积分包络同时覆盖公开练习生成器的 1770 m 均匀源域。
DENSITY_FACTOR = (1800.0 / 1770.0) ** 2
RADIUS_LIKELIHOOD_MARGIN = 1.0 / 500000001.0 + 1e-12


def missing_risk(known, miss):
    if known >= 16:
        return 0.0
    if known < 10:
        return 1.0
    w = min(1.0, max(0.0, float(miss)))
    odds = sum(math.comb(known + j, known) * w ** j for j in range(1, 17 - known))
    return odds / (1.0 + odds)


def allowed_miss(known, epsilon):
    if not 10 <= known < 16:
        return 0.0
    lo, hi = 0.0, 1.0
    for _ in range(52):
        mid = (lo + hi) / 2
        if missing_risk(known, mid) <= epsilon:
            lo = mid
        else:
            hi = mid
    return lo


class RiskOracle:
    def __init__(self):
        self.cache = {}

    def bounds(self, stations, known, epsilon, tolerance=None, max_depth=13):
        sites = np.unique(np.asarray(stations, float).reshape(-1, 2), axis=0)
        key = (tuple(map(tuple, sites)), known, epsilon, tolerance, max_depth)
        if key in self.cache:
            return self.cache[key]
        if known >= 16:
            return {'accepted': True, 'risk_upper': 0.0, 'mass_upper': 0.0, 'cells_checked': 0, 'reason': 'maximum_count'}
        if known < 10 or not len(sites):
            return {'accepted': False, 'risk_upper': 1.0, 'mass_upper': 1.0, 'cells_checked': 0, 'reason': 'insufficient_discovery'}
        target = allowed_miss(known, epsilon)
        centers = np.zeros((1, 2))
        half = REGION
        total_lo = total_hi = 0.0
        checked = 0
        reason = 'integration_budget'
        lo = hi = 0.0
        for depth in range(max_depth + 1):
            near_origin = np.maximum(np.abs(centers) - half, 0.0)
            centers = centers[np.sum(near_origin ** 2, axis=1) <= REGION ** 2]
            if not len(centers):
                lo, hi = total_lo, total_hi
                reason = 'resolved'
                break
            checked += len(centers)
            d = np.sqrt(np.min(np.sum((centers[:, None] - sites[None]) ** 2, axis=2), axis=1))
            delta = math.sqrt(2.0) * half
            upper = np.clip((d + delta - RMIN) / (RMAX - RMIN), 0.0, 1.0)
            lower = np.clip((d - delta - RMIN) / (RMAX - RMIN), 0.0, 1.0)
            inside = np.sum((np.abs(centers) + half) ** 2, axis=1) <= REGION ** 2
            lower[~inside] = 0.0
            area = 4 * half ** 2 * DENSITY_FACTOR / (np.pi * REGION ** 2)
            lower *= area
            upper *= area
            lo, hi = total_lo + float(lower.sum()), total_hi + float(upper.sum())
            if tolerance is None and (hi <= target or lo > target):
                reason = 'threshold_separated'
                break
            if tolerance is not None and hi - lo <= tolerance:
                reason = 'tolerance'
                break
            uncertain = upper - lower > 1e-18
            total_lo += float(lower[~uncertain].sum())
            total_hi += float(upper[~uncertain].sum())
            centers = centers[uncertain]
            if len(centers) > 35000:
                break
            half /= 2
            offsets = half * np.array([[-1, -1], [-1, 1], [1, -1], [1, 1]])
            centers = (centers[:, None] + offsets).reshape(-1, 2)
        # 离散微米半径的 CDF 与连续均匀先验最多相差一个概率格。
        hi = min(1.0, hi + RADIUS_LIKELIHOOD_MARGIN)
        upper_risk = missing_risk(known, hi)
        record = {'accepted': upper_risk <= epsilon, 'risk_upper': upper_risk,
                  'envelope_risk_lower': missing_risk(known, lo),
                  'mass_lower': min(1.0, lo), 'mass_upper': min(1.0, hi),
                  'cells_checked': checked, 'depth': depth, 'reason': reason,
                  'epsilon': epsilon, 'density_factor': DENSITY_FACTOR,
                  'radius_likelihood_margin': RADIUS_LIKELIHOOD_MARGIN,
                  'scope': 'conditional probability under the documented independent-source practice model'}
        self.cache[key] = record
        return record


class RiskPlanner:
    def __init__(self, radial=48, angular=192):
        radii = REGION * np.sqrt((np.arange(radial) + 0.5) / radial)
        angles = 2 * np.pi * (np.arange(angular) + 0.5) / angular
        self.points = (radii[:, None, None] * np.stack((np.cos(angles), np.sin(angles)), axis=1)[None]).reshape(-1, 2)
        self.total = len(self.points)
        self.station_key = None
        self.prior_distance = None
        self.calls = 0
        self.projected = 0

    def residual(self, stations):
        sites = np.asarray(stations, float).reshape(-1, 2)
        key = tuple(map(tuple, sites))
        if key != self.station_key:
            self.prior_distance = np.sqrt(np.min(np.sum((self.points[:, None] - sites[None]) ** 2, axis=2), axis=1))
            self.station_key = key
        keep = self.prior_distance > RMIN
        return self.points[keep], np.minimum(RMAX, self.prior_distance[keep])

    def propose(self, stations, current, known, epsilon, scan_seconds=48.0, project=True):
        self.calls += 1
        pts, prior = self.residual(stations)
        if not len(pts):
            return None
        current = np.asarray(current, float)
        weights = (prior - RMIN) / (RMAX - RMIN)
        old_mass = float(weights.sum()) * DENSITY_FACTOR / self.total
        target = 0.65 * allowed_miss(known, epsilon)
        indices = np.linspace(0, len(pts) - 1, min(120, len(pts)), dtype=int)
        near = np.argsort(np.sum((pts - current) ** 2, axis=1))[:12]
        angles = np.linspace(0, 2 * np.pi, 36, endpoint=False)
        rings = np.vstack([r * np.column_stack((np.cos(angles), np.sin(angles))) for r in (1000, 1350, 1600)])
        seeds = np.vstack((pts[indices], pts[near], np.average(pts, axis=0, weights=weights), rings))
        dist = np.linalg.norm(seeds[:, None] - pts[None], axis=2)
        masses = np.clip((np.minimum(dist, prior) - RMIN) / 500, 0, 1).sum(axis=1) * DENSITY_FACTOR / self.total
        travel = np.linalg.norm(seeds - current, axis=1)
        costs = travel / 5 + scan_seconds
        finishing = np.where(masses <= target)[0]
        if len(finishing):
            best_index = finishing[np.argmin(travel[finishing])]
            best = seeds[best_index].copy()
            if project and target > 0:
                def mass_gradient(x):
                    delta = x * 1000 - pts
                    d = np.linalg.norm(delta, axis=1)
                    active = (d < prior) & (d > RMIN) & (d < RMAX)
                    mass = float(np.clip((np.minimum(d, prior) - RMIN) / 500, 0, 1).sum()) * DENSITY_FACTOR / self.total
                    gradient = np.sum(delta[active] / d[active, None], axis=0) * (2 * DENSITY_FACTOR / self.total)
                    return mass, gradient

                def objective(x):
                    delta = x - current / 1000
                    return float(delta @ delta), 2 * delta

                for index in finishing[np.argsort(travel[finishing])[:2]]:
                    result = minimize(objective, seeds[index] / 1000, jac=True, method='SLSQP',
                                      constraints={'type': 'ineq',
                                                   'fun': lambda x: 1 - mass_gradient(x)[0] / target,
                                                   'jac': lambda x: -mass_gradient(x)[1] / target},
                                      bounds=[(-1.8, 1.8), (-1.8, 1.8)],
                                      options={'maxiter': 65, 'ftol': 1e-9})
                    q = result.x * 1000
                    if (np.all(np.isfinite(q)) and mass_gradient(result.x)[0] <= target * 1.001
                            and np.linalg.norm(q - current) < np.linalg.norm(best - current)):
                        best = q.copy()
                        self.projected += 1
            return best
        gain = np.maximum(0.0, old_mass - masses)
        utility = gain / costs
        return seeds[int(np.argmax(utility))].copy()
