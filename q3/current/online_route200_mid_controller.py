from __future__ import annotations

import numpy as np
import risk_gate_controller as gate


TUNE = {
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

    # Route-carried discovery: accept extra cheap measurements on required
    # service movement instead of paying for standalone search travel.
    'adaptive_route_scan': 1,
    'adaptive_route_scan_min_known': 0,
    'adaptive_route_scan_max_known': 16,
    'route_scan_value_s': 1800.0,

    # Empirical sweet spot: 1--2 post-clear information measurements. More
    # measurements increase fixed cost; zero measurements increase localization
    # travel/failures.
    'route_info_limit_low': 1,
    'route_info_limit_high': 2,
    'hard_done_info_limit': 0,
    'probe_info_limit': 1,
    'soft_stop_probe_limit': 0,

    # Reuse localization waypoints for discovery and for a small amount of
    # shared localization of other pending sources.
    'service_waypoint_unknown_scan': 1,
    'service_waypoint_unknown_thr': 0.10,
    'service_waypoint_unknown_max_known': 16,
    'service_shared_scan': 1,
    'service_shared_limit': 3,
    'service_shared_score_thr': 0.28,

    'stop_thr_10': 0.58,
    'stop_thr_11': 0.68,
    'stop_thr_12': 0.75,
    'stop_thr_13': 0.90,
    'stop_thr_14': 0.85,
    'stop_thr_15': 0.85,
}


class Q3OnlineRoute200MidController(gate.Q3RiskGateController):
    """Aggressive route-carried discovery/localization controller.

    Main structural changes versus the 232.196 validated controller:
    - eliminate the fixed second full-survey station;
    - start clearing immediately after the origin scan;
    - never insert a search-only detour while a detected source can be cleared;
    - use required localization/clear positions to discover unknown channels;
    - keep only 1--2 post-clear information measurements;
    - after >=10 discoveries, forbid dedicated search-only travel and accept a
      residual miss risk.  This is therefore a risk-seeking candidate and must
      not replace main until exact validation is satisfactory.
    """

    def __init__(self, client, tune=None):
        cfg = dict(TUNE)
        if tune:
            cfg.update(tune)
        super().__init__(client, cfg)

    def bootstrap_point(self):
        # The origin has just been fully scanned. Returning the current position
        # makes the normal second bootstrap scan a no-op and removes that fixed
        # travel+scan cost.
        return np.asarray(self.c.position, float)

    def scan_unknown(self, p):
        gain = super().scan_unknown(p)
        # Keep discovery aggressive on service/clear positions. The parent gate
        # can otherwise lower this value after its early-count heuristic.
        self.tune['route_scan_value_s'] = 1800.0
        return gain

    def joint_next(self, items, soft_done=False):
        if not items:
            return ('none', None, None)
        # Clearing work always wins over a standalone probe. Unknown-source
        # discovery must hitchhike on required motion whenever possible.
        order = self.source_order(items, discovery_done=(soft_done or self.known() >= 16))
        if not order:
            return ('none', None, None)
        ch, p = order[0]
        return ('source', ch, np.asarray(p, float))

    def exploration_point(self):
        # Hard risk cut: N>=10 is feasible, so after ten discoveries no movement
        # is made solely for search. Remaining sources may still be found at
        # localization and clear points.
        if self.known() >= 10:
            return None
        return super().exploration_point()


def run_q3_particle(client):
    return Q3OnlineRoute200MidController(client).run()
