from q3_v166_speedrisk60 import Q3ParticleController as Base


class Q3ParticleController(Base):
    """v167: tuned low-count exploration caps.

    Key empirical split on stratified-random regression:
    - at k=11, a true-11 expensive verification cost ~254.6 s;
    - a true-12 case still hiding one source had a cheaper next exploration ~222.9 s.
    A 240 s cap preserves the cheap useful search while skipping the expensive verification.
    """

    @staticmethod
    def _explore_cap(k):
        return {
            10: 260.0,
            11: 240.0,
            12: 220.0,
            13: 180.0,
            14: 160.0,
            15: 140.0,
        }.get(int(k), None)


def run_q3_particle(client):
    return Q3ParticleController(client).run()
