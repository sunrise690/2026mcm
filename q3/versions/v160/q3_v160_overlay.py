from __future__ import annotations

from q3_v159_overlay import Q3ParticleController as V159Controller


class Q3ParticleController(V159Controller):
    """v160: keep v159 geometry/risk fixes, lower only the k=10 stop threshold."""

    def stop_threshold(self, k=None):
        k = self.known() if k is None else int(k)
        if k <= 10:
            return 0.58
        if k == 11:
            return 0.78
        if k == 12:
            return 0.81
        if k == 13:
            return 0.83
        return 0.85


def run_q3_particle(client):
    return Q3ParticleController(client).run()
