from pathlib import Path

import pytest

from wan_mcp.config import ConfigError, apply_secrets_to_env, resolve_settings


def test_env_only(tmp_path: Path) -> None:
    settings = resolve_settings(
        {
            "DASHSCOPE_API_KEY": "sk-test",
            "WAN_WORKSPACE_ID": "ws-1",
            "WAN_REGION": "beijing",
        },
        secrets_root=tmp_path,
    )
    assert settings.api_key == "sk-test"
    assert settings.workspace_id == "ws-1"
    assert settings.region == "beijing"
    assert settings.base_url == "https://ws-1.cn-beijing.maas.aliyuncs.com"
    assert settings.create_url.endswith(
        "/api/v1/services/aigc/video-generation/video-synthesis"
    )


def test_singapore_host() -> None:
    settings = resolve_settings(
        {
            "DASHSCOPE_API_KEY": "sk-test",
            "WAN_WORKSPACE_ID": "abc",
            "WAN_REGION": "singapore",
        },
        secrets_root=Path("/nonexistent"),
    )
    assert settings.base_url == "https://abc.ap-southeast-1.maas.aliyuncs.com"
    assert settings.task_url("tid-1") == (
        "https://abc.ap-southeast-1.maas.aliyuncs.com/api/v1/tasks/tid-1"
    )


def test_agent_id_file(tmp_path: Path) -> None:
    agent = tmp_path / "agent-xyz"
    agent.mkdir()
    (agent / "wan.json").write_text(
        '{"api_key":"from-file","workspace_id":"ws-file","region":"singapore"}',
        encoding="utf-8",
    )
    settings = resolve_settings(
        {"WAN_AGENT_ID": "agent-xyz"},
        secrets_root=tmp_path,
    )
    assert settings.api_key == "from-file"
    assert settings.workspace_id == "ws-file"


def test_env_wins_over_file(tmp_path: Path) -> None:
    agent = tmp_path / "agent-xyz"
    agent.mkdir()
    (agent / "wan.json").write_text(
        '{"api_key":"from-file","workspace_id":"ws-file","region":"beijing"}',
        encoding="utf-8",
    )
    settings = resolve_settings(
        {
            "DASHSCOPE_API_KEY": "env-key",
            "WAN_WORKSPACE_ID": "env-ws",
            "WAN_REGION": "singapore",
            "WAN_AGENT_ID": "agent-xyz",
        },
        secrets_root=tmp_path,
    )
    assert settings.api_key == "env-key"
    assert settings.workspace_id == "env-ws"
    assert settings.region == "singapore"


def test_glob_single_file_no_agent_id(tmp_path: Path) -> None:
    folder = tmp_path / "some-agent"
    folder.mkdir()
    (folder / "wan.json").write_text(
        '{"api_key":"glob-key","workspace_id":"glob-ws","region":"beijing"}',
        encoding="utf-8",
    )
    settings = resolve_settings({}, secrets_root=tmp_path)
    assert settings.api_key == "glob-key"
    assert settings.workspace_id == "glob-ws"
    assert settings.region == "beijing"


def test_glob_multiple_files_requires_agent_id(tmp_path: Path) -> None:
    for name in ("a1", "a2"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "wan.json").write_text(
            '{"api_key":"k","workspace_id":"w","region":"singapore"}',
            encoding="utf-8",
        )
    with pytest.raises(ConfigError, match="WAN_AGENT_ID"):
        resolve_settings({}, secrets_root=tmp_path)


def test_missing_key(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="DASHSCOPE_API_KEY"):
        resolve_settings({}, secrets_root=tmp_path)


def test_invalid_region() -> None:
    with pytest.raises(ConfigError, match="WAN_REGION"):
        resolve_settings(
            {
                "DASHSCOPE_API_KEY": "sk",
                "WAN_WORKSPACE_ID": "ws",
                "WAN_REGION": "us-west",
            },
            secrets_root=Path("/nonexistent"),
        )


def test_region_defaults_singapore() -> None:
    settings = resolve_settings(
        {"DASHSCOPE_API_KEY": "sk", "WAN_WORKSPACE_ID": "ws"},
        secrets_root=Path("/nonexistent"),
    )
    assert settings.region == "singapore"


def test_apply_secrets_to_env(tmp_path: Path) -> None:
    env: dict[str, str] = {
        "DASHSCOPE_API_KEY": "sk",
        "WAN_WORKSPACE_ID": "ws",
        "WAN_REGION": "beijing",
    }
    apply_secrets_to_env(env, secrets_root=tmp_path)
    assert env["WAN_REGION"] == "beijing"
    assert "sk" == env["DASHSCOPE_API_KEY"]
