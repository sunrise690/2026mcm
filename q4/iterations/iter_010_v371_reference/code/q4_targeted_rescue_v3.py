"""Posterior-guided Q4 rescue probes for the supplied official-v3 rules."""
from __future__ import annotations

import hashlib
import math
import numpy as np


def _particles(no_signal_points, count=20000, directional_prior=0.55):
    rounded = np.round(np.asarray(no_signal_points, float), 3)
    digest = hashlib.blake2b(rounded.tobytes(), digest_size=8).digest()
    rng = np.random.default_rng(int.from_bytes(digest, "little"))
    radial = 1770.0 * np.sqrt(rng.random(count))
    angle = rng.uniform(0.0, 2.0 * math.pi, count)
    position = np.column_stack([radial * np.cos(angle), radial * np.sin(angle)])
    radius = rng.uniform(1000.0, 1500.0, count)
    heading = rng.uniform(0.0, 2.0 * math.pi, count)
    heading_u = np.column_stack([np.cos(heading), np.sin(heading)])
    directional = rng.random(count) < float(directional_prior)
    keep = np.ones(count, bool)
    for sensor in no_signal_points:
        delta = np.asarray(sensor, float) - position
        in_range = np.linalg.norm(delta, axis=1) <= radius
        visible = in_range & (~directional | (np.sum(delta * heading_u, axis=1) >= 0.0))
        keep &= ~visible
    return position[keep], radius[keep], heading_u[keep], directional[keep]


def select_probe(belief, current, used, travel_penalty=0.00035):
    pos, radius, heading_u, directional = _particles(belief.get("no_signal_points", []))
    if not len(pos):
        return None, 0.0
    current = np.asarray(current, float)
    used = [np.asarray(q, float) for q in used]
    best = None
    for ring_radius in (0.0, 500.0, 1000.0, 1400.0, 1750.0):
        angle_values = (0.0,) if ring_radius == 0.0 else np.arange(0.0, 360.0, 10.0)
        for angle_deg in angle_values:
            angle = math.radians(float(angle_deg))
            point = ring_radius * np.asarray([math.cos(angle), math.sin(angle)])
            if used and min(float(np.linalg.norm(point - q)) for q in used) < 220.0:
                continue
            delta = point - pos
            in_range = np.linalg.norm(delta, axis=1) <= radius
            visible = in_range & (~directional | (np.sum(delta * heading_u, axis=1) >= 0.0))
            probability = float(np.mean(visible))
            travel_s = float(np.linalg.norm(point - current)) / 5.0
            item = (probability - travel_penalty * travel_s, probability, -travel_s, point)
            if best is None or item[:3] > best[:3]:
                best = item
    if best is None:
        return None, 0.0
    return np.asarray(best[3], float), float(best[1])
