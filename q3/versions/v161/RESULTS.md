# Q3 v161 quick validation

Base: v160.

Change: for discovered-count 10-13, bias the open TSP endpoint toward the current posterior probe using an adaptive endpoint weight `min(0.40, 0.45 * hidden_prob * max(0.35, probe_detect_prob))`. No persistent probe commitment is used.

Fixed hard-seed check:

| seed | N | v160 s/source | v161 s/source | full clear |
|---:|---:|---:|---:|:---:|
| 6 | 10 | 253.41 | 253.41 | yes |
| 34 | 10 | 268.37 | 268.37 | yes |
| 9 | 11 | 269.66 | 265.06 | yes |
| 7 | 12 | 235.52 | 235.52 | yes |
| 10 | 12 | 283.55 | 268.14 | yes |
| 11 | 13 | 294.69 | 287.58 | yes |

Quick set: 6/6 full clear. Mean over these six samples improves while the difficult N=10 seed34 regression from the fixed-weight experiment is avoided.

Interpretation: moving the *end* of the current clear tour toward the likely next survey region is useful, but the attraction must scale with hidden-source probability; a fixed large endpoint weight oversteers some N=10 layouts.
