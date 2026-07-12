# Decision

- decision: REVERT
- stage: holdout
- acceptance_mode: pragmatic
- candidate: `prompts/candidates/candidate_1779646345.md`
- smoke_run: `runs/20260525_062748`
- dev_run: `runs/20260525_021650`
- holdout_run: `runs/20260525_062911`
- baseline_dev_run: `runs/20260524_041843`
- baseline_holdout_run: `runs/20260524_162523`

Reason:
- Dev passed under pragmatic acceptance: `90.64` vs baseline `88.03` (`+2.61`).
- Holdout failed: `86.61` vs baseline `89.44` (`-2.83`).
- Holdout risk perfect rate dropped to `83.3%`.
- Holdout `F12` increased from `1` to `3`.
- Holdout comparison questions regressed by `-10.67`.

Action:
- Do not promote this candidate to `prompts/baseline.md`.
- Keep it as `legal_case` specialist evidence only.
- Future automatic promotion should use pragmatic dev acceptance, but holdout remains a hard promotion gate.
