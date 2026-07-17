# -*- coding: utf-8 -*-
"""
lib/config.py — 統一配置管理。

讀取 config.json，支援環境變數覆蓋。
用法：
    from lib.config import get, get_section
    timeout = get("api", "timeout", 180)
    api_cfg = get_section("api")
"""
import copy
import json
import os

_CONFIG = None
_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")

_DEFAULTS = {
    "api": {
        "url": "https://api.minimaxi.chat/v1/text/chatcompletion_v2",
        "model": "MiniMax-M2.7",
        "timeout": 180,
        "retry": 4,
        "rate_limit": {
            "max_concurrent": 8,
            "min_interval_ms": 100,
        },
    },
    "parallel": {
        "smoke": 6,
        "dev": 24,
        "holdout": 24,
    },
    "thresholds": {
        "max_candidate_length": 550,
        "smoke_allowed_drop": 2.0,
        "smoke_min_score": 75.0,
        "dev_min_improvement": 2.0,
        "holdout_max_drop": 1.0,
        "type_max_regression": 3.0,
        "word_rate_min": 85.0,
    },
    "archive": {
        "max_versions": 20,
    },
    "multi_candidate": {
        "enabled": True,
        "count": 3,
        "temperatures": [0.5, 0.7, 0.9],
    },
}


def _load_config():
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG
    _CONFIG = copy.deepcopy(_DEFAULTS)
    if os.path.exists(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            _deep_merge(_CONFIG, user_cfg)
        except Exception:
            pass
    _apply_env_overrides(_CONFIG)
    validate_config(_CONFIG)
    return _CONFIG


def _deep_merge(base, override):
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


_NUMERIC_ENV_KEYS = frozenset({
    "AUTORESEARCH_API_TIMEOUT",
    "AUTORESEARCH_SMOKE_PARALLEL",
    "AUTORESEARCH_DEV_PARALLEL",
    "AUTORESEARCH_HOLDOUT_PARALLEL",
    "AUTORESEARCH_MAX_CANDIDATE_LENGTH",
})

_NUMERIC_SCHEMA = {
    "api.timeout": (int, float),
    "api.retry": (int, float),
    "api.rate_limit.max_concurrent": (int, float),
    "api.rate_limit.min_interval_ms": (int, float),
    "parallel.smoke": (int, float),
    "parallel.dev": (int, float),
    "parallel.holdout": (int, float),
    "thresholds.max_candidate_length": (int, float),
    "thresholds.smoke_allowed_drop": (int, float),
    "thresholds.smoke_min_score": (int, float),
    "thresholds.dev_min_improvement": (int, float),
    "thresholds.holdout_max_drop": (int, float),
    "thresholds.type_max_regression": (int, float),
    "thresholds.word_rate_min": (int, float),
    "archive.max_versions": (int, float),
    "multi_candidate.count": (int, float),
}


def validate_config(cfg):
    for dotted_key, expected_types in _NUMERIC_SCHEMA.items():
        parts = dotted_key.split(".")
        value = cfg
        for part in parts:
            if not isinstance(value, dict):
                value = {}
                break
            value = value.get(part, {})
        if value == {}:
            continue
        if not isinstance(value, expected_types):
            raise ValueError(
                f"設定值 {dotted_key}={value!r} 型別不符，期望 {expected_types}"
            )


def _apply_env_overrides(cfg):
    env_map = {
        "MINIMAX_API_KEY": ("api", "api_key"),
        "AUTORESEARCH_API_URL": ("api", "url"),
        "AUTORESEARCH_API_MODEL": ("api", "model"),
        "AUTORESEARCH_API_TIMEOUT": ("api", "timeout"),
        "AUTORESEARCH_SMOKE_PARALLEL": ("parallel", "smoke"),
        "AUTORESEARCH_DEV_PARALLEL": ("parallel", "dev"),
        "AUTORESEARCH_HOLDOUT_PARALLEL": ("parallel", "holdout"),
        "AUTORESEARCH_MAX_CANDIDATE_LENGTH": ("thresholds", "max_candidate_length"),
    }
    for env_key, (section, key) in env_map.items():
        val = os.environ.get(env_key)
        if val is not None:
            if section not in cfg:
                cfg[section] = {}
            if env_key in _NUMERIC_ENV_KEYS:
                if val.strip() == "":
                    raise ValueError(
                        f"環境變數 {env_key} 不可為空字串"
                    )
                try:
                    cfg[section][key] = int(val)
                except (ValueError, TypeError):
                    try:
                        cfg[section][key] = float(val)
                    except (ValueError, TypeError):
                        raise ValueError(
                            f"環境變數 {env_key}={val!r} 無法解析為數值"
                        ) from None
            else:
                cfg[section][key] = val


def get(section, key=None, default=None):
    """取得配置值。若只傳 section，回傳整個 section dict。"""
    cfg = _load_config()
    section_data = cfg.get(section, {})
    # 若 key 是 dict/list（誤用），視為只取 section
    if key is None or isinstance(key, (dict, list)):
        if key is not None and default is None:
            default = key  # get("section", {}) → default={}
        return section_data if section_data else default
    if isinstance(section_data, dict):
        return section_data.get(key, default)
    return default


def get_section(section):
    cfg = _load_config()
    return dict(cfg.get(section, {}))


def get_all():
    return dict(_load_config())
