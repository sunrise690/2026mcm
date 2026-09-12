# Cloud hybrid Q3/Q4 feedback iteration, 2026-09-13

Remote root: `/root/autodl-tmp/b0_iteration_20260912`.

Only `feedback_v2_q3` and `feedback_v2_q4` are treated as true hybrid evidence. The older `hybrid_20260912` directory is excluded because it did not correctly overwrite the hybrid source.

## Current run

Round10 is now running.

- Q3 main PID: `34711`, with 10 worker processes observed.
- Q4 main PID: `34628`, with 12 worker processes observed.
- No duplicate Q3/Q4 main process was observed after the restart.
- Active logs remain `feedback_v2_q3/feedback_q3_v2.log` and `feedback_v2_q4/feedback_q4_v2.log`.
- Fixed repeated validation is still used for model selection only; no formal test has been started.

## Iterations applied

Round8 archived the active hybrid state, then restarted both tuners.

- Q3: added sparse-bootstrap second-station radii. If the first census has found at most 3 sources, `bootstrap_point` searches `[650, 800, 950]`; otherwise it keeps `[700, 900, 1100]`.
- Q4: increased pressure on N10 time and reopened high `STOP_RISK` count-posterior candidates. This produced faster but low-clear candidates, so those were rejected.

Round9 archived Round8 state, then restarted both tuners.

- Q3: tuner initialization seeds from `best_fullclear.json`, `best_safe.json`, and `best_score.json`.
- Q4: tuner initialization seeds from `coevo_results/hall_of_fame.json` full-clear entries and existing feedback best config.

Round10 broadens the iteration from parameter-only tuning to find-point, rescue, and clear-route behavior.

- Q3: early discovery geometry is now tunable. The second-station sparse/dense radii and ring point count are optimizer genes, with compatibility handling for older seeded configs.
- Q4: candidate configs are now applied to both `live_q4` and `q4_core`; earlier feedback runs only changed the narrow `live_q4` surface for many genes.
- Q4: channel-risk target selection now probes the highest-survival unknown channel instead of defaulting to the first unknown channel.
- Q4: added tunable middle-count guard parameters (`RISK_STOP_MIN_FOUND`, `MID_RISK_TRIGGER`, `MID_RISK_EXTRA_PROBES`, `MID_RISK_MIN_FOUND`, `MID_RISK_MAX_FOUND`) to reduce N11-N15 leakage.
- Q4: feedback scoring now penalizes clear-rate gaps across all N=10..16, not only N10/N16, while still keeping N10 speed pressure.

## Metric snapshot

All metrics are seconds per source.

| Version | N=10 | N=16 | Overall | Status |
| --- | ---: | ---: | ---: | --- |
| Main Q3 historical | 293.7, 100.0%, n=4 | 197.4, 100.0%, n=4 | 246.8, 100.0% clear | Historical only |
| Main Q4 historical | not output, n=12 | not output, n=12 | 364.5, 56.0% clear | Historical only, unreliable |
| True hybrid Q3 latest reliable best | 340.8, 100.0%, n=5 | 195.5, 100.0%, n=5 | 252.6, 100.0% clear | Improved overall, N10 still too slow |
| True hybrid Q4 pre-Round10 best seen in log | 668.9, 90.0%, n not output | 298.1, 100.0%, n not output | 511.7, 92.9% clear | Too slow and not fully reliable |
| True hybrid Q4 Round10 early screen | 699.8, 100.0%, n not output | 366.8, 100.0%, n not output | 551.0, 100.0% clear | Safety recovered, speed not yet acceptable |

## Interpretation

Q3 improved from the prior true-hybrid reliable baseline of about 265.9 s/source to 252.6 s/source while keeping 100% clear on the fixed repeated validation bank. It is still above the 200 s/source target, mostly because N10 remains around 340.8 s/source.

Q4 Round10 immediately found a 100% clear early-screen candidate, but it is much too slow. That is useful because it confirms the new full-stack safety guard is active; the next search pressure should trim census/probe cost without accepting low-clear candidates.
