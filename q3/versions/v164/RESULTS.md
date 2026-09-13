# Q3 v164 random-seed safety branch

Purpose: use random/stratified-random seeds to expose generalization failures that fixed regression seeds missed.

## Key finding from v163
A stratified random batch (2 seeds per N=10..16) exposed two early-stop misses:
- seed 3140259: N=13, cleared 12/13, 232.61 s/source
- seed 9394680: N=15, cleared 14/15, 209.21 s/source

Both stopped with generic coverage estimate around 0.99, showing the previous posterior stop rule was over-confident on some layouts.

## v164 safety change
Raise stop thresholds only for k=12..15:
- k=12: 0.93
- k=13: 0.90
- k=14: 0.93
- k=15: 0.94

## Focused random validation
9 random/stratified-random cases used for the safety check: 9/9 full clear.

Notable repaired misses:
- seed 3140259: 12/13 -> 13/13, 263.14 s/source
- seed 9394680: 14/15 -> 15/15, 257.74 s/source

Other checked cases:
- N=14: 254.87, 205.07 s/source (both full clear)
- N=15: 234.89 s/source (full clear)
- N=16: 197.11, 220.92 s/source (full clear)
- N=12: 286.08, 288.19 s/source (both full clear)

Mean over these 9 focused cases: 245.33 s/source.

Conclusion: v164 is a safety branch, not yet the fastest branch. Next target is bounded single final validation: preserve these repaired clear rates while recovering the extra 30-50 s/source on some N=13..15 cases.
