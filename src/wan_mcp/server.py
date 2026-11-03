"""stdio MCP server: official Wan 3.0 Model Studio tools only."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from mcp.server import MCPServer
from pydantic import Field

from wan_mcp.client import DEFAULT_POLL_INTERVAL_SECONDS, WanAPIError, WanClient
from wan_mcp.config import ConfigError, resolve_settings
from wan_mcp.validation import (
    MODEL_ID,
    PROMPT_MAX_CHARS,
    SEED_MAX,
    MediaItem,
    ValidationError,
)

mcp = MCPServer("wan")

_client_override: WanClient | None = None


def set_client_override(client: WanClient | None) -> None:
    global _client_override
    _client_override = client


def _client() -> WanClient:
    if _client_override is not None:
        return _client_override
    return WanClient(resolve_settings())


def _error_payload(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, WanAPIError):
        return {"error": True, **exc.as_dict()}
    if isinstance(exc, (ValidationError, ConfigError)):
        return {"error": True, "message": str(exc)}
    return {"error": True, "message": str(exc)}


@mcp.tool()
async def wan_create_video(
    prompt: Annotated[
        str | None,
        Field(
            default=None,
            max_length=PROMPT_MAX_CHARS,
            description=(
                "Text prompt (Chinese or English). Either this or media must be "
                "provided. Max 20000 characters. In reference mode, "
                '"Image 1" / "Video 1" / "Audio 1" index media of that type in '
                "array order."
            ),
        ),
    ] = None,
    media: Annotated[
        list[MediaItem] | None,
        Field(
            default=None,
            description=(
                "input.media[] objects with type + url. Types: first_frame (max 1), "
                "last_frame (max 1), reference_image (max 10), reference_video "
                "(max 5, total ≤15s), reference_audio (max 5, total ≤15s), "
                "file (max 1, not with link), link (max 1, not with file). "
                "reference_*/file/link are mutually exclusive with "
                "first_frame/last_frame. url is public http(s) or, for images, "
                "data:{MIME_type};base64,..."
            ),
        ),
    ] = None,
    resolution: Annotated[
        Literal["1080P", "720P", "480P"] | None,
        Field(default=None, description="parameters.resolution. Official default 1080P."),
    ] = None,
    ratio: Annotated[
        Literal["adaptive", "16:9", "4:3", "1:1", "3:4", "9:16"] | None,
        Field(
            default=None,
            description="parameters.ratio. Official default adaptive.",
        ),
    ] = None,
    duration: Annotated[
        int | None,
        Field(
            default=None,
            description=(
                "parameters.duration in seconds: integer 2 to 30, or -1 smart "
                "duration. Official default 5. With video input, input + output "
                "duration must be at most 30s."
            ),
        ),
    ] = None,
    audio: Annotated[
        bool | None,
        Field(
            default=None,
            description=(
                "parameters.audio. Official default true. Enabling or disabling "
                "audio does not affect pricing."
            ),
        ),
    ] = None,
    seed: Annotated[
        int | None,
        Field(
            default=None,
            ge=0,
            le=SEED_MAX,
            description="parameters.seed in [0, 2147483647].",
        ),
    ] = None,
    watermark: Annotated[
        bool | None,
        Field(
            default=None,
            description="parameters.watermark. Official default false.",
        ),
    ] = None,
    model: Annotated[
        Literal["wan3.0-video"] | None,
        Field(
            default=MODEL_ID,
            description="Official model name. Fixed value wan3.0-video.",
        ),
    ] = MODEL_ID,
) -> dict[str, Any]:
    """Create a Wan 3.0 video-synthesis task (official Model Studio API).

    Asynchronous create: sends X-DashScope-Async: enable. Returns task_id and
    task_status (typically PENDING). Poll with wan_get_task or wan_wait_for_video.
    Does not invent fields (no enable_thinking).
    """
    try:
        return await _client().create_task(
            prompt=prompt,
            media=media,
            resolution=resolution,
            ratio=ratio,
            duration=duration,
            audio=audio,
            seed=seed,
            watermark=watermark,
            model=model or MODEL_ID,
        )
    except (WanAPIError, ValidationError, ConfigError) as exc:
        return _error_payload(exc)


@mcp.tool()
async def wan_get_task(
    task_id: Annotated[
        str,
        Field(description="Task id returned by wan_create_video. Valid for 24 hours."),
    ],
) -> dict[str, Any]:
    """Query a Wan 3.0 task by id (status, usage, video_url).

    Statuses: PENDING, RUNNING, SUCCEEDED, FAILED, CANCELED, UNKNOWN.
    video_url on SUCCEEDED is valid for 24 hours.
    """
    try:
        return await _client().get_task(task_id)
    except (WanAPIError, ConfigError) as exc:
        return _error_payload(exc)


@mcp.tool()
async def wan_wait_for_video(
    task_id: Annotated[
        str,
        Field(description="Task id returned by wan_create_video. Valid for 24 hours."),
    ],
    poll_interval_seconds: Annotated[
        float,
        Field(
            default=DEFAULT_POLL_INTERVAL_SECONDS,
            ge=0,
            description="Poll interval. Official recommendation is about 15 seconds.",
        ),
    ] = DEFAULT_POLL_INTERVAL_SECONDS,
    timeout_seconds: Annotated[
        float,
        Field(
            default=900,
            gt=0,
            description="Stop waiting after this many seconds.",
        ),
    ] = 900,
) -> dict[str, Any]:
    """Poll a Wan 3.0 task until terminal, then download the mp4 locally.

    On SUCCEEDED, downloads video_url (24h) to WAN_OUTPUT_DIR
    (default ./wan-output under the current working directory) and returns
    local_path plus official output/usage fields.
    """
    try:
        return await _client().wait_for_video(
            task_id,
            poll_interval_seconds=poll_interval_seconds,
            timeout_seconds=timeout_seconds,
        )
    except (WanAPIError, ConfigError) as exc:
        return _error_payload(exc)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
