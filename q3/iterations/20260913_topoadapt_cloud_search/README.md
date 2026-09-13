# Q3 adaptive topology cloud search (2026-09-13)

This iteration starts from `alg_topoadapt_k10_r75` in the reproducible package
`q3_best_202s_topoadapt_k10_r75.zip`.

Package SHA256:

```text
9c3fea695d8424a56526cd56b08abab77199f7a363beb0f0c892543f1e20a662
```

The package was reproduced on the cloud on the same 12 N14-N16 seeds:
12/12 full clear and 202.159973 seconds per source. This is a high-source
screening result, not an N10-N16 conclusion and not a formal independent test.

The cloud search keeps routing observation-adaptive. It does not install a fixed
route. Each round uses a full-clear hard gate, a balanced 14-case N10-N16 screen,
and a separate balanced 35-case N10-N16 expansion screen. These two seed sets
are optimization screens only; a later untouched holdout is still required.

The search varies route suffix locking, insertion detour, adaptive regret, dynamic
discovery value, dynamic-route activation count, and direct-probe detour. It runs
independently from `feedback_v2_q3` with eight workers.

Round 1 expansion screen (35 balanced N10-N16 cases):

- Fastest finalist: `topoadapt_r01_10`.
- Full-clear runs: 32/35; four sources were missed.
- Mean on full-clear runs: 237.910820 seconds per source.
- Decision: rejected by the full-clear hard gate; the search center remained the
  reproduced `alg_topoadapt_k10_r75` configuration for round 2.

This round is negative screening evidence. Its speed must not be reported as an
accepted Q3 result because it did not preserve full clear.
