# Decision: ROUTE_RETAINED_AS_EXPERIMENT

- Route: `prompts/routes/baseline_legal_case.json`
- Baseline dev: `runs/20260524_041843` (`88.03`)
- Routed dev: `89.03`
- Decision: retain experiment, do not promote

Reason:
- Overall score improved by `+1.00`, but did not reach the `+2.00` acceptance threshold.
- Legal case improved from `74.67` to `84.17`.
- Practical questions regressed from `90.17` to `86.83`, exceeding the `3` point regression limit.
- Risk perfect rate was `94.4%`, below the zero-risk acceptance rule.

Action:
- Keep the route file for future testing.
- Do not update `prompts/baseline.md`, `prompts/current.md`, or `prompts/baseline.meta.json`.
- Next best optimization: evolve a practical-question champion or add route-level acceptance logic before holdout.
