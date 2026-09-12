"""v360 Q4：三点分散普查 + 清源位置级联发现 + 混合后验补漏。

使用前先在官方模拟器界面进入“问题4演练测试”或“问题4正式测试”，
等倒计时结束、接口开放后运行本程序。程序只使用官方接口返回值，不
读取离线仿真的隐藏真值。

示例：
    python code/live_q4.py --robot-id 202613001114 --case-code practice-001

正式测试时建议显式给出案例编码，便于论文表格回填：
    python code/live_q4.py --robot-id 202613001114 --case-code Q4-official-1 --log figures/live_q4_official_1.jsonl
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np

from live_runner import SimulatorClient
from sim_engine import (
    Q4_OPT_CENTRAL_RADII,
    Q4_OPT_TAIL_RADII,
    Q4_QUICK_CLEAR_MAX_INSERTION_M,
    Q4_QUICK_CLEAR_MAX_MEC_M,
    Q4_QUICK_CLEAR_PER_POINT,
    Q4_SOURCE_COUNT_MAX,
    Q4_CORRIDOR_REMEASURE_AFTER_FAILS,
    Q4_CORRIDOR_REMEASURE_BUDGET,
    Q4_CORRIDOR_FAR_MASS_INWARD_THRESHOLD,
    _nearest_neighbor_order,
    _q4_probe_can_hit,
    _route_points_optimized,
    _two_opt_order,
    belief_polygon,
    locate_from_directions,
    minimum_enclosing_circle,
    new_beliefs,
    q4_census_points_opt21,
    q4_census_stages_opt21,
    q4_census_master_route_opt21,
    q4_select_rescan_channels,
    q4_joint_mec,
    q4_no_signal_probe_value,
    update_belief,
)
from utils import unit_vector_deg


VERSION = "v391-full-posterior"
DENSE_SWITCH_MIN = 14
DENSE_SWITCH_AFTER_INDEX = 2
DENSE_CONFIRM_POINTS = 1
MAX_RESCUE_SITES = 16
RESCUE_MIN_SEPARATION_M = 300.0
TARGETED_POST_CLEAR_RESCUE = True
TARGETED_POST_CLEAR_BUDGET = 4
TARGETED_BASE_TRIGGER_MIN_POSITIVE = 0
TARGETED_FORCE_MIN_POSITIVE = 0
TARGETED_FORCE_MAX_BUDGET = 1
TARGETED_RESCUE_REQUIRE_PRIOR_FIND = False
TARGETED_RESCUE_MIN_STOP_COUNT = 1
TARGETED_RESCUE_TRAVEL_PENALTY = 0.00015
TARGETED_BREAK_ON_EMPTY = True
TARGETED_REQUIRED_MIN_POSITIVE = 10
TARGETED_LOW_COUNT_TRAVEL_PENALTY = 0.00015
TARGETED_AFTER_FIND_TRAVEL_PENALTY = 0.00015
TARGETED_LOW_COUNT_MAX_EMPTY = 99
TARGETED_EMPTY_STREAK_STOP = 4
GUARD_MIN_POSITIVE = 99
FAR_CROSS_MIN_PROJECTION_M = 0.0
FAR_CROSS_FORWARD_M = 400.0
FAR_CROSS_LATERAL_M = 100.0
FAR_CROSS_TRY_BOTH = False
CORRIDOR_REMEASURE_BUDGET = 1
CENSUS_ROUTE_MODE = "two_ring14"
CENSUS_SINGLE_RING_RADIUS_M = 1400.0
CENSUS_SINGLE_RING_POINTS = 12
MAX_RESCANS_PER_CENSUS_POINT = 3
FORCE_SECOND_BEARING_RESCAN = True
FORCE_SECOND_BEARING_MIN_SEP_M = 300.0
THIRD_BEARING_MIN_POSITIVE = 12
QUICK_CLEAR_PER_POINT = Q4_QUICK_CLEAR_PER_POINT
QUICK_CLEAR_MAX_INSERTION_M = Q4_QUICK_CLEAR_MAX_INSERTION_M
OPPORTUNISTIC_LS_INSERTION_M = 120.0
ZERO_MOVE_MIN_SEPARATION_M = 220.0
ZERO_MOVE_MIN_VALUE = 0.55
ZERO_MOVE_MIN_JOINT_RADIUS_M = 150.0
ZERO_MOVE_MIN_EXPECTED_CROSS_DEG = 8.0
ONE_BEARING_HOMING = False
ONE_BEARING_HOMING_STEP_M = 400.0
ONE_BEARING_HOMING_MAX_STEPS = 5
ONE_BEARING_BRACKET_SPACING_M = 36.0
ADAPTIVE_TAIL_PROBES = False
MASTER_INNER_RADIUS_M = 700.0
MASTER_OUTER_RADIUS_M = 1600.0
MASTER_INNER_POINTS = 7
MASTER_INNER_ORDER_MODE = "spread"
LOW_K14_SWITCH_TO_CLEAR = False
Q4_FAST_RING_RADIUS_M = 800.0
Q4_RESCAN_MIN_SEPARATION_M = 1200.0
Q4_SPEED_RING_RADIUS_M = 1400.0
OUTWARD_RESCUE_BUDGET = 2
OUTWARD_RESCUE_MIN_RADIUS_M = 1050.0
OUTWARD_RESCUE_STEP_M = 650.0
OUTWARD_RESCUE_SECOND_STEP_M = 650.0
OUTWARD_RESCUE_MIN_ANGLE_DEG = 55.0
STATE_TAIL_RING_RADIUS_M = 2100.0
CURRENT_PROFILE = "speed320"


def configure_profile(name: str) -> None:
    """Select a tested operating point without exposing tuning constants to users."""
    global CURRENT_PROFILE, DENSE_SWITCH_MIN, DENSE_SWITCH_AFTER_INDEX
    global MAX_RESCUE_SITES, TARGETED_POST_CLEAR_RESCUE
    global TARGETED_RESCUE_REQUIRE_PRIOR_FIND, TARGETED_RESCUE_MIN_STOP_COUNT
    global TARGETED_RESCUE_TRAVEL_PENALTY, GUARD_MIN_POSITIVE
    global FAR_CROSS_MIN_PROJECTION_M, FAR_CROSS_FORWARD_M, FAR_CROSS_LATERAL_M
    global CORRIDOR_REMEASURE_BUDGET, MAX_RESCANS_PER_CENSUS_POINT
    global MASTER_INNER_RADIUS_M, MASTER_OUTER_RADIUS_M, MASTER_INNER_ORDER_MODE
    CURRENT_PROFILE = name
    if name == "safe":
        DENSE_SWITCH_MIN = 10
        DENSE_SWITCH_AFTER_INDEX = 7
        MAX_RESCUE_SITES = 14
        TARGETED_POST_CLEAR_RESCUE = True
        TARGETED_RESCUE_REQUIRE_PRIOR_FIND = True
        TARGETED_RESCUE_MIN_STOP_COUNT = 12
        TARGETED_RESCUE_TRAVEL_PENALTY = 0.0008
        GUARD_MIN_POSITIVE = 99
        FAR_CROSS_MIN_PROJECTION_M = 0.0
        FAR_CROSS_FORWARD_M = 400.0
        FAR_CROSS_LATERAL_M = 100.0
        CORRIDOR_REMEASURE_BUDGET = 1
        MAX_RESCANS_PER_CENSUS_POINT = 6
        MASTER_INNER_RADIUS_M = 1000.0
        MASTER_OUTER_RADIUS_M = 1700.0
        MASTER_INNER_ORDER_MODE = "sequential"


def _fast_q4_census_points() -> list[np.ndarray]:
    """沿用 v52 第三问的快速首轮：中心点加三个等角外环点。"""
    points = [np.zeros(2, dtype=float)]
    for angle_deg in (0.0, 120.0, 240.0):
        angle = math.radians(angle_deg)
        points.append(Q4_FAST_RING_RADIUS_M * np.asarray([math.cos(angle), math.sin(angle)]))
    return points


def _fast_q4_rescue_points() -> list[np.ndarray]:
    """快速首轮后的南北两个后验补扫点，减少单侧漏检。"""
    return [np.asarray([0.0, -1200.0], dtype=float),
            np.asarray([0.0, 1200.0], dtype=float)]


def _speed_q4_census_points() -> list[np.ndarray]:
    """400 秒目标实验布局：中心 + 1400 m 十二点环。"""
    points = [np.zeros(2, dtype=float)]
    for angle_deg in np.arange(0.0, 360.0, 30.0):
        angle = math.radians(float(angle_deg))
        points.append(Q4_SPEED_RING_RADIUS_M * np.asarray([math.cos(angle), math.sin(angle)]))
    return points


def _adaptive_q4_census_points() -> list[np.ndarray]:
    """认证21点本身的13+8重排；不会混入未认证的1400m环。"""
    first, rescue = q4_census_stages_opt21()
    return [np.asarray(p, float) for p in np.vstack([first, rescue])]


def _measure_live(client: SimulatorClient, beliefs: dict, point: np.ndarray, channel: int) -> dict:
    body = client.measure(float(point[0]), float(point[1]), channel)
    client.current_position_m = np.asarray(point, float)
    client.current_channel = channel
    if "virtual_time_s" in body:
        client.current_virtual_time_s = float(body["virtual_time_s"])
    event = {
        "position_m": np.asarray(point, float),
        "response": body.get("measure_result"),
        "svd_deg": body.get("svd_deg"),
    }
    update_belief(beliefs[channel], event, directional=True)
    return body


def _clear_live(client: SimulatorClient, beliefs: dict, point: np.ndarray, channel: int,
                candidate_type: str = "corridor") -> dict:
    body = client.clear(float(point[0]), float(point[1]), channel)
    client.current_position_m = np.asarray(point, float)
    if "virtual_time_s" in body:
        client.current_virtual_time_s = float(body["virtual_time_s"])
    raw_result = body.get("clear_result")
    event = {
        "position_m": np.asarray(point, float),
        "response": "cleared" if raw_result == "success" else "no_target",
        "svd_deg": None,
        "candidate_type": candidate_type,
    }
    update_belief(beliefs[channel], event, directional=True)
    return body


def _try_clear_live(client: SimulatorClient, beliefs: dict, channel: int, point: np.ndarray,
                    poly: np.ndarray | None = None) -> bool:
    belief = beliefs[channel]
    if not _q4_probe_can_hit(belief, point, poly=poly):
        return False
    body = _clear_live(client, beliefs, point, channel)
    return body.get("clear_result") == "success"


def _clear_corridor_live(client: SimulatorClient, beliefs: dict, channel: int,
                         remeasure_budget: int | None = None) -> bool:
    """严格走廊兜底 + 远段顺序优化 + 失败后同点机会复测。

    正确性仍由原来的±1°清除走廊覆盖保证。新增动作只改变访问顺序，
    并在连续若干次失败clear后原地补一次/measure；若复测失败仍继续
    原保守走廊，因此不会因为启发式失败而漏清。
    """
    belief = beliefs[channel]
    if remeasure_budget is None:
        remeasure_budget = CORRIDOR_REMEASURE_BUDGET
    if belief["status"] == "cleared" or not belief.get("directions"):
        return belief["status"] == "cleared"

    # A single bearing already points almost exactly toward the source. Walk in
    # long measured steps along that ray. A forward bearing means the source is
    # still ahead; a backward bearing or a lost directional signal brackets it
    # inside the last step. The certified corridor below remains the fallback.
    if (ONE_BEARING_HOMING and len(belief.get("directions", [])) == 1
            and not belief.get("_one_bearing_homing_done", False)):
        belief["_one_bearing_homing_done"] = True
        obs = belief["directions"][-1]
        anchor = np.asarray(obs["sensor"], float)
        heading = unit_vector_deg(float(obs["measured_deg"]))
        for _ in range(ONE_BEARING_HOMING_MAX_STEPS):
            q = anchor + ONE_BEARING_HOMING_STEP_M * heading
            body = _measure_live(client, beliefs, q, channel)
            result = body.get("measure_result")
            if result == "near":
                cb = _clear_live(client, beliefs, q, channel, candidate_type="one_bearing_homing_near")
                if cb.get("clear_result") == "success":
                    return True
                break
            if result == "direction":
                new_heading = unit_vector_deg(float(body["svd_deg"]))
                if float(np.dot(new_heading, heading)) < 0.0:
                    steps = np.arange(0.0, ONE_BEARING_HOMING_STEP_M + 1e-9,
                                      ONE_BEARING_BRACKET_SPACING_M)
                    for s in steps:
                        p = q + float(s) * new_heading
                        cb = _clear_live(client, beliefs, p, channel,
                                         candidate_type="one_bearing_reverse_bracket")
                        if cb.get("clear_result") == "success":
                            return True
                    break
                anchor = q
                heading = new_heading
                continue
            if result == "no_signal":
                steps = np.arange(ONE_BEARING_HOMING_STEP_M, -1e-9,
                                  -ONE_BEARING_BRACKET_SPACING_M)
                for s in steps:
                    p = anchor + float(s) * heading
                    cb = _clear_live(client, beliefs, p, channel,
                                     candidate_type="one_bearing_lost_bracket")
                    if cb.get("clear_result") == "success":
                        return True
                break
            break
        if belief.get("status") == "cleared":
            return True

    # v69: before committing to a long one-bearing corridor, exploit the current
    # robot position as a zero-movement information probe.  This is allowed at
    # most once per channel and only when geometry says the point is informative
    # and sufficiently separated from all existing observations.
    if len(belief.get("directions", [])) == 1 and not belief.get("_zero_move_rescan_done", False):
        here = np.asarray(client.current_position_m, float)
        observed = [np.asarray(o["sensor"], float) for o in belief.get("directions", [])]
        observed += [np.asarray(q, float) for q in belief.get("no_signal_points", [])]
        observed += [np.asarray(q, float) for q in belief.get("near_points", [])]
        separation = min((float(np.linalg.norm(here - q)) for q in observed), default=float("inf"))
        value = q4_no_signal_probe_value(belief, here) if separation >= ZERO_MOVE_MIN_SEPARATION_M else 0.0
        # A second positive bearing is only worth paying for when it is expected
        # to cross the first one at a useful angle.  Use the joint-belief center
        # only as a predictor; the certified fallback remains unchanged.
        expected_cross = 0.0
        joint_radius = 0.0
        if value >= ZERO_MOVE_MIN_VALUE:
            jc, joint_radius, _ = q4_joint_mec(belief, spacing_m=90.0)
            if jc is not None and float(np.linalg.norm(np.asarray(jc, float) - here)) > 1e-6:
                pred = math.degrees(math.atan2(float(jc[1] - here[1]), float(jc[0] - here[0]))) % 360.0
                old_bearing = float(belief["directions"][-1]["measured_deg"])
                expected_cross = abs((pred - old_bearing + 180.0) % 360.0 - 180.0)
        if (value >= ZERO_MOVE_MIN_VALUE
                and joint_radius >= ZERO_MOVE_MIN_JOINT_RADIUS_M
                and expected_cross >= ZERO_MOVE_MIN_EXPECTED_CROSS_DEG):
            belief["_zero_move_rescan_done"] = True
            body = _measure_live(client, beliefs, here, channel)
            result = body.get("measure_result")
            if result == "near":
                clear_body = _clear_live(client, beliefs, here, channel, candidate_type="zero_move_rescan_near")
                if clear_body.get("clear_result") == "success":
                    return True
            elif result == "direction":
                print(f"  频道 {channel}: 当前位置零移动复测得到第2条示向")
        else:
            # Do not repeatedly score the same corridor entry. A later call after
            # another channel moves the robot may still be useful, so only mark
            # the probe consumed when a measurement is actually made.
            pass

    feasible_poly = belief_polygon(belief, sides=192)
    if len(feasible_poly) == 0:
        return False

    # no_signal-aware joint cloud is guidance-only; certified geometry stays in feasible_poly.
    _, _, joint_cloud = q4_joint_mec(belief, spacing_m=90.0)
    if (len(belief.get("directions", [])) == 1
            and not belief.get("_far_cross_probe_done", False)
            and len(joint_cloud)):
        _obs=belief["directions"][-1];_o=np.asarray(_obs["sensor"],float)
        _e=unit_vector_deg(float(_obs["measured_deg"]));_n=np.asarray([-_e[1],_e[0]],float)
        _jp=np.dot(np.asarray(joint_cloud,float)-_o,_e)
        _rq=float(np.quantile(_jp,0.10)) if len(_jp) else 0.0
        if _rq >= FAR_CROSS_MIN_PROJECTION_M:
            belief["_far_cross_probe_done"]=True
            _qs=[_o+FAR_CROSS_FORWARD_M*_e+FAR_CROSS_LATERAL_M*_n,
                 _o+FAR_CROSS_FORWARD_M*_e-FAR_CROSS_LATERAL_M*_n]
            _here=np.asarray(client.current_position_m,float);_qs.sort(key=lambda q:float(np.linalg.norm(q-_here)))
            _try_qs = _qs if FAR_CROSS_TRY_BOTH else _qs[:1]
            for _q0 in _try_qs:
                _q=np.asarray(_q0,float);_body=_measure_live(client,beliefs,_q,channel);_res=_body.get("measure_result")
                if _res=="near":
                    _cb=_clear_live(client,beliefs,_q,channel,candidate_type="far_cross_near")
                    if _cb.get("clear_result")=="success":return True
                if _res=="direction":
                    return _clear_corridor_live(client,beliefs,channel,remeasure_budget=remeasure_budget)
            return _clear_corridor_live(client,beliefs,channel,remeasure_budget=remeasure_budget)

    # 多站正测向优先走交会定位。
    if len(belief.get("directions", [])) >= 2:
        center, radius = minimum_enclosing_circle(feasible_poly)
        if radius <= 20.0 + 1e-6:
            if _try_clear_live(client, beliefs, channel, np.asarray(center, float), poly=feasible_poly):
                return True

        d0 = unit_vector_deg(float(belief["directions"][-2]["measured_deg"]))
        d1 = unit_vector_deg(float(belief["directions"][-1]["measured_deg"]))
        crossing_angle = math.degrees(math.acos(max(-1.0, min(1.0, abs(float(np.dot(d0, d1)))))))
        if crossing_angle >= 12.0 and radius <= 120.0:
            estimate = locate_from_directions(belief["directions"][-4:])
            if estimate is not None:
                offsets = [(0.0, 0.0), (18.0, 0.0), (-18.0, 0.0), (0.0, 18.0), (0.0, -18.0)]
                quick_points = [np.asarray(estimate, float) + np.asarray(offset, float) for offset in offsets]
                for point in _route_points_optimized(client.current_position_m, quick_points, use_two_opt=False):
                    if _try_clear_live(client, beliefs, channel, point, poly=feasible_poly):
                        return True

    failed_probes = 0

    def probe(point: np.ndarray) -> bool:
        nonlocal failed_probes, remeasure_budget
        before_failures = len(belief.get("clear_failures", []))
        if _try_clear_live(client, beliefs, channel, point, poly=feasible_poly):
            return True
        after_failures = len(belief.get("clear_failures", []))
        if after_failures > before_failures:
            failed_probes += 1

        if remeasure_budget > 0 and failed_probes >= Q4_CORRIDOR_REMEASURE_AFTER_FAILS:
            here = np.asarray(client.current_position_m, float)
            body = _measure_live(client, beliefs, here, channel)
            remeasure_budget -= 1
            failed_probes = 0
            result = body.get("measure_result")
            if result == "near":
                clear_body = _clear_live(client, beliefs, here, channel, candidate_type="corridor_remeasure_near")
                if clear_body.get("clear_result") == "success":
                    print(f"  频道 {channel}: 走廊复测 near 后原地清除成功")
                    return True
            elif result == "direction":
                print(f"  频道 {channel}: 走廊失败后复测获得新示向，重建交会/走廊")
                return _clear_corridor_live(client, beliefs, channel, remeasure_budget=remeasure_budget)
        return False

    latest = belief["directions"][-1]
    origin = np.asarray(latest["sensor"], float)
    e = unit_vector_deg(float(latest["measured_deg"]))
    n = np.asarray([-e[1], e[0]], float)

    central = [origin + s * e for s in Q4_OPT_CENTRAL_RADII]
    current = np.asarray(client.current_position_m, float)
    start_index = min(range(len(central)), key=lambda i: float(np.linalg.norm(current - central[i])))

    # 单示向时，估计可行域在中心线分割点(1120m)之外的面积权重。
    # 若远段权重较高，先向内扫再一路向外，中央段若全部失败会停在远端，
    # 可直接衔接±0.5°双排尾段；避免“扫到1120m→退回近端→再冲到尾段”的大回头。
    projections = np.dot(np.asarray(feasible_poly, float) - origin, e)
    rlo = max(0.0, float(np.min(projections)))
    rhi = max(rlo + 1e-9, float(np.max(projections)))
    split = 1120.0
    far_mass = 0.0 if rhi <= split else (rhi * rhi - max(split, rlo) ** 2) / max(1e-9, rhi * rhi - rlo * rlo)
    joint_proj = np.dot(np.asarray(joint_cloud, float) - origin, e) if len(joint_cloud) else np.empty(0)
    if len(joint_proj):
        start_r = float(Q4_OPT_CENTRAL_RADII[start_index])
        # v68: use a confidence band, not the median.  no_signal may leave a
        # disconnected/straddling feasible set; its median can sit on the wrong
        # side of the true source.  Only override v66 when >=90% of the guidance
        # cloud is clearly on one side of the current radial probe.
        q10, q90 = np.quantile(joint_proj, [0.10, 0.90])
        margin = 80.0
        if q10 >= start_r + margin:
            central_order = list(range(start_index, len(central))) + list(range(start_index - 1, -1, -1))
        elif q90 <= start_r - margin:
            central_order = list(range(start_index, -1, -1)) + list(range(start_index + 1, len(central)))
        elif len(belief.get("directions", [])) == 1 and far_mass >= Q4_CORRIDOR_FAR_MASS_INWARD_THRESHOLD:
            central_order = list(range(start_index, -1, -1)) + list(range(start_index + 1, len(central)))
        else:
            central_order = list(range(start_index, len(central))) + list(range(start_index - 1, -1, -1))
    elif len(belief.get("directions", [])) == 1 and far_mass >= Q4_CORRIDOR_FAR_MASS_INWARD_THRESHOLD:
        central_order = list(range(start_index, -1, -1)) + list(range(start_index + 1, len(central)))
    else:
        central_order = list(range(start_index, len(central))) + list(range(start_index - 1, -1, -1))

    for index in central_order:
        if probe(central[index]):
            return True
        if belief.get("status") == "cleared":
            return True

    angle = math.radians(0.5)
    ep = math.cos(angle) * e + math.sin(angle) * n
    em = math.cos(angle) * e - math.sin(angle) * n
    tail = []
    for radial in Q4_OPT_TAIL_RADII:
        tail.extend([origin + radial * ep, origin + radial * em])
    for point in _route_points_optimized(client.current_position_m, tail, use_two_opt=True):
        if probe(point):
            return True
        if belief.get("status") == "cleared":
            return True
    return False


def _record_position_after_response(client: SimulatorClient, body: dict, point: np.ndarray | None = None) -> None:
    if body.get("accepted") is True and point is not None:
        client.current_position_m = np.asarray(point, float)
    if "virtual_time_s" in body:
        client.current_virtual_time_s = float(body["virtual_time_s"])


def _quick_clear_live(client: SimulatorClient, beliefs: dict, channel: int) -> bool:
    """多站交会已很紧时的小范围顺路 clear；绝不在这里启动长 corridor。"""
    belief = beliefs[channel]
    if belief.get("status") != "detected" or len(belief.get("directions", [])) < 2:
        return False
    poly = belief_polygon(belief, sides=128)
    if len(poly) < 3:
        return False
    center, radius = minimum_enclosing_circle(poly)
    center = np.asarray(center, float)
    if radius > Q4_QUICK_CLEAR_MAX_MEC_M:
        return False
    if radius <= 20.0 + 1e-6:
        return _try_clear_live(client, beliefs, channel, center, poly=poly)

    d0 = unit_vector_deg(float(belief["directions"][-2]["measured_deg"]))
    d1 = unit_vector_deg(float(belief["directions"][-1]["measured_deg"]))
    crossing_angle = math.degrees(math.acos(max(-1.0, min(1.0, abs(float(np.dot(d0, d1)))))))
    if crossing_angle < 12.0:
        return False
    estimate = locate_from_directions(belief["directions"][-4:])
    if estimate is None:
        return False
    offsets = [
        (0.0, 0.0), (18.0, 0.0), (-18.0, 0.0), (0.0, 18.0), (0.0, -18.0),
        (12.7, 12.7), (12.7, -12.7), (-12.7, 12.7), (-12.7, -12.7),
    ]
    points = [np.asarray(estimate, float) + np.asarray(offset, float) for offset in offsets]
    for q in _route_points_optimized(client.current_position_m, points, use_two_opt=False):
        if _try_clear_live(client, beliefs, channel, q, poly=poly):
            return True
    return False


def _quick_clear_candidates_live(beliefs: dict, current_point: np.ndarray,
                                 next_point: np.ndarray | None) -> list[int]:
    current = np.asarray(current_point, float)
    nxt = None if next_point is None else np.asarray(next_point, float)
    candidates = []
    for channel, belief in beliefs.items():
        if belief.get("status") != "detected" or len(belief.get("directions", [])) < 2:
            continue
        poly = belief_polygon(belief, sides=96)
        if len(poly) < 3:
            continue
        center, radius = minimum_enclosing_circle(poly)
        if radius > Q4_QUICK_CLEAR_MAX_MEC_M:
            continue
        center = np.asarray(center, float)
        if nxt is None:
            insertion = float(np.linalg.norm(current - center))
        else:
            insertion = float(np.linalg.norm(current - center) + np.linalg.norm(center - nxt) - np.linalg.norm(current - nxt))
        if insertion <= QUICK_CLEAR_MAX_INSERTION_M:
            candidates.append((insertion, radius, channel))
    candidates.sort()
    return [channel for _, _, channel in candidates[:QUICK_CLEAR_PER_POINT]]


def _belief_target_point(belief: dict) -> np.ndarray | None:
    if belief.get("status") != "detected" or not belief.get("directions"):
        return None
    dirs = belief.get("directions", [])
    if len(dirs) >= 2:
        # Route ordering only: a well-conditioned least-squares intersection is
        # usually closer to the source than the center of the conservative wedge.
        est = locate_from_directions(dirs[-4:])
        if est is not None:
            d0 = unit_vector_deg(float(dirs[-2]["measured_deg"]))
            d1 = unit_vector_deg(float(dirs[-1]["measured_deg"]))
            cross = math.degrees(math.acos(max(-1.0, min(1.0, abs(float(np.dot(d0,d1)))))))
            if cross >= 8.0:
                return np.asarray(est, float)
    poly = belief_polygon(belief, sides=128)
    if len(poly) >= 3:
        center, _ = minimum_enclosing_circle(poly)
        return np.asarray(center, float)
    return np.asarray(dirs[-1]["sensor"], float)


def _finish_detected_channels_live(client: SimulatorClient, beliefs: dict, cleared: set[int],
                                   positive_channels: set[int], start_wall: float,
                                   real_deadline_s: float) -> None:
    active, targets = [], []
    for channel in sorted(positive_channels):
        if beliefs[channel]["status"] != "detected":
            continue
        target = _belief_target_point(beliefs[channel])
        if target is not None:
            active.append(channel)
            targets.append(target)
    if not targets:
        return
    order = _nearest_neighbor_order(client.current_position_m, targets)
    order = _two_opt_order(client.current_position_m, targets, order, max_passes=40)
    for idx in order:
        if time.monotonic() - start_wall > real_deadline_s:
            return
        channel = active[idx]
        if beliefs[channel]["status"] == "cleared":
            continue
        ok = _clear_corridor_live(client, beliefs, channel)
        if ok:
            cleared.add(channel)
            print(f"  频道 {channel}: 多站交会/保守走廊清除成功")


def run_q4(client: SimulatorClient, *, case_code: str, real_margin_s: float = 45.0,
           scan_detected_again: bool = True, fast: bool = False,
           full_census: bool = False) -> dict:
    """v360 Q4 在线控制器：快速级联清源，并保留保守走廊兜底。"""
    start_wall = time.monotonic()
    client.current_position_m = np.zeros(2)
    client.current_virtual_time_s = 0.0
    entered = client.enter()
    remaining_real = float(entered.get("remaining_real_duration_s", 1200.0))
    real_deadline_s = max(0.0, remaining_real - real_margin_s)
    _record_position_after_response(client, entered)
    print(f"[{VERSION}] Q4 已进入，剩余真实时间 {remaining_real:.0f} 秒")

    beliefs = new_beliefs()
    cleared: set[int] = set()
    positive_channels: set[int] = set()
    visited: list[list[float]] = []
    high14_early_stop = False
    rescue_sites: list[np.ndarray] = []
    max_rescue_sites = MAX_RESCUE_SITES
    low_rescue_k: int | None = None
    low_rescue_se_done = False
    low_rescue_north_done = False
    low_rescue_found = False
    low_tail_unknown_only = False
    defer_high14_one_point = False
    density_plateau_count: int | None = None
    density_plateau_index: int | None = None
    density_stop_count: int | None = None
    rescue_discovery_count = 0
    outward_rescue_angles: list[float] = []
    outward_allow_second = False

    if fast:
        route_points = np.asarray(_fast_q4_census_points() + _fast_q4_rescue_points(), float)
        mode_text = "实验快速模式：4点首轮 + 2点补扫；不具备全域方向完备保证。"
    else:
        if CENSUS_ROUTE_MODE == "two_ring14":
            _a1 = np.deg2rad(np.arange(5) * (360.0 / 5.0))
            _inner = 900.0 * np.column_stack([np.cos(_a1), np.sin(_a1)])
            _a2 = np.deg2rad(22.5 + np.arange(8) * 45.0)
            _outer = 1900.0 * np.column_stack([np.cos(_a2), np.sin(_a2)])
            # 保留中心和五个内环点的发现前缀，完整保留八个外环点。
            # 从内环终点规划外环开放路径，避免先跨向远端再绕回。
            _outer_order = _nearest_neighbor_order(_inner[-1], _outer)
            _outer_order = _two_opt_order(_inner[-1], _outer, _outer_order, max_passes=40)
            route_points = np.vstack([np.zeros((1, 2)), _inner, _outer[_outer_order]])
        elif CENSUS_ROUTE_MODE == "single_ring":
            _angles = np.deg2rad(np.linspace(0.0, 360.0, CENSUS_SINGLE_RING_POINTS,
                                             endpoint=False))
            _ring = CENSUS_SINGLE_RING_RADIUS_M * np.column_stack(
                [np.cos(_angles), np.sin(_angles)])
            route_points = np.vstack([np.zeros((1, 2)), _ring])
        elif CENSUS_ROUTE_MODE == "outer_first":
            _master = np.asarray(q4_census_master_route_opt21(), float)
            _master[1:8] *= MASTER_INNER_RADIUS_M / 950.0
            _master[8:] *= MASTER_OUTER_RADIUS_M / 1800.0
            route_points = np.vstack([_master[:1], _master[8:], _master[1:8]])
        else:
            _master = np.asarray(q4_census_master_route_opt21(), float)
            _outer = _master[8:] * (MASTER_OUTER_RADIUS_M / 1800.0)
            if MASTER_INNER_POINTS == 7:
                _inner = _master[1:8] * (MASTER_INNER_RADIUS_M / 950.0)
                if MASTER_INNER_ORDER_MODE == "spread":
                    _inner = _inner[[0, 3, 5, 1, 4, 6, 2]]
            else:
                _step = 360.0 / float(MASTER_INNER_POINTS)
                _angles = np.deg2rad(0.25 * _step + np.arange(MASTER_INNER_POINTS) * _step)
                _inner = MASTER_INNER_RADIUS_M * np.column_stack([np.cos(_angles), np.sin(_angles)])
            route_points = np.vstack([np.zeros((1, 2)), _inner, _outer])
        mode_text = ("v360-320模式：三点分散普查 + 清源位置级联发现 + 混合后验补漏。"
                     if CURRENT_PROFILE == "speed320" else
                     "v360安全模式：八点普查前缀 + 清源位置补查 + 混合后验补漏。")
    print(mode_text)

    try:
        total_points = len(route_points)
        stop_discovery_at_source_cap = False
        for route_index, point in enumerate(route_points):
            if time.monotonic() - start_wall > real_deadline_s:
                print("现实时间接近上限，停止新增普查动作。")
                break
            point = np.asarray(point, float)
            if ADAPTIVE_TAIL_PROBES and route_index >= 8:
                _unknown_now = [c for c, b in beliefs.items() if b.get("status") == "unknown"]
                if _unknown_now:
                    from q4_targeted_rescue_v3 import select_probe
                    _q, _prob = select_probe(
                        beliefs[_unknown_now[0]], np.asarray(client.current_position_m, float),
                        [np.asarray(x, float) for x in visited])
                    if _q is not None:
                        point = np.asarray(_q, float)
            visited.append(point.tolist())
            phase = 1 if route_index < min(13, total_points) else 2
            phase_den = min(13, total_points) if phase == 1 else max(1, total_points - 13)
            phase_num = route_index + 1 if phase == 1 else route_index - 12
            print(f"阶段 {phase} 普查点 {phase_num}/{phase_den}: ({point[0]:.1f}, {point[1]:.1f})")

            channels = [c for c, b in beliefs.items() if b["status"] == "unknown"]
            if scan_detected_again:
                _rescans = q4_select_rescan_channels(beliefs, point, limit=MAX_RESCANS_PER_CENSUS_POINT)
                # v361: while already standing at a census point, a 5 s second
                # bearing is much cheaper than moving hundreds of metres later
                # just to create a crossing ray.  Add all one-bearing sources
                # that are geometrically separated from their first sensor.
                if FORCE_SECOND_BEARING_RESCAN:
                    _forced = []
                    for _c, _b in beliefs.items():
                        _dirs = _b.get("directions", [])
                        if _b.get("status") != "detected" or len(_dirs) != 1:
                            continue
                        _sep = float(np.linalg.norm(point - np.asarray(_dirs[-1]["sensor"], float)))
                        if _sep >= FORCE_SECOND_BEARING_MIN_SEP_M:
                            _forced.append(_c)
                    # preserve scored candidates first, then fill with forced ones
                    for _c in _forced:
                        if _c not in _rescans:
                            _rescans.append(_c)
                # third bearings are useful only once the case is clearly dense.
                if len(positive_channels) < THIRD_BEARING_MIN_POSITIVE:
                    _rescans = [c for c in _rescans if len(beliefs[c].get("directions", [])) < 2]
                _rescans = _rescans[:MAX_RESCANS_PER_CENSUS_POINT]
                for c in _rescans:
                    if c not in channels:
                        channels.append(c)
            if client.current_channel in channels:
                channels.remove(client.current_channel)
                channels.insert(0, client.current_channel)

            for channel in channels:
                if time.monotonic() - start_wall > real_deadline_s:
                    break
                before_status = beliefs[channel]["status"]
                body = _measure_live(client, beliefs, point, channel)
                _record_position_after_response(client, body, point)
                client.current_channel = channel
                result = body.get("measure_result")
                if result == "near":
                    positive_channels.add(channel)
                    clear_body = _clear_live(client, beliefs, point, channel, candidate_type="near")
                    _record_position_after_response(client, clear_body, point)
                    if clear_body.get("clear_result") == "success":
                        cleared.add(channel)
                        print(f"  频道 {channel}: near，原地清除成功")
                elif result == "direction":
                    positive_channels.add(channel)
                    if before_status == "unknown":
                        print(f"  频道 {channel}: 首次示向 {body.get('svd_deg')}°，继续固定主路线")
                    else:
                        print(f"  频道 {channel}: 顺路复测得到第 {len(beliefs[channel].get('directions', []))} 条示向")

                if len(positive_channels) >= Q4_SOURCE_COUNT_MAX:
                    stop_discovery_at_source_cap = True
                    print(f"已确认 {Q4_SOURCE_COUNT_MAX} 个有源频道；依据 N≤{Q4_SOURCE_COUNT_MAX} 严格提前结束发现普查。")
                    break

            if stop_discovery_at_source_cap:
                break

            # v321: symmetric fast prefix. Once >=14 active channels are found
            # after the first eight sites, switch from fixed census to mandatory
            # source-clearing locations and scan only still-unknown channels there.
            if (DENSE_SWITCH_MIN <= len(positive_channels) < Q4_SOURCE_COUNT_MAX
                    and route_index >= DENSE_SWITCH_AFTER_INDEX):
                count_now = len(positive_channels)
                if density_plateau_count != count_now:
                    density_plateau_count = count_now
                    density_plateau_index = route_index
                if (density_plateau_index is not None
                        and route_index - density_plateau_index >= DENSE_CONFIRM_POINTS):
                    density_stop_count = count_now
                    stop_discovery_at_source_cap = True
                    high14_early_stop = True
                    print(f"计数平台提前切换：第{route_index+1}点已发现{count_now}源。")
                    break

            next_point = None if route_index + 1 >= total_points else np.asarray(route_points[route_index + 1], float)
            for channel in _quick_clear_candidates_live(beliefs, point, next_point):
                if time.monotonic() - start_wall > real_deadline_s:
                    break
                if beliefs[channel]["status"] == "detected" and _quick_clear_live(client, beliefs, channel):
                    cleared.add(channel)
                    positive_channels.add(channel)
                    print(f"  频道 {channel}: 低插入代价顺路清除成功")

            # Opportunistic LS clear: only if the estimated point is almost on the
            # next census segment, so it does not destroy the discovery route.
            current_now = np.asarray(client.current_position_m, float)
            ls_candidates = []
            for ch, b in beliefs.items():
                if b.get("status") != "detected" or len(b.get("directions", [])) < 2:
                    continue
                dirs = b.get("directions", [])
                d0 = unit_vector_deg(float(dirs[-2]["measured_deg"]))
                d1 = unit_vector_deg(float(dirs[-1]["measured_deg"]))
                crossing = math.degrees(math.acos(max(-1.0, min(1.0, abs(float(np.dot(d0, d1)))))))
                if crossing < 15.0:
                    continue
                est = locate_from_directions(dirs[-4:])
                if est is None:
                    continue
                est = np.asarray(est, float)
                if any(float(np.linalg.norm(est - np.asarray(q,float))) <= 28.0 for q in b.get("clear_failures", [])):
                    continue
                if next_point is None:
                    insertion = float(np.linalg.norm(est - current_now))
                else:
                    nxt = np.asarray(next_point, float)
                    insertion = float(np.linalg.norm(est-current_now)+np.linalg.norm(est-nxt)-np.linalg.norm(current_now-nxt))
                if insertion <= OPPORTUNISTIC_LS_INSERTION_M:
                    ls_candidates.append((insertion, ch, est))
            ls_candidates.sort(key=lambda x: x[0])
            if ls_candidates:
                _, ch, est = ls_candidates[0]
                poly = belief_polygon(beliefs[ch], sides=128)
                if _try_clear_live(client, beliefs, ch, est, poly=poly):
                    cleared.add(ch)
                    positive_channels.add(ch)
                    print(f"  频道 {ch}: 主路线邻近交会点顺手清除成功")

            # Low-density branch: after the fourteenth visited point, only the
            # specific k=10/11 risk states use conditional rescue logic.
            if route_index == 13 and len(positive_channels) <= 11:
                k14 = len(positive_channels)
                if k14 < 10:
                    if LOW_K14_SWITCH_TO_CLEAR and k14 > 0:
                        high14_early_stop = True
                        density_stop_count = k14
                        print(f"14点已发现{k14}源：转入清除路径并沿途搜剩余源。")
                        break
                    print("14点后不足题设最少10源：严格继续第15点。")
                else:
                    low_rescue_k = k14
                    low_tail_unknown_only = (k14 == 11)
                    print(f"14点主网结束：已发现{k14}源，进入条件救援。")
                    break

        def rescue_unknown_here() -> None:
            nonlocal rescue_sites, low_rescue_se_done, low_rescue_north_done, low_rescue_found, rescue_discovery_count
            here = np.asarray(client.current_position_m, float)
            do_scan = False
            label = "高密度"
            if high14_early_stop:
                if len(positive_channels) >= Q4_SOURCE_COUNT_MAX:
                    return
                if len(rescue_sites) >= max_rescue_sites:
                    return
                prior = [np.asarray(q,float) for q in visited] + rescue_sites
                if prior and min(float(np.linalg.norm(here-q)) for q in prior) < RESCUE_MIN_SEPARATION_M:
                    return
                rescue_sites.append(here.copy())
                do_scan = True
            elif (not low_rescue_found) and low_rescue_k in (10, 13):
                x, y = float(here[0]), float(here[1])
                label = "低密度"
                if (not low_rescue_se_done) and ((x > 1000.0 and y < 0.0) or (x > 500.0 and y < -500.0)):
                    low_rescue_se_done = True
                    do_scan = True
                elif low_rescue_k == 10 and (not low_rescue_north_done) and y > 500.0:
                    low_rescue_north_done = True
                    do_scan = True
            if not do_scan:
                return
            unknown = [c for c,b in beliefs.items() if b.get("status") == "unknown"]
            if client.current_channel in unknown:
                unknown.remove(client.current_channel)
                unknown.insert(0, client.current_channel)
            found = 0
            for c in unknown:
                body = _measure_live(client, beliefs, here, c)
                _record_position_after_response(client, body, here)
                client.current_channel = c
                r = body.get("measure_result")
                if r == "direction":
                    positive_channels.add(c)
                    found += 1
                elif r == "near":
                    positive_channels.add(c)
                    found += 1
                    cb = _clear_live(client, beliefs, here, c, candidate_type="high14_rescue_near")
                    _record_position_after_response(client, cb, here)
                    if cb.get("clear_result") == "success":
                        cleared.add(c)
            if found:
                rescue_discovery_count += found
                if not high14_early_stop:
                    low_rescue_found = True
                print(f"  {label}条件救援新发现{found}个频道")

        if low_rescue_k == 13:
            rescue_unknown_here()

        if low_tail_unknown_only and total_points >= 15:
            tail_point = np.asarray(route_points[-1], float)
            unknown = [c for c,b in beliefs.items() if b.get("status") == "unknown"]
            if unknown:
                print("k=11风险分支：unknown-only第15点救援。")
                for c in unknown:
                    body = _measure_live(client, beliefs, tail_point, c)
                    _record_position_after_response(client, body, tail_point)
                    client.current_channel = c
                    r = body.get("measure_result")
                    if r == "direction":
                        positive_channels.add(c)
                    elif r == "near":
                        positive_channels.add(c)
                        cb = _clear_live(client, beliefs, tail_point, c, candidate_type="low_tail_rescue_near")
                        _record_position_after_response(client, cb, tail_point)
                        if cb.get("clear_result") == "success":
                            cleared.add(c)

        # v335: prefix-conditioned guards are integrated into the clear route
        # as pseudo-tasks.  This keeps the discovery reliability of v334 while
        # avoiding a separate post-clear guard tour.
        pending_guards: list[np.ndarray] = []
        deferred_guards: list[np.ndarray] = []
        dense_clear_successes = 0
        if high14_early_stop and GUARD_MIN_POSITIVE <= len(positive_channels) < Q4_SOURCE_COUNT_MAX:
            _guard_map = {
                8: [30.0, 180.0, 300.0],
                9: [90.0],
                10: [180.0],
                11: [90.0, 135.0, 180.0],
                12: [30.0, 90.0, 180.0],
                13: [30.0, 90.0],
                14: [30.0],
            }
            for _ad in _guard_map.get(len(visited), [30.0, 90.0, 180.0, 300.0]):
                _aa = math.radians(_ad)
                deferred_guards.append(1800.0*np.asarray([math.cos(_aa), math.sin(_aa)], float))

        def scan_guard(_q: np.ndarray) -> None:
            _unknown = [c for c,b in beliefs.items() if b.get("status") == "unknown"]
            if not _unknown:
                return
            _found = []
            for _c in _unknown:
                _body = _measure_live(client, beliefs, _q, _c)
                _record_position_after_response(client, _body, _q)
                client.current_channel = _c
                _r = _body.get("measure_result")
                if _r == "direction":
                    positive_channels.add(_c); _found.append(_c)
                elif _r == "near":
                    positive_channels.add(_c); _found.append(_c)
                    _cb = _clear_live(client, beliefs, _q, _c, candidate_type="joint_guard_near")
                    _record_position_after_response(client, _cb, _q)
                    if _cb.get("clear_result") == "success": cleared.add(_c)
            if _found:
                print(f"  联合路径守卫新发现{len(_found)}个频道，累计{len(positive_channels)}源")

        def consume_nearby_guard(_q: np.ndarray) -> None:
            nonlocal pending_guards, deferred_guards
            if len(positive_channels) >= Q4_SOURCE_COUNT_MAX:
                pending_guards.clear(); deferred_guards.clear(); return
            _limit = 500.0 if len(positive_channels) >= 15 else 600.0
            q=np.asarray(_q,float)
            for _lst in (pending_guards, deferred_guards):
                if not _lst: continue
                _d=[float(np.linalg.norm(q-np.asarray(g,float))) for g in _lst]
                _i=int(np.argmin(_d))
                if _d[_i] <= _limit:
                    _lst.pop(_i); scan_guard(q)
                    print(f"  顺路消化守卫：距离{_d[_i]:.0f}m，阈值{_limit:.0f}m")
                    if len(positive_channels) >= Q4_SOURCE_COUNT_MAX:
                        pending_guards.clear(); deferred_guards.clear()
                    return

        def outward_rescue_here() -> None:
            nonlocal rescue_discovery_count, outward_allow_second
            if len(outward_rescue_angles) >= OUTWARD_RESCUE_BUDGET:
                return
            if len(outward_rescue_angles) >= 1 and not outward_allow_second:
                return
            if len(positive_channels) >= Q4_SOURCE_COUNT_MAX:
                return
            here = np.asarray(client.current_position_m, float)
            rr = float(np.linalg.norm(here))
            if rr < OUTWARD_RESCUE_MIN_RADIUS_M:
                return
            aa = math.atan2(float(here[1]), float(here[0]))
            for old in outward_rescue_angles:
                dd = abs(math.degrees(math.atan2(math.sin(aa-old), math.cos(aa-old))))
                if dd < OUTWARD_RESCUE_MIN_ANGLE_DEG:
                    return
            _ostep = OUTWARD_RESCUE_STEP_M if len(outward_rescue_angles) == 0 else OUTWARD_RESCUE_SECOND_STEP_M
            q = here + _ostep * here / rr
            unknown = [c for c,b in beliefs.items() if b.get("status") == "unknown"]
            if not unknown:
                return
            outward_rescue_angles.append(aa)
            found = 0
            for c in unknown:
                body = _measure_live(client, beliefs, q, c)
                _record_position_after_response(client, body, q)
                client.current_channel = c
                r = body.get("measure_result")
                if r == "direction":
                    positive_channels.add(c); found += 1
                elif r == "near":
                    positive_channels.add(c); found += 1
                    cb = _clear_live(client, beliefs, q, c, candidate_type="outward_rescue_near")
                    _record_position_after_response(client, cb, q)
                    if cb.get("clear_result") == "success": cleared.add(c)
            if found:
                rescue_discovery_count += found
                print(f"  外缘顺路探针新发现{found}个频道")
            if len(outward_rescue_angles) == 1:
                outward_allow_second = bool(found and len(positive_channels) >= 13)

        while True:
            if time.monotonic() - start_wall > real_deadline_s:
                break
            active, targets = [], []
            for channel in sorted(positive_channels):
                if beliefs[channel]["status"] != "detected":
                    continue
                target = _belief_target_point(beliefs[channel])
                if target is not None:
                    active.append(channel)
                    targets.append(target)
            if len(positive_channels) >= Q4_SOURCE_COUNT_MAX:
                pending_guards.clear()
            task_points = list(targets) + list(pending_guards)
            if not task_points:
                break
            task_order = _nearest_neighbor_order(client.current_position_m, task_points)
            task_order = _two_opt_order(client.current_position_m, task_points, task_order, max_passes=20)
            first = task_order[0]
            if first >= len(targets):
                gi = first - len(targets)
                q = np.asarray(pending_guards.pop(gi), float)
                scan_guard(q)
                continue
            channel = active[first]
            ok = _clear_corridor_live(client, beliefs, channel)
            if ok:
                cleared.add(channel)
                dense_clear_successes += 1
                print(f"  频道 {channel}: 多站交会/保守走廊清除成功")
                consume_nearby_guard(np.asarray(client.current_position_m,float))
                rescue_unknown_here()
                outward_rescue_here()
                if len(positive_channels) >= Q4_SOURCE_COUNT_MAX:
                    pending_guards.clear(); deferred_guards.clear()
                elif dense_clear_successes >= 2 and not pending_guards and deferred_guards:
                    pending_guards = list(deferred_guards)
                    deferred_guards.clear()
                    print(f"  已清{dense_clear_successes}源仍未发现16源：激活延迟守卫")
            else:
                break

        for channel in sorted(positive_channels):
            if time.monotonic() - start_wall > real_deadline_s:
                break
            if beliefs[channel]["status"] == "detected":
                if _clear_corridor_live(client, beliefs, channel):
                    cleared.add(channel)
                    consume_nearby_guard(np.asarray(client.current_position_m,float))
                    outward_rescue_here()
                    print(f"  频道 {channel}: 末轮保守走廊清除成功")

        # 全部计数状态共用完整圆盘后验，不把漏源先验限制在外环。
        _state_tail_suspect = False
        _targeted_trigger = (not _state_tail_suspect) and (
            rescue_discovery_count > 0
            or not TARGETED_RESCUE_REQUIRE_PRIOR_FIND
            or (density_stop_count is not None
                and density_stop_count >= TARGETED_RESCUE_MIN_STOP_COUNT)
        )
        if TARGETED_POST_CLEAR_RESCUE and _targeted_trigger:
            from q4_targeted_rescue_v3 import select_probe
            targeted_sites: list[np.ndarray] = []
            _base_target_budget = (TARGETED_POST_CLEAR_BUDGET
                                   if len(positive_channels) >= TARGETED_BASE_TRIGGER_MIN_POSITIVE else 0)
            _target_budget = max(
                _base_target_budget,
                TARGETED_FORCE_MAX_BUDGET if len(positive_channels) < TARGETED_FORCE_MIN_POSITIVE else 0,
            )
            _target_empty_streak = 0
            for _target_index in range(_target_budget):
                if (_target_index >= _base_target_budget
                        and len(positive_channels) >= TARGETED_FORCE_MIN_POSITIVE):
                    break
                unknown = [c for c, b in beliefs.items() if b.get("status") == "unknown"]
                if not unknown or len(positive_channels) >= Q4_SOURCE_COUNT_MAX:
                    break
                _k_before_probe = len(positive_channels)
                if _k_before_probe < TARGETED_REQUIRED_MIN_POSITIVE:
                    _probe_penalty = TARGETED_LOW_COUNT_TRAVEL_PENALTY
                elif _target_index > 0 and targeted_sites:
                    _probe_penalty = TARGETED_AFTER_FIND_TRAVEL_PENALTY
                else:
                    _probe_penalty = TARGETED_RESCUE_TRAVEL_PENALTY
                _used_all = [np.asarray(x, float) for x in visited] + rescue_sites + targeted_sites
                # 连续无信号也重新条件化完整圆盘后验；不切换成仅按角隙的外环规则。
                q, probability = select_probe(
                    beliefs[unknown[0]], np.asarray(client.current_position_m, float),
                    _used_all, travel_penalty=_probe_penalty)
                if q is None:
                    break
                targeted_sites.append(q.copy())
                found = []
                print(f"后验定向补查：预测可见率{probability:.3f}")
                for c in list(unknown):
                    body = _measure_live(client, beliefs, q, c)
                    _record_position_after_response(client, body, q)
                    if body.get("measure_result") in ("direction", "near"):
                        positive_channels.add(c); found.append(c)
                        if body.get("measure_result") == "near":
                            cb = _clear_live(client, beliefs, q, c, candidate_type="targeted_rescue_near")
                            _record_position_after_response(client, cb, q)
                            if cb.get("clear_result") == "success":
                                cleared.add(c)
                # Newly found sources create useful, widely scattered sensor
                # locations of their own.  Clear them one by one and rescan the
                # remaining unknown channels there; continue until the cascade
                # stops.  Every source is attempted at most once in this block.
                attempted: set[int] = set()
                while True:
                    candidates = [c for c in sorted(positive_channels)
                                  if beliefs[c].get("status") == "detected"
                                  and c not in attempted]
                    if not candidates:
                        break
                    targets = [_belief_target_point(beliefs[c]) for c in candidates]
                    valid = [(c, q) for c, q in zip(candidates, targets) if q is not None]
                    if not valid:
                        break
                    ci = min(range(len(valid)), key=lambda i: float(np.linalg.norm(
                        np.asarray(valid[i][1], float) - np.asarray(client.current_position_m, float))))
                    c = valid[ci][0]
                    attempted.add(c)
                    if _clear_corridor_live(client, beliefs, c):
                        cleared.add(c)
                        rescue_unknown_here()

                # 补查总预算固定为四次；空探针只更新后验，不作为不存在剩余源的证明。
                # 达到题设最大16源时仍立即停止；不读取实际源数或源位置。
                if found:
                    _target_empty_streak = 0
                else:
                    _target_empty_streak += 1
                    if (TARGETED_BREAK_ON_EMPTY
                            and len(positive_channels) >= TARGETED_REQUIRED_MIN_POSITIVE
                            and _target_empty_streak >= TARGETED_EMPTY_STREAK_STOP):
                        break
                    if (len(positive_channels) < TARGETED_REQUIRED_MIN_POSITIVE
                            and _target_empty_streak >= TARGETED_LOW_COUNT_MAX_EMPTY):
                        break

        # v380: one state-conditioned external tail probe. A moderate prefix
        # uses posterior-mean coverage; a fully exhausted ring uses equal-sector
        # tail coverage to protect rare edge-directional modes.
        _tail_mode = None
        # 原 k=13/14 的外环专项探针已由上面的完整圆盘连续补查取代。
        if _tail_mode is not None:
            _unknown=[c for c,b in beliefs.items() if b.get("status")=="unknown"]
            if _unknown:
                from q4_targeted_rescue_v3 import select_state_tail_probe
                _q,_pv=select_state_tail_probe(beliefs[_unknown[0]],np.asarray(client.current_position_m,float),mode=_tail_mode,ring_radius=STATE_TAIL_RING_RADIUS_M,travel_penalty=0.00003)
                if _q is not None:
                    _found=[]
                    for _c in list(_unknown):
                        _body=_measure_live(client,beliefs,_q,_c);_record_position_after_response(client,_body,_q);client.current_channel=_c
                        if _body.get("measure_result") in ("direction","near"):
                            positive_channels.add(_c);_found.append(_c)
                            if _body.get("measure_result")=="near":
                                _cb=_clear_live(client,beliefs,_q,_c,candidate_type="state_tail_near");_record_position_after_response(client,_cb,_q)
                                if _cb.get("clear_result")=="success":cleared.add(_c)
                    if _found:
                        print(f"  状态尾部探针({_tail_mode})新发现{len(_found)}个频道")
                        for _c in list(_found):
                            if beliefs[_c].get("status")=="detected":
                                if _clear_corridor_live(client,beliefs,_c):cleared.add(_c)

        if len(positive_channels) < Q4_SOURCE_COUNT_MAX and deferred_guards and not pending_guards:
            pending_guards = list(deferred_guards)
            deferred_guards.clear()
        if pending_guards and len(positive_channels) < Q4_SOURCE_COUNT_MAX:
            for _q in _route_points_optimized(client.current_position_m, pending_guards, use_two_opt=True):
                if len(positive_channels) >= Q4_SOURCE_COUNT_MAX:
                    break
                scan_guard(np.asarray(_q,float))
                # clear any newly detected source before moving to another guard
                for _c in sorted(positive_channels):
                    if beliefs[_c].get("status") == "detected" and _c not in cleared:
                        if _clear_corridor_live(client, beliefs, _c):
                            cleared.add(_c)

        exit_body = client.exit()
        _record_position_after_response(client, exit_body)
        print("正常退出：", exit_body.get("exit_reason"))
    except Exception:
        print("运行中断：已保留动作日志，请先查看模拟器界面确认本次测试状态。")
        raise

    elapsed = time.monotonic() - start_wall
    unknown_channels = sorted(c for c, b in beliefs.items() if b["status"] == "unknown")
    summary = {
        "version": VERSION,
        "profile": CURRENT_PROFILE,
        "fast_mode": bool(fast),
        "full_census": bool(full_census),
        "problem": 4,
        "case_code": case_code,
        "cleared_channels": sorted(cleared),
        "cleared_count_observed_by_program": len(cleared),
        "positive_channels": sorted(positive_channels),
        "unknown_channels_at_exit": unknown_channels,
        "visited_census_points_m": visited,
        "visited_census_count": len(visited),
        "density_stop_count": density_stop_count,
        "rescue_discovery_count": rescue_discovery_count,
        "source_cap_early_stop": bool((not fast) and len(positive_channels) >= Q4_SOURCE_COUNT_MAX),
        "virtual_time_s": client.current_virtual_time_s,
        "average_clear_time_s_observed_by_program": (
            client.current_virtual_time_s / len(cleared) if cleared else None
        ),
        "program_runtime_s": elapsed,
        "log_path": str(client.log_path),
        "note": "v360：分散前缀、清源位置级联发现、全向/定向混合后验补漏及保守走廊兜底。",
    }
    summary_path = client.log_path.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    average = client.current_virtual_time_s / len(cleared) if cleared else None
    average_text = "不可计算" if average is None else f"{average:.3f} 秒/源"
    print(f"Q4 完成：程序观测清除 {len(cleared)} 个频道，虚拟时间 {client.current_virtual_time_s:.3f} 秒，平均 {average_text}")
    print(f"摘要：{summary_path}")
    return summary

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--robot-id", required=True, help="当前模拟器右上角显示的参赛队号")
    parser.add_argument("--base-url", default="http://127.0.0.1:2026")
    parser.add_argument("--case-code", default="q4-live", help="本次演练或正式测试的案例编码/备注")
    parser.add_argument("--log", default=None, help="JSONL动作日志路径；不填则自动按时间命名")
    parser.add_argument("--real-margin-s", type=float, default=45.0, help="现实时间剩余多少秒时停止新增动作")
    parser.add_argument("--fast", action="store_true", help="实验性快速模式；不保证定向源全域发现，不建议正式测试使用")
    parser.add_argument("--full-census", action="store_true", help="兼容参数；v321默认使用自适应对称普查")
    parser.add_argument("--no-rescan-detected", action="store_true", help="关闭必经普查点上的顺路第2条示向；仅用于消融对照")
    parser.add_argument("--profile", choices=["speed320", "safe"], default="speed320",
                        help="speed320为默认低均值模式；safe提高源级清除率但耗时更长")
    args = parser.parse_args()
    configure_profile(args.profile)

    if args.log is None:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        log_path = Path("figures") / f"live_q4_{stamp}.jsonl"
    else:
        log_path = Path(args.log)

    client = SimulatorClient(args.robot_id, args.base_url, log_path=log_path)
    client.current_channel = 1
    client.current_position_m = np.zeros(2)
    client.current_virtual_time_s = 0.0
    run_q4(
        client,
        case_code=args.case_code,
        real_margin_s=args.real_margin_s,
        scan_detected_again=not args.no_rescan_detected,
        fast=args.fast,
        full_census=args.full_census,
    )


if __name__ == "__main__":
    main()
