from pathlib import Path
import sys, math, hashlib
import numpy as np

ROOT = Path(__file__).resolve().parent
CODE = ROOT.parent / "iter_073_deferred_fifth_joint_route" / "workspace" / "code"
sys.path.insert(0, str(CODE))
import sim_engine as s


class FixedErrors(dict):
    def __init__(self, seed):
        super().__init__()
        self.seed = seed

    def __contains__(self, key):
        if not dict.__contains__(self, key):
            raw = hashlib.sha256(repr((self.seed, key)).encode()).digest()
            self[key] = (int.from_bytes(raw[:8], "big") / 2**64 * 2 - 1) * s.BEARING_ERROR_BOUND_DEG
        return True


def make_scenario(n, seed, directional_fraction):
    world = s.make_scenario(n, seed, directional_fraction)
    world["error_cache"] = FixedErrors(seed)
    return world


def posterior_probe(belief, current, used, count=24000, travel_penalty=0.00045, directional_prior=0.55):
    no_signal = np.round(np.asarray(belief.get("no_signal_points", []), float), 3)
    digest = hashlib.blake2b(no_signal.tobytes(), digest_size=8).digest()
    rng = np.random.default_rng(int.from_bytes(digest, "little"))

    radial = 1770 * np.sqrt(rng.random(count))
    ang = rng.uniform(0, 2 * math.pi, count)
    pos = np.column_stack([radial * np.cos(ang), radial * np.sin(ang)])
    radius = rng.uniform(1000, 1500, count)
    heading = rng.uniform(0, 2 * math.pi, count)
    heading_u = np.column_stack([np.cos(heading), np.sin(heading)])
    directional = rng.random(count) < directional_prior
    keep = np.ones(count, bool)

    for sensor in belief.get("no_signal_points", []):
        d = np.asarray(sensor, float) - pos
        visible = (np.linalg.norm(d, axis=1) <= radius) & (~directional | (np.sum(d * heading_u, axis=1) >= 0))
        keep &= ~visible

    pos, radius, heading_u, directional = pos[keep], radius[keep], heading_u[keep], directional[keep]
    if not len(pos):
        return None

    cur = np.asarray(current, float)
    candidates = []
    for rr in [0, 500, 1000, 1400, 1750]:
        degs = [0] if rr == 0 else np.arange(0, 360, 20)
        for deg in degs:
            a = math.radians(float(deg))
            candidates.append(rr * np.array([math.cos(a), math.sin(a)]))
    for local_r in [350, 650, 900]:
        for deg in np.arange(0, 360, 30):
            a = math.radians(float(deg))
            q = cur + local_r * np.array([math.cos(a), math.sin(a)])
            if np.linalg.norm(q) <= 1800:
                candidates.append(q)

    best = None
    for q in candidates:
        if used and min(np.linalg.norm(q - u) for u in used) < 220:
            continue
        d = q - pos
        visible = (np.linalg.norm(d, axis=1) <= radius) & (~directional | (np.sum(d * heading_u, axis=1) >= 0))
        prob = float(np.mean(visible))
        travel = np.linalg.norm(q - cur) / 5
        item = (prob - travel_penalty * travel, prob, -travel, q)
        if best is None or item[:3] > best[:3]:
            best = item
    return None if best is None else best[3]


def state_tail_probe(belief, current, count=24000, ring_radius=1500.0):
    no_signal = np.round(np.asarray(belief.get("no_signal_points", []), float), 3)
    digest = hashlib.blake2b(b"tail" + no_signal.tobytes(), digest_size=8).digest()
    rng = np.random.default_rng(int.from_bytes(digest, "little"))

    r0, r1 = 900.0, 1770.0
    radial = np.sqrt(r0 * r0 + (r1 * r1 - r0 * r0) * rng.random(count))
    ang = rng.uniform(0, 2 * math.pi, count)
    pos = np.column_stack([radial * np.cos(ang), radial * np.sin(ang)])
    radius = rng.uniform(1000, 1500, count)
    heading = rng.uniform(0, 2 * math.pi, count)
    heading_u = np.column_stack([np.cos(heading), np.sin(heading)])
    keep = np.ones(count, bool)

    for sensor in belief.get("no_signal_points", []):
        d = np.asarray(sensor, float) - pos
        visible = (np.linalg.norm(d, axis=1) <= radius) & (np.sum(d * heading_u, axis=1) >= 0)
        keep &= ~visible

    pos, radius, heading_u = pos[keep], radius[keep], heading_u[keep]
    if not len(pos):
        return None

    cur = np.asarray(current, float)
    best = None
    for deg in np.arange(0, 360, 15):
        a = math.radians(float(deg))
        q = ring_radius * np.array([math.cos(a), math.sin(a)])
        d = q - pos
        visible = (np.linalg.norm(d, axis=1) <= radius) & (np.sum(d * heading_u, axis=1) >= 0)
        prob = float(np.mean(visible))
        travel = np.linalg.norm(q - cur) / 5
        item = (prob - 0.00008 * travel, prob, -travel, q)
        if best is None or item[:3] > best[:3]:
            best = item
    return None if best is None else best[3]
