import pytest
from auditor import resolve_token, load_settings


def test_resolve_token_prefers_env(monkeypatch):
    monkeypatch.setenv("JIRA_API_TOKEN", "from-env")
    assert resolve_token(flag_token="from-flag", config_token="from-cfg") == "from-env"


def test_resolve_token_flag_over_config(monkeypatch):
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    assert resolve_token(flag_token="from-flag", config_token="from-cfg") == "from-flag"


def test_resolve_token_config_last(monkeypatch):
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    assert resolve_token(flag_token=None, config_token="from-cfg") == "from-cfg"


def test_resolve_token_missing_raises(monkeypatch):
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        resolve_token(flag_token=None, config_token=None)


def test_load_settings_merges_flags_over_config(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('base_url = "https://cfg.atlassian.net"\nemail = "cfg@x.com"\ngroups = ["a"]\nout_dir = "/tmp/cfg"\n')

    class Args:
        config = str(cfg)
        base_url = "https://flag.atlassian.net"
        email = None
        token = None
        group = ["b", "c"]
        out_dir = None

    settings = load_settings(Args())
    assert settings["base_url"] == "https://flag.atlassian.net"   # flag wins
    assert settings["email"] == "cfg@x.com"                       # falls back to config
    assert settings["groups"] == ["b", "c"]                       # flag groups win
    assert settings["out_dir"] == "/tmp/cfg"
