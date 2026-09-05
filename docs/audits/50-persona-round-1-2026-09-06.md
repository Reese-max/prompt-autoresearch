# 50-Persona Audit — Round 1

Date: 2026-09-06
Protocol: `Reese-max/autodev-ng/docs/portfolio-audit/2026-09-06-50-persona-audit.md`

> Fixed 50-persona model simulation plus repository evidence review; not 50 human participants.

## Round 1 result

Status: **P2 OPEN — NOT CLEAN**

Existing issue #1 remains reproducible. The default branch contains substantial autoresearch/evolution code, API/UI, two config formats, tests/coverage tooling and tracked generated-looking artifacts (`evolution_log.jsonl`, `htmlcov/`) but still no root README that defines the authoritative config, objective, budget/stop rules, holdout boundaries, recovery behavior or source-vs-generated artifact contract.

Existing actionable issue: #1 — `[P2][50-persona audit] Add repository contract and separate generated research artifacts from source`.

## Fixed-persona regression

H05/D04/D05/I02/J05 still cannot clone the repo and safely determine which configuration is authoritative, how to run a zero-cost validation, how to stop/resume without duplicate spend, or which tracked outputs are canonical evidence versus regenerated artifacts.

## New P0/P1/P2 findings this round

No additional reproducible P0/P1/P2 was confirmed from the static evidence reviewed.

## Regression gates

1. Resolve #1, including canonical config and generated-artifact retention boundaries.
2. Add explicit budget/concurrency/stop behavior and a no-network/dry-run path.
3. Demonstrate interrupted-run recovery without corrupting the best candidate or duplicating paid work.
4. Demonstrate holdout/evaluation isolation.
5. Re-run the fixed personas and require two consecutive rounds with no new P0/P1/P2 before CLEAN.

## Runtime status

**Pending.** This round did not execute long-running evolution or provider calls.