# Cloud hybrid Q3/Q4 feedback iteration, 2026-09-13

Remote root: `/root/autodl-tmp/b0_iteration_20260912`.

Only the directories `feedback_v2_q3` and `feedback_v2_q4` are treated as true hybrid evidence. The older `hybrid_20260912` directory is not used as evidence because it did not correctly overwrite the hybrid source.

## Recovery check

Read-only recovery was performed at about 2026-09-13 02:47 Beijing time.

- Current Q3 process after recovery check: main PID `28309`, with 10 worker processes in `feedback_v2_q3`.
- Current Q4 process after recovery check: main PID `29810`, with 12 worker processes in `feedback_v2_q4`.
- No duplicate Q3/Q4 main process was found at recovery time.
- Root-level `feedback_q3_v2.log` and `feedback_q4_v2.log` were stale around 02:03. Active logs were under the true hybrid directories.
- Main Q3 and main Q4 directories were treated as historical baselines only.

## Iterations applied

Round8 archived the active hybrid state, then restarted both tuners.

- Q3: added sparse-bootstrap second-station radii. If the first census has found at most 3 sources, `bootstrap_point` now searches radii `[650, 800, 950]`; otherwise it keeps `[700, 900, 1100]`. This uses only observed discovered-source count.
- Q4: increased pressure on N10 time and reopened high `STOP_RISK` count-posterior candidates. This round produced faster but low-clear Q4 candidates, so it is not accepted as a reliable candidate.

Round9 archived Round8 state, then restarted both tuners.

- Q3: tuner initialization now seeds from existing `best_fullclear.json`, `best_safe.json`, and `best_score.json`, so the search starts around reliable mixed candidates instead of only the default/random population.
- Q4: tuner initialization now also seeds from `coevo_results/hall_of_fame.json` full-clear entries and existing feedback best config. Fixed repeated validation remains part of selection, not an independent holdout test.

Round10 moved Q4 toward a full-stack risk/search scorer, but the useful signal was mixed: high-clear candidates became safer, while N10 cost rose into the 600-700 s/source range. It also made Q3 bootstrap radii searchable and fixed compatibility for older seeded Q3 configs.

Round11 changes the Q4 direction from fixed-route coverage to adaptive probing.

- Q4 no longer uses a fixed initial ring as the default discovery route. The bootstrap step now selects the next probe from the current posterior risk and travel cost; fixed ring and no-bootstrap modes remain only as searched controls.
- First joint probe, second joint probe, and tail probe now target the unknown channel with the highest posterior survival risk instead of always using `unknown[0]`.
- First-probe gates, post-clear scan gates, bootstrap mode, bootstrap travel penalty, and bootstrap radius are now searchable parameters.
- Dynamic posterior probe sampling was reduced from 200000 to 80000 particles, with tail probes at 24000 particles, to improve cloud search throughput without changing the scoring definition.
- The Q4 tuner was cleanly restarted at PID `36067`; stale orphan workers from the previous Q4 run were removed.

## Current metric snapshot

As of 2026-09-13 04:05 Beijing time, the active cloud strategy has been reset to the best strategy already recorded in GitHub/cloud evidence. The lower-clear Q4 Round11 dynamic-route candidate is rejected and must not overwrite the active Q4 configuration.

- Active Q3: `feedback_v2_q3/results/best_fullclear.json`, candidate `55d21aa07712f13a`, `252.618 s/source`, `100.0%` clear. The runnable export is `/root/autodl-tmp/b0_iteration_20260912/feedback_v2_q3/exported/q3_github_best_fullclear`.
- Active Q4: `feedback_v2_q4/round6_before_probe_batch_score_20260913_022101/feedback_results/best.json`, candidate `fc32832baead`, `443.101 s/source`, `88.57%` full clear, `99.12%` source clear.
- Q4 Round11 dynamic route is stopped/rejected for now. Its best valid candidate `6c5294175ebb` reached only about `70%` full clear at `464.4 s/source`, so it is not accepted despite the route-search idea.
- Remaining cloud autotune process after the reset is Q3 only, running in `/root/autodl-tmp/b0_iteration_20260912/feedback_v2_q3`.

All metrics are seconds per source. Reported validation rows are fixed repeated validation for selection; no formal test was started.

| Version | N=10 | N=16 | Overall | Status |
| --- | ---: | ---: | ---: | --- |
| Main Q3 historical | 293.7, 100.0%, n=4 | 197.4, 100.0%, n=4 | 246.8, 100.0% clear | Historical only |
| Main Q4 historical | not output, n=12 | not output, n=12 | 364.5, 56.0% clear | Historical only, unreliable |
| True hybrid Q3 reliable best | 330.3, 100.0%, n=5 | 211.5, 100.0%, n=5 | 270.0, 100.0% clear | Current reliable hybrid baseline |
| True hybrid Q4 pre-Round8 best seen in log | 668.9, 90.0%, n not output | 298.1, 100.0%, n not output | 511.7, 92.9% clear | Too slow and not fully reliable |
| True hybrid Q4 Round9 fixed validation | 460.1, 80.0%, n not output | 293.4, 90.0%, n not output | 386.8, 71.4% clear | Rejected: leaks sources |
| True hybrid Q4 pre-Round11 safety baseline | 668.9, 90.0%, n not output | 298.1, 100.0%, n not output | 511.7, 92.9% clear | Too slow; used only as baseline |

## Interpretation

Q3 is still above the 200 s/source target, but the reliable mixed baseline is preserved and the tuner now searches from that baseline. Directly replaying the main Q3 historical best config inside the true hybrid Q3 current source failed completely, so that config must not be used as hybrid evidence.

Q4 remains the harder blocker. Round10 showed that heavy safety fallback can recover high source-clear rates, but it pays too much travel and repeated scan cost, especially for N10. Round11 therefore removes the fixed initial route as the default and lets the posterior choose the next probe dynamically; the run is still early, so no Round11 candidate is accepted yet.
