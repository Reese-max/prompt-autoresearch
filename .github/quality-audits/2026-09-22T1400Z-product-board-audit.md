# Product Board Audit — prompt-autoresearch

Audit time: 2026-09-22T14:00Z  
Repository: `Reese-max/prompt-autoresearch`  
Inspected HEAD before write: `244f7598b0157fa76217f988549869b0577f45b8`  
Underlying product baseline: `723746c96c7fdc03ba3ab9f754b79f7ae6addd75`  
Issue-quality-v2 blob: `8167e10798071d2276addaff6b201c6b0e904a2a`  
Fixed A01–J05 Round 3: [50-persona-round-3-2026-09-22-1128Z.md](https://github.com/Reese-max/prompt-autoresearch/blob/244f7598b0157fa76217f988549869b0577f45b8/docs/audits/50-persona-round-3-2026-09-22-1128Z.md)  
Evidence labels: `CONFIRMED`, `LIKELY`, `UNKNOWN`; runtime labels: `SOURCE_CONFIRMED`, `EXECUTED_REPRODUCTION`, `NEEDS_RUNTIME_VERIFICATION`.

This product-board panel and the 50 market personas below are model simulations, not independent experts, users, market share, incident frequency, ROI, or implementation authorization. They are separate from the fixed A01–J05 CLEAN audit.

## Executive result

Decision: **INVEST / SIMPLIFY / MAINTAIN**.

A new current-default P1 authorization-boundary defect is now tracked by [Issue #12](https://github.com/Reese-max/prompt-autoresearch/issues/12). `run_app.py` binds `ThreadingTCPServer(("", PORT), ...)` to wildcard interfaces while its console says `localhost`; unauthenticated, permissive-CORS POST routes can start evolution/final subprocesses or forward provider requests. This is `BUG / P1 / SOURCE_CONFIRMED / HIGH / NEEDS_REVIEW / auto_implementation=false`.

The minimum effective fix is loopback-only by default. If the owner deliberately retains external bind, mutating routes need a small configured authorization boundary and controlled Origin policy. Preserve the provider-host allowlist. Do not build accounts, OAuth, a database, API gateway, general IAM, or a new platform.

No actual LAN/Internet exposure, unauthorized subprocess, provider spend, credential disclosure, data loss, or arbitrary-code execution was observed. No attack, paid provider call, deployment, branch, merge, product change, CI/config change, worker, or GOAL was run.

## Discovery and evidence

| Item | Result |
|---|---|
| Product direction | Local, evidence-bound promotion harness for Taiwan legal-exam prompt research; serve prompt researchers, legal content specialists, QA/maintainers, and cost-conscious operators. |
| Current default | `master@244f7598…`; latest commit is audit-only. Product behavior remains `723746c…`. |
| Root onboarding | Root README remains absent on default; [#1](https://github.com/Reese-max/prompt-autoresearch/issues/1) / PR #2 already track the source/artifact contract. |
| Evidence gate | [Actions run 35448297228](https://github.com/Reese-max/prompt-autoresearch/actions/runs/35448297228): all nine OS/Python jobs reached their declared test path and failed; `test-matrix-required` failed. Existing [#4](https://github.com/Reese-max/prompt-autoresearch/issues/4), PRs #9/#10. |
| Provider lifecycle | Retired Gemini IDs remain on default; existing [#7](https://github.com/Reese-max/prompt-autoresearch/issues/7), PRs #8/#11. |
| New trust-boundary evidence | `run_app.py` lines 429–565: wildcard bind; `Access-Control-Allow-Origin: *`; unauthenticated `/api/run-evolution`, `/api/run-final`, and `/api/proxy`. |
| Dedupe/ownership | All-state Issue/PR search found no existing `run_app` / localhost / CORS / auth / proxy tracker or implementation PR. #12 lock was released at 2026-09-22T11:28:30Z. Existing #1/#4/#7 PR scopes were not changed. |
| Inventory limit | Connected inventory exposed 41 Reese-max repos while older checkpoints exposed 42. This blocks whole-portfolio CLEAN and is not interpreted as deletion. |

## Competitive matrix

Fresh official-source check: 2026-09-22 UTC. Product claims are reference points, not independent outcome proof.

| Alternative | Confirmed current signal | Relevance | Product response |
|---|---|---|---|
| [LangSmith repetitions](https://docs.langchain.com/langsmith/repetition) | **CONFIRMED:** SDK evaluation supports repetitions and UI exposes individual scores, averages, and standard deviation. | Stronger hosted experiment inspection and team workflow. | **MUST MATCH:** replayable evidence and variance receipt. **DO NOT COPY:** hosted multi-tenant observability/RBAC. |
| [promptfoo temperature/repeat guide](https://www.promptfoo.dev/docs/guides/evaluate-llm-temperature/) | **CONFIRMED**, page updated 2026-09-18: config-driven comparisons, assertions, `--repeat`, and cache control. | Strong CLI portability and provider-neutral regression workflow. | **SHOULD BE BETTER:** vertical legal gates, local/private evidence, typed `INCONCLUSIVE`. Do not become a generic provider marketplace. |
| [DSPy](https://dspy.ai/current/) | **CONFIRMED:** structured signatures, evaluation, and optimizers including GEPA; current docs surface DSPy 3.4.0b1. | Broader program optimization ecosystem. | **DIFFERENTIATOR:** Taiwan legal corpus and defensible promotion receipts. **DO NOT COPY:** framework rewrite. |
| Manual scripts/spreadsheets | **CONFIRMED** as a feasible substitute; no vendor dependency. | Lower setup, weaker lineage and repeatability. | Preserve inspectable local files and a zero-cost preflight; remove confusing tracked artifacts. |

Capability summary: competitors are stronger in onboarding, generic provider breadth, hosted drill-down, and mature repetition UX. prompt-autoresearch should compete on local privacy, vertical legal evidence, hard risk gates, and auditable promotion—not breadth, mobile, SaaS, or collaboration.

## Virtual executive board

- **CEO:** only three moves: close #12; restore the exact-SHA evidence gate (#4); then validate variance/SME evidence. Do not add optimizers or providers first.
- **CPO:** the promise is “a promotion decision you can defend.” A control plane that is not actually local breaks trust before model quality matters.
- **CTO:** loopback default is the smallest root-cause repair. External mode may be explicit and authenticated; no general auth platform.
- **Staff/Principal Engineer:** bind address, authorization check, subprocess/provider mocks, and exact negative tests are sufficient.
- **UX Lead:** console language and actual listen boundary must agree. Make external mode visibly exceptional.
- **UX Researcher:** no human comprehension or operator-safety study exists; synthetic personas cannot validate it.
- **Growth:** do not market autonomy while CI is red and local control is remotely triggerable.
- **CFO:** unauthorized work is a cost-control defect, but real spend remains unmeasured; do not invent ROI.
- **Security/Privacy:** CORS is not caller authorization; host firewall/private LAN are defense-in-depth, not the product boundary.
- **QA:** require zero subprocess/provider calls for unauthorized requests and preserve the provider-host allowlist.
- **SRE:** exact-head network-isolated receipt is required; no production probe.
- **Accessibility:** keyboard, screen reader, zoom, mobile, and tablet remain `UNKNOWN`.
- **Support:** document “local-only by default,” the explicit external-mode warning, and typed rejection without exposing secrets.

Material disagreement: Growth favors an easier LAN-access mode; Security and SRE reject default LAN exposure. Resolution: loopback default, explicit opt-in external mode only if authorization is present. CTO rejects OAuth/accounts as disproportionate.

## 50 synthetic market personas

Protocol: P01–P30 preserve the 2026-09-12 regression baseline; P31–P50 explore the new trust boundary and adjacent edge cases. “Result” is simulated against repository evidence, not human testing.

| ID | Background / constraint | Goal / expectation | Task / journey | Friction / result | Severity / action / evidence |
|---|---|---|---|---|---|
| P01 | Prompt engineer, Linux | Reproducible uplift | evolve→dev→holdout→promote | single-run luck; FAIL | P1; #3; SOURCE_CONFIRMED |
| P02 | QA, Windows | Green baseline | run 9-cell matrix | all cells red; FAIL | P1; #4; EXECUTED |
| P03 | Legal teacher, Mac | Stable legal quality | inspect champion/rubric | no SME calibration; PARTIAL | P2; bounded SME study; UNKNOWN |
| P04 | Candidate, Android | Reliable essay help | consume best prompt | no deployed user journey; CANNOT_VERIFY | NOT_ESTABLISHED; research |
| P05 | Operator, Windows | Bounded cost | set budget→long run | cost receipt incomplete; PARTIAL | P2; #3/#5 context |
| P06 | Data scientist | Measure noise | repetitions→statistics | checked-in probe is mock; FAIL | P1; #3; SOURCE_CONFIRMED |
| P07 | CFO, tablet | Cost per reliable uplift | inspect decision | no measured unit economics; CANNOT_VERIFY | NOT_ESTABLISHED; no ROI claim |
| P08 | SRE, Linux | Trust release gate | inspect Actions | required gate red; FAIL | P1; #4; EXECUTED |
| P09 | New maintainer, Mac | Fast onboarding | clone→README→dry run | root README absent; FAIL | P2; #1 |
| P10 | Legal scholar | Valid scoring | inspect rubric/sample | real judge validity unknown | NOT_ESTABLISHED; SME evidence |
| P11 | ML engineer | Paired deltas | compare candidate distribution | no canonical replicate receipt | P1; #3 |
| P12 | PM | Typed decision | read PROMOTE/REJECT/INCONCLUSIVE | insufficient evidence can be hard decision | P1; #3 |
| P13 | Security engineer | Secret/data boundary | review fixtures/logs | runtime leakage untested | NOT_ESTABLISHED; safe scan |
| P14 | NVDA user | Keyboard/screen-reader flow | open local UI | no assistive-tech receipt | NOT_ESTABLISHED |
| P15 | New research assistant | Zero-cost first run | clone→preflight | fix only in unmerged PR #2 | P2; #1 |
| P16 | Power user | Independent holdout | many route rounds | repeated holdout feedback risk | P1; #3 |
| P17 | Statistician | Quantified uncertainty | export per-item scores | no canonical raw replicates | P1; #3 |
| P18 | CI maintainer | Diagnostic failure | minimal fixture→trace | typed contract broken | P1; #4 |
| P19 | Tuition-center lead | Defensible adoption | compare outcomes | no real-user evidence | NOT_ESTABLISHED; do not market |
| P20 | Cost-sensitive developer | Local/no SaaS | run mock | mock can be mistaken for effect | P2; explicit mock gate |
| P21 | LangSmith user | Repetition drill-down | compare tools | hosted UX is stronger; SWITCH | P3 opportunity; do not copy SaaS |
| P22 | promptfoo user | Portable assertions | config→repeat→compare | generic CLI is stronger; SWITCH | P3; preserve vertical moat |
| P23 | DSPy researcher | Program optimizer | signature→metric→compile | broader ecosystem; SWITCH | P3; no rewrite |
| P24 | Team eval lead | Trace-to-eval | inspect production loop | product is local research tool | P3; DON'T build observability |
| P25 | Low-bandwidth researcher | Offline evidence review | shallow clone→inspect | tracked artifacts are noisy | P2; #1 |
| P26 | Data governance lead | Dataset lineage | trace hashes/splits | cross-platform semantics unclear | P3; evidence backlog |
| P27 | Legal/reuse reviewer | Clear license | inspect repository | license absent | NOT_ESTABLISHED priority; owner decision |
| P28 | Research intern | Canonical config | edit thresholds→run | JSON/YAML drift risk | P2; #1/#4 |
| P29 | Model vendor manager | Model drift safety | swap model→retest | cohort invalidation incomplete | P1; #3/#7 context |
| P30 | Research-ethics reviewer | No overclaim | read evidence labels | labels separate mock/runtime; PASS | Maintain |
| P31 | Home Wi-Fi operator | Local really means local | launch UI→inspect socket | wildcard bind contradicts message | P1; #12; SOURCE_CONFIRMED |
| P32 | Shared-office peer | Cannot trigger others' work | POST mutation from LAN | no caller auth if reachable | P1; #12; NEEDS_RUNTIME |
| P33 | Browser attacker | Cross-origin mutation blocked | hostile origin→POST | permissive CORS, no auth | P1; #12 |
| P34 | Cost owner | Prevent unauthorized calls | peer→proxy provider | allowlist limits host, not caller | P1; #12 |
| P35 | Legal-data steward | Prevent state mutation | peer→start evolution | subprocess inherits environment | P1; #12 |
| P36 | Remote developer | Explicit LAN mode | opt in→authenticate | no explicit secure mode | P1; #12 |
| P37 | Firewall-reliant user | Defense in depth | run behind host firewall | configuration may reduce reachability | PARTIAL; Red Team; still #12 |
| P38 | Container user | Predictable bind | map port→launch | wildcard becomes externally mapped | P1; #12; runtime unknown |
| P39 | WSL user | Local boundary understood | launch→Windows/LAN | platform reachability varies | P1 source; runtime unknown |
| P40 | Public-cloud VM user | Safe default | launch for inspection | wildcard may expose control plane | P1; #12; no deployment observed |
| P41 | Support engineer | Explain failure safely | unauthorized POST | no typed 401/403 contract | P2 within #12 acceptance |
| P42 | QA automation | Assert zero side effects | mock Popen/urlopen | no negative auth fixture | P1; #12 |
| P43 | SRE incident responder | Identify initiator | review mutation logs | no caller identity/auth context | P1; #12 |
| P44 | Accessibility tester | External device testing | open from tablet | secure remote test path undefined | P2 research after #12 |
| P45 | Air-gapped researcher | Preserve offline mode | loopback/no network | loopback fix fits requirement | PASS candidate; verify |
| P46 | Reverse-proxy operator | Controlled remote UI | proxy→token→origin | no product auth hook | P1; #12; minimal token only |
| P47 | Multi-user workstation | Per-user isolation | two local accounts | shared port/process boundary unclear | P2 research; not new issue |
| P48 | Malware-on-host scenario | Least privilege | local process POST | loopback cannot stop same-host malware | Red Team: out of scope for #12 |
| P49 | Maintainer under time pressure | Small safe patch | change bind + tests | tempting to add auth framework | PASS if minimal; no platform |
| P50 | CEO persona | Choose only three | prioritize board | #12→#4→bounded validity | INVEST/SIMPLIFY |

No synthetic preference share is reported; the simulations do not establish incidence or demand.

## Red Team

- **Counter-evidence:** firewall, NAT, private networks, and “usually launched on a laptop” may make remote reachability impossible in some environments. This limits observed impact but does not repair the product’s wildcard bind or authorize callers.
- **Existing safeguard:** provider hostname allowlisting blocks arbitrary proxy targets. It does not decide who may spend provider quota or start subprocesses.
- **Smaller alternative:** loopback-only default solves the supported local workflow without tokens. Authentication is needed only if an explicit external mode is retained.
- **Wrong-root check:** CORS alone is not the root; removing wildcard CORS without fixing wildcard listen/auth would leave non-browser callers able to mutate.
- **Overengineering check:** OAuth, accounts, RBAC, databases, API gateways, audit platforms, or secret brokers are rejected.
- **Severity brake:** no actual exposure or incident was observed; therefore P1, not P0, and `NEEDS_RUNTIME_VERIFICATION`.
- **Scope separation:** `api/server.py --host 0.0.0.0` is owner-explicit and not automatically folded into #12. Re-evaluate only with a distinct supported-flow failure after #12.

## Findings and roadmap

| Finding | Kind / severity | Status | Minimum scope |
|---|---|---|---|
| [#12](https://github.com/Reese-max/prompt-autoresearch/issues/12) local control-plane boundary | BUG / P1 / HIGH | New; NEEDS_REVIEW; no PR; `auto_implementation=false` | Loopback default; auth + Origin only for explicit external mode; direct negative tests |
| [#4](https://github.com/Reese-max/prompt-autoresearch/issues/4) evidence contract / red matrix | BUG / P1 | Existing; active PRs #9/#10; SKIPPED_LOCKED | Canonical typed contract; exact-SHA 9-cell green |
| [#7](https://github.com/Reese-max/prompt-autoresearch/issues/7) retired Gemini IDs | BUG / P2 | Existing; active PRs #8/#11; SKIPPED_LOCKED | Supported IDs + stale persisted-model handling |
| [#1](https://github.com/Reese-max/prompt-autoresearch/issues/1) repository/source-artifact contract | MAINTENANCE / P2 | Existing; active PR #2; SKIPPED_LOCKED | Root contract, offline first run, artifact boundary |

**NOW:** #12, then #4.  
**NEXT:** #7 and #1 after their competing PRs are reconciled; bounded variance/SME receipts only after the evidence gate is trustworthy.  
**LATER:** accessibility/device study, external-mode usability, cost-per-reliable-uplift, and legal-SME calibration.  
**DON'T:** hosted multi-tenant SaaS, generic observability, provider marketplace, new optimizer framework, mobile app, broad collaboration/RBAC, or general auth platform.

## Runtime and regression requirements

For #12, start the exact product SHA in an isolated namespace with `subprocess.Popen` and provider forwarding mocked. Record actual listen address; test loopback and a non-loopback test interface; test authorized/unauthorized origin/auth combinations; assert unauthorized paths produce zero subprocesses and zero provider calls. No real provider or production network is required.

Existing exact-head CI failure remains [run 35448297228](https://github.com/Reese-max/prompt-autoresearch/actions/runs/35448297228); it proves #4 remains open, not that #12 is executed. A merge or diff alone will not verify #12. Re-run the same isolated scenario after the fix lands on default.

## Accounting and CLEAN

- New actionable findings: **1** (#12 P1)
- New Issue / updated Issue / reopened Issue: **1 / 0 / 0**
- Duplicate candidates rejected: **0 for #12** after all-state search; related external-feedback signal deferred
- Existing active scopes left unchanged: **#1, #4, #7; PRs #2/#8/#9/#10/#11**
- Verified fixed / confirmed regression: **0 / 0**
- Runtime reproductions: **0**
- Product implementation, CI/config, secret, settings, branch, merge, deployment, worker, GOAL, or paid-call writes: **0**
- Fixed A01–J05 result: **NOT CLEAN, 0/2**
- Portfolio: **NOT CLEAN**; inventory is incomplete and runtime evidence is pending.

This audit is a decision/tracking artifact, not authorization to implement, merge, deploy, spend, or externally write.
