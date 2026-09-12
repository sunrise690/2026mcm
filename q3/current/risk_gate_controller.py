from __future__ import annotations
import math
import numpy as np
import tunable_controller as base

TUNE = {
    'particle_n': 32000,
    'particle_rebuild_n': 64000,
    'adaptive_route_scan': 1,
    'route_scan_value_s': 900,
    'stop_thr_13': 0.9,
    'service_waypoint': 1,
    'service_waypoint_min_prob': 0.4,
    'service_waypoint_cross_weight': 300,
    'service_waypoint_prob_weight': 100,
    'adaptive_bootstrap_info': 1,
    'scan_info_score_thr': 0.3,
    'service_uncertainty_trigger': 80,
    'stop_thr_10': 0.58,
    'stop_thr_11': 0.68,
    'stop_thr_12': 0.75,
    'service_waypoint_detour_weight': 1.5,
    'service_aware_route': 1,
    'service_aware_uncertainty_scale': 0.8,
    'hard_done_info_limit': 1,
    'bootstrap_sparse_radii': [650, 800, 950],
    'bootstrap_sparse_max_known': 3,
}


class Q3RiskGateController(base.Q3ParticleController):
    """Risk-aware candidate: dynamic route-fill gate + high-quality direct triangulation."""

    def __init__(self, client, tune=None):
        cfg = dict(TUNE)
        if tune:
            cfg.update(tune)
        super().__init__(client, cfg)
        self._unknown_scan_count = 0
        self._first_known = None
        self._gate_enabled = False

    def scan_unknown(self, p):
        gain = super().scan_unknown(p)
        self._unknown_scan_count += 1
        if self._unknown_scan_count == 1:
            self._first_known = self.known()
        elif self._unknown_scan_count == 2:
            origin = int(self._first_known if self._first_known is not None else 99)
            boot = int(self.known())
            boot_gain = boot - origin
            self._gate_enabled = (
                origin >= 4
                and boot <= 7
                and (boot_gain >= 2 or (origin >= 6 and boot == 7))
            )
            if self._gate_enabled:
                # More aggressively scan unknown channels at later clear points,
                # trading a small measurement cost for avoiding a long dedicated probe trip.
                self.tune['route_scan_value_s'] = 1150.0
        return gain

    def service(self, ch):
        # When two or more bearings already have a strong crossing angle, first try
        # a direct least-squares intersection.  Fall back to the validated service
        # routine immediately if the direct clear is not good enough.
        b = self.B[ch]
        dirs = [h for h in b.hist if h[1] == 'direction']
        if len(dirs) >= 2:
            cross = 0.0
            for i in range(len(dirs)):
                ai = math.radians(float(dirs[i][2]))
                ei = np.array([math.cos(ai), math.sin(ai)])
                for j in range(i):
                    aj = math.radians(float(dirs[j][2]))
                    ej = np.array([math.cos(aj), math.sin(aj)])
                    cross = max(cross, abs(float(ei[0] * ej[1] - ei[1] * ej[0])))
            if cross >= 0.50:
                A = []
                y = []
                for pp, _, th in dirs:
                    a = math.radians(float(th))
                    e = np.array([math.cos(a), math.sin(a)])
                    n = np.array([-e[1], e[0]])
                    A.append(n)
                    y.append(float(np.dot(n, pp)))
                try:
                    q = np.linalg.lstsq(np.asarray(A, float), np.asarray(y, float), rcond=None)[0]
                    nq = float(np.linalg.norm(q))
                    if nq > base.REGION:
                        q = q * (base.REGION / nq)
                    z = self.c.clear(float(q[0]), float(q[1]), int(ch))
                    if z.get('clear_result') == 'success':
                        b.status = 'cleared'
                        self.cleared.add(ch)
                        return True
                    b.add_clear_fail(q)
                    self.measure(q, ch)
                    if ch in self.cleared:
                        return True
                except Exception:
                    pass
        return super().service(ch)


def run_q3_particle(client):
    return Q3RiskGateController(client).run()
