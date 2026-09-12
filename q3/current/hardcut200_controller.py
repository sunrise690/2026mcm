from __future__ import annotations

import numpy as np
import risk_gate_controller as gate


TUNE = {
    # Start from the validated sparse-bootstrap family, but remove expensive
    # dedicated exploration after enough sources have been discovered.
    'particle_n': 32000,
    'particle_rebuild_n': 64000,
    'bootstrap_sparse_radii': [650, 800, 950],
    'bootstrap_sparse_max_known': 3,
    'adaptive_bootstrap_info': 1,
    'scan_info_score_thr': 0.30,
    'service_waypoint': 1,
    'service_waypoint_min_prob': 0.40,
    'service_waypoint_cross_weight': 300,
    'service_waypoint_prob_weight': 100,
    'service_waypoint_detour_weight': 1.5,
    'service_uncertainty_trigger': 80,
    'service_aware_route': 1,
    'service_aware_uncertainty_scale': 0.8,

    # Route-fill becomes the main discovery mechanism.  Measurement cost is
    # accepted to avoid hundreds of seconds of dedicated travel.
    'adaptive_route_scan': 1,
    'adaptive_route_scan_min_known': 0,
    'adaptive_route_scan_max_known': 16,
    'route_scan_value_s': 1500.0,

    # Cut post-clear information work aggressively.
    'route_info_limit_low': 1,
    'route_info_limit_high': 1,
    'hard_done_info_limit': 0,
    'probe_info_limit': 1,
    'soft_stop_probe_limit': 0,

    # Keep stop thresholds conservative; the structural hard cut below decides
    # when dedicated search is forbidden.
    'stop_thr_10': 0.58,
    'stop_thr_11': 0.68,
    'stop_thr_12': 0.75,
    'stop_thr_13': 0.90,
    'stop_thr_14': 0.85,
    'stop_thr_15': 0.85,
}


class Q3HardCut200Controller(gate.Q3RiskGateController):
    """Aggressive <200 candidate.

    Structural rule:
    - while there are detected-but-uncleared sources, never make a dedicated
      probe detour; clear sources first and use clear positions for route-fill;
    - once >=10 sources are known, never make another dedicated exploration trip;
    - before 10, if no source is waiting to be cleared, choose the best local
      information point by expected discovery per virtual second rather than
      raw detection probability, strongly penalising long travel.

    This intentionally accepts some miss risk in exchange for a much lower
    travel-time ceiling.
    """

    def __init__(self, client, tune=None):
        cfg = dict(TUNE)
        if tune:
            cfg.update(tune)
        super().__init__(client, cfg)
        # Disable the milder gate controller's conditional value mutation: this
        # hard-cut policy uses one globally aggressive route-fill value.
        self._gate_enabled = True
        self._dedicated_probe_cap_m = 900.0

    def scan_unknown(self, p):
        # Keep first/second-station bookkeeping from the parent, but force the
        # hard-cut route scan value after every update.
        gain = super().scan_unknown(p)
        self.tune['route_scan_value_s'] = 1500.0
        return gain

    def joint_next(self, items, soft_done=False):
        # Never insert a probe while there is useful source-clearing work to do.
        if not items:
            return ('none', None, None)
        order = self.source_order(items, discovery_done=(soft_done or self.known() >= 16))
        if not order:
            return ('none', None, None)
        ch, p = order[0]
        return ('source', ch, np.asarray(p, float))

    def exploration_point(self):
        cur = np.asarray(self.c.position, float)
        k = self.known()

        # Core hard cut: after the minimum feasible source count has been found,
        # dedicated travel solely for search is forbidden.  Any additional
        # sources must be discovered opportunistically on the clear route.
        if k >= 10:
            return None

        cand = self._explore_candidates(cur, max_pool=220)
        if not cand:
            return None

        m = len(self.unknown())
        scan_s = 5.0 * m + max(0, m - 1)
        best_local = None
        best_any = None
        for p in cand:
            p = np.asarray(p, float)
            dist = float(np.linalg.norm(p - cur))
            pd = float(self.cover.conditional_detect(p))
            # Utility is expected discovery probability per virtual second.
            # Squared travel penalty deliberately rejects heroic long jumps.
            cost = scan_s + dist / 5.0
            utility = pd / max(1.0, cost) - 2.5e-7 * dist * dist
            rec = (utility, pd, -dist, p)
            if best_any is None or rec[:3] > best_any[:3]:
                best_any = rec
            if dist <= self._dedicated_probe_cap_m:
                if best_local is None or rec[:3] > best_local[:3]:
                    best_local = rec

        chosen = best_local if best_local is not None else best_any
        return None if chosen is None else chosen[3]


def run_q3_particle(client):
    return Q3HardCut200Controller(client).run()
