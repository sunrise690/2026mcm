from __future__ import annotations

import numpy as np
import online_route200_mid_controller as mid


class Q3OnlineRoute200V2Controller(mid.Q3OnlineRoute200MidController):
    """Route200 v2: keep the large structural speedup, add one bounded rescue probe.

    Compared with online_route200_mid:
    - still deletes the fixed second survey station;
    - still clears first and carries discovery on service/clear motion;
    - still forbids long dedicated search trips after ten discoveries;
    - but when the source-count posterior is not convincing, allow at most one
      short rescue probe selected for hidden-source probability per virtual second.
    """

    def __init__(self, client, tune=None):
        cfg = {
            'route_info_limit_low': 1,
            'route_info_limit_high': 2,
            'probe_info_limit': 1,
            'service_shared_limit': 2,
            'service_shared_score_thr': 0.30,
        }
        if tune:
            cfg.update(tune)
        super().__init__(client, cfg)
        self._bounded_rescue_used = False

    def exploration_point(self):
        k = self.known()
        if k < 10:
            return super(mid.Q3OnlineRoute200MidController, self).exploration_point()

        # If the count posterior already supports stopping, retain the aggressive
        # no-detour behaviour of the mid controller.
        ps = self.posterior_same_count()
        if ps >= self.stop_threshold(k):
            return None
        if self._bounded_rescue_used:
            return None

        # Never pay the old kilometre-scale standalone exploration cost.  Permit
        # only one short rescue move, with tighter caps as more sources are known.
        if k <= 10:
            cap = 700.0
        elif k == 11:
            cap = 650.0
        elif k == 12:
            cap = 600.0
        elif k == 13:
            cap = 550.0
        else:
            cap = 500.0

        cur = np.asarray(self.c.position, float)
        unknown_n = len(self.unknown())
        scan_s = 5.0 * unknown_n + max(0, unknown_n - 1)
        best = None
        for q in self._explore_candidates(cur, max_pool=120):
            q = np.asarray(q, float)
            dist = float(np.linalg.norm(q - cur))
            if dist > cap:
                continue
            pd = self.cover.conditional_detect(q)
            if pd <= 0.02:
                continue
            q1 = self._q_after_probe(q)
            ps1 = self._posterior_same_at_q(k, q1)
            cost = dist / 5.0 + scan_s
            posterior_gain = max(0.0, ps1 - ps)
            # Hidden-source hit probability dominates; posterior progress breaks ties.
            utility = (pd + 0.35 * posterior_gain) / max(1.0, cost)
            rec = (utility, pd, posterior_gain, -cost, q)
            if best is None or rec[:4] > best[:4]:
                best = rec

        if best is None:
            return None
        self._bounded_rescue_used = True
        return best[4]


def run_q3_particle(client):
    return Q3OnlineRoute200V2Controller(client).run()
