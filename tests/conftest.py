import copy

import pytest

import lib.config as config


@pytest.fixture(autouse=True)
def isolate_lib_config():
    """Reset lib.config module cache and config path for each test case."""
    original = copy.deepcopy(config._CONFIG)
    original_path = config._CONFIG_PATH
    config._CONFIG = None
    try:
        yield
    finally:
        config._CONFIG = original
        config._CONFIG_PATH = original_path
