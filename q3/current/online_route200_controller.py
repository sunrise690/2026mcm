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
    'adaptive_route_scan': 1,
    'adaptive_route_scan_min_known': 0,
    'adaptive_route_scan_max_known': 16,
    'route_scan_value_s': 1800.0,
    'route_info_limit_low': 4,
    'route_info_limit_high': 6,
    'hard_done_info_limit': 0,
    'probe_info_limit': 1,
    'soft_stop_probe_limit': 0,
    'service_waypoint_unknown_scan': 1,
    'service_waypoint_unknown_thr': 0.10,
    'service_waypoint_unknown_max_known': 16,
    'service_shared_scan': 1,
    'service_shared_limit': 6,
    'service_shared_score_thr': 0.25,
    'stop_thr_10': 0.58,
    'stop_thr_11': 0.68,
    'stop_thr_12': 0.75,
    'stop_thr_13': 0.90,
    'stop_thr_14': 0.85,
    'stop_thr_15': 0.85,
}


class Q3OnlineRoute200Controller(gate.Q3RiskGateController):
    """Aggressive route-carried discovery candidate.

    Major structural change:
    1. remove the dedicated second bootstrap survey station;
    2. immediately start clearing sources found at the origin;
    3. reuse service/localization waypoints and clear positions to discover
       unknown channels and localize other detected sources;
    4. while any source is waiting to be cleared, never insert a dedicated
       exploration detour;
    5. once at least 10 sources have been found, forbid dedicated search-only
       travel and accept the residual miss risk. Additional sources can still be
       found opportunistically on the clear route.

    This is intentionally risk-seeking and is kept off main until exact
    validation shows the miss rate is acceptable.
    """

    def __init__(self, client, tune=None):
        cfg = dict(TUNE)
        if tune:
            cfg.update(tune)
        super().__init__(client, cfg)

    def bootstrap_point(self):
        # Returning the current position makes the normal second full survey a
        # no-op because the origin has already been scanned. This deletes one
        # fixed travel+scan station without rewriting the validated run loop.
        return np.asarray(self.c.position, float)

    def scan_unknown(self, p):
        gain = super().scan_unknown(p)
        # The parent gate may lower this to 1150 based on the first two scans;
        # this candidate intentionally keeps route-carried discovery aggressive.
        self.tune['route_scan_value_s'] = 1800.0
        return gain

    def joint_next(self, items, soft_done=False):
        # Clearing work always has priority. Search must hitchhike on required
        # service movement rather than creating a standalone probe detour.
        if not items:
            return ('none', None, None)
        order = self.source_order(items, discovery_done=(soft_done or self.known() >= 16))
        if not order:
            return ('none', None, None)
        ch, p = order[0]
        return ('source', ch, np.asarray(p, float))

    def exploration_point(self):
        # Before 10 sources the hard prior N>=10 still requires active search if
        # the clear queue becomes empty. After 10, search-only travel is banned.
        if self.known() >= 10:
            return None
        return super().exploration_point()


def run_q3_particle(client):
    return Q3OnlineRoute200Controller(client).run()
