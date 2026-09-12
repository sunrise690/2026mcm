"""第三问证书补扫：在剩余单元覆盖集合上规划完整多测站路线。

候选点预先转换为 Python 整数位集，束搜索优化行走和扫描总时间。
只有覆盖当前全部缺口的完整计划可作为规划结果；始终有贪心完整
计划保底，固定状态预算保证种子复跑不受机器负载影响。所有完成证书仍由父类逐格验证。
"""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path
import time

import numpy as np

_EFFICIENT_PATH = Path(__file__).with_name("baseline_efficient.py")
_spec = importlib.util.spec_from_file_location("_q3_efficient_for_planned", _EFFICIENT_PATH)
if _spec is None:
    raise ImportError(f"不能加载补扫候选: {_EFFICIENT_PATH}")
_efficient = importlib.util.module_from_spec(_spec)
exec(compile(_EFFICIENT_PATH.read_bytes(), str(_EFFICIENT_PATH), "exec"), _efficient.__dict__)


def _mask_integer(mask):
    return int.from_bytes(np.packbits(mask, bitorder="little").tobytes(), "little")


class PlannedCoverageCertificate(_efficient.EfficientCoverageCertificate):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.planning_calls = 0
        self.last_plan = []
        self.last_plan_cost_seconds = None
        self.last_plan_expanded_states = 0
        self.last_plan_search_seconds = 0.0
        self.cached_plan = []
        self.cached_unknown_channels = None
        self.beam_width = 32
        self.branch_limit = 16
        self.max_depth = 10
        self.max_expanded_states = 320

    def _candidate_points(self, current, remaining, fallback):
        if len(remaining) > 180:
            pool = remaining[np.linspace(0, len(remaining) - 1, 180, dtype=int)]
        else:
            pool = remaining.copy()
        angles = np.linspace(0.0, 2.0 * math.pi, 32, endpoint=False)
        unit = np.column_stack((np.cos(angles), np.sin(angles)))
        rings = np.vstack([unit * radius for radius in (1000.0, 1300.0, 1500.0, 1650.0)])
        delta = current - pool
        distance = np.linalg.norm(delta, axis=1)
        projected = pool + delta * np.minimum(
            1.0, (self.safe_radius - 1e-4) / np.maximum(distance, 1e-12)
        )[:, None]
        points = np.vstack((current[None, :], fallback[None, :],
                            np.mean(remaining, axis=0)[None, :], pool, rings, projected))
        norms = np.linalg.norm(points, axis=1)
        outside = norms > self.radius - 1e-6
        points[outside] *= ((self.radius - 1e-6) / norms[outside])[:, None]
        masks = np.sum((points[:, None, :] - remaining[None, :, :]) ** 2, axis=2) <= self._safe_r2
        gains = np.count_nonzero(masks, axis=1)
        travels = np.linalg.norm(points - current, axis=1)
        ranked = np.argsort(gains / (travels / 5.0 + 36.0))[-10:]
        extra = []
        whole = self._nearest_cluster_probe(current, remaining)
        if whole is not None:
            extra.append(whole)
        for index in ranked:
            q = self._nearest_cluster_probe(current, remaining[masks[index]])
            if q is not None:
                extra.append(q)
        if extra:
            points = np.vstack((points, np.asarray(extra)))
        # 仅把确实覆盖缺口的点加入位集；相同覆盖可以保留不同位置供行走优化。
        rounded = np.round(points, 6)
        _, indices = np.unique(rounded, axis=0, return_index=True)
        points = points[np.sort(indices)]
        masks = np.sum((points[:, None, :] - remaining[None, :, :]) ** 2, axis=2) <= self._safe_r2
        keep = np.any(masks, axis=1)
        points, masks = points[keep], masks[keep]
        union = np.any(masks, axis=0)
        if not np.all(union):
            # 候选采样不可遗漏小缺口：必要时补入每个未覆盖单元的圆内投影中心。
            missing = remaining[~union].copy()
            norms = np.linalg.norm(missing, axis=1)
            outside = norms > self.radius - 1e-6
            missing[outside] *= ((self.radius - 1e-6) / norms[outside])[:, None]
            more = np.sum((missing[:, None, :] - remaining[None, :, :]) ** 2, axis=2) <= self._safe_r2
            points, masks = np.vstack((points, missing)), np.vstack((masks, more))
        if not np.all(np.any(masks, axis=0)):
            raise RuntimeError("补扫候选点不能覆盖全部残余证书单元")
        return points, [_mask_integer(mask) for mask in masks]

    def _planned_probe(self, current, channels, fallback):
        started = time.monotonic()
        remaining = self.centers[self.unresolved(channels)]
        points, coverage = self._candidate_points(current, remaining, fallback)
        full = (1 << len(remaining)) - 1
        scan_seconds = 6.0 * len(channels)
        travel = np.linalg.norm(points[:, None, :] - points[None, :, :], axis=2) / 5.0
        initial_travel = np.linalg.norm(points - current, axis=1) / 5.0
        costs = travel + scan_seconds
        initial_costs = initial_travel + scan_seconds
        max_gain = max(mask.bit_count() for mask in coverage)
        count = len(coverage)
        expanded = 0

        def greedy(variant):
            uncovered = full
            position = -1
            total = 0.0
            route = []
            while uncovered:
                row = initial_costs if position == -1 else costs[position]
                gain = [(uncovered & mask).bit_count() for mask in coverage]
                options = [i for i, g in enumerate(gain) if g]
                finishing = [i for i in options if gain[i] == uncovered.bit_count()]
                if finishing:
                    nxt = min(finishing, key=lambda i: float(row[i]))
                elif variant == 0:
                    nxt = max(options, key=lambda i: (gain[i] / max(1.0, float(row[i])), gain[i]))
                elif variant == 1:
                    nxt = max(options, key=lambda i: (gain[i] / max(1.0, float(row[i])) ** 0.45, gain[i]))
                else:
                    nxt = max(options, key=lambda i: (gain[i], -float(row[i])))
                total += float(row[nxt])
                route.append(nxt)
                uncovered &= ~coverage[nxt]
                position = nxt
            return total, route

        best_cost, best_route = min((greedy(i) for i in range(3)), key=lambda x: x[0])
        # 每个状态：(已花时间, 未覆盖位集, 最后测站, 路线)。
        beam = [(0.0, full, -1, tuple())]
        for depth in range(self.max_depth):
            if not beam or expanded >= self.max_expanded_states:
                break
            next_states = {}
            for spent, uncovered, position, route in beam:
                if expanded >= self.max_expanded_states:
                    break
                expanded += 1
                row = initial_costs if position == -1 else costs[position]
                left = uncovered.bit_count()
                gains = [(uncovered & mask).bit_count() for mask in coverage]
                feasible = [i for i in range(count) if gains[i] and spent + float(row[i]) < best_cost]
                # 完成一步不能被单位收益排序挤出分支。
                finishing = [i for i in feasible if gains[i] == left]
                for i in finishing:
                    candidate_cost = spent + float(row[i])
                    if candidate_cost < best_cost:
                        best_cost, best_route = candidate_cost, list(route) + [i]
                ranked = sorted(feasible, key=lambda i: (
                    gains[i] / max(1.0, float(row[i])), gains[i], -float(row[i])
                ), reverse=True)[:self.branch_limit]
                # 保留覆盖最多的候选，避免仅按短期比值忽略远处大簇。
                ranked = set(ranked)
                ranked.update(sorted(feasible, key=lambda i: (gains[i], -float(row[i])), reverse=True)[:4])
                for i in sorted(ranked):
                    new_left = uncovered & ~coverage[i]
                    if not new_left:
                        continue
                    new_spent = spent + float(row[i])
                    optimistic_scans = math.ceil(new_left.bit_count() / max_gain)
                    lower_bound = new_spent + optimistic_scans * scan_seconds
                    if lower_bound >= best_cost:
                        continue
                    new_route = route + (i,)
                    key = (new_left, i)
                    old = next_states.get(key)
                    if old is None or new_spent < old[0]:
                        next_states[key] = (new_spent, new_left, i, new_route)
            if not next_states:
                break
            # 排序估计用当前最大覆盖能力和最低到达费用；仅用于保留束宽。
            ranked_states = []
            for state in next_states.values():
                spent, uncovered, position, route = state
                remaining_gain = [(uncovered & mask).bit_count() for mask in coverage]
                maximum = max(remaining_gain)
                minimum_visits = math.ceil(uncovered.bit_count() / maximum)
                available = [i for i, g in enumerate(remaining_gain) if g]
                min_arrival = min(float(travel[position, i]) for i in available)
                estimate = spent + minimum_visits * scan_seconds + min_arrival
                # 额外的覆盖比例惩罚仅为束排序启发项，不影响完整计划验证。
                estimate += 40.0 * uncovered.bit_count() / len(remaining)
                ranked_states.append((estimate, state))
            ranked_states.sort(key=lambda entry: (entry[0], entry[1][1].bit_count(), entry[1][0]))
            beam = [state for _, state in ranked_states[:self.beam_width]]
        union = 0
        for i in best_route:
            union |= coverage[i]
        if union != full:
            raise RuntimeError("补扫规划返回的路线未覆盖全部残余单元")
        self.planning_calls += 1
        self.last_plan = [points[i].tolist() for i in best_route]
        self.last_plan_cost_seconds = float(best_cost)
        self.last_plan_expanded_states = expanded
        self.last_plan_search_seconds = time.monotonic() - started
        self.cached_plan = [points[i].copy() for i in best_route[1:]]
        self.cached_unknown_channels = tuple(channels)
        return points[best_route[0]].copy()

    def best_probe(self, current, channels, max_candidates=240):
        channels = list(channels)
        if self.is_complete(channels):
            return None
        current = np.asarray(current, dtype=float)
        # 未发现新频道时兑现已规划的完整路线，避免滚动重算导致往返小洞。
        if self.cached_unknown_channels == tuple(channels):
            while self.cached_plan:
                point = self.cached_plan.pop(0)
                if self.gain(point, channels) > 0:
                    return point
        self.cached_plan = []
        fallback = super().best_probe(current, channels, max_candidates)
        return self._planned_probe(current, channels, fallback)

    def summary(self, channels):
        result = super().summary(channels)
        result.update({
            "probe_selection": "complete_residual_coverage_beam_route_with_bitsets",
            "planning_calls": self.planning_calls,
            "last_plan": self.last_plan,
            "last_plan_estimated_seconds": self.last_plan_cost_seconds,
            "last_plan_expanded_states": self.last_plan_expanded_states,
            "last_plan_search_seconds": self.last_plan_search_seconds,
            "beam_width": self.beam_width,
            "beam_depth_limit": self.max_depth,
            "max_expanded_states": self.max_expanded_states,
        })
        return result


class Q3ParticleController(_efficient.Q3ParticleController):
    def __init__(self, client):
        super().__init__(client)
        self.certificate = PlannedCoverageCertificate()


def run_q3_particle(client):
    return Q3ParticleController(client).run()
