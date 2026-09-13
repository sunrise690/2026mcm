# Q3 v163 quick validation

Changes:
- based on v162
- keep v161 adaptive route-endpoint attraction
- keep k=13 stop threshold at 0.80
- widen only the k=12 finishing-probe admissible detection-probability gap to 0.15, allowing a cheaper finishing probe when posterior confidence is already sufficient

Quick fixed-seed checks:

| seed | N | cleared | avg s/source |
|---:|---:|---:|---:|
| 7 | 12 | 12/12 | 235.52 |
| 10 | 12 | 12/12 | 265.97 |
| 19 | 15 | 15/15 | 204.47 |

Compared with v162:
- seed 7: 235.52 -> 235.52
- seed 10: 268.14 -> 265.97
- seed 19: 204.47 -> 204.47

Quick check clear rate: 3/3 full clear.

Rejected experiments in the same iteration:
- partial unknown-channel scans at clear points: much worse because conservative coverage then forced extra cross-map exploration
- mandatory third survey before clearing when known<10: much worse due to upfront movement cost
