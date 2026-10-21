# Issue #3: DEV variance and promotion research

**Decision: NARROW.** This is a zero-network, synthetic research probe. It does not change `route_evolve.py`, `scripts/compare_runs.py`, champion state, or the production acceptance threshold. A real-model DEV canary with measured noise and spend is still required before adopting a live promotion rule.

## Current baseline

At `master@01dc864c04a052356e365ea877cae092067b44fa` (after PR #10), `route_evolve.evolve_one_type()` evaluates the current champion once on each DEV and holdout subset. For each candidate it runs one DEV evaluation and `compare_run()`, then one holdout evaluation and `compare_run()`, then calls `save_champion()` if both pass. It reuses the accepted candidate runs as the next baselines. `scripts.compare_runs.compare()` has a score condition of `score_diff >= thresholds.dev_min_improvement` (default `+2.0`) or `avg_new >= 92` without regression, alongside other existing risk/type/evidence gates. The tests in this change replay the actual comparator with a one-run lucky score and pin the route call sequence with deterministic stubs. The simulator isolates the **score** condition with all other gates held passing; its rates are not whole-product promotion rates.

## Reproduce the synthetic experiment

```sh
python -m research.variance_promotion --seed 20260929 --cases 500 --calibration-pairs 24 --min-pairs 2 --max-pairs 5 --budget-eval-units 10 --guard-multiplier 1.0 --output docs/research/variance-promotion-guard1.json
python -m research.variance_promotion --seed 20260929 --cases 500 --calibration-pairs 24 --min-pairs 2 --max-pairs 5 --budget-eval-units 10 --guard-multiplier 2.0 --output docs/research/variance-promotion-guard2.json
python -m pytest tests/test_variance_promotion_research.py -q -o addopts=
```

Each scenario has 500 independent synthetic cases, four DEV items per trial, and an exact reproducible seed per paired trial. The candidate's true improvement is either `0` or `+3`. A shared `N(0,1)` item perturbation plus independent baseline/candidate `N(0,2)` perturbations produce paired scores. A separate 24-pair fixed-prompt baseline/control calibration estimates score, risk, and type-level paired dispersion. The two illustrative guard multipliers show policy sensitivity; neither is a validated confidence level, p-value, or production default. Each pair costs two synthetic evaluation units, with a hard cap of ten units per case. Provider tokens, USD cost, and latency remain `UNKNOWN`.

| True score delta | Rule | PROMOTE | REJECT | INCONCLUSIVE | Evaluation units for 500 cases |
| --- | --- | ---: | ---: | ---: | ---: |
| 0 | Current single-run score condition | 38 | 462 | 0 | 1,000 |
| 0 | Paired research rule, multiplier 1.0 | 1 | 494 | 5 | 2,274 |
| 0 | Paired research rule, multiplier 2.0 | 0 | 432 | 68 | 3,162 |
| +3 | Current single-run score condition | 369 | 131 | 0 | 1,000 |
| +3 | Paired research rule, multiplier 1.0 | 381 | 13 | 106 | 3,176 |
| +3 | Paired research rule, multiplier 2.0 | 176 | 0 | 324 | 4,370 |

The separate calibration cost is 48 synthetic evaluation units for each report. The guarded rule reduces false promotions in this **chosen synthetic world**, while a wider guard produces more inconclusive results and spends more evaluations. This is a policy tradeoff, not evidence that either multiplier improves real MiniMax/judge decisions. The paired rule can stop after two pairs when the calibrated margin is clear; otherwise it consumes up to the cap and returns `INCONCLUSIVE_NEEDS_MORE_TRIALS`. A failed existing hard gate always rejects before score comparison. Missing/cached/error trials do not count as independent replicates. Changes to the dataset, model, judge, evaluator, scorer, or calibration cohort return `BLOCKED_EVIDENCE_DRIFT`.

## Receipt and holdout boundary

`research.variance_promotion` defines a versioned `EvaluationReplicateSet`-style receipt: prompt SHA-256; DEV dataset hash; provider/model/judge/evaluator/scorer cohort; ordered replicate index and an actual synthetic trial seed or `null` when no seed is controllable; per-item scores, risk scores, types, and failures; score/risk/type dispersion; separately status-marked primary, judge, and retry usage; and latency status. It rejects holdout input. The synthetic report stores one complete paired receipt and the calibration profile. The `evaluator_sha256` and `scorer_sha256` in these reports hash this module's normalized source bytes; synthetic provider/judge identifiers are explicitly labeled synthetic. A live adapter would have to supply artifact hashes and measured or explicitly unknown usage without claiming seed reproducibility when the provider offers none.

Only DEV aggregate evidence is eligible to inform mutation. Holdout should be a bounded final gate after a candidate has cleared DEV; its item-level outcomes and repeated pass/fail probes must stay out of mutation prompts. The current route code logs holdout decisions, so this isolation is a **design recommendation**, not a claim that the current automation fully enforces it. This research module neither reads nor runs holdout.

## Next evidence needed

1. Run a small fixed-prompt, fixed-DEV real-model calibration with cache bypass, exact dataset/prompt/model/judge/evaluator hashes, independent attempts, invalid-trial accounting, and a pre-authorized token/USD/time cap. `scripts/measure_noise.py` has exploratory repeated calls but defaults to cache reuse and lacks a complete hard spend cap; do not use its default mode as live independent evidence.
2. Pair baseline/candidate on the same items and provider cohort. Measure primary generation, judge scoring, retry spend, and latency separately; compare the observed paired dispersion and cost with this synthetic model. Mark a profile stale whenever its cohort changes.
3. Select any numerical margin and replication cap from those empirical DEV results, then test a bounded final holdout gate without feeding its item-level outcome to mutation. Keep `INCONCLUSIVE` when the budget ends.

Until those checks and the repository's required CI matrix execute, the recommendation is **DEV-only calibration followed by budget-capped adaptive paired replication, with no fixed production replicate count and no repeated holdout probing**. No live reliability or cost improvement is claimed here.
