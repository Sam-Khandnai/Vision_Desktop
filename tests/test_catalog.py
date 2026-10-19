import pytest

from vision import catalog


def test_catalog_has_at_least_90_unique_entries():
    servers = catalog.load()["servers"]
    assert len(servers) >= 90
    assert len({s["id"] for s in servers}) == len(servers)
    cats = set(catalog.load()["categories"])
    assert {s["category"] for s in servers} <= cats


def test_every_entry_is_well_formed_and_never_puts_secrets_in_args():
    for s in catalog.load()["servers"]:
        assert s["transport"] in ("stdio", "streamable_http", "sse")
        if s["transport"] == "stdio":
            assert s["command"] in ("npx", "uvx")
        else:
            assert s["url"].startswith(("http://", "https://"))
        for inp in s["inputs"]:
            assert inp["target"] in ("arg", "env", "header")
            if inp["type"] == "secret":
                assert inp["target"] in ("env", "header"), f"{s['id']}: secret would be stored in plain args"
        placeholders = {i["key"] for i in s["inputs"] if i["target"] == "arg"}
        for a in s.get("args", []):
            for key in placeholders:
                a = a.replace("{{" + key + "}}", "")
            assert "{{" not in a, f"{s['id']}: unresolved placeholder in {a}"


def test_filesystem_install_resolves_folder():
    kw = catalog.build_server(catalog.get("filesystem"), {"folder": "C:\\work"})
    assert kw["config"]["command"] == "npx"
    assert kw["config"]["args"][-1] == "C:\\work"


def test_github_token_goes_to_header_with_bearer_prefix():
    kw = catalog.build_server(catalog.get("github"), {"token": "ghp_x"})
    assert kw["headers"] == {"Authorization": "Bearer ghp_x"}
    assert kw["config"] == {"url": "https://api.githubcopilot.com/mcp/"}


def test_env_inputs_use_defaults_and_required_is_enforced():
    kw = catalog.build_server(catalog.get("redis"), {})
    assert kw["env"]["REDIS_HOST"] == "127.0.0.1"
    assert "REDIS_PWD" not in kw["env"]
    with pytest.raises(ValueError):
        catalog.build_server(catalog.get("brave-search"), {})


def test_every_text_is_bilingual():
    data = catalog.load()
    for cat in data["categories"].values():
        assert cat["fa"] and cat["en"]
    for s in data["servers"]:
        texts = [s["description"], *(i["label"] for i in s["inputs"])]
        texts += [s["note"]] if "note" in s else []
        texts += [i["help"] for i in s["inputs"] if "help" in i]
        for t in texts:
            assert t["fa"].strip() and t["en"].strip(), s["id"]
        # the Persian text must really be Persian, the English text must not be
        assert any("\u0600" <= ch <= "\u06ff" for ch in s["description"]["fa"]), s["id"]
        assert not any("\u0600" <= ch <= "\u06ff" for ch in s["description"]["en"]), s["id"]


def test_static_env_is_included():
    kw = catalog.build_server(catalog.get("n8n"), {})
    assert kw["env"] == {"MCP_MODE": "stdio", "LOG_LEVEL": "error", "DISABLE_CONSOLE_OUTPUT": "true"}


def test_exa_works_without_a_key_and_uses_bearer_when_given():
    assert catalog.build_server(catalog.get("exa"), {})["headers"] == {}
    assert catalog.build_server(catalog.get("exa"), {"token": "k"})["headers"] == {"Authorization": "Bearer k"}
