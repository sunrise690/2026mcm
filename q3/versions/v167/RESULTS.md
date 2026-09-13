# Q3 v167 tuned low-count exploration caps

Changes vs v166:
- keep 60 s bounded final validation and lean info scans;
- add exploration caps for low counts: k=10 -> 260 s, k=11 -> 240 s;
- keep k=12..15 caps at 220/180/160/140 s.

Why 240 s at k=11:
- stratified-random true-N=11 case had next exploration cost ~254.6 s and was already fully cleared; skipping it saved a large verification detour;
- true-N=12 case with one hidden source had next exploration cost ~222.9 s, so 240 s still allows that useful search and avoids the extra miss seen with a 220 s cap.

## Stratified-random validation (2 seeds per true N=10..16)
- N=10: 265.91, 242.57; 2/2 full clear; mean 254.24
- N=11: 209.22 full clear; 196.47 with 10/11 cleared; mean 202.84
- N=12: 235.25, 249.05; 2/2 full clear; mean 242.15
- N=13: 230.84, 231.86; 2/2 full clear; mean 231.35
- N=14: 233.36, 231.83; 2/2 full clear; mean 232.60
- N=15: 208.15, 201.50; 2/2 full clear; mean 204.82
- N=16: 227.00, 242.63; 2/2 full clear; mean 234.81

Overall full-clear rate: 13/14 = 92.9%.
Mean of N-group means: 228.97 s/source.
Worst run: 265.91 s/source.

Important: no new miss vs v166. The only miss is still the same hard N=11 coverage-hole seed 7809053, and it misses exactly one source.
