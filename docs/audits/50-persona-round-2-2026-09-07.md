# 50-Persona Audit — Round 2

Date: 2026-09-07
Protocol: Reese-max/autodev-ng/docs/portfolio-audit/2026-09-06-50-persona-audit.md

> Fixed 50-persona model simulation plus repository evidence review; not 50
> human participants.

## Result

Status: **local contract implemented; real model run remains unverified**

The repository now has a root contract that names the runtime entry points,
canonical config, fixed evaluation splits, generated artifacts, retention
policy versus enforcement, holdout protocol, recovery steps, and provider
boundary. The implementation adds an offline preflight mode and validates
long-run limits before invoking the preflight subprocess.

## Evidence

The focused regression suite passed:

    python -m pytest tests/test_preflight.py tests/test_untested_entrypoints.py tests/test_infinite_evolve_behavior.py -q

The added checks cover:

- preflight passing without MINIMAX_API_KEY when --offline is present;
- infinite_evolve forwarding --offline during --dry-run and returning before
  run_opt or evolution_log writes;
- rejecting a positive budget without a positive per-call cost estimate before
  any subprocess is started.

No provider request, model evolution, real user data, deployment, or paid API
call was made. Existing tracked logs, run evidence, prompts, question fixtures,
and holdout data were preserved.

## Remaining acceptance

The offline path proves configuration and local fixture checks only. A real
provider run still requires an authorized key, an explicitly bounded
invocation, and separate spend/quality evidence. The estimated budget gate is
checked after a completed round, so it cannot guarantee an exact provider
invoice cap. Holdout data is tracked in this repository and is protocol
isolated rather than secret; a hidden external holdout requires a separate
runner. Retention and rotation remain maintainer policy rather than automatic
enforcement.

The legacy auto_evolve.py, run_opt.py, route_evolve.py, and route_loop.py
entry points remain provider-consuming paths; use infinite_evolve.py
--dry-run or scripts/preflight.py --offline for zero-network checks.
