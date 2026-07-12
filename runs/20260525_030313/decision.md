# Decision: REVERT

- Candidate: `prompts/candidates/candidate_1779646345_risk_repair.md`
- Baseline dev: `runs/20260524_041843` (`88.03`)
- Candidate dev: `83.14`
- Decision: reject

Reason:
- Overall score regressed by `-4.89`.
- Legal case average dropped from `74.67` to `64.83`.
- Risk perfect rate was `88.9%`, below the zero-risk acceptance rule.
- The repair was too broad: banning answer formats and adding conservative law wording increased `F03` and `F04`.

Action:
- Do not promote to baseline.
- Keep only as failed experiment evidence.
