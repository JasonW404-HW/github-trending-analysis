from src.util import model_util


def test_normalize_provider_env_prefix_handles_symbols():
    assert model_util._normalize_provider_env_prefix("open-router") == "OPEN_ROUTER"
    assert model_util._normalize_provider_env_prefix(" ") == ""


def test_resolve_model_name_prefers_argument():
    assert model_util.resolve_model_name("ollama/gemma3:4b") == "ollama/gemma3:4b"


def test_resolve_model_name_raises_when_empty(monkeypatch):
    monkeypatch.setattr(model_util, "MODEL", "")

    try:
        model_util.resolve_model_name(None)
    except ValueError as error:
        assert "MODEL 环境变量未设置" in str(error)
    else:
        raise AssertionError("Expected ValueError")


def test_resolve_model_api_key_prefers_explicit_then_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "from-env")

    assert model_util.resolve_model_api_key("openai/gpt-4.1", api_key="manual") == "manual"
    assert model_util.resolve_model_api_key("openai/gpt-4.1") == "from-env"


def test_build_completion_kwargs_adds_api_key_when_present(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")

    kwargs = model_util.build_completion_kwargs(model="openai/gpt-4.1")

    assert kwargs["model"] == "openai/gpt-4.1"
    assert kwargs["api_key"] == "env-key"


def test_litellm_completion_passes_options(monkeypatch):
    captured = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(model_util, "completion", fake_completion)

    result = model_util.litellm_completion(
        messages=[{"role": "user", "content": "hello"}],
        model="openai/gpt-4.1",
        api_key="manual-key",
        temperature=0.1,
    )

    assert result == {"ok": True}
    assert captured["model"] == "openai/gpt-4.1"
    assert captured["api_key"] == "manual-key"
    assert captured["messages"][0]["content"] == "hello"
    assert captured["temperature"] == 0.1
