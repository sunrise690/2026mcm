from __future__ import annotations

import numpy as np

from q3_v160_overlay import Q3ParticleController as V160Controller


class Q3ParticleController(V160Controller):
    """v161: adaptive route-endpoint attraction toward the next posterior probe.

    Goal: reduce N=10-13 cross-map tail search without stale probe commitment.
    """

    def joint_next(self, items, soft_done=False):
        if soft_done or self.known() >= 16:
            order = self.exact_order(items)
            return ('none', None, None) if not order else ('source', order[0][0], order[0][1])

        cur = np.asarray(self.c.position, float)
        probe, pd = self.cover.best_posterior_probe(cur)
        if probe is None:
            order = self.exact_order(items)
            return ('none', None, None) if not order else ('source', order[0][0], order[0][1])

        hp = max(0.0, min(1.0, 1.0 - self.posterior_same_count()))
        if 10 <= self.known() <= 13:
            endpoint_weight = min(0.40, 0.45 * hp * max(0.35, pd))
        else:
            endpoint_weight = 0.0 if self.known() < 11 else min(0.25, max(0.0, 0.20 * hp * pd))

        order = self.exact_order(items, route_target=probe, endpoint_weight=endpoint_weight)
        if not order:
            return ('none', None, None)

        probe = np.asarray(probe, float)
        pts = [np.asarray(p, float) for _, p in order]
        best = (float('inf'), 0)
        for pos in range(len(pts) + 1):
            a = cur if pos == 0 else pts[pos - 1]
            if pos < len(pts):
                b = pts[pos]
                delta = float(np.linalg.norm(probe-a) + np.linalg.norm(b-probe) - np.linalg.norm(b-a))
            else:
                delta = float(np.linalg.norm(probe-a))
            if delta < best[0]:
                best = (delta, pos)

        allowance = (260.0 + 1900.0 * hp * pd) if self.known() < 12 else (160.0 + 1200.0 * hp * pd)
        m = len(self.unknown())
        scan_s = 5.0 * m + max(0, m - 1)
        allowance = max(40.0, allowance - 2.0 * scan_s)
        if best[1] == 0 and best[0] <= allowance:
            return ('probe', None, probe)
        return ('source', order[0][0], order[0][1])


def run_q3_particle(client):
    return Q3ParticleController(client).run()
