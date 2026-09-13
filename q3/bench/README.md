# Q3 <200 optimizer bench

Temporary reproducible benchmark harness for the `q3-opt-200` branch. It restores the exact supplied offline simulator, selects deterministic local seeds from 1000 onward until each N=10..16 bucket is filled, and reports the mean of the seven per-N means plus full-clear counts.
