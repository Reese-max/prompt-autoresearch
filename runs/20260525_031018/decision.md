# Decision: REVERT

- Candidate: `prompts/candidates/candidate_1779646345_risk_repair_v2.md`
- Baseline dev: `runs/20260524_041843` (`88.03`)
- Candidate dev: `86.83`
- Decision: reject

Reason:
- Overall score regressed by `-1.19`.
- Legal case improved from `74.67` to `84.83`, but comparison, commentary, and practical questions regressed too much.
- Risk perfect rate was `86.1%`, below the zero-risk acceptance rule.

Action:
- Do not promote to baseline.
- The result supports keeping `prompts/champions/legal_case.md` as a specialist prompt, not merging it into the general daily prompt.
