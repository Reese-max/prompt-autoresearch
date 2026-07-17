# -*- coding: utf-8 -*-
"""測試未覆蓋的 CLI/腳本入口：參數缺失 vs 參數非法路徑，驗證 help/預設/驗證/error exit code。"""
import sys

import pytest


# ---------------------------------------------------------------------------
# infinite_evolve.py — argparse，可直接傳 argv
# ---------------------------------------------------------------------------

class TestInfiniteEvolveParseArgs:
    """infinite_evolve.parse_args：help / 預設 / 非法參數。"""

    def test_help_exits_zero(self):
        from infinite_evolve import parse_args
        with pytest.raises(SystemExit) as exc:
            parse_args(["--help"])
        assert exc.value.code == 0

    def test_no_args_uses_defaults(self):
        from infinite_evolve import parse_args
        args = parse_args([])
        assert args.max_rounds == 100
        assert args.parallel == 24
        assert args.smoke_parallel == 24
        assert args.dev_parallel == 24
        assert args.holdout_parallel == 24
        assert args.no_improve_limit == 10
        assert args.same_failure_limit == 5
        assert args.rotate_after == 2
        assert args.force_direction == ""
        assert args.budget_usd == 0.0
        assert args.estimated_cost_per_call == 0.0
        assert args.route_every == 3
        assert args.sleep_seconds == 5
        assert args.round_timeout_seconds == 3600
        assert args.route_timeout_seconds == 1800
        assert args.dry_run is False

    def test_non_int_max_rounds_rejects(self):
        from infinite_evolve import parse_args
        with pytest.raises(SystemExit) as exc:
            parse_args(["--max-rounds", "abc"])
        assert exc.value.code != 0

    def test_non_int_parallel_rejects(self):
        from infinite_evolve import parse_args
        with pytest.raises(SystemExit) as exc:
            parse_args(["--parallel", "xyz"])
        assert exc.value.code != 0

    def test_non_float_budget_rejects(self):
        from infinite_evolve import parse_args
        with pytest.raises(SystemExit) as exc:
            parse_args(["--budget-usd", "notanumber"])
        assert exc.value.code != 0

    def test_unknown_flag_rejects(self):
        from infinite_evolve import parse_args
        with pytest.raises(SystemExit) as exc:
            parse_args(["--unknown-flag"])
        assert exc.value.code != 0

    def test_smoke_parallel_overrides_parallel(self):
        from infinite_evolve import parse_args
        args = parse_args(["--parallel", "10", "--smoke-parallel", "3"])
        assert args.smoke_parallel == 3
        assert args.dev_parallel == 10
        assert args.holdout_parallel == 10

    def test_dry_run_flag(self):
        from infinite_evolve import parse_args
        args = parse_args(["--dry-run"])
        assert args.dry_run is True

    def test_negative_max_rounds_accepted_by_argparse(self):
        from infinite_evolve import parse_args
        args = parse_args(["--max-rounds", "-5"])
        assert args.max_rounds == -5


# ---------------------------------------------------------------------------
# route_evolve.py — argparse + main() 內建驗證
# ---------------------------------------------------------------------------

class TestRouteEvolve:
    """route_evolve：help / 預設 / 缺 --type/--all / 非法參數。"""

    def test_help_exits_zero(self):
        from route_evolve import parse_args
        with pytest.raises(SystemExit) as exc:
            sys.argv = ["route_evolve.py", "--help"]
            try:
                parse_args()
            finally:
                sys.argv = sys.argv[:1]
        assert exc.value.code == 0

    def test_no_args_default(self):
        from route_evolve import parse_args
        old = sys.argv[:]
        try:
            sys.argv = ["route_evolve.py"]
            args = parse_args()
        finally:
            sys.argv = old
        assert args.all is False
        assert args.type_name is None
        assert args.rounds == 1
        assert args.parallel == 24
        assert args.mode == "pragmatic"
        assert args.skip_route_eval is False

    def test_invalid_mode_rejects(self):
        from route_evolve import parse_args
        old = sys.argv[:]
        try:
            sys.argv = ["route_evolve.py", "--mode", "invalid_mode"]
            with pytest.raises(SystemExit) as exc:
                parse_args()
            assert exc.value.code != 0
        finally:
            sys.argv = old

    def test_non_int_rounds_rejects(self):
        from route_evolve import parse_args
        old = sys.argv[:]
        try:
            sys.argv = ["route_evolve.py", "--rounds", "abc"]
            with pytest.raises(SystemExit) as exc:
                parse_args()
            assert exc.value.code != 0
        finally:
            sys.argv = old

    def test_missing_type_and_all_returns_error(self):
        from route_evolve import main
        old = sys.argv[:]
        try:
            sys.argv = ["route_evolve.py"]
            code = main()
        finally:
            sys.argv = old
        assert code == 1

    def test_unknown_flag_rejects(self):
        from route_evolve import parse_args
        old = sys.argv[:]
        try:
            sys.argv = ["route_evolve.py", "--bogus"]
            with pytest.raises(SystemExit) as exc:
                parse_args()
            assert exc.value.code != 0
        finally:
            sys.argv = old


# ---------------------------------------------------------------------------
# route_loop.py — argparse
# ---------------------------------------------------------------------------

class TestRouteLoop:
    """route_loop：help / 預設 / 非法參數。"""

    def test_help_exits_zero(self):
        from route_loop import parse_args
        with pytest.raises(SystemExit) as exc:
            sys.argv = ["route_loop.py", "--help"]
            try:
                parse_args()
            finally:
                sys.argv = sys.argv[:1]
        assert exc.value.code == 0

    def test_no_args_default(self):
        from route_loop import parse_args
        old = sys.argv[:]
        try:
            sys.argv = ["route_loop.py"]
            args = parse_args()
        finally:
            sys.argv = old
        assert args.loops == 1
        assert args.evolve_rounds == 0
        assert args.parallel == 24
        assert args.stop_on_accept is True

    def test_non_int_loops_rejects(self):
        from route_loop import parse_args
        old = sys.argv[:]
        try:
            sys.argv = ["route_loop.py", "--loops", "abc"]
            with pytest.raises(SystemExit) as exc:
                parse_args()
            assert exc.value.code != 0
        finally:
            sys.argv = old

    def test_non_int_parallel_rejects(self):
        from route_loop import parse_args
        old = sys.argv[:]
        try:
            sys.argv = ["route_loop.py", "--parallel", "xyz"]
            with pytest.raises(SystemExit) as exc:
                parse_args()
            assert exc.value.code != 0
        finally:
            sys.argv = old

    def test_unknown_flag_rejects(self):
        from route_loop import parse_args
        old = sys.argv[:]
        try:
            sys.argv = ["route_loop.py", "--unknown"]
            with pytest.raises(SystemExit) as exc:
                parse_args()
            assert exc.value.code != 0
        finally:
            sys.argv = old


# ---------------------------------------------------------------------------
# auto_evolve.py — 自訂 parse_args(generations + forwarded parallel args)
# ---------------------------------------------------------------------------

class TestAutoEvolveParseArgs:
    """auto_evolve.parse_args：缺值走預設 / 無效值。"""

    def test_no_args_defaults_to_10(self):
        from auto_evolve import parse_args
        gen, rest = parse_args([])
        assert gen == 10
        assert rest == []

    def test_valid_generations(self):
        from auto_evolve import parse_args
        gen, rest = parse_args(["5"])
        assert gen == 5
        assert rest == []

    def test_non_int_generations_keeps_default(self):
        from auto_evolve import parse_args
        gen, rest = parse_args(["abc"])
        assert gen == 10
        assert rest == ["abc"]

    def test_generations_with_forwarded_args(self):
        from auto_evolve import parse_args
        gen, rest = parse_args(["3", "--smoke-parallel", "2"])
        assert gen == 3
        assert rest == ["--smoke-parallel", "2"]

    def test_empty_string_generations_keeps_default(self):
        from auto_evolve import parse_args
        gen, rest = parse_args([""])
        assert gen == 10
        assert rest == [""]


# ---------------------------------------------------------------------------
# run_opt.py — 自訂 parse_run_opt_args / parse_parallel_args
# ---------------------------------------------------------------------------

class TestRunOptParseArgs:
    """run_opt.parse_run_opt_args / parse_parallel_args：缺失 vs 非法路徑。"""

    def test_no_args_uses_defaults(self):
        from run_opt import parse_run_opt_args
        config = parse_run_opt_args([])
        assert config["smoke_parallel"] >= 1
        assert config["dev_parallel"] >= 1
        assert config["holdout_parallel"] >= 1

    def test_smoke_parallel_from_flag(self):
        from run_opt import parse_run_opt_args
        config = parse_run_opt_args(["--smoke-parallel", "8"])
        assert config["smoke_parallel"] == 8

    def test_dev_parallel_from_flag(self):
        from run_opt import parse_run_opt_args
        config = parse_run_opt_args(["--dev-parallel", "16"])
        assert config["dev_parallel"] == 16

    def test_holdout_parallel_from_flag(self):
        from run_opt import parse_run_opt_args
        config = parse_run_opt_args(["--holdout-parallel", "12"])
        assert config["holdout_parallel"] == 12

    def test_non_int_parallel_falls_back_to_default(self):
        from run_opt import parse_run_opt_args
        config = parse_run_opt_args(["--smoke-parallel", "abc"])
        assert config["smoke_parallel"] >= 1

    def test_missing_value_after_flag_falls_back(self):
        from run_opt import parse_run_opt_args
        config = parse_run_opt_args(["--smoke-parallel"])
        assert config["smoke_parallel"] >= 1

    def test_zero_parallel_clamped_to_one(self):
        from run_opt import parse_run_opt_args
        config = parse_run_opt_args(["--smoke-parallel", "0"])
        assert config["smoke_parallel"] == 1

    def test_negative_parallel_clamped_to_one(self):
        from run_opt import parse_run_opt_args
        config = parse_run_opt_args(["--smoke-parallel", "-5"])
        assert config["smoke_parallel"] == 1

    def test_force_direction_from_flag(self):
        from run_opt import parse_run_opt_args
        config = parse_run_opt_args(["--force-direction", "D03"])
        assert config["force_direction"] == "D03"

    def test_force_direction_missing_value_defaults_empty(self):
        from run_opt import parse_run_opt_args
        config = parse_run_opt_args(["--force-direction"])
        assert config["force_direction"] == ""

    def test_avoid_failures_from_flag(self):
        from run_opt import parse_run_opt_args
        config = parse_run_opt_args(["--avoid-failures", "F01,F03"])
        assert config["avoid_failures"] == ["F01", "F03"]

    def test_avoid_failures_missing_value_defaults_empty(self):
        from run_opt import parse_run_opt_args
        config = parse_run_opt_args(["--avoid-failures"])
        assert config["avoid_failures"] == []

    def test_avoid_failures_with_spaces(self):
        from run_opt import parse_run_opt_args
        config = parse_run_opt_args(["--avoid-failures", " F01 , F03 "])
        assert config["avoid_failures"] == ["F01", "F03"]


class TestRunOptParseParallelArgs:
    """run_opt.parse_parallel_args：env 覆寫 + 非法 env 值回退。"""

    def test_default_smoke_parallel(self, monkeypatch):
        monkeypatch.delenv("AUTORESEARCH_SMOKE_PARALLEL", raising=False)
        monkeypatch.delenv("AUTORESEARCH_DEV_PARALLEL", raising=False)
        monkeypatch.delenv("AUTORESEARCH_HOLDOUT_PARALLEL", raising=False)
        from run_opt import parse_parallel_args
        config = parse_parallel_args([])
        assert config["smoke_parallel"] >= 1
        assert config["dev_parallel"] >= 1
        assert config["holdout_parallel"] >= 1

    def test_env_override_smoke(self, monkeypatch):
        monkeypatch.setenv("AUTORESEARCH_SMOKE_PARALLEL", "42")
        from run_opt import parse_parallel_args
        config = parse_parallel_args([])
        assert config["smoke_parallel"] == 42

    def test_invalid_env_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("AUTORESEARCH_SMOKE_PARALLEL", "not_a_number")
        from run_opt import parse_parallel_args
        config = parse_parallel_args([])
        assert config["smoke_parallel"] >= 1

    def test_flag_overrides_env(self, monkeypatch):
        monkeypatch.setenv("AUTORESEARCH_SMOKE_PARALLEL", "5")
        from run_opt import parse_parallel_args
        config = parse_parallel_args(["--smoke-parallel", "99"])
        assert config["smoke_parallel"] == 99
