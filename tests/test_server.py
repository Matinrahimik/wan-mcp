from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from wan_mcp.client import WanClient
from wan_mcp.config import WanSettings
from wan_mcp.server import mcp, set_client_override


def _settings(tmp_path: Path) -> WanSettings:
    return WanSettings(
        api_key="sk-test",
        workspace_id="ws1",
        region="singapore",
        output_dir=tmp_path,
    )


@pytest.fixture
def patched_client(tmp_path: Path):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        url = str(request.url)
        if url.endswith("/video.mp4"):
            return httpx.Response(200, content=b"mp4")
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "output": {"task_status": "PENDING", "task_id": "tid-mcp"},
                    "request_id": "req-mcp",
                },
            )
        return httpx.Response(
            200,
            json={
                "request_id": "req-mcp",
                "output": {
                    "task_id": "tid-mcp",
                    "task_status": "SUCCEEDED",
                    "video_url": "https://cdn.example/video.mp4",
                    "orig_prompt": "kitten",
                },
                "usage": {
                    "video_count": 1,
                    "duration": 5,
                    "input_video_duration": 0,
                    "output_video_duration": 5,
                    "fps": 30,
                    "SR": 1080,
                    "ratio": "16:9",
                },
            },
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = WanClient(_settings(tmp_path), http=http, poll_interval_seconds=0)
    set_client_override(client)
    try:
        yield client, requests
    finally:
        set_client_override(None)


async def _call(name: str, arguments: dict[str, Any]) -> Any:
    from mcp import Client

    async with Client(mcp) as session:
        return await session.call_tool(name, arguments)


@pytest.mark.asyncio
async def test_list_tools_names() -> None:
    from mcp import Client

    async with Client(mcp) as session:
        listed = await session.list_tools()
    tools = listed.tools if hasattr(listed, "tools") else listed
    names = {t.name for t in tools}
    assert names == {"wan_create_video", "wan_get_task", "wan_wait_for_video"}


@pytest.mark.asyncio
async def test_create_via_mcp(patched_client) -> None:
    _client, requests = patched_client
    result = await _call("wan_create_video", {"prompt": "A kitten on a rooftop"})
    data = _tool_json(result)
    assert data["output"]["task_id"] == "tid-mcp"
    assert requests[0].headers["x-dashscope-async"] == "enable"
    body = json.loads(requests[0].content)
    assert body["model"] == "wan3.0-video"
    assert "enable_thinking" not in body


@pytest.mark.asyncio
async def test_create_rejects_illegal_combo(patched_client) -> None:
    result = await _call(
        "wan_create_video",
        {
            "prompt": "x",
            "media": [
                {"type": "first_frame", "url": "https://example.com/a.png"},
                {"type": "reference_image", "url": "https://example.com/b.png"},
            ],
        },
    )
    data = _tool_json(result)
    assert data.get("error") is True
    assert "mutually exclusive" in data["message"]


@pytest.mark.asyncio
async def test_get_and_wait(patched_client, tmp_path: Path) -> None:
    got = _tool_json(await _call("wan_get_task", {"task_id": "tid-mcp"}))
    assert got["output"]["task_status"] == "SUCCEEDED"
    waited = _tool_json(await _call("wan_wait_for_video", {"task_id": "tid-mcp"}))
    assert waited["local_path"].endswith(".mp4")
    assert Path(waited["local_path"]).exists()
    assert waited["usage"]["video_count"] == 1


def _tool_json(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        if "result" in structured and isinstance(structured["result"], dict):
            return structured["result"]
        if "error" in structured or "output" in structured:
            return structured
    content = getattr(result, "content", None)
    if content:
        text = content[0].text
        return json.loads(text)
    raise AssertionError(f"unexpected tool result: {result!r}")
