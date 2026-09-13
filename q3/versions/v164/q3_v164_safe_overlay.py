from __future__ import annotations

from q3_v163_overlay import Q3ParticleController as V163Controller


class Q3ParticleController(V163Controller):
    """v164: safer random-seed branch; strengthen final validation for k=12..15."""

    def stop_threshold(self, k=None):
        k = self.known() if k is None else int(k)
        if k <= 10:
            return 0.58
        if k == 11:
            return 0.78
        if k == 12:
            return 0.93
        if k == 13:
            return 0.90
        if k == 14:
            return 0.93
        if k == 15:
            return 0.94
        return 0.99


def run_q3_particle(client):
    return Q3ParticleController(client).run()
