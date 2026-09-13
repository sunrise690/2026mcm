# Q3 v156 low-N iteration

Baseline: current commit10 snapshot.

Changes:
- Only when localization posterior radius > 120 m, choose a lateral triangulation point that balances signal probability, bearing crossing angle, and movement cost instead of measuring again at the current position estimate.
- Reduce the k=10 stopping posterior threshold from 0.74 to 0.60; k>=11 thresholds unchanged.

Difficult-seed validation (offline simulator v3):

| seed | N | cleared | avg s/source | measure | clear fail |
|---:|---:|---:|---:|---:|---:|
| 6 | 10 | 10/10 | 246.85 | 98 | 2 |
| 34 | 10 | 10/10 | 281.40 | 116 | 4 |
| 9 | 11 | 11/11 | 258.61 | 106 | 2 |
| 7 | 12 | 12/12 | 236.60 | 109 | 0 |
| 10 | 12 | 12/12 | 263.59 | 102 | 1 |
| 11 | 13 | 13/13 | 271.15 | 121 | 2 |

Results:
- Full clear: 6/6 (100%) on this difficult-seed set.
- Sample average: 259.70 s/source.
- Mean of N-group means: 261.00 s/source.
- Baseline mean of N-group means on the same set: 271.33 s/source.

SHA256 of local full q3_v156.py: `ddcc822b828180060280931867ae8b67fe25e3aedc6fe3bad42f70aadf84f8db`.

This is an intermediate iteration, not the final <220 target.
