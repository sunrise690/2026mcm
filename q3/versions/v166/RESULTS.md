# Q3 v166 speed-risk60

Changes vs v165:
- final validation budget: 120 s -> 60 s;
- leaner `scan_info`: bootstrap 5, probe/exploration 3, post-service 2, final probe 2;
- keeps v165 single-bearing triangulation and N=12..15 exploration cost caps.

## Stratified-random validation
Two independent random seeds for each true N=10..16 (14 runs):

- N=10: 265.91, 242.57 s/source; 2/2 full clear
- N=11: 232.37 full clear; 249.99 with 10/11 cleared
- N=12: 235.25, 249.05 s/source; 2/2 full clear
- N=13: 230.84, 231.86 s/source; 2/2 full clear
- N=14: 233.36, 231.83 s/source; 2/2 full clear
- N=15: 208.15, 201.50 s/source; 2/2 full clear
- N=16: 227.00, 242.63 s/source; 2/2 full clear

Full-clear rate: 13/14 = 92.9%.
Mean of N-group means: 234.45 s/source.
No additional misses relative to v165; the only miss is the same hard N=11 coverage-hole seed (7809053).

A 0 s final-validation experiment added an N=14 miss, so 60 s is the current observed risk/speed boundary on this regression set.
