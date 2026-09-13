from __future__ import annotations

import math
import numpy as np

from q3_v163_overlay import Q3ParticleController as V163Controller


FINAL_BUDGET_S = 60.0


class Q3ParticleController(V163Controller):
    """v166: v165 speed-risk policy with 60 s max final validation and lean info scans."""

    def __init__(self, client):
        super().__init__(client)
        self._final_check_used = False

    def stop_threshold(self, k=None):
        k = self.known() if k is None else int(k)
        if k <= 10:
            return 0.58
        if k == 11:
            return 0.74
        if k == 12:
            return 0.81
        if k == 13:
            return 0.80
        return 0.85

    def _bounded_final_probe(self):
        k = self.known()
        if self._final_check_used or not (11 <= k <= 15):
            return None
        cur = np.asarray(self.c.position, float)
        cand = self._explore_candidates(cur)
        if not cand:
            return None
        m = len(self.unknown())
        scan_s = 5.0 * m + max(0, m - 1)
        feasible = []
        for p in cand:
            p = np.asarray(p, float)
            dist = float(np.linalg.norm(p - cur))
            cost = dist / 5.0 + scan_s
            if cost > FINAL_BUDGET_S:
                continue
            if any(float(np.linalg.norm(p - q)) < 2.0 for q in self.used):
                continue
            pd = self.cover.conditional_detect(p)
            q1 = self._q_after_probe(p)
            ps1 = self._posterior_same_at_q(k, q1)
            feasible.append((pd, ps1, -cost, p))
        if not feasible:
            return None
        best = max(feasible, key=lambda z: (z[0], z[1], z[2]))
        if best[0] < 0.045:
            return None
        self._final_check_used = True
        return best[3]

    def _triangulation_point(self, b):
        dirs = [h for h in b.hist if h[1] == 'direction']
        if len(dirs) != 1:
            return None
        cur = np.asarray(self.c.position, float)
        est, r = b.estimate()
        if est is None:
            return None
        cand = []
        for d in (180.0, 280.0, 400.0, 520.0):
            for a in range(0, 360, 45):
                th = math.radians(a)
                p = cur + d * np.array([math.cos(th), math.sin(th)])
                if float(np.linalg.norm(p)) > 1790.0:
                    continue
                prob = b.signal_prob(p)
                cross = b.expected_cross(p)
                score = prob * (0.35 + 1.65 * cross) - d / 3500.0
                cand.append((score, prob, cross, -d, p))
        if not cand:
            return None
        best = max(cand, key=lambda z: (z[0], z[1], z[2], z[3]))
        if best[1] < 0.42 or best[2] < 0.20:
            return None
        return best[4]

    def service(self, ch):
        b = self.B[ch]
        p0, r0 = b.estimate()
        dirs = sum(1 for h in b.hist if h[1] == 'direction')
        if dirs == 1 and p0 is not None and r0 > 220.0:
            tp = self._triangulation_point(b)
            if tp is not None:
                self.measure(tp, ch)
                if ch in self.cleared:
                    return True
        return super().service(ch)

    @staticmethod
    def _explore_cap(k):
        return {12: 220.0, 13: 180.0, 14: 160.0, 15: 140.0}.get(int(k), None)

    def run(self):
        self.c.enter()
        try:
            self.scan_unknown(np.zeros(2))
            p = self.bootstrap_point()
            self.scan_unknown(p)
            self.scan_info(p, limit=5)
            for _ in range(120):
                k = self.known()
                ps = self.posterior_same_count()
                thr = self.stop_threshold(k)
                soft_done = k >= 10 and len(self.cleared) >= 9 and ps >= thr
                hard_done = k >= 16
                discovery_done = hard_done or soft_done
                detected = [(ch, b.estimate()[0]) for ch, b in self.B.items()
                            if ch not in self.cleared and b.status == 'detected' and b.estimate()[0] is not None]
                if detected:
                    kind, ch, p = self.joint_next(detected, soft_done=discovery_done)
                    if kind == 'probe':
                        self.scan_unknown(p)
                        self.scan_info(p, limit=3)
                        continue
                    self.service(ch)
                    q = np.asarray(self.c.position, float)
                    if not hard_done and not soft_done:
                        pd = self.cover.conditional_detect(q)
                        thscan = 0.08 if self.known() >= 14 else (0.11 if self.known() >= 12 else 0.15)
                        if pd >= thscan:
                            self.scan_unknown(q)
                    self.scan_info(q, limit=2)
                    continue
                if discovery_done:
                    fp = self._bounded_final_probe()
                    if fp is not None:
                        self.scan_unknown(fp)
                        self.scan_info(fp, limit=2)
                        continue
                    break
                ep = self.exploration_point()
                if ep is None:
                    break
                cap = self._explore_cap(k)
                if cap is not None:
                    cur = np.asarray(self.c.position, float)
                    m = len(self.unknown())
                    scan_s = 5.0 * m + max(0, m - 1)
                    cost = float(np.linalg.norm(np.asarray(ep, float) - cur)) / 5.0 + scan_s
                    if cost > cap:
                        fp = self._bounded_final_probe()
                        if fp is not None:
                            self.scan_unknown(fp)
                            self.scan_info(fp, limit=2)
                            continue
                        break
                self.scan_unknown(ep)
                self.scan_info(ep, limit=3)
            return len(self.cleared)
        finally:
            self.c.exit()


def run_q3_particle(client):
    return Q3ParticleController(client).run()
