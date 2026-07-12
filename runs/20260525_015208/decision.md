# Decision

- decision: REVERT
- source_prompt: prompts/candidates/user_prompt_20260525_hybrid.md
- source_note: 使用者提供長版提示詞後，壓縮並融合 baseline 形成 hybrid 候選。
- smoke_run: runs/20260525_014821
- dev_run: runs/20260525_015208
- baseline_dev_run: runs/20260524_041843
- score_diff: -0.61
- reason: dev 平均分未提升，且比較題退步 -3.17、法律案例題退步 -4.00，風險滿分率僅 94.4%。
- elite_saved: 0
