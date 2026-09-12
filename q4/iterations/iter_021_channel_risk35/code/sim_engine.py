"""官方动作语义的离线情景模拟器与滚动策略公共实现。"""
from params import *
from utils import *
import math
import numpy as np

try:
    from shapely.geometry import Point as ShPoint, Polygon as ShPolygon
    from shapely.ops import unary_union as sh_unary_union
except Exception:  # pragma: no cover - runtime fallback if shapely is unavailable
    ShPoint = ShPolygon = sh_unary_union = None


def make_scenario(source_count, seed, directional_fraction=0.0):
    rng = np.random.default_rng(seed)
    channels = rng.choice(np.arange(CHANNEL_MIN, CHANNEL_MAX + 1), source_count, replace=False)
    radii = REGION_RADIUS_M * np.sqrt(rng.random(source_count))
    angles = rng.uniform(0.0, 2.0 * math.pi, source_count)
    positions = np.column_stack([radii * np.cos(angles), radii * np.sin(angles)])
    effective = rng.uniform(R_EFF_LO_M, R_EFF_HI_M, source_count)
    headings = rng.uniform(0.0, 360.0, source_count)
    directional_count = int(round(source_count * directional_fraction))
    directional_indices = set(rng.choice(source_count, directional_count, replace=False).tolist()) if directional_count else set()
    sources = {}
    for index, channel in enumerate(channels):
        sources[int(channel)] = {
            "channel": int(channel), "position": positions[index], "effective_radius_m": float(effective[index]),
            "directional": index in directional_indices, "heading_deg": float(headings[index]), "cleared": False,
        }
    return {"source_count": source_count, "seed": seed, "sources": sources, "rng": rng, "error_cache": {}}


def initial_state():
    return {"position": np.zeros(2), "receiver_channel": CHANNEL_MIN, "virtual_time_s": 0.0, "events": [], "cleared_count": 0}


def signal_visible(source, point):
    delta = np.asarray(point, float) - source["position"]
    if np.linalg.norm(delta) > source["effective_radius_m"] + GEOM_TOL_M:
        return False
    if not source["directional"]:
        return True
    return float(np.dot(delta, unit_vector_deg(source["heading_deg"]))) >= -GEOM_TOL_M


def simulate_action(world, state, action):
    start = state["position"].copy()
    target = np.asarray(action["position"], float)
    travel_s = float(np.linalg.norm(target - start) / ROBOT_SPEED_MPS)
    channel = int(action["channel"])
    switch_s = 0.0
    source = world["sources"].get(channel)
    if action["kind"] == "measure":
        switch_s = CHANNEL_SWITCH_TIME_S if channel != state["receiver_channel"] else 0.0
        action_s = MEASURE_ACTION_TIME_S
        if source is None or source["cleared"] or not signal_visible(source, target):
            response, measured = "no_signal", None
        else:
            distance = float(np.linalg.norm(target - source["position"]))
            if distance <= NEAR_RADIUS_M + GEOM_TOL_M:
                response, measured = "near", None
            else:
                key = (channel, float(target[0]), float(target[1]))
                if key not in world["error_cache"]:
                    world["error_cache"][key] = float(world["rng"].uniform(-BEARING_ERROR_BOUND_DEG, BEARING_ERROR_BOUND_DEG))
                measured = (bearing_deg(target, source["position"]) + world["error_cache"][key]) % 360.0
                response = "direction"
        state["receiver_channel"] = channel
    else:
        success = source is not None and not source["cleared"] and np.linalg.norm(target - source["position"]) <= CLEAR_RADIUS_M + GEOM_TOL_M
        response, measured = ("cleared" if success else "no_target"), None
        action_s = CLEAR_SUCCESS_TIME_S if success else CLEAR_FAILED_TIME_S
        if success:
            source["cleared"] = True
            state["cleared_count"] += 1
    delta_s = travel_s + switch_s + action_s
    accepted = bool(state["virtual_time_s"] + delta_s <= VIRTUAL_TIME_LIMIT_S and np.max(np.abs(target)) <= COORD_ABS_LIMIT_M)
    if not accepted:
        delta_s = 0.0
        response, measured = "rejected", None
    else:
        state["position"] = target
        state["virtual_time_s"] += delta_s
    event = {
        "index": len(state["events"]), "kind": action["kind"], "candidate_type": action.get("candidate_type", action["kind"]),
        "channel": channel, "start_position_m": start.tolist(), "position_m": target.tolist(), "accepted": accepted,
        "travel_time_s": travel_s if accepted else 0.0, "channel_switch_time_s": switch_s if accepted else 0.0,
        "action_time_s": action_s if accepted else 0.0, "delta_time_s": delta_s,
        "virtual_time_s": state["virtual_time_s"], "response": response, "svd_deg": measured,
    }
    state["events"].append(event)
    return event


def new_beliefs():
    return {channel: {"status": "unknown", "directions": [], "near_points": [], "no_signal_points": [], "clear_failures": [],
                      "type_branches": ["empty", "omnidirectional", "directional"],
                      "effective_radius_interval_m": [R_EFF_LO_M, R_EFF_HI_M],
                      "heading_interval_deg": [0.0, 360.0]} for channel in range(CHANNEL_MIN, CHANNEL_MAX + 1)}


def update_belief(belief, event, directional=False):
    # Any observation changes the joint (position, heading, radius/type) feasible set.
    # The joint set is only a guidance layer; the strict outer envelope remains the
    # correctness fallback used by the certified corridor.
    belief.pop("_joint_cache", None)
    belief.pop("_joint_stats", None)
    point = np.asarray(event["position_m"], float)
    if event["response"] == "direction":
        belief["status"] = "detected"
        belief["type_branches"] = [x for x in belief.get("type_branches", []) if x != "empty"]
        belief["directions"].append({"sensor": point, "measured_deg": event["svd_deg"], "received": True})
    elif event["response"] == "near":
        belief["status"] = "detected"
        belief["type_branches"] = [x for x in belief.get("type_branches", []) if x != "empty"]
        belief["near_points"].append(point)
    elif event["response"] == "no_signal":
        belief["no_signal_points"].append(point)
        if directional:
            belief.setdefault("belief_branches", []).append({"disjunctive": ["distance_exceeds_effective_radius", "directional_heading_faces_away"]})
    elif event["response"] == "cleared":
        belief["status"] = "cleared"
    elif event["response"] == "no_target":
        belief["clear_failures"].append(point)


def locate_from_directions(observations):
    if len(observations) < 2:
        return None
    matrix, rhs = [], []
    for observation in observations:
        direction = unit_vector_deg(observation["measured_deg"])
        normal = np.array([-direction[1], direction[0]])
        matrix.append(normal)
        rhs.append(float(np.dot(normal, observation["sensor"])))
    estimate, _, _, _ = np.linalg.lstsq(np.asarray(matrix), np.asarray(rhs), rcond=None)
    norm = np.linalg.norm(estimate)
    return estimate if norm <= REGION_RADIUS_M else estimate * REGION_RADIUS_M / norm


def information_gain(action, belief):
    if action["candidate_type"] == "census":
        return 1.0
    if action["candidate_type"] == "intersection":
        return 2.0 + len(belief["directions"])
    return 0.5


def estimated_action_time(state, action):
    travel = np.linalg.norm(np.asarray(action["position"], float) - state["position"]) / ROBOT_SPEED_MPS
    switch = CHANNEL_SWITCH_TIME_S if action["kind"] == "measure" and action["channel"] != state["receiver_channel"] else 0.0
    action_time = MEASURE_ACTION_TIME_S if action["kind"] == "measure" else CLEAR_SUCCESS_TIME_S
    return float(travel + switch + action_time)


def candidate_actions(state, channel, belief, remaining_census):
    candidates = [{"kind": "measure", "channel": channel, "position": point, "candidate_type": "census"} for point in remaining_census]
    if belief["directions"]:
        observation = belief["directions"][-1]
        direction = unit_vector_deg(observation["measured_deg"])
        candidates.append({"kind": "measure", "channel": channel, "position": observation["sensor"] + 600.0 * direction, "candidate_type": "intersection"})
        candidates.append({"kind": "measure", "channel": channel, "position": observation["sensor"] + 1000.0 * direction, "candidate_type": "homing"})
    return candidates


def choose_information_action(state, channel, belief, remaining_census):
    candidates = candidate_actions(state, channel, belief, remaining_census)
    return max(candidates, key=lambda action: information_gain(action, belief) / max(estimated_action_time(state, action), 1e-12))


def census_points():
    angles = np.arange(6, dtype=float) * math.pi / 3.0
    ring = np.column_stack([1300.0 * np.cos(angles), 1300.0 * np.sin(angles)])
    return np.vstack([np.zeros((1, 2)), ring])


def coverage_radius(points):
    points = np.asarray(points, float)
    center_index = int(np.argmin(np.linalg.norm(points, axis=1)))
    ring = np.delete(points, center_index, axis=0)
    ring_radius = float(np.mean(np.linalg.norm(ring, axis=1)))
    angles = np.sort(np.mod(np.arctan2(ring[:, 1], ring[:, 0]), 2.0 * math.pi))
    gaps = np.diff(np.r_[angles, angles[0] + 2.0 * math.pi])
    gap = float(np.max(gaps))
    boundary_angle = angles[int(np.argmax(gaps))] + gap / 2.0
    boundary_point = REGION_RADIUS_M * np.array([math.cos(boundary_angle), math.sin(boundary_angle)])
    boundary_radius = float(np.min(np.linalg.norm(points - boundary_point, axis=1)))
    interior_radius = ring_radius / (2.0 * math.cos(gap / 2.0))
    return max(boundary_radius, interior_radius), boundary_point.tolist()


def triangular_census(spacing=750.0, expansion=2400.0):
    vertical = spacing * math.sqrt(3.0) / 2.0
    points = []
    row = 0
    y = -expansion
    while y <= expansion + GEOM_TOL_M:
        offset = spacing / 2.0 if row % 2 else 0.0
        x = -expansion - spacing
        while x <= expansion + spacing:
            point = np.array([x + offset, y])
            if np.linalg.norm(point) <= expansion + spacing:
                points.append(point)
            x += spacing
        y += vertical
        row += 1
    return np.asarray(points)


def point_in_convex(point, hull):
    if len(hull) < 3:
        return False
    signs = []
    for first, second in zip(hull, np.vstack([hull[1:], hull[:1]])):
        signs.append(np.cross(second - first, point - first))
    return bool(np.all(np.asarray(signs) >= -GEOM_TOL_M) or np.all(np.asarray(signs) <= GEOM_TOL_M))


def surrounding_certificate(points):
    tests = [np.zeros(2)]
    for radius in np.linspace(0.0, REGION_RADIUS_M, 73):
        count = max(12, int(math.ceil(2.0 * math.pi * max(radius, 1.0) / 50.0)))
        angles = np.arange(count) * 2.0 * math.pi / count
        tests.extend(np.column_stack([radius * np.cos(angles), radius * np.sin(angles)]))
    minimum_neighbors = 10**9
    worst_margin = float("inf")
    for test in np.asarray(tests):
        distances = np.linalg.norm(points - test, axis=1)
        neighbors = points[distances <= R_EFF_LO_M + GEOM_TOL_M]
        minimum_neighbors = min(minimum_neighbors, len(neighbors))
        if len(neighbors) < 3 or not point_in_convex(test, convex_hull(neighbors)):
            return {"pass": False, "minimum_neighbor_count": int(minimum_neighbors), "failed_point_m": test.tolist(), "grid_resolution_m": 50.0}
        worst_margin = min(worst_margin, float(R_EFF_LO_M - distances[distances <= R_EFF_LO_M].max()))
    return {"pass": True, "minimum_neighbor_count": int(minimum_neighbors), "failed_point_m": None,
            "grid_resolution_m": 50.0, "minimum_range_margin_m": worst_margin,
            "diagnostic_only": True,
            "continuous_domain_proof": "该50m网格检查仅作数值诊断；21点布局的严格保守连续域证书见 q4_opt21_certificate.py"}


def belief_polygon(belief, sides=256):
    """Position feasible-set OUTER envelope from positive bearings.

    The target disk and received-signal upper-radius disks are circumscribed,
    never inscribed.  This is important when the polygon is used to certify a
    clear probe as impossible: an outer envelope may keep extra points, but it
    cannot delete the true source merely because of circle discretization.
    """
    poly = regular_polygon(np.zeros(2), REGION_RADIUS_M, sides, True)
    for observation in belief["directions"]:
        poly = bearing_wedge(poly, observation["sensor"], observation["measured_deg"])
        poly = intersect_convex(poly, regular_polygon(observation["sensor"], R_EFF_HI_M, sides, True))
    return convex_hull(poly)




def _points_inside_convex_batch(points, poly):
    """Vectorized point-in-convex-polygon test used only by the guidance layer."""
    pts = np.asarray(points, float)
    poly = np.asarray(poly, float)
    if len(pts) == 0 or len(poly) < 3:
        return np.zeros(len(pts), dtype=bool)
    a = poly
    b = np.vstack([poly[1:], poly[:1]])
    edge = b - a
    rel = pts[:, None, :] - a[None, :, :]
    cross = edge[None, :, 0] * rel[:, :, 1] - edge[None, :, 1] * rel[:, :, 0]
    return np.all(cross >= -1e-8, axis=1) | np.all(cross <= 1e-8, axis=1)


def _joint_heading_feasible(points, positive_points, no_signal_points, lower_radius, heading_step_deg=5.0):
    """Approximate existence of a directional heading for candidate positions.

    R is analytically eliminated.  For candidate g the smallest radius compatible
    with all positive observations is L(g)=max(1000,max_p ||p-g||).  A no-signal
    q with ||q-g||<=L(g) cannot be explained by range and therefore must lie in
    the back half-plane.  The heading grid is guidance-only and is never used to
    delete the strict certified corridor.
    """
    pts = np.asarray(points, float)
    m = len(pts)
    if m == 0:
        return np.zeros(0, dtype=bool)
    headings = np.arange(0.0, 360.0, float(heading_step_deg))
    h = np.column_stack([np.cos(np.radians(headings)), np.sin(np.radians(headings))])
    allowed = np.ones((m, len(h)), dtype=bool)
    for p in positive_points:
        vec = np.asarray(p, float)[None, :] - pts
        allowed &= (vec @ h.T) >= -1e-9
    for q in no_signal_points:
        vec = np.asarray(q, float)[None, :] - pts
        d = np.linalg.norm(vec, axis=1)
        forced_back = d <= np.asarray(lower_radius, float) + 1e-9
        if np.any(forced_back):
            dot = vec[forced_back] @ h.T
            allowed[forced_back] &= dot < 1e-9
    return np.any(allowed, axis=1)


def q4_joint_belief_cloud(belief, spacing_m=90.0, sides=96):
    """Joint Q4 feasible-position cloud exploiting no_signal without unsafe pruning.

    The cloud marginalizes R analytically and checks omni/directional branches.
    It is deliberately a *guidance* approximation.  If it becomes empty, callers
    must fall back to belief_polygon(), which remains the certified outer envelope.
    """
    if belief.get("status") != "detected" or not belief.get("directions"):
        return np.empty((0, 2), float)
    key = (float(spacing_m), int(sides))
    cache = belief.get("_joint_cache")
    if cache and cache.get("key") == key:
        return np.asarray(cache["cloud"], float)

    safe = belief_polygon(belief, sides=sides)
    if len(safe) < 3:
        return np.empty((0, 2), float)
    lo = np.min(safe, axis=0); hi = np.max(safe, axis=0)
    xs = np.arange(lo[0], hi[0] + spacing_m * 0.5, spacing_m)
    ys = np.arange(lo[1], hi[1] + spacing_m * 0.5, spacing_m)
    if len(xs) * len(ys) > 12000:
        # Keep real CPU time bounded for pathological one-bearing wedges.
        scale = math.sqrt((len(xs) * len(ys)) / 12000.0)
        step = spacing_m * scale
        xs = np.arange(lo[0], hi[0] + step * 0.5, step)
        ys = np.arange(lo[1], hi[1] + step * 0.5, step)
    grid = np.array([(x, y) for y in ys for x in xs], float)
    grid = grid[_points_inside_convex_batch(grid, safe)]
    extras = [np.asarray(safe, float), np.mean(safe, axis=0, keepdims=True)]
    points = np.vstack([grid] + extras) if len(grid) else np.vstack(extras)

    # Clear failures rigorously exclude their 20 m disks.  Using them here is safe
    # even though the whole cloud remains guidance-only.
    for c in belief.get("clear_failures", []):
        points = points[np.linalg.norm(points - np.asarray(c, float), axis=1) > CLEAR_RADIUS_M + 1e-9]
        if len(points) == 0:
            break
    if len(points) == 0:
        belief["_joint_cache"] = {"key": key, "cloud": np.empty((0, 2), float)}
        return np.empty((0, 2), float)

    positives = [np.asarray(o["sensor"], float) for o in belief.get("directions", [])]
    positives += [np.asarray(p, float) for p in belief.get("near_points", [])]
    pd = np.column_stack([np.linalg.norm(points - p, axis=1) for p in positives]) if positives else np.zeros((len(points), 0))
    lower = np.maximum(R_EFF_LO_M, np.max(pd, axis=1) if pd.shape[1] else R_EFF_LO_M)
    valid = lower <= R_EFF_HI_M + 1e-9
    points = points[valid]; lower = lower[valid]
    if len(points) == 0:
        belief["_joint_cache"] = {"key": key, "cloud": np.empty((0, 2), float)}
        return np.empty((0, 2), float)

    negatives = [np.asarray(q, float) for q in belief.get("no_signal_points", [])]
    if not negatives:
        cloud = points
        omni_fraction = 1.0
    else:
        nd = np.column_stack([np.linalg.norm(points - q, axis=1) for q in negatives])
        omni_ok = np.all(nd > lower[:, None] + 1e-9, axis=1)
        directional_ok = _joint_heading_feasible(points, positives, negatives, lower)
        keep = omni_ok | directional_ok
        cloud = points[keep]
        omni_fraction = float(np.mean(omni_ok[keep])) if np.any(keep) else 0.0

    # Never let a numerical guidance approximation erase the fallback geometry.
    if len(cloud) == 0:
        cloud = np.empty((0, 2), float)
    belief["_joint_cache"] = {"key": key, "cloud": np.asarray(cloud, float)}
    if len(cloud):
        center, radius = minimum_enclosing_circle(cloud)
        belief["_joint_stats"] = {
            "candidate_count": int(len(cloud)), "center_m": np.asarray(center, float).tolist(),
            "radius_m": float(radius), "omni_fraction": float(omni_fraction),
            "no_signal_count": int(len(negatives)),
        }
    else:
        belief["_joint_stats"] = {"candidate_count": 0, "no_signal_count": int(len(negatives))}
    return np.asarray(cloud, float)


def q4_joint_mec(belief, spacing_m=90.0):
    cloud = q4_joint_belief_cloud(belief, spacing_m=spacing_m)
    if len(cloud) >= 1:
        center, radius = minimum_enclosing_circle(cloud)
        return np.asarray(center, float), float(radius), cloud
    safe = belief_polygon(belief, sides=128)
    if len(safe) == 0:
        return None, float("inf"), cloud
    center, radius = minimum_enclosing_circle(safe)
    return np.asarray(center, float), float(radius), cloud


def q4_joint_target_point(belief):
    center, _, _ = q4_joint_mec(belief)
    return center


def q4_no_signal_probe_value(belief, point):
    """How informative a future route point is for an already detected channel."""
    cloud = q4_joint_belief_cloud(belief, spacing_m=100.0)
    if len(cloud) == 0:
        return 0.0
    positives = [np.asarray(o["sensor"], float) for o in belief.get("directions", [])]
    positives += [np.asarray(p, float) for p in belief.get("near_points", [])]
    if positives:
        pd = np.column_stack([np.linalg.norm(cloud - p, axis=1) for p in positives])
        lower = np.maximum(R_EFF_LO_M, np.max(pd, axis=1))
    else:
        lower = np.full(len(cloud), R_EFF_LO_M)
    d = np.linalg.norm(cloud - np.asarray(point, float), axis=1)
    forced_back = d <= lower + 1e-9
    guaranteed_min_range = bool(np.max(d) <= R_EFF_LO_M + 1e-9)
    in_max_range = float(np.mean(d <= R_EFF_HI_M + 1e-9))
    forced_fraction = float(np.mean(forced_back))
    # Both outcomes are useful near the current uncertainty boundary; a point that
    # is guaranteed inside 1000 m is especially valuable because no_signal then
    # proves a back-side observation rather than ambiguous range loss.
    split_value = 4.0 * forced_fraction * (1.0 - forced_fraction)
    return float(0.55 * in_max_range + 0.65 * split_value + (0.85 if guaranteed_min_range else 0.0))

def localize_and_clear_q3(world, state, channel, belief):
    first = belief["directions"][0]
    base = np.asarray(first["sensor"], float)
    direction = unit_vector_deg(first["measured_deg"])
    perpendicular = np.array([-direction[1], direction[0]])
    for sign in (1.0, -1.0):
        action = {"kind": "measure", "channel": channel, "position": base + 750.0 * direction + sign * 400.0 * perpendicular, "candidate_type": "intersection"}
        event = simulate_action(world, state, action)
        update_belief(belief, event, directional=False)
        if event["response"] == "near":
            clear_event = simulate_action(world, state, {"kind": "clear", "channel": channel, "position": action["position"], "candidate_type": "homing"})
            update_belief(belief, clear_event)
            return
    for _ in range(6):
        polygon = belief_polygon(belief)
        if not len(polygon):
            return
        center, radius = minimum_enclosing_circle(polygon)
        if radius <= CLEAR_RADIUS_M:
            event = simulate_action(world, state, {"kind": "clear", "channel": channel, "position": center, "candidate_type": "homing"})
            update_belief(belief, event)
            return
        action = {"kind": "measure", "channel": channel, "position": center, "candidate_type": "homing"}
        event = simulate_action(world, state, action)
        update_belief(belief, event, directional=False)
        if event["response"] in ("near", "no_signal"):
            clear_event = simulate_action(world, state, {"kind": "clear", "channel": channel, "position": center, "candidate_type": "homing"})
            update_belief(belief, clear_event)
            return


def localize_and_clear_q4(world, state, channel, belief):
    for _ in range(110):
        if belief["status"] == "cleared":
            return
        latest = belief["directions"][-1]
        point = np.asarray(latest["sensor"], float) + 15.0 * unit_vector_deg(latest["measured_deg"])
        event = simulate_action(world, state, {"kind": "measure", "channel": channel, "position": point, "candidate_type": "homing"})
        update_belief(belief, event, directional=True)
        if event["response"] in ("near", "no_signal"):
            clear_event = simulate_action(world, state, {"kind": "clear", "channel": channel, "position": point, "candidate_type": "homing"})
            update_belief(belief, clear_event, directional=True)
            if clear_event["response"] == "cleared":
                return


def run_policy(world, directional_mode=False, census=None):
    state = initial_state()
    beliefs = new_beliefs()
    census = np.asarray(census if census is not None else census_points(), float)
    remaining = [point.copy() for point in census]
    visited = []
    while remaining:
        reference_channel = next((channel for channel, belief in beliefs.items() if belief["status"] != "cleared"), CHANNEL_MIN)
        action = choose_information_action(state, reference_channel, beliefs[reference_channel], remaining)
        next_point = np.asarray(action["position"], float)
        next_index = int(np.argmin([np.linalg.norm(point - next_point) for point in remaining]))
        point = remaining.pop(next_index)
        visited.append(point.tolist())
        for channel, belief in beliefs.items():
            if belief["status"] == "cleared":
                continue
            event = simulate_action(world, state, {"kind": "measure", "channel": channel, "position": point, "candidate_type": "census"})
            update_belief(belief, event, directional=directional_mode)
            if event["response"] == "near":
                clear_event = simulate_action(world, state, {"kind": "clear", "channel": channel, "position": point, "candidate_type": "homing"})
                update_belief(belief, clear_event, directional=directional_mode)
            elif event["response"] == "direction":
                if directional_mode:
                    localize_and_clear_q4(world, state, channel, belief)
                else:
                    localize_and_clear_q3(world, state, channel, belief)
    return state, beliefs, visited


def validate_case(case):
    required = ("source_count", "cleared_count", "virtual_time_s", "events", "seed", "data_source")
    if not all(key in case for key in required):
        return False
    if case["data_source"] != "scenario_simulation":
        return False
    if not (0 <= case["cleared_count"] <= case["source_count"]):
        return False
    if not (0.0 <= case["virtual_time_s"] <= VIRTUAL_TIME_LIMIT_S):
        return False
    running = 0.0
    for event in case["events"]:
        if not event["accepted"] and event["delta_time_s"] != 0.0:
            return False
        expected = event["travel_time_s"] + event["channel_switch_time_s"] + event["action_time_s"]
        if abs(expected - event["delta_time_s"]) > 1e-8:
            return False
        running += event["delta_time_s"]
        if abs(running - event["virtual_time_s"]) > 1e-6:
            return False
    return abs(running - case["virtual_time_s"]) <= 1e-6

# =====================================================================
# Q3/Q4 optimized policies (2026-09-11 v3)
# These policies use only observable simulator responses; no source truth is
# consulted for decisions.  The original implementations above are retained
# for audit/ablation, while problem3.py/problem4.py call the v3 entry points.
# =====================================================================

Q3_OPT_HEX_RADIUS_M = 1125.0
Q3_OPT_BONUS_ATTEMPTS = 3
Q3_OPT_MEC_CLEAR_M = 19.5
Q4_OPT_INNER_RADIUS_M = 900.0
Q4_OPT_OUTER_RADIUS_M = 1800.0
Q4_OPT_CLEAR_EFFECTIVE_M = 19.8
Q4_OPT_CENTER_SPLIT_M = 1120.0


def q3_census_points_optimized(radius=Q3_OPT_HEX_RADIUS_M):
    angles = np.arange(6, dtype=float) * math.pi / 3.0
    ring = np.column_stack([radius * np.cos(angles), radius * np.sin(angles)])
    return np.vstack([np.zeros((1, 2)), ring])


def _ring_points(n, radius, phase_deg=0.0):
    angles = np.radians(phase_deg + np.arange(n, dtype=float) * 360.0 / n)
    return np.column_stack([radius * np.cos(angles), radius * np.sin(angles)])


def q4_census_points_opt21():
    return np.vstack([np.zeros((1,2)), _ring_points(4,Q4_OPT_INNER_RADIUS_M,0.0), _ring_points(10,Q4_OPT_OUTER_RADIUS_M,0.0)])


Q4_RESCAN_MAX_DIRECTIONS = 3
Q4_RESCAN_PER_POINT = 6
Q4_RESCAN_MIN_SCORE = 0.04017867682600296
Q4_RESCAN_MIN_SENSOR_SEP_M = 650.0
Q4_QUICK_CLEAR_MAX_MEC_M = 92.3913741305919
Q4_QUICK_CLEAR_MAX_INSERTION_M = 451.2004438945374
Q4_QUICK_CLEAR_PER_POINT = 1
Q4_SOURCE_COUNT_MAX = 16
Q4_CORRIDOR_REMEASURE_AFTER_FAILS = 1
Q4_CORRIDOR_REMEASURE_BUDGET = 2
Q4_CORRIDOR_FAR_MASS_INWARD_THRESHOLD = 0.426051235315754


def q4_census_stages_opt21():
    full=q4_census_points_opt21(); return np.asarray(full[:8],float), np.asarray(full[8:],float)



def q4_census_master_route_opt21():
    # v307b/v321: adaptive symmetric prefix, then low-density outer rescue ring.
    fast_angles = np.deg2rad(12.857142857000 + np.arange(7) * 51.428571428571)
    fast = np.column_stack([950.000000000000*np.cos(fast_angles), 950.000000000000*np.sin(fast_angles)])
    outer_angles = np.deg2rad(np.asarray([324, 288, 252, 216, 180, 144, 108, 72, 36, 0], float))
    outer = np.column_stack([1800.0*np.cos(outer_angles), 1800.0*np.sin(outer_angles)])
    return np.vstack([np.zeros((1,2)), fast, outer])


def q4_rescan_score(belief, point):
    """未来必经普查点对已发现频道的“免费复测”价值。

    只用于动作排序，不参与正确性证明。评分综合：
    1) 与已有测点的几何交会角（约60~65度附近优）；
    2) 候选点到当前位置外包络中心的距离；
    3) 与已有传感器位置的最小间距。
    """
    if belief.get("status") != "detected":
        return -1.0
    directions = belief.get("directions", [])
    if not directions or len(directions) >= Q4_RESCAN_MAX_DIRECTIONS:
        return -1.0
    p = np.asarray(point, float)
    if min(float(np.linalg.norm(p - np.asarray(obs["sensor"], float))) for obs in directions) < Q4_RESCAN_MIN_SENSOR_SEP_M:
        return -1.0
    poly = belief_polygon(belief, sides=96)
    if len(poly) < 3:
        return -1.0
    center, _ = minimum_enclosing_circle(poly)
    center = np.asarray(center, float)
    r = float(np.linalg.norm(p - center))
    if r > 1650.0:
        return -1.0
    candidate_vec = p - center
    nv = float(np.linalg.norm(candidate_vec))
    if nv < 1e-9:
        return -1.0
    candidate_vec /= nv

    # 对一条已有方向，使用 f(beta)=(1-beta/pi)sin(beta)；
    # 多条方向时取与最近几何方向的最好补充价值。
    values = []
    for obs in directions:
        old_vec = np.asarray(obs["sensor"], float) - center
        no = float(np.linalg.norm(old_vec))
        if no < 1e-9:
            continue
        old_vec /= no
        beta = math.acos(max(-1.0, min(1.0, float(np.dot(candidate_vec, old_vec)))))
        values.append((1.0 - beta / math.pi) * math.sin(beta))
    if not values:
        return -1.0
    geometry = max(values) if len(values) == 1 else min(1.0, sum(values) / len(values) + 0.15 * max(values))
    range_weight = max(0.15, 1.0 - max(0.0, r - 900.0) / 1200.0)
    return float(geometry * range_weight)


def q4_select_rescan_channels(beliefs, point, limit=Q4_RESCAN_PER_POINT):
    scored = []
    for channel, belief in beliefs.items():
        score = q4_rescan_score(belief, point)
        if score >= Q4_RESCAN_MIN_SCORE:
            scored.append((score, channel))
    scored.sort(reverse=True)
    return [channel for _, channel in scored[:limit]]


def _route_length_from(start, points, order):
    if not order:
        return 0.0
    total = float(np.linalg.norm(np.asarray(points[order[0]], float) - np.asarray(start, float)))
    for a, b in zip(order, order[1:]):
        total += float(np.linalg.norm(np.asarray(points[b], float) - np.asarray(points[a], float)))
    return total


def _nearest_neighbor_order(start, points):
    points = [np.asarray(p, float) for p in points]
    remaining = list(range(len(points)))
    current = np.asarray(start, float)
    order = []
    while remaining:
        idx = min(remaining, key=lambda i: float(np.linalg.norm(points[i] - current)))
        order.append(idx)
        current = points[idx]
        remaining.remove(idx)
    return order


def _two_opt_order(start, points, order, max_passes=30):
    order = list(order)
    best = _route_length_from(start, points, order)
    for _ in range(max_passes):
        improved = False
        for i in range(len(order) - 1):
            for j in range(i + 1, len(order)):
                candidate = order[:i] + list(reversed(order[i:j + 1])) + order[j + 1:]
                length = _route_length_from(start, points, candidate)
                if length + 1e-9 < best:
                    order, best, improved = candidate, length, True
        if not improved:
            break
    return order


def _route_points_optimized(start, points, use_two_opt=True):
    pts = [np.asarray(p, float) for p in points]
    if not pts:
        return []
    order = _nearest_neighbor_order(start, pts)
    if use_two_opt and len(pts) <= 60:
        order = _two_opt_order(start, pts, order)
    return [pts[i] for i in order]


def _belief_mec(belief, sides=256):
    poly = belief_polygon(belief, sides=sides)
    if len(poly) == 0:
        return None, float("inf"), poly
    center, radius = minimum_enclosing_circle(poly)
    return np.asarray(center, float), float(radius), poly


def _q3_cross_quality(belief, point):
    if not belief["directions"]:
        return -1e100
    center, rho, _ = _belief_mec(belief, sides=128)
    if center is None:
        return -1e100
    point = np.asarray(point, float)
    delta = center - point
    norm = float(np.linalg.norm(delta))
    if norm < 1e-9:
        return -1e100
    last = belief["directions"][-1]
    ray = unit_vector_deg(last["measured_deg"])
    look = delta / norm
    dot = max(-1.0, min(1.0, abs(float(np.dot(ray, look)))))
    gamma = math.acos(dot)
    return math.sin(gamma) / (1.0 + norm / 900.0) - 0.00015 * rho


def _q3_active_candidates(belief, current):
    center, _, _ = _belief_mec(belief, sides=128)
    if center is None or not belief["directions"]:
        return []
    last = belief["directions"][-1]
    e = unit_vector_deg(last["measured_deg"])
    n = np.array([-e[1], e[0]])
    scored = []
    for off in (180.0, 250.0, 350.0, 450.0):
        for side in (-1.0, 1.0):
            for radial in (0.0, 100.0, -100.0, 200.0, -200.0):
                p = center + side * off * n + radial * e
                if np.max(np.abs(p)) > COORD_ABS_LIMIT_M:
                    continue
                score = _q3_cross_quality(belief, p) - float(np.linalg.norm(np.asarray(current) - p)) / 6000.0
                scored.append((score, p))
    scored.sort(key=lambda z: z[0], reverse=True)
    return [p for _, p in scored]


def _q3_finish_channel_optimized(world, state, channel, belief, max_active=1):
    """普查后处理一个Q3频道：最多一次短程主动补测，再以MEC中心迭代逼近。"""
    for _ in range(max_active):
        center, rho, _ = _belief_mec(belief)
        if center is None:
            break
        if rho <= Q3_OPT_MEC_CLEAR_M:
            event = simulate_action(world, state, {"kind": "clear", "channel": channel, "position": center, "candidate_type": "homing"})
            update_belief(belief, event, directional=False)
            if event["response"] == "cleared":
                return
        candidates = _q3_active_candidates(belief, state["position"])
        if not candidates:
            break
        p = candidates[0]
        event = simulate_action(world, state, {"kind": "measure", "channel": channel, "position": p, "candidate_type": "intersection"})
        update_belief(belief, event, directional=False)
        if event["response"] == "near":
            clear_event = simulate_action(world, state, {"kind": "clear", "channel": channel, "position": p, "candidate_type": "homing"})
            update_belief(belief, clear_event, directional=False)
            if clear_event["response"] == "cleared":
                return

    # Short MEC-directed loop.  Each positive measurement contracts the exact
    # set-membership polygon; this is much shorter than the old fixed ±400m legs.
    for _ in range(8):
        if belief["status"] == "cleared":
            return
        center, rho, _ = _belief_mec(belief)
        if center is None:
            return
        if rho <= Q3_OPT_MEC_CLEAR_M:
            clear_event = simulate_action(world, state, {"kind": "clear", "channel": channel, "position": center, "candidate_type": "homing"})
            update_belief(belief, clear_event, directional=False)
            if clear_event["response"] == "cleared":
                return
        event = simulate_action(world, state, {"kind": "measure", "channel": channel, "position": center, "candidate_type": "homing"})
        update_belief(belief, event, directional=False)
        if event["response"] == "near":
            clear_event = simulate_action(world, state, {"kind": "clear", "channel": channel, "position": center, "candidate_type": "homing"})
            update_belief(belief, clear_event, directional=False)
            if clear_event["response"] == "cleared":
                return
        elif event["response"] == "no_signal":
            # No-signal is not converted into an unsafe point estimate.  Try a
            # geometry-aware lateral point on the next iteration instead.
            candidates = _q3_active_candidates(belief, state["position"])
            if candidates:
                p = candidates[0]
                ev2 = simulate_action(world, state, {"kind": "measure", "channel": channel, "position": p, "candidate_type": "intersection"})
                update_belief(belief, ev2, directional=False)

    # Compatibility fallback: retain the original conservative routine for rare
    # degenerate geometries rather than sacrificing clear rate.
    if belief["status"] != "cleared" and belief["directions"]:
        localize_and_clear_q3(world, state, channel, belief)


def run_policy_q3_optimized(world, census=None):
    state = initial_state()
    beliefs = new_beliefs()
    census = np.asarray(census if census is not None else q3_census_points_optimized(), float)
    survey = _route_points_optimized(state["position"], census)
    visited = []
    bonus_used = {c: 0 for c in range(CHANNEL_MIN, CHANNEL_MAX + 1)}

    for point in survey:
        visited.append(np.asarray(point, float).tolist())
        discovery = [c for c, b in beliefs.items() if b["status"] == "unknown"]
        bonus = []
        for c, b in beliefs.items():
            if b["status"] == "detected" and bonus_used[c] < Q3_OPT_BONUS_ATTEMPTS:
                qv = _q3_cross_quality(b, point)
                if qv > 0.16:
                    bonus.append((qv, c))
        bonus = [c for _, c in sorted(bonus, reverse=True)[:6]]
        channels = []
        for c in discovery + bonus:
            if c not in channels:
                channels.append(c)
        if state["receiver_channel"] in channels:
            channels.remove(state["receiver_channel"])
            channels = [state["receiver_channel"]] + channels

        for channel in channels:
            belief = beliefs[channel]
            was_detected = belief["status"] == "detected"
            event = simulate_action(world, state, {"kind": "measure", "channel": channel, "position": point, "candidate_type": "census"})
            update_belief(belief, event, directional=False)
            if was_detected:
                bonus_used[channel] += 1
            if event["response"] == "near":
                clear_event = simulate_action(world, state, {"kind": "clear", "channel": channel, "position": point, "candidate_type": "homing"})
                update_belief(belief, clear_event, directional=False)

    active = []
    centers = []
    for c, b in beliefs.items():
        if b["status"] == "detected":
            center, _, _ = _belief_mec(b, sides=128)
            if center is not None:
                active.append(c)
                centers.append(center)
    if centers:
        order = _nearest_neighbor_order(state["position"], centers)
        order = _two_opt_order(state["position"], centers, order, max_passes=40)
        for idx in order:
            channel = active[idx]
            if beliefs[channel]["status"] != "cleared":
                _q3_finish_channel_optimized(world, state, channel, beliefs[channel], max_active=1)

    # last safety pass for any real detected source that survived a degenerate path
    for channel, belief in beliefs.items():
        if belief["status"] == "detected" and belief["directions"]:
            _q3_finish_channel_optimized(world, state, channel, belief, max_active=1)
    return state, beliefs, visited


def _q4_interval_lo_hi(s, alpha_deg, rc=Q4_OPT_CLEAR_EFFECTIVE_M):
    a = math.radians(alpha_deg)
    ca, sa = math.cos(a), math.sin(a)
    q = math.sqrt(max(0.0, rc * rc - s * s * sa * sa))
    return s * ca - q, s * ca + q


def _q4_next_radial_center(covered, alpha_deg, rc=Q4_OPT_CLEAR_EFFECTIVE_M, upper=5000.0):
    a = math.radians(alpha_deg)
    sa = math.sin(a)
    max_s = (rc / sa) * 0.999999 if sa > 0 else upper
    lo, hi = 0.0, min(max_s, upper)
    if _q4_interval_lo_hi(hi, alpha_deg, rc)[0] < covered - 1e-10:
        raise RuntimeError("Q4 radial cover cannot advance")
    for _ in range(70):
        mid = (lo + hi) / 2.0
        if _q4_interval_lo_hi(mid, alpha_deg, rc)[0] < covered:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _build_q4_corridor_sequences():
    central = [0.0]
    covered = _q4_interval_lo_hi(0.0, 1.0)[1]
    while covered < Q4_OPT_CENTER_SPLIT_M - 1e-9:
        s = _q4_next_radial_center(covered, 1.0, upper=1130.0)
        central.append(s)
        covered = _q4_interval_lo_hi(s, 1.0)[1]
    tail = []
    tail_covered = covered
    while tail_covered < R_EFF_HI_M - 1e-9:
        s = _q4_next_radial_center(tail_covered, 0.5, upper=2300.0)
        tail.append(s)
        new_covered = _q4_interval_lo_hi(s, 0.5)[1]
        if new_covered <= tail_covered + 1e-8:
            raise RuntimeError("Q4 tail cover stalled")
        tail_covered = new_covered
    return central, tail


Q4_OPT_CENTRAL_RADII, Q4_OPT_TAIL_RADII = _build_q4_corridor_sequences()


def _point_segment_distance(point, a, b):
    point, a, b = map(lambda x: np.asarray(x, float), (point, a, b))
    ab = b - a
    denom = float(np.dot(ab, ab))
    if denom <= 1e-20:
        return float(np.linalg.norm(point - a))
    t = max(0.0, min(1.0, float(np.dot(point - a, ab)) / denom))
    return float(np.linalg.norm(point - (a + t * ab)))


def _point_in_convex_polygon(point, poly):
    poly = np.asarray(poly, float)
    if len(poly) < 3:
        return False
    vals = []
    for a, b in zip(poly, np.vstack([poly[1:], poly[:1]])):
        vals.append(float(np.cross(b - a, np.asarray(point, float) - a)))
    vals = np.asarray(vals)
    return bool(np.all(vals >= -GEOM_TOL_M) or np.all(vals <= GEOM_TOL_M))


def _distance_point_to_polygon(point, poly):
    poly = np.asarray(poly, float)
    if len(poly) == 0:
        return float("inf")
    if len(poly) == 1:
        return float(np.linalg.norm(np.asarray(point, float) - poly[0]))
    if _point_in_convex_polygon(point, poly):
        return 0.0
    return min(_point_segment_distance(point, a, b) for a, b in zip(poly, np.vstack([poly[1:], poly[:1]])))


def _q4_residual_geometry(belief, poly=None):
    """正测向外包络减去已失败 clear 的20m开圆盘。

    no_signal 对定向源不能安全删位置；clear 失败却严格给出
    P notin B(q,20)。这里仅把该信息用于后续 clear 探针剪枝。
    """
    if ShPolygon is None or ShPoint is None:
        return None
    if poly is None:
        poly = belief_polygon(belief, sides=192)
    poly = np.asarray(poly, float)
    if len(poly) < 3:
        return None
    geom = ShPolygon(poly)
    failures = belief.get("clear_failures", [])
    if failures:
        holes = [ShPoint(float(q[0]), float(q[1])).buffer(CLEAR_RADIUS_M, quad_segs=24) for q in failures]
        geom = geom.difference(sh_unary_union(holes))
    return geom


def _q4_probe_can_hit(belief, point, poly=None):
    if poly is None:
        poly = belief_polygon(belief, sides=192)
    if len(poly) == 0:
        return False
    geom = _q4_residual_geometry(belief, poly=poly)
    if geom is not None:
        if geom.is_empty:
            return False
        return float(geom.distance(ShPoint(float(point[0]), float(point[1])))) <= CLEAR_RADIUS_M + 1e-9
    return _distance_point_to_polygon(point, poly) <= CLEAR_RADIUS_M + 1e-9


def _q4_try_clear(world, state, channel, belief, point, poly=None):
    if not _q4_probe_can_hit(belief, point, poly=poly):
        return False
    event = simulate_action(world, state, {"kind": "clear", "channel": channel, "position": point, "candidate_type": "corridor"})
    update_belief(belief, event, directional=True)
    return event["response"] == "cleared"


def _q4_quick_clear(world, state, channel, belief, max_mec=Q4_QUICK_CLEAR_MAX_MEC_M):
    """仅尝试多站交会附近的小范围 clear；失败后不启动长走廊。"""
    if belief.get("status") != "detected" or len(belief.get("directions", [])) < 2:
        return False
    feasible_poly = belief_polygon(belief, sides=128)
    if len(feasible_poly) < 3:
        return False
    center, radius = minimum_enclosing_circle(feasible_poly)
    center = np.asarray(center, float)
    if radius > max_mec:
        return False
    if radius <= CLEAR_RADIUS_M + 1e-6:
        return _q4_try_clear(world, state, channel, belief, center, poly=feasible_poly)

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
    for point in _route_points_optimized(state["position"], points, use_two_opt=False):
        if _q4_try_clear(world, state, channel, belief, point, poly=feasible_poly):
            return True
    return False


def _q4_quick_clear_candidates(state, beliefs, current_point, next_point=None):
    candidates = []
    current = np.asarray(current_point, float)
    nxt = None if next_point is None else np.asarray(next_point, float)
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
        if insertion <= Q4_QUICK_CLEAR_MAX_INSERTION_M:
            candidates.append((insertion, radius, channel))
    candidates.sort()
    return [channel for _, _, channel in candidates[:Q4_QUICK_CLEAR_PER_POINT]]


def _q4_clear_corridor(world, state, channel, belief, remeasure_budget=Q4_CORRIDOR_REMEASURE_BUDGET):
    """严格走廊兜底 + 失败后同点机会复测。

    走廊 clear 仍是最终完备性保证。若连续若干个实际 clear 探针失败，
    在当前点对同频道额外 measure 一次；若重新收到 direction/near，
    利用新正观测重启几何定位。该复测仅增加5~6虚拟秒，且失败时仍继续
    原严格走廊，因此不牺牲完备性。
    """
    if belief.get("status") == "cleared" or not belief.get("directions"):
        return belief.get("status") == "cleared"

    feasible_poly = belief_polygon(belief, sides=192)
    if len(feasible_poly) == 0:
        return False

    # 先吃掉多站交会带来的定位收益。
    if len(belief.get("directions", [])) >= 2:
        center, radius = minimum_enclosing_circle(feasible_poly)
        if radius <= CLEAR_RADIUS_M + 1e-6:
            if _q4_try_clear(world, state, channel, belief, np.asarray(center, float), poly=feasible_poly):
                return True

        d0 = unit_vector_deg(float(belief["directions"][-2]["measured_deg"]))
        d1 = unit_vector_deg(float(belief["directions"][-1]["measured_deg"]))
        crossing_angle = math.degrees(math.acos(max(-1.0, min(1.0, abs(float(np.dot(d0, d1)))))))
        if crossing_angle >= 12.0:
            estimate = locate_from_directions(belief["directions"][-4:])
            if estimate is not None:
                offsets = [
                    (0.0, 0.0), (18.0, 0.0), (-18.0, 0.0), (0.0, 18.0), (0.0, -18.0),
                    (12.7, 12.7), (12.7, -12.7), (-12.7, 12.7), (-12.7, -12.7),
                ]
                quick_points = [np.asarray(estimate, float) + np.asarray(offset, float) for offset in offsets]
                for point in _route_points_optimized(state["position"], quick_points, use_two_opt=False):
                    if _q4_try_clear(world, state, channel, belief, point, poly=feasible_poly):
                        return True

    failed_probes = 0

    def probe(point):
        nonlocal failed_probes, remeasure_budget
        before = len(state["events"])
        if _q4_try_clear(world, state, channel, belief, point, poly=feasible_poly):
            return True
        if len(state["events"]) > before and state["events"][-1].get("kind") == "clear":
            failed_probes += 1
        if remeasure_budget > 0 and failed_probes >= Q4_CORRIDOR_REMEASURE_AFTER_FAILS:
            # 在刚刚失败的 clear 点原地补一次测向；没有额外移动成本。
            event = simulate_action(world, state, {
                "kind": "measure", "channel": channel, "position": np.asarray(state["position"], float),
                "candidate_type": "corridor_remeasure",
            })
            update_belief(belief, event, directional=True)
            remeasure_budget -= 1
            failed_probes = 0
            if event["response"] == "near":
                clear_event = simulate_action(world, state, {
                    "kind": "clear", "channel": channel, "position": np.asarray(state["position"], float),
                    "candidate_type": "corridor_remeasure_near",
                })
                update_belief(belief, clear_event, directional=True)
                if clear_event["response"] == "cleared":
                    return True
            elif event["response"] == "direction":
                # 新 direction 是严格正观测；从它重建走廊/交会定位。
                return _q4_clear_corridor(world, state, channel, belief, remeasure_budget=remeasure_budget)
        return False

    # 严格 fallback：以最新一条 direction 的 ±1° 走廊作20m清除覆盖。
    latest = belief["directions"][-1]
    origin = np.asarray(latest["sensor"], float)
    e = unit_vector_deg(latest["measured_deg"])
    n = np.array([-e[1], e[0]])
    central = [origin + s * e for s in Q4_OPT_CENTRAL_RADII]
    k = min(range(len(central)), key=lambda i: float(np.linalg.norm(state["position"] - central[i])))
    projections = np.dot(np.asarray(feasible_poly, float) - origin, e)
    rlo = max(0.0, float(np.min(projections)))
    rhi = max(rlo + 1e-9, float(np.max(projections)))
    split = float(Q4_OPT_CENTER_SPLIT_M)
    far_mass = 0.0 if rhi <= split else (rhi*rhi - max(split, rlo)**2) / max(1e-9, rhi*rhi - rlo*rlo)
    if len(belief.get("directions", [])) == 1 and far_mass >= Q4_CORRIDOR_FAR_MASS_INWARD_THRESHOLD:
        order = list(range(k, -1, -1)) + list(range(k + 1, len(central)))
    else:
        order = list(range(k, len(central))) + list(range(k - 1, -1, -1))
    for i in order:
        if probe(central[i]):
            return True
        if belief.get("status") == "cleared":
            return True

    a = math.radians(0.5)
    ep = math.cos(a) * e + math.sin(a) * n
    em = math.cos(a) * e - math.sin(a) * n
    tail = []
    for radial in Q4_OPT_TAIL_RADII:
        tail.extend([origin + radial * ep, origin + radial * em])
    for point in _route_points_optimized(state["position"], tail, use_two_opt=True):
        if probe(point):
            return True
        if belief.get("status") == "cleared":
            return True
    return False


def run_policy_q4_optimized(world, census=None):
    """v63 Q4：认证21点固定低路程主路径 + 免费多站复测 + 延迟走廊。

    持续 unknown 的频道仍完整经历同一组认证21点，因此发现完备性不变。
    与v62不同，本版不再把21点拆成会造成长跳跃的两个独立TSP阶段；
    quick-clear 后也继续沿固定主路径前进，使插入代价真正可控。
    """
    state = initial_state()
    beliefs = new_beliefs()
    visited = []

    route_points = (q4_census_master_route_opt21() if census is None
                    else np.asarray(census, float))

    stop_discovery_at_source_cap = False
    for route_index, point in enumerate(route_points):
        point = np.asarray(point, float)
        visited.append(point.tolist())

        discovery = [c for c, b in beliefs.items() if b["status"] == "unknown"]
        bonus = q4_select_rescan_channels(beliefs, point)
        channels = []
        for c in discovery + bonus:
            if c not in channels:
                channels.append(c)
        if state["receiver_channel"] in channels:
            channels.remove(state["receiver_channel"])
            channels.insert(0, state["receiver_channel"])

        for channel in channels:
            belief = beliefs[channel]
            event = simulate_action(world, state, {"kind": "measure", "channel": channel, "position": point, "candidate_type": "census"})
            update_belief(belief, event, directional=True)
            if event["response"] == "near":
                clear_event = simulate_action(world, state, {"kind": "clear", "channel": channel, "position": point, "candidate_type": "homing"})
                update_belief(belief, clear_event, directional=True)

            positive_count = sum(1 for b in beliefs.values() if b.get("status") in ("detected", "cleared"))
            if positive_count >= Q4_SOURCE_COUNT_MAX:
                stop_discovery_at_source_cap = True
                break

        if stop_discovery_at_source_cap:
            break

        # 固定下一主路径点，不在quick-clear后重新TSP，避免局部插入判断被重规划破坏。
        next_point = None if route_index + 1 >= len(route_points) else np.asarray(route_points[route_index + 1], float)
        for channel in _q4_quick_clear_candidates(state, beliefs, point, next_point):
            if beliefs[channel]["status"] == "detected":
                _q4_quick_clear(world, state, channel, beliefs[channel])

    # 普查结束后滚动处理剩余源：每清掉一个源后，根据真实当前位置重新排序剩余目标。
    while True:
        active, targets = [], []
        for channel, belief in beliefs.items():
            if belief["status"] != "detected" or not belief.get("directions"):
                continue
            poly = belief_polygon(belief, sides=128)
            if len(poly) >= 3:
                center, _ = minimum_enclosing_circle(poly)
                target = np.asarray(center, float)
            else:
                target = np.asarray(belief["directions"][-1]["sensor"], float)
            active.append(channel)
            targets.append(target)
        if not active:
            break
        order = _nearest_neighbor_order(state["position"], targets)
        order = _two_opt_order(state["position"], targets, order, max_passes=20)
        channel = active[order[0]]
        belief = beliefs[channel]
        before = belief["status"]
        _q4_clear_corridor(world, state, channel, belief)
        if belief["status"] != "cleared":
            localize_and_clear_q4(world, state, channel, belief)
        # 防止异常情况下死循环
        if belief["status"] == before and belief["status"] != "cleared":
            break

    # 最后安全兜底。
    for channel, belief in beliefs.items():
        if belief["status"] == "detected" and belief.get("directions"):
            _q4_clear_corridor(world, state, channel, belief)
            if belief["status"] != "cleared":
                localize_and_clear_q4(world, state, channel, belief)
    return state, beliefs, visited

