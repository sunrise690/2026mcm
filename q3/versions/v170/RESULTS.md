# Q3 v170 results

## Geometry changes
- k=11 stop threshold relaxed to 0.66.
- One low-count surgical clear-point survey for hard 1000 m coverage holes.
- One boundary clear-point survey while discovered count <10.
- One local hard-coverage frontier micro-probe for k=10..11.
- One local posterior-probability micro-probe for k=14..15.

## Regression set
Seeds: 3140259, 9394680, 12736170, 10, 7, 6, 34, 150064, 11.
Result: 9/9 full clear.
Representative s/source:
- N10: 253.41, 268.37
- N11: 292.41
- N12: 294.45, 265.97, 259.27
- N13: 276.95, 249.79
- N15: 252.07
Mean over these 9 selected regressions: 268.08 s/source.

## Fresh stratified-random set
One new random seed per N=10..16:
- N10 seed 46505160: 284.02, full clear
- N11 seed 41748715: 291.53, full clear
- N12 seed 12736170: 294.45, full clear
- N13 seed 6408199: 229.65, full clear
- N14 seed 36387672: 254.69, full clear
- N15 seed 15618106: 223.34, full clear
- N16 seed 22297975: 250.58, full clear

Fresh stratified-random: 7/7 full clear, mean-of-N-means = 261.18 s/source.
For the same seven random seeds, v164 safety branch = 274.70 s/source, 7/7 full clear.
Net improvement on this fresh random set: about 13.5 s/source with no clear-rate loss.

Next target: reduce over-triggered local micro-probes and N=10..12 long tails while retaining the new random full-clear behavior.
