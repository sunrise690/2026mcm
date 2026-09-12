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

## Current metric snapshot

All metrics are seconds per source. Reported validation rows are fixed repeated validation for selection; no formal test was started.

| Version | N=10 | N=16 | Overall | Status |
| --- | ---: | ---: | ---: | --- |
| Main Q3 historical | 293.7, 100.0%, n=4 | 197.4, 100.0%, n=4 | 246.8, 100.0% clear | Historical only |
| Main Q4 historical | not output, n=12 | not output, n=12 | 364.5, 56.0% clear | Historical only, unreliable |
| True hybrid Q3 reliable best | 330.3, 100.0%, n=5 | 211.5, 100.0%, n=5 | 270.0, 100.0% clear | Current reliable hybrid baseline |
| True hybrid Q4 pre-Round8 best seen in log | 668.9, 90.0%, n not output | 298.1, 100.0%, n not output | 511.7, 92.9% clear | Too slow and not fully reliable |
| True hybrid Q4 Round9 fixed validation | 460.1, 80.0%, n not output | 293.4, 90.0%, n not output | 386.8, 71.4% clear | Rejected: leaks sources |

## Interpretation

Q3 is still above the 200 s/source target, but the reliable mixed baseline is preserved and the tuner now searches from that baseline. Directly replaying the main Q3 historical best config inside the true hybrid Q3 current source failed completely, so that config must not be used as hybrid evidence.

Q4 remains the harder blocker. The more aggressive count-posterior candidates reduce time but lose too many full clears. The next useful direction is a narrower search around the slower high-clear candidates, with stronger N10 pressure but without accepting low-clear speed candidates.
