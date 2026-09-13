from __future__ import annotations

import numpy as np

from q3_v162_overlay import Q3ParticleController as V162Controller


class Q3ParticleController(V162Controller):
    """v163: cheaper N=12 finishing probe without changing the risk model elsewhere."""

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
            dist = float(np.linalg.norm(p-cur))
            cost = dist / 5.0 + scan_s
            q1 = self._q_after_probe(p)
            ps1 = self._posterior_same_at_q(k, q1)
            pd = self.cover.conditional_detect(p)
            rec.append((p, dist, cost, q1, ps1, pd))
        finish = [r for r in rec if r[4] >= thr]
        if finish:
            maxpd = max(r[5] for r in finish)
            gap = 0.15 if k == 12 else (0.01 if k >= 15 else (0.05 if k >= 14 else 0.10))
            safe = [r for r in finish if r[5] >= maxpd-gap]
            if k == 13:
                return max(finish, key=lambda r: (r[5], r[4], -r[2]))[0]
            return min(safe, key=lambda r: (r[2], -r[5], -r[4]))[0]
        def utility(r):
            gain = max(0.0, r[4]-ps0)
            return gain / max(1.0, r[2]) + 0.00012 * gain
        return max(rec, key=lambda r: (utility(r), r[4], r[5], -r[2]))[0]


def run_q3_particle(client):
    return Q3ParticleController(client).run()
