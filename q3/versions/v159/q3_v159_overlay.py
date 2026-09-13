from __future__ import annotations

import numpy as np

from q3_controller import Q3ParticleController as BaseController


class Q3ParticleController(BaseController):
    """v159 overlay: aggressive N=10 finish, safer N=13 hidden-source interception.

    This subclasses the current commit10 controller so the change set stays small
    and easy to reproduce/rollback.
    """

    def __init__(self, client):
        super().__init__(client)
        # commit10 introduced a persistent committed probe; v159 deliberately
        # returns to receding-horizon replanning to avoid stale-hotspot lock-in.
        self.committed_probe = None

    def stop_threshold(self, k=None):
        k = self.known() if k is None else int(k)
        if k <= 10:
            return 0.62
        if k == 11:
            return 0.78
        if k == 12:
            return 0.81
        if k == 13:
            return 0.83
        return 0.85

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
        ew = 0.0 if self.known() < 11 else min(0.25, max(0.0, 0.20 * hp * pd))
        order = self.exact_order(items, route_target=probe, endpoint_weight=ew)
        if not order:
            return ('none', None, None)

        probe = np.asarray(probe, float)
        pts = [np.asarray(p, float) for _, p in order]
        best = (float('inf'), 0)
        for pos in range(len(pts) + 1):
            a = cur if pos == 0 else pts[pos - 1]
            if pos < len(pts):
                b = pts[pos]
                delta = float(np.linalg.norm(probe - a) + np.linalg.norm(b - probe) - np.linalg.norm(b - a))
            else:
                delta = float(np.linalg.norm(probe - a))
            if delta < best[0]:
                best = (delta, pos)

        allowance = (260.0 + 1900.0 * hp * pd) if self.known() < 12 else (160.0 + 1200.0 * hp * pd)
        m = len(self.unknown())
        scan_s = 5.0 * m + max(0, m - 1)
        allowance = max(40.0, allowance - 2.0 * scan_s)
        if best[1] == 0 and best[0] <= allowance:
            return ('probe', None, probe)
        return ('source', order[0][0], order[0][1])

    def exploration_point(self):
        cur = np.asarray(self.c.position, float)
        k = self.known()
        if k < 10:
            p, _ = self.cover.best_posterior_probe(cur)
            return p

        cand = self._explore_candidates(cur)
        if not cand:
            return None

        thr = self.stop_threshold(k)
        ps0 = self.posterior_same_count()
        m = len(self.unknown())
        scan_s = 5.0 * m + max(0, m - 1)
        rec = []
        for p in cand:
            dist = float(np.linalg.norm(p - cur))
            cost = dist / 5.0 + scan_s
            q1 = self._q_after_probe(p)
            ps1 = self._posterior_same_at_q(k, q1)
            pd = self.cover.conditional_detect(p)
            rec.append((p, dist, cost, q1, ps1, pd))

        finish = [r for r in rec if r[4] >= thr]
        if finish:
            maxpd = max(r[5] for r in finish)
            gap = 0.01 if k >= 15 else (0.05 if k >= 14 else 0.10)
            safe = [r for r in finish if r[5] >= maxpd - gap]
            if k == 13:
                # The old cheap-finish choice missed a 14th source on a hard seed.
                # At k=13, pay a modest extra detour for the highest hit probability.
                return max(finish, key=lambda r: (r[5], r[4], -r[2]))[0]
            return min(safe, key=lambda r: (r[2], -r[5], -r[4]))[0]

        def utility(r):
            gain = max(0.0, r[4] - ps0)
            return gain / max(1.0, r[2]) + 0.00012 * gain

        return max(rec, key=lambda r: (utility(r), r[4], r[5], -r[2]))[0]


def run_q3_particle(client):
    return Q3ParticleController(client).run()
