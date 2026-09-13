# Q3 v165 speed-risk branch

Main changes from v164/v163:
- single final validation probe, hard budget 120 s;
- if all currently known sources are cleared and N=12..15, reject an exploration whose estimated cost exceeds an N-dependent cap (12:220s, 13:180s, 14:160s, 15:140s); accept the residual miss risk instead;
- for a source with only one bearing and very high uncertainty (>220m), take one short lateral triangulation measurement before attempting the long direct clear route.

## Stratified-random validation
Two independent seeds for each true N=10..16 (14 runs total):

- N=10: 265.91, 242.57 s/source; 2/2 full clear
- N=11: 232.37 full clear; 249.99 with 10/11 cleared
- N=12: 235.25, 253.79; 2/2 full clear
- N=13: 230.84, 231.86; 2/2 full clear
- N=14: 233.36, 236.32; 2/2 full clear
- N=15: 209.45, 208.60; 2/2 full clear
- N=16: 227.51, 242.63; 2/2 full clear

Full-clear rate: 13/14 = 92.9%.
Mean of N-group means: 235.75 s/source.
Std across these 14 runs: about 14.85 s/source.
Worst avg: 265.91 s/source.

Important: this is explicitly a speed-risk branch, not the safest branch. The one miss is a true N=11 layout where only 10 sources were ever discovered; the missed source lies in a hard coverage hole. v164 remains the safer reference branch.

A rejected experiment that biased the k=8/9 TSP endpoint toward the posterior hotspot caused a severe 13/16 miss on a random N=16 case, so that geometry change is not included here.
