from __future__ import annotations

import online_route200_v2_controller as v2


class Q3OnlineRoute200V3Controller(v2.Q3OnlineRoute200V2Controller):
    """Route200 v3: adaptive information budget for the high-N tail."""

    def g(self, key):
        # At high discovery counts, the remaining route already provides many
        # geometrically diverse positions.  Keep only one post-clear information
        # measurement instead of paying two after every source.
        if key == 'route_info_limit_high':
            try:
                return 1 if self.known() >= 14 else 2
            except Exception:
                return 2
        if key == 'service_shared_limit':
            try:
                return 1 if self.known() >= 14 else 2
            except Exception:
                return 2
        return super().g(key)


def run_q3_particle(client):
    return Q3OnlineRoute200V3Controller(client).run()
