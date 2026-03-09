from src import config


def test_get_theme_returns_default_for_unknown_name():
    theme = config.get_theme("non-existent")

    assert theme == config.THEMES[config.DEFAULT_THEME]


def test_get_category_info_returns_other_for_unknown_key():
    category = config.get_category_info("unknown")

    assert category == config.CATEGORIES["other"]


def test_format_number_handles_k_and_m_ranges():
    assert config.format_number(999) == "999"
    assert config.format_number(1500) == "1.5K"
    assert config.format_number(2500000) == "2.5M"


def test_get_repo_url_formats_expected_path():
    assert config.get_repo_url("owner", "repo") == "https://github.com/owner/repo"


def test_env_parsers_handle_invalid_values(monkeypatch):
    monkeypatch.setenv("TEST_INT", "abc")
    monkeypatch.setenv("TEST_FLOAT", "1.5")
    monkeypatch.setenv("TEST_LIST", "a, b, ,c")

    assert config._get_env_int("TEST_INT", 10) == 10
    assert config._get_env_float("TEST_FLOAT", 0.2) == 1.0
    assert config._get_env_list("TEST_LIST") == ["a", "b", "c"]
