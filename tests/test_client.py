from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from wan_mcp.client import TEST_MODE_ENV, WanAPIError, WanClient
from wan_mcp.config import WanSettings
from wan_mcp.validation import MediaItem


def _settings(tmp_path: Path) -> WanSettings:
    return WanSettings(
        api_key="sk-test",
        workspace_id="ws1",
        region="singapore",
        output_dir=tmp_path,
    )


def _client(tmp_path: Path, handler) -> WanClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport)
    return WanClient(_settings(tmp_path), http=http, poll_interval_seconds=0)


@pytest.mark.asyncio
async def test_create_sends_async_header_and_official_body(tmp_path: Path) -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["method"] = request.method
        seen["headers"] = dict(request.headers)
        seen["body"] = request.read()
        return httpx.Response(
            200,
            json={
                "output": {"task_status": "PENDING", "task_id": "tid-1"},
                "request_id": "req-1",
            },
        )

    client = _client(tmp_path, handler)
    result = await client.create_task(
        prompt="A kitten running",
        resolution="480P",
        duration=5,
    )
    assert result["output"]["task_id"] == "tid-1"
    assert seen["method"] == "POST"
    assert seen["url"] == (
        "https://ws1.ap-southeast-1.maas.aliyuncs.com"
        "/api/v1/services/aigc/video-generation/video-synthesis"
    )
    headers = {k.lower(): v for k, v in seen["headers"].items()}
    assert headers["x-dashscope-async"] == "enable"
    assert headers["authorization"] == "Bearer sk-test"
    assert headers["content-type"].startswith("application/json")
    import json

    body = json.loads(seen["body"])
    assert body["model"] == "wan3.0-video"
    assert "enable_thinking" not in body
    await client.aclose()


@pytest.mark.asyncio
async def test_beijing_create_url(tmp_path: Path) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json={"output": {"task_status": "PENDING", "task_id": "t"}, "request_id": "r"},
        )

    settings = WanSettings(
        api_key="sk",
        workspace_id="bjws",
        region="beijing",
        output_dir=tmp_path,
    )
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = WanClient(settings, http=http)
    await client.create_task(prompt="hello")
    assert seen["url"].startswith("https://bjws.cn-beijing.maas.aliyuncs.com/")
    await client.aclose()


@pytest.mark.asyncio
async def test_get_task_no_async_header(tmp_path: Path) -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["headers"] = dict(request.headers)
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "request_id": "r",
                "output": {
                    "task_id": "tid-1",
                    "task_status": "RUNNING",
                },
            },
        )

    client = _client(tmp_path, handler)
    payload = await client.get_task("tid-1")
    assert payload["output"]["task_status"] == "RUNNING"
    headers = {k.lower(): v for k, v in seen["headers"].items()}
    assert "x-dashscope-async" not in headers
    assert seen["url"].endswith("/api/v1/tasks/tid-1")
    await client.aclose()


@pytest.mark.asyncio
async def test_wait_downloads_mp4(tmp_path: Path) -> None:
    polls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/video.mp4"):
            return httpx.Response(200, content=b"\x00\x00mp4fake")
        polls["n"] += 1
        if polls["n"] < 3:
            status = "PENDING" if polls["n"] == 1 else "RUNNING"
            return httpx.Response(
                200,
                json={
                    "request_id": "r",
                    "output": {"task_id": "tid-9", "task_status": status},
                },
            )
        return httpx.Response(
            200,
            json={
                "request_id": "r",
                "output": {
                    "task_id": "tid-9",
                    "task_status": "SUCCEEDED",
                    "orig_prompt": "beach",
                    "video_url": "https://dashscope-result.example/xxx/video.mp4",
                    "submit_time": "2026-08-06 10:01:35.452",
                    "scheduled_time": "2026-08-06 10:01:35.507",
                    "end_time": "2026-08-06 10:13:33.838",
                },
                "usage": {
                    "video_count": 1,
                    "duration": 5,
                    "input_video_duration": 0,
                    "output_video_duration": 5,
                    "fps": 30,
                    "SR": 720,
                    "ratio": "16:9",
                },
            },
        )

    async def no_sleep(_: float) -> None:
        return None

    client = _client(tmp_path, handler)
    result = await client.wait_for_video(
        "tid-9",
        poll_interval_seconds=0,
        timeout_seconds=30,
        sleep=no_sleep,
    )
    assert result["output"]["task_status"] == "SUCCEEDED"
    assert result["usage"]["SR"] == 720
    path = Path(result["local_path"])
    assert path.exists()
    assert path.read_bytes() == b"\x00\x00mp4fake"
    await client.aclose()


@pytest.mark.asyncio
async def test_failed_task(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "request_id": "r",
                "output": {
                    "task_id": "tid-f",
                    "task_status": "FAILED",
                    "code": "InvalidParameter",
                    "message": "The two modes are mutually exclusive. Do not pass reference_xx and first_frame/last_frame at the same time.",
                },
            },
        )

    client = _client(tmp_path, handler)
    with pytest.raises(WanAPIError, match="mutually exclusive"):
        await client.wait_for_video("tid-f", poll_interval_seconds=0, timeout_seconds=5)
    await client.aclose()


@pytest.mark.asyncio
async def test_create_invalid_api_key_payload(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={
                "code": "InvalidApiKey",
                "message": "No API-key provided.",
                "request_id": "r",
            },
        )

    client = _client(tmp_path, handler)
    with pytest.raises(WanAPIError, match="No API-key"):
        await client.create_task(prompt="x")
    await client.aclose()


def test_test_mode_blocks_live_http(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TEST_MODE_ENV, "1")
    with pytest.raises(RuntimeError, match="WAN_TEST_MODE"):
        WanClient(_settings(tmp_path))


@pytest.mark.asyncio
async def test_create_media_first_frame(tmp_path: Path) -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen["body"] = json.loads(request.read())
        return httpx.Response(
            200,
            json={"output": {"task_status": "PENDING", "task_id": "t"}, "request_id": "r"},
        )

    client = _client(tmp_path, handler)
    await client.create_task(
        prompt="urban",
        media=[MediaItem(type="first_frame", url="https://example.com/rap.png")],
    )
    assert seen["body"]["input"]["media"][0]["type"] == "first_frame"
    await client.aclose()
