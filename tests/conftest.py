import copy

import pytest

import lib.config as config


@pytest.fixture(autouse=True)
def isolate_lib_config():
    """Reset lib.config module cache for each test case."""
    original = copy.deepcopy(config._CONFIG)
    config._CONFIG = None
    try:
        yield
    finally:
        config._CONFIG = original
