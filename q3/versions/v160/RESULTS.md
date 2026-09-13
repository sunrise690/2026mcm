# Q3 v160 validation

Change from v159: only the k=10 stop threshold is adjusted from 0.62 to 0.58.

Low-source fixed set (15 seeds across N=10/11/12):
- Full-clear: 15/15
- Sample mean: 276.99 s/source
- N=10 mean: 276.03
- N=11 mean: 269.13
- N=12 mean: 285.81

For comparison, v159 on the same low-source set:
- Full-clear: 15/15
- Sample mean: 279.89 s/source
- N=10 mean: 284.72
- N=11 mean: 269.13
- N=12 mean: 285.81

Higher-source safety check (12 seeds across N=13..16):
- Full-clear: 12/12
- N=13 mean: 242.19
- N=14 mean: 233.10
- N=15 mean: 219.66
- N=16 mean: 189.56

Conclusion: 0.58 is the current best tested k=10 threshold. More aggressive 0.54/0.50 did not improve the aggregate and caused worse route outcomes on some N=12 cases.
