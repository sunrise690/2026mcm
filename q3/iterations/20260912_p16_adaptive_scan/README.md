# Q3 posterior-risk adaptive scan iteration

This iteration adds two experimental structures to the observation-only offline controller:

- posterior-risk adaptive route scanning: reduce the scan budget only when the posterior probability of a 16-source case is below a configured boundary;
- one-shot terminal route probe: insert a survey point into the remaining clear route, invalidate it when a later discovery changes the posterior, and keep low-source/high-source boundary guards.

The offline runner now prints the key metrics directly after every batch: full-clear count, source-clear rate, mean seconds per source, true-source-normalized mean, weighted mean, P90, N10-N16 grouped means, and the target verdict.

## Evidence

The global P16<0.05 candidate improved the fixed 35-seed mean from 231.1383 to 230.6262 s/source with 35/35 full clears and reduced P90 from 266.6040 to 261.8525. On the independent 70-seed holdout it cleared 67/70, adding a failure on seed 10073 relative to the reliable dynamic-max8 baseline. It is therefore retained as an experimental candidate and is not promoted as the default.

The safe13 boundary guard restored seed 10073 in the targeted regression set (10/10 full clears), but its measured gain was small. The reliable default remains dynamic-max8. All evaluations use the local offline simulator and observation-only client.
