import pytest

from vision import providers


def test_local_model_needs_no_key_and_gets_a_placeholder():
    model = providers.create_chat_model(base_url="http://localhost:11434/v1", api_key="",
                                        model_name="llama3", local=True)
    assert model.model_name == "llama3"
    assert model.openai_api_key.get_secret_value() == "ollama"


def test_remote_model_still_requires_a_key():
    with pytest.raises(ValueError, match="API key"):
        providers.create_chat_model(base_url="https://api.example.com/v1", api_key="", model_name="m")


def test_model_name_is_always_required():
    with pytest.raises(ValueError, match="Model name"):
        providers.create_chat_model(base_url="http://localhost:11434/v1", api_key="", model_name="", local=True)


async def test_list_models_accepts_ollama_tags_payload(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"models": [{"name": "llama3:latest"}, {"name": "qwen2:7b"}]}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None):
            assert url.endswith("/models")
            return FakeResponse()

    monkeypatch.setattr(providers.httpx, "AsyncClient", FakeClient)
    models = await providers.list_models(base_url="http://localhost:11434/v1", api_key="", local=True)
    assert [m["id"] for m in models] == ["llama3:latest", "qwen2:7b"]


async def test_list_models_requires_a_key_for_remote_servers():
    with pytest.raises(ValueError, match="API key"):
        await providers.list_models(base_url="https://api.example.com/v1", api_key="")
