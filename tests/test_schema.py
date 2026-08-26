from __future__ import annotations

from typing import Any

import pytest


CREATE_PROPS = {
    "prompt",
    "media",
    "resolution",
    "ratio",
    "duration",
    "audio",
    "seed",
    "watermark",
    "model",
}

MEDIA_PROPS = {"type", "url"}
MEDIA_TYPES = {
    "first_frame",
    "last_frame",
    "reference_image",
    "reference_video",
    "reference_audio",
    "file",
    "link",
}
RESOLUTIONS = {"1080P", "720P", "480P"}
RATIOS = {"adaptive", "16:9", "4:3", "1:1", "3:4", "9:16"}


def _tools_by_name(listed: Any) -> dict[str, Any]:
    tools = listed.tools if hasattr(listed, "tools") else listed
    return {t.name: t for t in tools}


def _schema(tool: Any) -> dict[str, Any]:
    return getattr(tool, "inputSchema", None) or getattr(tool, "input_schema")


def _enums(schema: dict[str, Any], *path: str) -> set[str]:
    node: Any = schema
    for key in path:
        node = node[key]
    if "enum" in node:
        return set(node["enum"])
    if "anyOf" in node:
        for option in node["anyOf"]:
            if "enum" in option:
                return set(option["enum"])
            if option.get("type") == "string" and "enum" in option:
                return set(option["enum"])
    if "items" in node:
        return _enums(node, "items")
    return set()


def _defs(schema: dict[str, Any]) -> dict[str, Any]:
    return schema.get("$defs") or schema.get("definitions") or {}


def _media_schema(schema: dict[str, Any]) -> dict[str, Any]:
    media = schema["properties"]["media"]
    # unwrap anyOf / null
    candidates = [media]
    if "anyOf" in media:
        candidates = media["anyOf"]
    for item in candidates:
        if item.get("type") == "array":
            items = item["items"]
            if "$ref" in items:
                ref = items["$ref"].rsplit("/", 1)[-1]
                return _defs(schema)[ref]
            return items
    raise AssertionError(f"media schema not found: {media}")


@pytest.mark.asyncio
async def test_official_fields_only() -> None:
    from mcp import Client

    from wan_mcp.server import mcp

    async with Client(mcp) as session:
        listed = await session.list_tools()

    by_name = _tools_by_name(listed)
    create = _schema(by_name["wan_create_video"])
    props = set(create["properties"])
    assert props == CREATE_PROPS
    dumped = str(create).lower()
    assert "enable_thinking" not in dumped
    assert "acedatacloud" not in dumped

    media = _media_schema(create)
    assert set(media["properties"]) == MEDIA_PROPS
    types = set(media["properties"]["type"]["enum"])
    assert types == MEDIA_TYPES

    res = create["properties"]["resolution"]
    assert RESOLUTIONS <= _flatten_enum(res)
    assert RATIOS <= _flatten_enum(create["properties"]["ratio"])
    assert _flatten_enum(create["properties"]["model"]) == {"wan3.0-video"}

    get_schema = _schema(by_name["wan_get_task"])
    assert set(get_schema["properties"]) == {"task_id"}

    wait_schema = _schema(by_name["wan_wait_for_video"])
    assert "task_id" in wait_schema["properties"]
    assert "enable_thinking" not in wait_schema["properties"]


def _flatten_enum(node: dict[str, Any]) -> set[str]:
    found: set[str] = set()
    if "enum" in node:
        found.update(node["enum"])
    if "const" in node and isinstance(node["const"], str):
        found.add(node["const"])
    for key in ("anyOf", "oneOf"):
        for option in node.get(key, []):
            if isinstance(option, dict):
                found.update(_flatten_enum(option))
    return {v for v in found if v is not None}
