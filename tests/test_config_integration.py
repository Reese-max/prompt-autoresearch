"""配置輸入到 lib.api 外部請求的整合測試。"""

import json
from unittest import mock

import pytest

import lib.api as api
import lib.config as config


class FakeHTTPResponse:
    def __init__(self, body):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def read(self):
        return self._body


@pytest.fixture
def api_consumer(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "_CONFIG", None)
    monkeypatch.setattr(config, "_CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    monkeypatch.setattr(api, "_semaphore", None)
    monkeypatch.setattr(api, "_last_call_ts", 0.0)
    monkeypatch.setattr(api, "_rate_wait", lambda: None)


def _response():
    return FakeHTTPResponse(
        json.dumps(
            {"choices": [{"message": {"content": "  回應  "}}]},
            ensure_ascii=False,
        ).encode("utf-8")
    )


def test_invalid_env_config_reaches_consumer_as_failure_without_request(api_consumer, monkeypatch, tmp_path):
    (tmp_path / "config.json").write_text(
        json.dumps({"api": {"url": "https://file.example/v1", "timeout": 300}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("AUTORESEARCH_API_TIMEOUT", "not-a-number")
    urlopen = mock.Mock()
    monkeypatch.setattr(api.urllib.request, "urlopen", urlopen)

    with pytest.raises(ValueError, match="AUTORESEARCH_API_TIMEOUT"):
        api.call_minimax("system", "user")

    urlopen.assert_not_called()
    assert config._CONFIG is None


def test_env_override_wins_over_file_at_http_consumer(api_consumer, monkeypatch, tmp_path):
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "api": {
                    "url": "https://file.example/v1",
                    "model": "file-model",
                    "timeout": 300,
                    "rate_limit": {"max_concurrent": 1},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AUTORESEARCH_API_URL", "https://env.example/v2")
    monkeypatch.setenv("AUTORESEARCH_API_MODEL", "env-model")
    monkeypatch.setenv("AUTORESEARCH_API_TIMEOUT", "7")
    urlopen = mock.Mock(return_value=_response())
    monkeypatch.setattr(api.urllib.request, "urlopen", urlopen)

    assert api.call_minimax("system", "user") == "回應"

    request = urlopen.call_args.args[0]
    assert request.full_url == "https://env.example/v2"
    assert urlopen.call_args.kwargs["timeout"] == 7
    assert json.loads(request.data.decode("utf-8"))["model"] == "env-model"


def test_missing_config_fallback_reaches_http_consumer_with_defaults(api_consumer, monkeypatch):
    urlopen = mock.Mock(return_value=_response())
    monkeypatch.setattr(api.urllib.request, "urlopen", urlopen)

    assert api.call_minimax("system", "user") == "回應"

    request = urlopen.call_args.args[0]
    assert request.full_url == config._DEFAULTS["api"]["url"]
    assert urlopen.call_args.kwargs["timeout"] == config._DEFAULTS["api"]["timeout"]
    assert json.loads(request.data.decode("utf-8"))["model"] == config._DEFAULTS["api"]["model"]
