# Product Board Audit — prompt-autoresearch

Audit date: 2026-09-12 (Asia/Taipei)  
Repository baseline: `master@1b8467c2665a13dad6680a909a98ac033a6aa5cc`  
Scope: static code/config/documentation review, GitHub Issue/PR/Actions evidence, fresh public competitor research, 50 synthetic-persona simulation, red team, issue closure.  
Evidence labels: **CONFIRMED** = directly observed in repository/CI; **LIKELY** = static inference; **UNKNOWN / NEEDS_RUNTIME_VERIFICATION** = requires execution or human study. Synthetic personas are simulations, not real participants or market research.

## Executive Summary

Decision: **INVEST / SIMPLIFY**.

The product should become a trustworthy, local-first prompt research and promotion harness for Taiwanese civil-service essay prompts—not a general hosted eval platform. Its moat is the vertical question/rubric corpus, hard risk gates, prompt lineage, and evidence-first promotion workflow.

Two root findings passed the Quality Gate:

1. **P1 RELIABILITY / TECH_DEBT — NEW #4:** the default-branch evidence/report contract is red across all 9 declared OS/Python cells. Latest readable Linux 3.11 evidence reports 8 failed / 1381 passed; complete fixtures are classified `INCOMPLETE_EVIDENCE`, and raw `PermissionError` / `KeyError` paths escape.
2. **P2 RESEARCH_REQUIRED / RELIABILITY — UPDATED #3:** a noise probe exists, but checked-in evidence is mock-only and the actual route promotion path still uses one candidate dev run plus one holdout run, then promotes and makes those runs the new baselines.

CEO — if resources permit only three moves:
1. Restore one canonical, typed best-version evidence contract and return default-branch CI to green (#4).
2. Use the existing noise probe to design a budget-aware paired replicate receipt and typed `INCONCLUSIVE` decision (#3).
3. Run one bounded independent legal-SME calibration after the technical gates are trustworthy.

Do **not** build a hosted multi-tenant eval SaaS, generic agent observability platform, another optimizer framework, or mobile app.

## Project Discovery

| Dimension | Assessment | Evidence |
|---|---|---|
| Product type | Local-first autonomous prompt research/evaluation tool for Taiwan national-exam essay prompts | CONFIRMED: `program.md`, `route_evolve.py`, questions/rubrics/prompts |
| Maturity | Feature-rich research prototype with extensive fixtures/evidence; release governance currently blocked | CONFIRMED |
| Target users | Prompt researchers, legal-exam content specialists, maintainers/QA | LIKELY from code and docs |
| Core job | Generate bounded prompt mutations, evaluate smoke/dev/holdout, promote or rollback with evidence | CONFIRMED |
| Primary value | Vertical legal corpus + hard risk gates + auditable prompt lineage | CONFIRMED |
| Largest weakness | Promotion trust: CI evidence contract is red and stochastic promotion is not distribution-aware | CONFIRMED |
| Runtime | No production deployment observed; real provider, usability, legal validity, accessibility and cost behavior remain unverified | UNKNOWN |
| Root README | Missing on current `master`; PR #2 adds contract/offline preflight | CONFIRMED; duplicate tracked by #1 |
| Config | `config.json` is runtime canonical; `config.yaml` is a reporting/reproduction input and may drift | CONFIRMED from PR #2 documentation |
| CI | 9-cell Linux/macOS/Windows × Python 3.10–3.12 matrix, aggregate required gate; all latest readable cells fail | CONFIRMED |
| Tests | 1,381 pass and 8 fail in latest readable L311 PR run; failures cluster in best-version evidence/report tests | CONFIRMED |
| Prior audit | `docs/audits/50-persona-round-1-2026-09-06.md`; no prior `.github/quality-audits/` product-board report on master | CONFIRMED |
| Open work | #1/PR #2 repository contract; #3 variance-aware research; new #4 CI/evidence contract | CONFIRMED |

### Key code path

`route_evolve.py::evolve_one_type()` evaluates a current baseline once on dev/holdout, evaluates each candidate once on dev and once on holdout, saves the champion after those single comparisons, then replaces `base_dev_run` and `base_holdout_run` with the candidate runs. `evaluate_route()` also runs one dev and one holdout comparison. This is code-confirmed; the real false-promotion rate is unknown.

`scripts/measure_noise.py` is a useful exploratory probe with mock/live modes, repetitions, cache bypass, prompt hash, per-question dispersion and JSON output. However:
- `docs/noise-report.json` is explicitly mock (`mode=mock`, seed 42, 12 questions × 5 repetitions);
- the script is not integrated into promotion decisions;
- latest readable coverage reports it at 0%;
- no canonical replicate-set/staleness/inconclusive contract exists.

## Competitive Intelligence (fresh check: 2026-09-11 UTC)

Sources: [LangSmith repetitions](https://docs.langchain.com/langsmith/repetition), [LangSmith evaluation](https://docs.langchain.com/langsmith/evaluation), [promptfoo repetition/temperature guide](https://www.promptfoo.dev/docs/guides/evaluate-llm-temperature/), [promptfoo caching](https://www.promptfoo.dev/docs/configuration/caching/), [DSPy](https://dspy.ai/), [Braintrust](https://www.braintrust.dev/), [OpenAI Evals documentation index](https://developers.openai.com/).

| Capability | prompt-autoresearch | LangSmith | promptfoo | DSPy | Braintrust | Manual scripts |
|---|---|---|---|---|---|---|
| Target user | Legal prompt researcher | AI app teams | Eval/red-team engineers | LM program researchers | Product/ML teams | Individual engineer |
| Value proposition | Vertical legal prompt evolution | Hosted eval + observability | Provider-neutral assertions/evals | Programmatic LM optimization | Trace→dataset→experiment | Maximum control |
| Killer feature | Hard legal risk gates + corpus | Run drill-down/production loop | CLI/config portability | Optimizer ecosystem | Trace discovery and team workflow | Simplicity |
| Repetitions/variance | Probe only; no promotion integration | Explicit repetitions, mean/std | `--repeat`, cache controls | Metrics/optimizers; policy chosen by user | Experiment/scorer analytics | Custom |
| Holdout isolation | Protocol-only tracked fixture; repeated outcome exposure | Dataset/experiment separation | User-configured | Trainset/evalset user-configured | Versioned datasets | User-configured |
| Evidence lineage | Rich tracked manifests, currently inconsistent | Hosted experiment records | Config/results/cache | Saved program/metric workflow | Versioned datasets/traces | Ad hoc |
| Onboarding | Root README absent on master | Hosted UI/SDK docs | CLI quick start | Python framework docs | Hosted platform | Varies |
| Automation/AI | Autonomous mutation and route champions | Experiment/online eval workflows | Eval and red-team automation | Multiple optimizers | Loop/discovery/scoring | None by default |
| Integrations/API | MiniMax-centric Python/local API | Broad SDK ecosystem | Many providers/CI | Python LM stack | SDKs/MCP/observability | Unlimited but manual |
| Mobile | None | Web dashboard | Web viewer | None | Web dashboard | None |
| Reliability | Required matrix exists but red | Managed platform | Mature CLI assertions | Large OSS ecosystem | Managed platform | Operator-dependent |
| Security/privacy | Local artifacts; boundary docs pending merge | Hosted/hybrid options | Local/open source options | Open source | Hosted/hybrid, enterprise controls | Local |
| Pricing | Provider cost; no product fee stated | Hosted tiers | Open source + provider costs | Open source + provider costs | Hosted tiers | Labor/provider costs |
| Open/closed | Repository private; no LICENSE | Closed service/SDKs | Open source core | MIT | Closed service/SDKs | N/A |
| Community/docs | Extensive internal docs; noisy tree | Strong docs/ecosystem | Strong docs/community | Large OSS community | Strong commercial docs | None |
| Distribution | Git clone/local | Cloud/SDK | npm/CLI | PyPI | Cloud/SDK | Copy scripts |

### Gap classification

- **MUST MATCH:** trustworthy green baseline CI; typed evidence errors; independent repetition semantics; cache/provenance receipts.
- **SHOULD BE BETTER:** vertical legal hard gates; budget-aware adaptive repetition; explicit `INCONCLUSIVE`; failure receipts understandable without hosted UI.
- **DIFFERENTIATOR:** Taiwanese legal essay corpus, per-type champions, risk regression, local/private research, auditable lineage.
- **DO NOT COPY:** hosted multi-tenant observability, broad provider marketplace, team billing/RBAC, generic agent tracing, mobile app.

## Virtual Executive Board

- **CEO:** Focus on evidence trust, variance-aware promotion, then SME validity. Stop platform expansion.
- **CPO:** Serve legal prompt researchers and maintainers; the product promise is “promotion you can defend,” not “more prompts.”
- **CTO:** Consolidate producer/consumer schema contracts before adding decision states. Multiple entrypoints and tracked generated artifacts magnify drift.
- **Staff/Principal Engineer:** Build minimal canonical valid/invalid fixtures, paired replicate receipts, and cohort invalidation on model/judge/dataset hashes.
- **UX Lead:** A root contract and one decision summary matter more than another dashboard. PR #2 partially addresses onboarding.
- **UX Researcher:** Persona simulation cannot validate student/teacher comprehension; plan a small moderated study only after runtime exists.
- **Growth Lead:** Distribution should come from reproducible legal-domain results. Do not market “90+” without independent evidence.
- **CFO/Business Analyst:** Measure cost per reliable uplift and false-promotion reduction; adaptive sampling beats fixed repetition everywhere.
- **Security/Privacy Lead:** Preserve local/no-production boundary; do not put real cases, identities, provider responses or secrets into fixtures/issues.
- **QA Lead:** #4 is the release blocker. Fail closed with typed results; never xfail or loosen evidence completeness to obtain green.
- **SRE Lead:** Require exact-SHA receipts and two consecutive green matrices. Red baseline destroys signal.
- **Accessibility Specialist:** No browser/assistive-tech test was run; accessibility stays UNKNOWN, not a defect claim.
- **Customer Support Lead:** Make `mock`, `live`, `inconclusive`, and “why rejected” obvious in every report.

Cross-review:
- Consensus: #4 before #3 implementation; fix/simplify before add.
- Minority opinion: shrink the 9-cell matrix. Rejected for this round because failures reproduce across all platforms; support-policy reduction is not root-cause repair.
- Minority opinion: mandate five repetitions. Rejected because N=5 comes from a mock probe/default, not a calibrated decision boundary.
- Minority opinion: replace the evaluator with DSPy/LangSmith/promptfoo. Rejected; they are reference points, not evidence that a rewrite beats the vertical workflow.

## 50 Synthetic Personas

Protocol: 30 regression-baseline personas (P01–P30) and 20 rotating/edge personas (P31–P50). These are synthetic simulations, not human research.

| ID | Background | Goal | Expectation | Task | Journey | Friction | Outcome | Comment | Severity | Suggestion |
|---|---|---|---|---|---|---|---|---|---|---|
| P01 | 28／Prompt engineer／高熟練／Linux laptop | 穩定提升申論 prompt | 可重播比較 | 跑一輪 route evolution | 產生候選→dev→holdout→promotion | 單次分數看不出幸運值 | FAIL | 需要分布，不只 best run | P1 | paired replicates + inconclusive |
| P02 | 34／QA engineer／高熟練／Windows desktop | 驗證 promotion gate | 所有 fixture 一致 | 跑 CI matrix | 安裝→pytest→aggregate gate | 8 個 evidence tests 失敗 | FAIL | baseline red 無法判斷新回歸 | P1 | 先修 #4 canonical fixture |
| P03 | 41／法律補教老師／中熟練／MacBook | 取得穩定高分範文 | 風險項不倒退 | 比較 champion | 選題→生成→檢視 rubric | 沒有真人閱卷校準 | PARTIAL | 分數高不等於教學有效 | P2 | 保留人工抽查 gate |
| P04 | 23／國考考生／中熟練／Android 4G | 得到可靠申論架構 | 答案不亂編法條 | 使用最佳 prompt | 選題→生成→閱讀 | runtime 未部署、成果未知 | CANNOT_VERIFY | 不能把 repository test 當使用者效果 | P2 | 小規模真人可用性研究 |
| P05 | 52／維運者／中熟練／Windows desktop | 在預算內長跑 | 成本可預測 | 設定 budget 後執行 | preflight→round→停止 | 預算於完整 round 後才檢查 | PARTIAL | 可能小幅超支 | P2 | receipt 記錄估算與實際 calls |
| P06 | 31／資料科學家／高熟練／Linux | 估計 noise | 真實重複樣本 | 執行 measure_noise | 選題→5 repeats→統計 | 目前 checked-in report 是 mock | FAIL | mock 只能驗 plumbing | P1 | 受控 canary + cohort hashes |
| P07 | 45／CFO persona／低熟練／iPad | 判斷研究是否值得投資 | 清楚成本／效益 | 看 dashboard | 開 UI→比較候選→決策 | 缺少 dollar-normalized uplift | PARTIAL | 沒有每改善點成本 | P2 | cost per reliable improvement |
| P08 | 37／SRE／高熟練／Linux | 信任 release gate | default branch 綠 | 查 Actions | 開 run→看 9-cell matrix | 所有格都紅 | FAIL | 紅色基線等於失去告警能力 | P1 | 兩次 exact-SHA 綠色 receipt |
| P09 | 29／開源維護者／高熟練／MacBook | 快速 onboarding | 根目錄有 contract | clone→讀 README→dry-run | root README 在 master 缺失 | FAIL | README 只在未合併 PR #2 | P2 | 完成 #1/PR #2，不另開 duplicate |
| P10 | 60／法律學者／低熟練／桌機 | 理解評分依據 | rubric 可審查 | 檢視規則與樣本 | 讀 program→rubrics→evidence | LLM judge 真實一致性未知 | CANNOT_VERIFY | 技術分數不能冒充學術效度 | P2 | SME blind sample |
| P11 | 26／ML engineer／高熟練／Linux | 比較 candidate distribution | paired item deltas | 執行 repeated eval | baseline/candidate 同題比較 | 沒有 replicate-set schema | FAIL | aggregate-only 會藏題型差異 | P1 | versioned paired receipt |
| P12 | 39／產品經理／中熟練／Windows | 決定何時 promote | 有 PROMOTE/REJECT/INCONCLUSIVE | 檢視 decision | 跑完→讀 decision.md | 目前主要是二元接受/拒絕 | FAIL | 證據不足不該硬判 | P1 | 加入 typed inconclusive |
| P13 | 33／資安工程師／高熟練／Linux | 避免敏感資料進題庫 | 清楚資料邊界 | 審查 fixtures/logs | 搜尋 secrets→檢查 docs | 無 runtime secret scan 結論 | CANNOT_VERIFY | 不要宣稱無洩漏 | P2 | 維持 source boundary + CI scan |
| P14 | 48／Accessibility reviewer／中熟練／NVDA+Windows | 操作本機 UI | 鍵盤/螢幕閱讀器可用 | 打開 index | Tab→選 prompt→執行 | 未做 runtime accessibility test | CANNOT_VERIFY | 靜態碼不足以宣稱可及 | P3 | 後續實機研究，不阻塞 #3/#4 |
| P15 | 22／新手研究助理／低熟練／Chromebook | 零成本試跑 | 不需 key | 執行 dry-run | 複製命令→preflight→停止 | 功能只在 PR #2 尚未進 master | PARTIAL | 文件與行為尚未成預設 | P2 | 沿用 #1/PR #2 |
| P16 | 36／Power user／高熟練／Linux | 多題型 champion | 題型 route 不互相傷害 | --all 演化 | 逐題型→route dev/holdout | 每次 holdout 都回饋成敗 | FAIL | 長跑會逐步學到 holdout gate | P1 | bounded final holdout |
| P17 | 44／統計學家／高熟練／R workstation | 檢驗 uplift | 估計不確定性 | 匯出每題分數 | 收集→paired bootstrap→decision | 沒有 canonical raw replicate receipt | FAIL | 不能先硬設 95% 或 N=5 | P1 | simulation-driven policy |
| P18 | 30／CI maintainer／高熟練／Ubuntu | 定位第一失配欄位 | 錯誤具診斷性 | 跑最小 test | pytest single fixture→trace | 目前多個 KeyError/PermissionError | FAIL | 需要 typed field diagnostics | P1 | minimal valid/invalid fixtures |
| P19 | 55／補教班主管／低熟練／iPhone | 選擇教學工具 | 可展示可解釋成果 | 比較產品 | 看範例→信任→採用 | 產品缺公開案例與 runtime證據 | CANNOT_VERIFY | 不應先做行銷 | P3 | 先證明 evidence reliability |
| P20 | 27／成本敏感開發者／高熟練／舊 laptop | 本機免費研究 | stdlib、無 SaaS | clone→mock | 跑 noise mock→讀 JSON | mock 數據易被誤當實測 | PARTIAL | metadata 有標 mock，但需醒目 gate | P2 | 禁止 mock 驅動 promotion |
| P21 | 32／LangSmith 使用者／高熟練／Mac | 比較 repetition UX | 看平均與標準差 | 切換工具 | 匯入 dataset→repetitions→inspect | 本產品無視覺 drill-down | SWITCH | 偏好 LangSmith 可觀察性 | P2 | 先 CLI receipts，不抄 UI |
| P22 | 29／promptfoo 使用者／高熟練／Linux | 跨 provider 重複 eval | repeat/cache 控制 | 切換工具 | config→repeat→assertions | 本產品綁 MiniMax 特定流程 | SWITCH | 偏好 promptfoo 通用性 | P2 | 保留垂直法律 moat |
| P23 | 35／DSPy 研究者／高熟練／GPU workstation | 最佳化整個 LM program | 模組化 optimizer | 切換工具 | signature→metric→compile | 本產品只優化 prompt/route | SWITCH | DSPy 更通用 | P3 | 不要重寫成 DSPy |
| P24 | 46／Braintrust 團隊 lead／中熟練／Cloud | 連結 production traces | 觀測→dataset→eval | 切換工具 | trace→cluster→experiment | 本產品非 production traffic | SWITCH | Braintrust 適合團隊治理 | P3 | 不建 observability SaaS |
| P25 | 25／獨立研究者／高熟練／Linux 低頻寬 | 可離線審查證據 | 所有關鍵 artifact tracked | clone shallow→讀報告 | tree 很大、生成物過多 | PARTIAL | repository 噪音提高理解成本 | P2 | 完成 #1 artifact retention |
| P26 | 40／資料治理者／中熟練／Windows | 追蹤 dataset lineage | hash 與 split 明確 | 查 manifests | prompt hash→run path→summary | baseline meta 路徑含 Windows separator | PARTIAL | 跨平台語意不乾淨 | P3 | 正規化 path；若獨立證據再建 issue |
| P27 | 38／法務 persona／低熟練／Web | 確認授權 | LICENSE 清楚 | 查看 repo | 首頁→license→reuse | 目前無 LICENSE | FAIL | 不可宣稱可再散布 | P3 | 由 owner 研究授權；本輪證據不足另開 |
| P28 | 24／研究實習生／低熟練／Windows | 了解 canonical config | 只有一份真相 | 改 threshold | 讀 yaml→改值→執行 | JSON runtime 與 YAML report 可漂移 | FAIL | 容易改錯消費者 | P2 | 先完成 #1 contract；再評估 schema sync |
| P29 | 43／模型供應商管理者／高熟練／Cloud | 處理 model drift | profile 過期可見 | 換模型版本 | 改 config→重跑→比較 | noise profile 無 model/judge cohort gate | FAIL | 跨版本不該混分布 | P1 | stale cohort on hash drift |
| P30 | 31／研究倫理 reviewer／中熟練／Mac | 避免過度宣稱 | 合成/真人分清楚 | 讀 audit | 查 evidence labels | 既有 noise report 明確 mock | SUCCESS | 標示良好但 promotion 未隔離 | P2 | 延續 CONFIRMED/LIKELY/UNKNOWN |
| P31 | 50／客服 lead／低熟練／iPad | 回答『為何被拒』 | reason code 可理解 | 查 decision | candidate→rejection→summary | typed evidence 有但 CI 破裂 | PARTIAL | 使用者會看到互相矛盾訊息 | P2 | 修 #4 後再改善文案 |
| P32 | 28／Reliability engineer／高熟練／Linux | 復現同一結論 | cache/seed 邊界清楚 | 重跑 noise | repeat→compare→rerun | cache 可能重播舊輸出；force 需人工選 | FAIL | 重複不等於獨立樣本 | P1 | receipt 記錄 cache identity |
| P33 | 57／閱卷委員／低熟練／紙本+桌機 | 確認分數代表性 | 盲評樣本 | 抽查答案 | 取樣→盲評→比較 judge | 尚無真人 gold set | CANNOT_VERIFY | 不能宣稱 90+ 真的高分 | P1 | SME calibration experiment |
| P34 | 21／考生／低熟練／手機弱網 | 快速得到答案 | 低延遲 | 使用 UI | 選題→等待→結果 | 無正式部署與行動測試 | CANNOT_VERIFY | 競品 UX 比較僅靜態 | P3 | 不開 mobile feature issue |
| P35 | 42／平台工程師／高熟練／Windows | 安全中斷與恢復 | 不重算付費 run | Ctrl+C→resume | 保留 artifacts→人工判斷 | 沒有自動 resume/spend de-dup | PARTIAL | 重跑可能重複花費 | P2 | receipt-based resume research later |
| P36 | 33／研究 lead／高熟練／Mac | 避免 holdout overfit | holdout 不回饋 mutation | 長跑 20 rounds | dev→holdout reject→下一輪 | 成敗本身可成 optimizer 訊號 | FAIL | 隱性 leakage 仍是 leakage | P1 | final-only/rotated hidden holdout |
| P37 | 47／CEO persona／中熟練／Laptop | 選三件事 | 可靠、簡單、差異化 | 看 roadmap | 問題→投資排序 | 功能很多但 gate 紅 | FAIL | 先修可信度再增 optimizer | P1 | #4→#3→SME canary |
| P38 | 39／CPO persona／中熟練／Tablet | 定義核心客群 | 法律 prompt researcher | 比較市場 | 研究 competitor→JTBD | 通用 eval 平台競爭太強 | PARTIAL | 垂直法律資料是選擇理由 | P2 | 聚焦垂直 evidence |
| P39 | 45／CTO persona／高熟練／Linux | 降低架構複雜度 | 一套 evidence contract | 審查 producers/consumers | trace schema→tests→CI | 生成物與多入口造成漂移 | FAIL | 不能再加平行框架 | P1 | 合併 schema，非重寫 |
| P40 | 29／UX researcher／中熟練／Mac | 觀察首次任務 | 10 分鐘內理解 | 新 clone walkthrough | 找 README→dry-run→結果 | master 無 root README | FAIL | 認知成本太高 | P2 | #1/PR #2 |
| P41 | 54／企業採購／低熟練／Windows | 評估安全與支援 | 版本、授權、SLA | 比較產品 | 文件→定價→部署 | 非 SaaS、無 license/SLA | SWITCH | 選 hosted competitor | P3 | 不追 enterprise SaaS |
| P42 | 26／OSS hacker／高熟練／Linux | 自訂 scorer | 可插拔 evaluator | 修改 scripts | fork→改 rubric→跑 test | 規則禁止改 evaluator 以防作弊 | PARTIAL | 限制是優點也是彈性代價 | P3 | 保留 hard boundary |
| P43 | 35／教育科技創業者／中熟練／Cloud | 多租戶 prompt lab | 帳號/協作 | 評估採用 | 登入→dataset→team review | 本產品是本機研究工具 | SWITCH | 偏好 LangSmith/Braintrust | P3 | DO NOT build multitenant |
| P44 | 62／低視力法律老師／低熟練／高對比桌機 | 讀取結果 | 可放大且語意清楚 | 使用本機 UI | zoom→keyboard→report | 未驗證 accessibility | CANNOT_VERIFY | 不可由 Persona 模擬宣稱 bug | P3 | 獨立 runtime study |
| P45 | 30／離線環境研究員／高熟練／air-gapped Linux | 檢查 pipeline | 不呼叫 provider | dry-run | preflight→fixtures→exit | master 入口仍需 PR #2 | PARTIAL | 離線 contract 未合併 | P2 | 完成既有 PR |
| P46 | 41／審計師／中熟練／Windows | 驗證每次 promotion | 不可變 receipt | 追 metadata | hash→run→decision→archive | 單次 baseline 指標可被 lucky run污染 | FAIL | lineage 正確不等於統計可靠 | P1 | replicate lineage + decision reason |
| P47 | 27／效能工程師／高熟練／Linux | 控制並發/延遲 | backpressure 可測 | 24 parallel | 啟動→limiter→完成 | 跨 process 總並發靠操作者 | PARTIAL | 沒有量測就不開性能 issue | P3 | 先 telemetry research |
| P48 | 36／Customer support／低熟練／Web | 解釋 mock vs live | 狀態醒目 | 閱讀 noise report | 打開 JSON→辨識 mode | JSON 有 mode 但非一般人友善 | PARTIAL | 可能被截圖誤傳 | P3 | 報告頁加 prominent provenance later |
| P49 | 32／Red-team analyst／高熟練／Linux | 挑戰 improvement claim | 避免 evaluator gaming | 檢查 mutation feedback | 讀 history→找 leakage | tracked holdout 與成敗回饋可被利用 | FAIL | 統計 gate 不能解決資料洩漏 | P1 | separate hidden final set |
| P50 | 44／Portfolio CEO／中熟練／Laptop | 減少專案重複 | 共用 evidence receipts | 比較 autodev/skill-foundry/cyber coach | 盤點 schema→尋共用層 | 每 repo 另造 receipt 風險 | PARTIAL | 應先共用 schema vocabulary | P2 | 共享契約，不強行 merge 產品 |

## Competitor Switching Test

Scenario: choose a tool for the persona's primary evaluation/prompt-optimization job with the currently evidenced product state.

| Choice | Personas | Synthetic preference share | Main reason |
|---|---:|---:|---|
| prompt-autoresearch | 17 | 34% | Vertical legal corpus, local control, hard risk gates |
| promptfoo | 11 | 22% | Portable provider/config/assertion workflow and explicit repeat/cache control |
| DSPy | 9 | 18% | Broader program optimization and optimizer ecosystem |
| LangSmith | 7 | 14% | Repetition inspection, experiment UX, managed workflow |
| Braintrust | 4 | 8% | Trace-to-dataset team workflow and observability |
| Manual scripts | 2 | 4% | Minimal dependency and maximum custom control |

This is a synthetic scenario result, not market share or a real survey. prompt-autoresearch loses primarily on baseline reliability, onboarding and statistical decision evidence; it wins on vertical fit, privacy/locality and hard legal-domain gates.

## Red Team

1. Persona mix overweights engineers and legal researchers; enterprise/team buyers may prefer hosted competitors regardless of feature parity.
2. A repeated-evaluation gate could add cost without improving validity if the judge itself is biased.
3. Statistical stability cannot repair holdout leakage or weak human/legal construct validity.
4. The tracked mock noise report can create false confidence; it must never set production thresholds.
5. Restoring CI may reveal tests that encode obsolete expectations; the solution is a versioned contract, not blindly making old assertions pass.
6. Green CI does not prove real provider behavior, legal correctness, usability, accessibility, or cost safety.
7. Adding another receipt/schema can worsen complexity unless it replaces competing implicit contracts.
8. The full 9-cell matrix may be larger than needed, but that is a product support decision, not a reason to bypass current failures.
9. “Competitor gap” is not an instruction to copy hosted dashboards or provider breadth.
10. Growth before trustworthy evidence would optimize claims rather than product value.
11. The product may be better as a narrow internal research instrument than a public commercial product.
12. Simplification opportunity: archive noisy generated artifacts under an explicit retention policy rather than adding search/UI over them.

## Findings and Quality Gate

| Finding | Type | Priority | Impact | Strategic value | Risk reduction | Confidence | Effort | Mapping |
|---|---|---:|---|---|---|---|---|---|
| Required matrix is red because best-version evidence/report fixtures and typed error contract disagree | RELIABILITY / TECH_DEBT | P1 | High | High | High | 0.97 | Medium | NEW [#4](https://github.com/Reese-max/prompt-autoresearch/issues/4) |
| Single-run dev/holdout promotion lacks tested replicate distribution, typed inconclusive, and holdout feedback isolation | RESEARCH_REQUIRED / RELIABILITY / COMPETITIVE_GAP | P2 | High | High | High | 0.91 gap / medium policy | Medium–High | UPDATED [#3](https://github.com/Reese-max/prompt-autoresearch/issues/3) |

Quality Gate: evidence PASS; distinctness PASS; actionability PASS; impact PASS; acceptance criteria PASS; duplicate check PASS; confidence recorded. Finding mapping 2/2 PASS.

### Duplicate Avoided

1. Missing root README → existing #1 / PR #2.
2. Offline dry-run/provider-key boundary → existing #1 / PR #2.
3. Runtime-vs-YAML config explanation → existing #1 / PR #2.
4. Generated artifact retention → existing #1 / PR #2.
5. Mock noise provenance → #3.
6. Cache independence for repeats → #3.
7. Model/judge/dataset drift → #3.
8. Holdout outcome leakage → #3.
9. All 9 matrix failures → one root #4.
10. PermissionError, KeyError and invalid positive fixtures → one schema-contract root #4.

## Roadmap

### NOW
- **FIX:** #4 canonical evidence fixture/error contract and exact-SHA green matrix.
- **SIMPLIFY:** complete #1/PR #2 repository contract without expanding into new features.
- **RESEARCH:** #3 deterministic known-noise simulation and replicate receipt, after #4.

### NEXT
- Bounded live-provider noise canary with cache/provenance receipts.
- Independent legal-SME gold sample and judge disagreement measurement.
- Decide canonical config/schema relationship and generated-artifact retention.

### LATER
- Better decision-summary UX and export.
- Carefully scoped evaluator/provider adapters only if vertical workflow demands them.
- Runtime accessibility/usability study if a real UI is distributed.

### DON'T
- Hosted multi-tenant SaaS, accounts/RBAC/billing.
- General observability/tracing platform.
- Native mobile app.
- Another LLM-as-judge as a substitute for independent calibration.
- Fixed 20× or uncalibrated N=5 repetition.
- Repeated holdout probing until a candidate passes.
- Xfail/skip or weakened evidence gates to obtain green CI.

## Change From Previous Round

- Previous 50-persona audit centered on repository contract, offline preflight and artifact boundaries (#1/PR #2).
- This round adds a full product-board report in the required `.github/quality-audits/` location.
- New CI evidence isolates a separate P1 best-version evidence-contract failure (#4).
- #3 is refined from an abstract variance gap to **PARTIALLY IMPLEMENTED / STILL REPRODUCIBLE**: a noise probe exists, but only mock evidence is checked in, coverage is 0%, and promotion remains single-run.
- No source/runtime feature was changed.

## Regression

- #1: **PARTIALLY FIXED / PR OPEN / NEEDS MERGE AND EXACT-SHA CI**. Not touched due active PR #2.
- #3: **PARTIALLY IMPLEMENTED / STILL REPRODUCIBLE / RESEARCH_RUNTIME_REQUIRED**. Noise probe exists; promotion gate remains unchanged.
- #4: **STILL REPRODUCIBLE** at the latest readable default and PR CI runs.
- Verified Fixed: none.

## Runtime Pending

- Real provider noise distribution and cost.
- Independent legal-SME validity and false-approval rate.
- Hidden/bounded holdout behavior under long runs.
- Clean-clone onboarding after PR #2.
- Browser/mobile/assistive-technology usability.
- Any production deployment or real-user outcome.

## Decision Memo

- **What this product should become:** a local, evidence-bound promotion harness for Taiwan legal-exam prompt research.
- **Who it should serve:** prompt researchers, legal content specialists, QA/maintainers and cost-conscious operators.
- **Why users choose it:** vertical corpus/rubrics, hard risk gates, local control, lineage and route champions.
- **Why users choose competitors:** better onboarding, hosted experiment inspection, provider breadth, explicit repetition/cache controls, collaboration and production traces.
- **Biggest competitive gaps:** trustworthy green baseline, typed evidence schema, calibrated uncertainty, holdout isolation, independent legal validity.
- **Potential moat:** vertical legal datasets/rubrics plus defensible, privacy-preserving promotion receipts.
- **Top priorities:** #4 CI contract; #3 variance/holdout research; SME calibration.
- **What NOT to build:** generic eval SaaS, team platform, observability stack, mobile app, marketplace.
- **Features worth removing/simplifying:** redundant tracked generated artifacts and implicit parallel evidence/config contracts, after retention review.
- **Biggest risks:** false promotion, holdout overfitting, judge bias, evidence drift, cost overruns, unsupported “90+” claims.
- **Next experiments:** minimal evidence fixture; known-noise false-promotion simulation; small bounded live canary; blinded SME sample.
- **Decision:** **INVEST / SIMPLIFY** — the vertical concept is valuable, but trust infrastructure must precede growth.

## Portfolio CEO Review

Overlap worth standardizing, not merging products:
- `autodev-ng`: exact-SHA evidence receipts and execution status vocabulary.
- `skill-foundry`: compatibility/staleness manifests.
- `cf-ai-router`: model lifecycle and provider drift.
- `cyber-prep-coach`: independent SME calibration.
- `prompt-autoresearch`: paired evaluation/holdout receipts.

Shared opportunity: a small versioned evidence vocabulary (artifact hash, dataset/model/judge version, state, reason, runtime boundary), not a common mega-framework.

Portfolio ranking for incremental investment:
1. `autodev-ng` — common delivery infrastructure.
2. `prompt-autoresearch` — strong vertical research moat after #4/#3.
3. `cyber-prep-coach` / exam products — user-facing value gated by SME evidence.
4. Generic/placeholder tools — maintain, simplify or archive unless differentiated.

## Mandatory Verification

- Total Findings: **2**
- New Issues Created: **1**
  - `Reese-max/prompt-autoresearch#4` — [P1][RELIABILITY] Restore the best-version evidence contract so the required matrix can pass — https://github.com/Reese-max/prompt-autoresearch/issues/4
- Updated Existing Issues: **1**
  - `Reese-max/prompt-autoresearch#3` — variance-aware repeated evaluation / stability gate — https://github.com/Reese-max/prompt-autoresearch/issues/3
- Reopened Issues: **0**
- Research Issues: **1** (#3)
- Duplicate Avoided: **10 root-cause symptom groups**
- Issue Write Blocked: **0**
- SKIPPED_LOCKED: **#1 / PR #2 scope** (active dedicated branch `docs/issue-1-contract-and-cleanup`)
- Rejected Findings: **12**
  1. Hosted multi-tenant SaaS — feature bloat and wrong positioning.
  2. Generic provider marketplace — weak vertical value, broad maintenance.
  3. Replace system with DSPy — rewrite without outcome evidence.
  4. Copy LangSmith/Braintrust UI — hosted UX is not the root gap.
  5. Fixed N=5 promotion — mock/default is not calibration.
  6. Run every candidate 20× — uncontrolled cost.
  7. Repeatedly probe holdout — creates overfitting.
  8. Weaken/xfail evidence tests — hides release risk.
  9. Declare legal 90+ validity — no independent SME study.
  10. Declare accessibility/performance defects — no runtime measurements.
  11. Native mobile app — no validated demand.
  12. Separate Issues for config/retention/onboarding symptoms — existing #1/PR #2.
- Verified Fixed: **0**
- Priority distribution: **P0 0 / P1 1 / P2 1 / P3 0 / STRATEGIC 0**
- Highest Priority: **#4**, then **#3**
- Finding mapping: **2/2 PASS**
- Runtime verification: **pending** as listed above.

## Safety and Mutex Receipt

Before every write, full target Issue comments, open PRs/branches, and `autodev-ng` matching state were re-read. #3 and #4 each received a `github-issue-lock:v1` marker and were re-read with no competing active marker. No PR was merged, no deployment occurred, no product source or secrets/settings/permissions were changed.
