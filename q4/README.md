# Question 4 offline iterations

This directory preserves each local optimization as a separate Git commit and source snapshot.
All measurements use the bundled offline simulator. No version here is an official-server result.

Primary metric: for every case, compute virtual time divided by cleared sources; average within
each actual jammer count N=10..16, then average the seven strata equally. Failed full-clear cases
remain in the metric and full-clear rate must be reported alongside it.

Current verified reference results on the frozen 140-case holdout:

- `iter_001_outer_route`: 495.29 s/source, 126/140 full clear.
- `iter_009_no_outward_budget2`: 509.27 s/source, 133/140 full clear.
- Aggressive short-triangle experiment: 354.26 s/source, 69/140 full clear (rejected).

The target of less than 350 s/source with reliable clearing has not been reached.
Raw per-action logs and large benchmark outputs remain local; source, problem facts, and compact
iteration metadata are committed here.
