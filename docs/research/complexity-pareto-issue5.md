# Issue #5: offline complexity and compaction prerequisite

**Decision: NARROW.** This finite, inactive research harness exercises a proposed
evidence contract. It does not replace production selection, change a champion,
run a model, establish human quality labels, or authorize a release. Every result
has `active: false` and `promotion_allowed: false`, including
`COMPACT_CANDIDATE`. The original #3 research and #4 best-version repair are
closed and merged. This prototype preserves those existing contracts. A new
integration still needs its own exact-head required CI evidence and the unchanged
complete candidate gates.

## What current source actually says

At `master@fe806b285fce0deb5ff13f28acef3e4ed93ec413`,
`program.md` condition 9 documents at most 10% prompt-token growth.
`scripts/gatekeeper.py` already rejects prompts above **700 Unicode characters**
and warns above 550; an absolute text limit is therefore already implemented.
A targeted search of the optimizer, routing, comparator and Gatekeeper source
did not locate an executable 10% token-growth check. The ratchet below replays
the **documented relative rule in a toy world**, not a claim that production
currently executes that rule or accepts the entire trajectory. Production
Gatekeeper/Smoke/DEV/Holdout and existing promotion semantics remain unchanged.

## Reproduce without credentials or network

```sh
python -m pytest tests/test_complexity_pareto_research.py -q -o addopts=
python -m research.complexity_pareto
python scripts/preflight.py --offline --json
```

The CLI writes JSON to stdout only. It has no output-path option, champion
writer, provider/client import, environment/key lookup, training or experiment
launcher. It reads its source and one versioned frozen historical fixture.
The committed `complexity-pareto-report-v1.json` is reproducible with
`python -m research.complexity_pareto`; JSON contains no timestamps or random
sampling. The tests prohibit sockets and check deterministic, read-only replay.

## Combined candidate provenance

The mathematical module, its tests, frozen five-artifact history fixture and
golden JSON report remain byte-identical to research candidate
`4bc38ffc58a7cd9397d1c061fb3ddcdca3d114da`. The combined candidate also repairs
child report-path inheritance in `scripts/run_test_matrix.py`, with dedicated
isolation tests and [report-ownership documentation](../matrix-report-child-isolation.md).
Of the 2,417 files already tracked on the original master base, 2,416 keep their
original blobs; the matrix runner is the sole exception. Optimizer/prompt
selection, fixed evaluation data, provider code and historical artifacts are
unchanged. This is a scoped preservation claim, not a claim that every original
file is unchanged.

The report's source hash identifies the mathematical module only; it does not
attest the combined tree or its CI execution. New execution evidence must bind
the exact combined head/tree and commands separately. The report's references to
#3/#4 in `remaining_gates` describe future integration evidence for those merged
contracts, not unresolved or reopened issues. A standalone native runner must
retain its actual M1–M6 and ALL records without mocked child rows. Local Linux
evidence does not establish the other eight native CI cells, their hosted
required aggregate, model stability, or provider cost/latency.

## Versioned evidence, without converting unknown into zero

`PromptComplexityReceipt` version 1 records the exact prompt hash/version,
Unicode characters, UTF-8 bytes, nonempty lines and Markdown headings. Counts
refer to the supplied Python Unicode text. Historical files use UTF-8 decoding
and universal-newline normalization to LF, matching normal text reads; receipt
hashes explicitly refer to those logical input bytes, not checkout file bytes.
Semantic rule count is `UNKNOWN`; line/heading counts are not rule counts.

Input tokens, average evaluation input/output/tool-call tokens, cost per
successful task and latency p50/p95 each carry
`MEASURED | ESTIMATED | UNKNOWN`, a value and provenance. Unknown values are null.
Input tokens require an integer and an identified tokenizer. A complete DEV
cohort binds dataset/judge/evaluator/scorer hashes, provider/model/tokenizer and
price basis. Cohort identifiers must be nonblank and have no leading/trailing
whitespace; `UNKNOWN` remains an explicit unknown rather than a padded identifier.
Cache eligibility has an optional hash and stays unknown by default.
Malformed observations and reversed latency quantiles are rejected. These
receipts describe inputs and declared provenance, not an authenticated execution
attestation or real billing certificate.

The synthetic tokenizer is exactly Python `str.split`, labeled
`synthetic-whitespace-v1`. Operational values are **chosen synthetic assumptions**
marked `ESTIMATED`, never measured provider usage, savings or latencies. All
historical model tokens, cost, cache eligibility and comparable latency remain
unknown. A historical wall time alone is not a matched latency distribution.

## Deterministic Pareto controls

The caller must supply illustrative absolute-character and relative-token
budgets. The demonstration uses 900 characters and 10%; neither is a calibrated
production recommendation. Twelve toy generations each grow by less than 10%,
while their cumulative token count more than doubles. The relative reference
accepts every step; the explicit absolute budget eventually rejects. This shows
the mathematical limit of a relative-only rule, alongside the already existing
production 700-character cap. The research selector retains the relative guard.

The finite controls produce:

| Chosen offline input | Research result |
| --- | --- |
| Equivalent synthetic quality/safety, all dimensions no worse and at least one smaller | `COMPACT_CANDIDATE` |
| Better synthetic quality and shorter input, higher assumed cost/latency | `TRADEOFF_REVIEW` |
| Quality, safety, type or an existing gate fails | `REJECT` |
| Prompt/model/provider/tokenizer/dataset/evaluator/price/cache identity drifts | `BLOCKED_EVIDENCE_DRIFT` |
| Unknown or mixed measured/estimated operational evidence, incomplete real quality/stability evidence | `INCONCLUSIVE` |
| No advantage or a dominated candidate | `KEEP` |

Only explicitly chosen `SYNTHETIC_TRUTH` may exercise the candidate branch.
Synthetic Smoke/DEV/Holdout `PASS` fields are fixture assumptions, not executions
of those pipelines. Separate tests call the **actual existing Gatekeeper**:
removing the real prompt's anti-fabrication clause or expert role makes the
shorter candidate fail its existing hard rules and remain rejected.

The quality interface binds both prompt hashes and the full DEV cohort. It
accepts no item-level or holdout outcomes. An adapter for the merged #3 research
receipt would still need to consume repeated/stability evidence and its
uncertainty, rather than treating a single
score or this harness's chosen labels as stable equivalence. That adapter is not
implemented here; there is no new noise estimator. Every real candidate still
needs Gatekeeper, Smoke, DEV and a bounded final Holdout, without feeding Holdout
item outcomes into mutation. Fresh exact-head evidence for the CI contract
restored in merged #4 stays mandatory.

## Conservative compaction lane

Every candidate includes before/after hashes, operations, remaining section IDs,
the exact candidate text, a display diff and immutable protected-section hashes.
The supported subset deliberately avoids a semantic model claiming that a rule
is redundant:

- `DELETE` removes one exact duplicate only when an identical section remains.
- `MERGE` coalesces exact duplicates, retaining the first section's exact text.
- `REWRITE` only collapses repeated ASCII spaces and trims trailing spaces/tabs;
  it cannot join words, remove line breaks or paraphrase requirements.

Protected sections cannot be targeted, and their exact hashes must survive.
`ADD`, arbitrary paraphrases, unique-rule deletion and semantic merges are
rejected. The demonstration protects the entire current canonical core and
adds/removes a **synthetic duplicate** in a separate candidate; canonical files
are never modified. This is a narrow textual invariant, not proof that model
behavior is unchanged. Explicit semantic review and all existing evaluation
gates remain required. Failure-pattern diagnosis and model-generated semantic
compaction are deferred, rather than given a shallow safety claim.

## Frozen historical replay and honest result

`research/fixtures/complexity-history-v1.json` freezes five existing tracked
artifacts/projections with their base commit, Git blob IDs and normalized content
hashes: the June 2 predecessor archive, current baseline, baseline metadata,
current DEV summary and the exact original log lines whose `promoted` is true.
The first four contain full logical text; the log projection retains seven rows
and records both the full source hash and projection hash. No generated answers,
human labels or new evaluations are added. The normal replay reads these frozen
copies, so legitimate future champion/history changes do not break this research
test or silently change its conclusion. Fixture edits require explicit versioned
review; embedded hashes describe provenance, not cryptographic authority.
The archive timestamp matches the baseline metadata; one log row binds that
current DEV run and prompt hash. This establishes **one archived transition**,
not a complete champion history, matched old/new whole-DEV experiment or proof
that historical promotion satisfied today's gates. Six later `promoted` log
rows have no DEV run link; they are counted as excluded, never used as quality
or champion evidence. No history or run files are rewritten, and no Holdout run
or item outcomes are read.

| Logical prompt input | Characters | UTF-8 bytes | Provider tokens / cost |
| --- | ---: | ---: | --- |
| Archived predecessor | 442 | 1,270 | `UNKNOWN` |
| Current baseline | 438 | 1,282 | `UNKNOWN` |

Characters decreased by four while bytes increased by twelve. Without matching
tokenizer measurements, even the documented 10% token result is `UNKNOWN`.
The bound current DEV machine summary reports average 89.2083, 48 questions,
zero cache hits/errors, **word-count pass rate 0%** and risk-perfect rate 95.8333%.
Those are frozen machine metadata, not human quality or all-gates approval.
There is no verified stability/equivalence pair, so the historical conclusion is
`NO_VERIFIED_COMPACTION_OPPORTUNITY`. No real savings or empirical bloat is claimed.

Keep the existing rules and the documented 10% guard. The synthetic counterexample
supports researching an explicit long-term budget and Pareto review, but does
not calibrate a replacement threshold. Before FEATURE adoption: integrate the
merged #3 receipt only with real repeated DEV evidence and obtain fresh exact-head
passing CI for the existing contract restored by #4; obtain an
explicitly authorized bounded provider canary with matching cohorts and measured
cost/latency; and run each genuine compaction through the unchanged complete
gates. This offline prerequisite grants no provider or release authority.
