"""Resolve DashScope / Wan credentials without hardcoding machine paths."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, MutableMapping

SECRET_FILENAME = "wan.json"
DEFAULT_OUTPUT_DIRNAME = "wan-output"
DEFAULT_REGION = "singapore"
VALID_REGIONS = frozenset({"singapore", "beijing"})

REGION_HOSTS = {
    "singapore": "ap-southeast-1.maas.aliyuncs.com",
    "beijing": "cn-beijing.maas.aliyuncs.com",
}


class ConfigError(RuntimeError):
    """Missing or invalid connector configuration."""


@dataclass(frozen=True)
class WanSettings:
    api_key: str
    workspace_id: str
    region: str
    output_dir: Path

    @property
    def base_url(self) -> str:
        host = REGION_HOSTS[self.region]
        return f"https://{self.workspace_id}.{host}"

    @property
    def create_url(self) -> str:
        return (
            f"{self.base_url}/api/v1/services/aigc/video-generation/video-synthesis"
        )

    def task_url(self, task_id: str) -> str:
        return f"{self.base_url}/api/v1/tasks/{task_id}"


def default_output_dir() -> Path:
    """Succeeded mp4 files go to ./wan-output under the current working directory."""
    return Path.cwd() / DEFAULT_OUTPUT_DIRNAME


def _nonempty(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _read_secret_file(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"Secret file {path} must be a JSON object")
    return raw


def _fill_from_file(
    path: Path,
    api_key: str | None,
    workspace_id: str | None,
    region: str | None,
) -> tuple[str | None, str | None, str | None]:
    data = _read_secret_file(path)
    if api_key is None:
        api_key = _nonempty(_as_str(data.get("api_key")))
    if workspace_id is None:
        workspace_id = _nonempty(_as_str(data.get("workspace_id")))
    if region is None:
        region = _nonempty(_as_str(data.get("region")))
    return api_key, workspace_id, region


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _normalize_region(region: str) -> str:
    lowered = region.strip().lower()
    if lowered not in VALID_REGIONS:
        allowed = ", ".join(sorted(VALID_REGIONS))
        raise ConfigError(f"WAN_REGION must be one of: {allowed}")
    return lowered


def load_env_file(
    path: Path,
    environ: MutableMapping[str, str] | None = None,
) -> None:
    """Load KEY=VALUE lines into environ without overwriting existing keys.

    Values are never logged. Missing files are ignored.
    """
    env: MutableMapping[str, str] = os.environ if environ is None else environ
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key and key not in env:
            env[key] = value


def discover_secret_files(
    secrets_root: Path | None = None,
) -> list[Path]:
    if secrets_root is None or not secrets_root.is_dir():
        return []
    return sorted(p for p in secrets_root.glob(f"*/{SECRET_FILENAME}") if p.is_file())


def _secrets_root_from(
    env: Mapping[str, str],
    secrets_root: Path | None,
) -> Path | None:
    if secrets_root is not None:
        return secrets_root
    raw = _nonempty(env.get("WAN_SECRETS_ROOT"))
    return Path(raw) if raw else None


def resolve_settings(
    environ: Mapping[str, str] | None = None,
    *,
    secrets_root: Path | None = None,
) -> WanSettings:
    """Resolve credentials from env, then optional JSON secret files.

    Order:
    1. ``DASHSCOPE_API_KEY`` / ``WAN_WORKSPACE_ID`` / ``WAN_REGION``
    2. ``WAN_SECRETS_FILE`` JSON when set
    3. ``<WAN_SECRETS_ROOT>/<WAN_AGENT_ID>/wan.json`` when ``WAN_AGENT_ID`` is set
    4. any ``<WAN_SECRETS_ROOT>/*/wan.json`` (exactly one file, or error if several)
    """
    if environ is None:
        load_env_file(Path.cwd() / ".env", os.environ)
        env: Mapping[str, str] = os.environ
    else:
        env = environ

    root = _secrets_root_from(env, secrets_root)

    api_key = _nonempty(env.get("DASHSCOPE_API_KEY"))
    workspace_id = _nonempty(env.get("WAN_WORKSPACE_ID"))
    region = _nonempty(env.get("WAN_REGION"))

    still_missing = api_key is None or workspace_id is None or region is None
    secrets_file = _nonempty(env.get("WAN_SECRETS_FILE"))
    if still_missing and secrets_file:
        path = Path(secrets_file)
        if not path.is_file():
            raise ConfigError(f"WAN_SECRETS_FILE not found: {path}")
        api_key, workspace_id, region = _fill_from_file(
            path, api_key, workspace_id, region
        )

    agent_id = _nonempty(env.get("WAN_AGENT_ID"))
    if (
        (api_key is None or workspace_id is None or region is None)
        and agent_id
        and root is not None
    ):
        specific = root / agent_id / SECRET_FILENAME
        if specific.is_file():
            api_key, workspace_id, region = _fill_from_file(
                specific, api_key, workspace_id, region
            )

    still_missing = api_key is None or workspace_id is None or region is None
    if still_missing and root is not None:
        matches = discover_secret_files(root)
        if agent_id:
            matches = [p for p in matches if p.parent.name != agent_id]
        if len(matches) == 1:
            api_key, workspace_id, region = _fill_from_file(
                matches[0], api_key, workspace_id, region
            )
        elif len(matches) > 1 and (api_key is None or workspace_id is None):
            raise ConfigError(
                "Multiple */wan.json files found under WAN_SECRETS_ROOT. "
                "Set WAN_AGENT_ID to select one."
            )

    if not api_key:
        raise ConfigError("DASHSCOPE_API_KEY is not set")
    if not workspace_id:
        raise ConfigError("WAN_WORKSPACE_ID is not set")
    if not region:
        region = DEFAULT_REGION

    output_dir_raw = _nonempty(env.get("WAN_OUTPUT_DIR"))
    output_dir = Path(output_dir_raw) if output_dir_raw else default_output_dir()

    return WanSettings(
        api_key=api_key,
        workspace_id=workspace_id,
        region=_normalize_region(region),
        output_dir=output_dir,
    )


def apply_secrets_to_env(
    environ: MutableMapping[str, str] | None = None,
    *,
    secrets_root: Path | None = None,
) -> WanSettings:
    """Load settings and copy them into the process environment (no logging)."""
    env: MutableMapping[str, str] = os.environ if environ is None else environ
    settings = resolve_settings(env, secrets_root=secrets_root)
    env["DASHSCOPE_API_KEY"] = settings.api_key
    env["WAN_WORKSPACE_ID"] = settings.workspace_id
    env["WAN_REGION"] = settings.region
    env["WAN_OUTPUT_DIR"] = str(settings.output_dir)
    return settings
