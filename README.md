# prompt-autoresearch

> **Iterative, evidence-driven prompt optimization.** A research loop that
> proposes prompt changes, scores them on a held-out gate, and only accepts
> changes that pass the gate. No silent regressions, no overfitting to the
> smoke/dev split.

## What this is

A pair of research drivers (`auto_evolve.py`, `infinite_evolve.py`) plus an
API surface (`api/`), a web UI (`index.html`, `app.js`), and a research
artifact directory tree. The system runs prompt experiments against a model
endpoint, evaluates against a smoke/holdout split, and writes the round-by-
round history to `evolution_log.jsonl`.

## What it is NOT

- Not a single-shot prompt tuner. Every change has to clear an evaluation
  gate before it lands.
- Not connected to production traffic. The holdout split is **isolated**.
- Not a generic "improve the prompt" service. It is configuration-bounded
  by `config.json` (see "Config" below); metrics outside that envelope
  are out of scope.

## Quick start / stop

```bash
# dry-run (no network, no model cost): use --dry-run if implemented, else omit api calls
python auto_evolve.py --help

# bounded run: respect parallel.{smoke,dev,holdout} in config.json
python auto_evolve.py

# infinite mode
python infinite_evolve.py

# stop: Ctrl+C. On exit the run writes a final line to evolution_log.jsonl.
```

Always set `--concurrency` from `config.json.parallel.dev` and never exceed
`config.json.api.rate_limit.max_concurrent` per process. Multiply that by
host CPU count and parallel instances when running more than one driver.

## Config

Two formats of the same config are tracked:

| File | Role |
|------|------|
| `config.json` | **Canonical.** Read by `auto_evolve.py`, `infinite_evolve.py`, and the API. |
| `config.yaml` | **Mirror.** Human-readable form for ops review / tooling that prefers YAML. |

When changing config, edit **both** and run a smoke round to confirm parity.
Do NOT delete `config.yaml` from the root — third-party tools and reviewers
expect to see it. Do NOT delete `config.json` — the runtime reads from
this file.

If they drift, the canonical source is `config.json`; `config.yaml` is
regenerated from it by an out-of-band sync (not part of this repo's
runtime).

## Repository layout

| Path | Purpose |
|------|---------|
| `auto_evolve.py`, `infinite_evolve.py` | Run-loop drivers. |
| `lib/` | Library code shared between drivers and the API. |
| `api/` | FastAPI (or similar) surface; the web UI talks to this. |
| `index.html`, `app.js` | Static web UI. No build step. |
| `prompts/` | Prompt templates. Source of truth for what gets evaluated. |
| `program.md` | Long-form narrative description of the autosearch protocol. |
| `orca.yaml` | Local orchestration metadata for orca-cli. |
| `output/` | Generated state. Per-run files (see .gitignore). |
| `htmlcov/`, `.coverage`, `*.lcov` | **Generated.** Coverage reports. `.gitignore` updated to keep them out of new commits. |
| `evolution_log.jsonl`, `metrics.jsonl` | **Append-only evidence.** Each line is one round. Do not edit history. |
| `docs/` | Audit history and process docs. |
| `.serena/` | Local tool state (memory of edits, sessions). Do not commit. |
| `tests/` | Unit + integration tests. |
| `.github/` | CI workflows. |

## Generated vs canonical

| Kind | Path | Source of truth |
|------|------|-----------------|
| **Authoritative** | `*.py`, `lib/`, `api/`, `prompts/`, `program.md`, `config.json`, `config.yaml`, `tests/`, `index.html`, `app.js` | Human-edited. |
| **Append-only evidence** | `evolution_log.jsonl`, `metrics.jsonl` | The drivers. Read these to compare rounds. |
| **Generated, regenerable** | `output/*`, `htmlcov/*`, `*.lcov`, `.coverage*` | Re-derived on every run. Safe to delete. |

## Holdout isolation

The system enforces a three-tier evaluation split:

| Tier | Purpose | Allowed to optimize on? |
|------|---------|-------------------------|
| `smoke` | Cheap fast-fail on every proposed change | Yes |
| `dev` | Mid-tier scoring; rounds that exceed `dev_min_improvement` are accepted | Yes |
| `holdout` | Final gate; only consulted for the round-summarizing drop-test | **No.** Never exposed to the optimizer as a target. Any tool/regex/script that peeks at `holdout` answers for evaluation purposes is a bug, full stop. |

`holdout` data lives outside the repository (`config.json.parallel.holdout`
points to a path that is NOT in this repo). It is intentionally not
checked in.

## Dry-run / no-network path

For local testing and CI, run with stubbed data:

```python
# Stub the API call before importing
import os
os.environ["PROMPT_AUTORESEARCH_OFFLINE"] = "1"
# Now the drivers refuse to call config.json.api.url.
```

Or pass `--dry-run` if exposed by the driver. Offline-mode is enforced by
a sentinel import that raises before any network socket is opened.

The CI workflow in `.github/` runs unit tests only, on an offline runner.

## Budget & concurrency

| Cap | Value | Override |
|-----|-------|----------|
| `api.rate_limit.max_concurrent` | `8` | reduce per host, never raise without raising the model's rate-limit window |
| `api.rate_limit.min_interval_ms` | `100` | raise this if the model throttles |
| `parallel.smoke` | `6` | per-process smoke concurrency |
| `parallel.dev` | `24` | per-process dev concurrency |
| `parallel.holdout` | `24` | per-process holdout concurrency |
| `thresholds.max_candidate_length` | `550` | upper bound for prompt length |

## Retention / rotation

`evolution_log.jsonl` and `metrics.jsonl` are append-only evidence and
should not be rotated by an automated job without a maintainer review.
Suggested manual cadence:

| File | Retention |
|------|-----------|
| `evolution_log.jsonl` | Keep forever. Archive yearly snapshots under `archive/evolution_log/<year>.jsonl`. |
| `metrics.jsonl` | Keep indefinitely. Cap last 90 days as the active file. |
| `output/research_workspace.json` | 30 days hot, then archive. |
| `output/research_validation_state.json*` | Per-run; safe to delete after merge. |
| `htmlcov/` | Per-run; safe to delete after `diff` against `index.html` is updated. |

## Known gaps

- A repository-level `LICENSE` file is not committed. Until one is added,
  all-rights-reserved by the maintainers.
- A pure "diffs only" workflow file does not yet exist in `.github/`.
  Each PR must run `pytest -m "not integration"` and `coverage run -m
  pytest` locally before pushing.

## Failure modes & how to recover

| Symptom | Likely cause | Recovery |
|---------|--------------|----------|
| `evolution_log.jsonl` shows declining `dev_min_improvement` | Optimizer drift or holdout leak | Roll back the last accepted prompt in `prompts/`; re-run with `--no-promote` until stable. |
| Run hangs after `holdout` step | A worker is holding a file lock on `output/research_workspace.json` | Kill the worker, then delete the lock file. Re-run. |
| Coverage drops > 1% on `holdout` | Recent change introduced a hidden cost regression | Revert; bisect with `git log -p -- prompts/`. |
