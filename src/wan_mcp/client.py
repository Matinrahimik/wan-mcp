"""Official Model Studio HTTP client for Wan 3.0 video.

Singapore create:
  POST https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis
Beijing create:
  POST https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis
Poll:
  GET https://{WorkspaceId}.{region-host}.maas.aliyuncs.com/api/v1/tasks/{task_id}
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import httpx

from wan_mcp.config import WanSettings
from wan_mcp.validation import TERMINAL_STATUSES, MediaItem, build_create_body

DEFAULT_POLL_INTERVAL_SECONDS = 15
TEST_MODE_ENV = "WAN_TEST_MODE"
_SAFE_TASK_ID = re.compile(r"[^A-Za-z0-9._-]+")


class WanAPIError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        request_id: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.request_id = request_id
        self.status_code = status_code

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"message": str(self)}
        if self.code is not None:
            payload["code"] = self.code
        if self.request_id is not None:
            payload["request_id"] = self.request_id
        if self.status_code is not None:
            payload["status_code"] = self.status_code
        return payload


def _auth_headers(api_key: str, *, async_enable: bool) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if async_enable:
        # Required on create. Missing → "current user api does not support synchronous calls".
        headers["X-DashScope-Async"] = "enable"
    return headers


def _raise_if_api_error(payload: Any, status_code: int) -> None:
    if not isinstance(payload, dict):
        raise WanAPIError(
            "Model Studio returned a non-JSON response",
            status_code=status_code,
        )
    code = payload.get("code")
    message = payload.get("message")
    output = payload.get("output") if isinstance(payload.get("output"), dict) else {}
    task_status = output.get("task_status") if output else None
    if code and task_status != "FAILED":
        raise WanAPIError(
            str(message or code),
            code=str(code),
            request_id=_as_str(payload.get("request_id")),
            status_code=status_code,
        )
    if status_code >= 400:
        raise WanAPIError(
            str(message or f"HTTP {status_code}"),
            code=_as_str(code),
            request_id=_as_str(payload.get("request_id")),
            status_code=status_code,
        )


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _safe_filename(task_id: str) -> str:
    cleaned = _SAFE_TASK_ID.sub("_", task_id).strip("._") or "video"
    return f"{cleaned}.mp4"


class WanClient:
    def __init__(
        self,
        settings: WanSettings,
        *,
        http: httpx.AsyncClient | None = None,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> None:
        if http is None and os.environ.get(TEST_MODE_ENV) == "1":
            raise RuntimeError(
                "WAN_TEST_MODE=1 refuses live Model Studio HTTP "
                "(no paid generate in tests)"
            )
        self.settings = settings
        self._owns_http = http is None
        self._http = http or httpx.AsyncClient(timeout=httpx.Timeout(60.0))
        self.poll_interval_seconds = poll_interval_seconds

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def create_task(
        self,
        *,
        prompt: str | None = None,
        media: list[MediaItem] | None = None,
        resolution: str | None = None,
        ratio: str | None = None,
        duration: int | None = None,
        audio: bool | None = None,
        seed: int | None = None,
        watermark: bool | None = None,
        model: str = "wan3.0-video",
    ) -> dict[str, Any]:
        body = build_create_body(
            prompt=prompt,
            media=media,
            resolution=resolution,  # type: ignore[arg-type]
            ratio=ratio,  # type: ignore[arg-type]
            duration=duration,
            audio=audio,
            seed=seed,
            watermark=watermark,
            model=model,
        )
        response = await self._http.post(
            self.settings.create_url,
            headers=_auth_headers(self.settings.api_key, async_enable=True),
            json=body,
        )
        payload = _json_or_error(response)
        _raise_if_api_error(payload, response.status_code)
        return payload

    async def get_task(self, task_id: str) -> dict[str, Any]:
        if not task_id or not task_id.strip():
            raise WanAPIError("task_id is required")
        response = await self._http.get(
            self.settings.task_url(task_id.strip()),
            headers=_auth_headers(self.settings.api_key, async_enable=False),
        )
        payload = _json_or_error(response)
        _raise_if_api_error(payload, response.status_code)
        return payload

    async def download_video(self, video_url: str, task_id: str) -> Path:
        self.settings.output_dir.mkdir(parents=True, exist_ok=True)
        dest = self.settings.output_dir / _safe_filename(task_id)
        timeout = httpx.Timeout(300.0)
        async with self._http.stream("GET", video_url, timeout=timeout) as response:
            response.raise_for_status()
            with dest.open("wb") as handle:
                async for chunk in response.aiter_bytes():
                    handle.write(chunk)
        return dest

    async def wait_for_video(
        self,
        task_id: str,
        *,
        poll_interval_seconds: float | None = None,
        timeout_seconds: float = 900.0,
        sleep=None,
    ) -> dict[str, Any]:
        import asyncio
        import time

        interval = (
            self.poll_interval_seconds
            if poll_interval_seconds is None
            else poll_interval_seconds
        )
        sleeper = sleep or asyncio.sleep
        deadline = time.monotonic() + timeout_seconds
        last: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            last = await self.get_task(task_id)
            output = last.get("output") if isinstance(last.get("output"), dict) else {}
            status = output.get("task_status")
            if status in TERMINAL_STATUSES:
                if status == "SUCCEEDED":
                    video_url = output.get("video_url")
                    if not video_url:
                        raise WanAPIError(
                            "SUCCEEDED task did not include video_url",
                            request_id=_as_str(last.get("request_id")),
                        )
                    local_path = await self.download_video(str(video_url), task_id)
                    result = dict(last)
                    result["local_path"] = str(local_path)
                    return result
                if status == "FAILED":
                    raise WanAPIError(
                        str(output.get("message") or "task FAILED"),
                        code=_as_str(output.get("code")),
                        request_id=_as_str(last.get("request_id")),
                    )
                return last
            await sleeper(interval)
        raise WanAPIError(
            f"Timed out after {timeout_seconds}s waiting for task {task_id}",
            request_id=_as_str((last or {}).get("request_id")),
        )


def _json_or_error(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise WanAPIError(
            "Model Studio returned a non-JSON response",
            status_code=response.status_code,
        ) from exc
