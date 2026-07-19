"""設定讀取 API 不得把內部快取的可變物件暴露給呼叫端。"""

import lib.config as config


def test_get_section_nested_mutation_does_not_change_cached_config():
    section = config.get_section("api")

    section["rate_limit"]["max_concurrent"] = 0

    assert config.get_section("api")["rate_limit"]["max_concurrent"] == 8


def test_get_section_value_mutation_does_not_change_cached_config():
    temperatures = config.get("multi_candidate", "temperatures")

    temperatures.append(1.1)

    assert config.get("multi_candidate", "temperatures") == [0.5, 0.7, 0.9]


def test_get_whole_section_mutation_does_not_change_cached_config():
    section = config.get("multi_candidate")

    section["temperatures"].append(1.1)

    assert config.get("multi_candidate")["temperatures"] == [0.5, 0.7, 0.9]
