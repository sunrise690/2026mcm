# Q3 v162 quick validation

Base: v161.

Change: lower only the discovered-count `k=13` finish threshold from `0.83` to `0.80`. This targets the expensive final cross-map verification after 13 sources have already been cleared.

Key hard seed:

- seed 11, N=13: `287.58 -> 253.25 s/source`, full clear retained.

Guard set for accidental 13/14 early termination:

| seed | N | s/source | full clear |
|---:|---:|---:|:---:|
| 0 | 14 | 242.00 | yes |
| 1 | 14 | 212.40 | yes |
| 12 | 14 | 227.51 | yes |
| 17 | 14 | 252.29 | yes |
| 25 | 14 | 216.52 | yes |
| 37 | 14 | 244.98 | yes |
| 49 | 14 | 226.62 | yes |

Seven N=14 guard seeds: 7/7 full clear, mean `231.76 s/source`.

Interpretation: v161 already improved the direction in which a clear tour terminates; v162 removes a remaining expensive verification tail at k=13 without causing an observed 13/14 miss in the guard set.
