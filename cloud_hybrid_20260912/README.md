# Cloud hybrid Q3/Q4 feedback iteration, 2026-09-13

Remote root: `/root/autodl-tmp/b0_iteration_20260912`.

Only `feedback_v2_q3` and `feedback_v2_q4` are treated as true hybrid evidence. The older `hybrid_20260912` directory is excluded because it did not correctly overwrite the hybrid source.

## Current run

Round11 dynamic-route Q4 search is now running, while Q3 Round10 continues.

- Q3 main PID: `34711`, with 10 worker processes observed.
- Q4 main PID: `36067`, with 12 worker processes observed.
- Stale orphan Q4 workers from the prior run were removed before the Round11 speed restart.
- Active logs remain `feedback_v2_q3/feedback_q3_v2.log` and `feedback_v2_q4/feedback_q4_v2.log`.
- Fixed repeated validation is still used for model selection only; no formal test has been started.

## Iterations applied

Round8 archived the active hybrid state, then restarted both tuners.

- Q3: added sparse-bootstrap second-station radii. If the first census has found at most 3 sources, `bootstrap_point` searches `[650, 800, 950]`; otherwise it keeps `[700, 900, 1100]`.
- Q4: increased pressure on N10 time and reopened high `STOP_RISK` count-posterior candidates. This produced faster but low-clear candidates, so those were rejected.

Round9 archived Round8 state, then restarted both tuners.

- Q3: tuner initialization seeds from `best_fullclear.json`, `best_safe.json`, and `best_score.json`.
- Q4: tuner initialization seeds from `coevo_results/hall_of_fame.json` full-clear entries and existing feedback best config.

Round10 broadened Q4 from parameter-only tuning to find-point, rescue, clear-route, and scoring behavior. It recovered safer high-clear candidates but made N10 much too slow.

Round11 changes the Q4 direction from fixed-route coverage to adaptive probing.

- Q4 no longer uses a fixed initial ring as the default discovery route. The bootstrap step now selects the next probe from the current posterior risk and travel cost; fixed ring and no-bootstrap modes remain only as searched controls.
- First joint probe, second joint probe, and tail probe now target the unknown channel with the highest posterior survival risk instead of always using `unknown[0]`.
- First-probe gates, post-clear scan gates, bootstrap mode, bootstrap travel penalty, and bootstrap radius are now searchable parameters.
- Dynamic posterior probe sampling was reduced from 200000 to 80000 particles, with tail probes at 24000 particles, to improve cloud search throughput without changing the scoring definition.

## Metric snapshot

All metrics are seconds per source.

| Version | N=10 | N=16 | Overall | Status |
| --- | ---: | ---: | ---: | --- |
| Main Q3 historical | 293.7, 100.0%, n=4 | 197.4, 100.0%, n=4 | 246.8, 100.0% clear | Historical only |
| Main Q4 historical | not output, n=12 | not output, n=12 | 364.5, 56.0% clear | Historical only, unreliable |
| True hybrid Q3 latest reliable best | 340.8, 100.0%, n=5 | 195.5, 100.0%, n=5 | 252.6, 100.0% clear | Improved overall, N10 still too slow |
| True hybrid Q4 pre-Round11 baseline | 668.9, 90.0%, n not output | 298.1, 100.0%, n not output | 511.7, 92.9% clear | Too slow and not fully reliable |
| True hybrid Q4 Round11 first screen | 675.9, 100.0%, n not output | 440.8, 100.0%, n not output | 565.1, 78.6% clear | Early dynamic-route signal; rejected so far |

## Interpretation

Q3 remains at the current reliable true-hybrid best of 252.6 s/source with 100% clear on the fixed repeated validation bank. It is still above the 200 s/source target, mostly because N10 remains around 340.8 s/source.

Q4 remains the harder blocker. Round10 showed that heavy safety fallback can recover high source-clear rates, but it pays too much travel and repeated scan cost, especially for N10. Round11 removes the fixed initial route as the default and lets the posterior choose the next probe dynamically. The first Round11 screen is not good enough yet, so no Round11 candidate is accepted.
