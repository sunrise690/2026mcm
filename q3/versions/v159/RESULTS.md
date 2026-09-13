# Q3 v159 validation

Small fixed validation set, 16 representative seeds across N=10..14.

- Full-clear: 16/16
- Sample mean time: 249.29 s/source
- N=10 mean: 262.30
- N=11 mean: 259.00
- N=12 mean: 271.29
- N=13 mean: 242.19
- N=14 mean: 228.66

Main changes:
1. N=10 stop threshold lowered from 0.74 to 0.62 to remove expensive final verification when the map is likely exactly 10 sources.
2. Receding-horizon probe planning is retained instead of locking a stale future hotspot.
3. At k=13, the finishing probe now maximizes hidden-source detection probability instead of choosing a cheaper low-probability finishing probe. This fixed the previously observed 13/14 miss on the hard N=14 seed.

Next target: reduce N=10..12 cross-map tail latency while keeping the current 16/16 clear result on this fixed validation set.
