"""Official Wan 3.0 create-task validation.

Field names, enums, and limits come only from:
https://www.alibabacloud.com/help/en/model-studio/wan3-video-generation-api-reference
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MODEL_ID = "wan3.0-video"
PROMPT_MAX_CHARS = 20_000
SEED_MAX = 2_147_483_647

MediaType = Literal[
    "first_frame",
    "last_frame",
    "reference_image",
    "reference_video",
    "reference_audio",
    "file",
    "link",
]

Resolution = Literal["1080P", "720P", "480P"]
Ratio = Literal["adaptive", "16:9", "4:3", "1:1", "3:4", "9:16"]

MEDIA_TYPES: tuple[str, ...] = (
    "first_frame",
    "last_frame",
    "reference_image",
    "reference_video",
    "reference_audio",
    "file",
    "link",
)
TYPE_LIMITS: dict[str, int] = {
    "first_frame": 1,
    "last_frame": 1,
    "reference_image": 10,
    "reference_video": 5,
    "reference_audio": 5,
    "file": 1,
    "link": 1,
}
FRAME_TYPES = frozenset({"first_frame", "last_frame"})
REFERENCE_GROUP = frozenset(
    {
        "reference_image",
        "reference_video",
        "reference_audio",
        "file",
        "link",
    }
)
IMAGE_TYPES = frozenset({"first_frame", "last_frame", "reference_image"})
IMAGE_MIMES = frozenset(
    {"image/jpeg", "image/jpg", "image/png", "image/bmp", "image/webp"}
)

TASK_STATUSES = (
    "PENDING",
    "RUNNING",
    "SUCCEEDED",
    "FAILED",
    "CANCELED",
    "UNKNOWN",
)
TERMINAL_STATUSES = frozenset({"SUCCEEDED", "FAILED", "CANCELED", "UNKNOWN"})

PARAMETER_KEYS = frozenset(
    {"resolution", "ratio", "duration", "audio", "seed", "watermark"}
)
CREATE_BODY_KEYS = frozenset({"model", "input", "parameters"})
INPUT_KEYS = frozenset({"prompt", "media"})


class ValidationError(ValueError):
    """Illegal Wan 3.0 create-task combination or field."""


class MediaItem(BaseModel):
    """One ``input.media[]`` object: official ``type`` + ``url`` only."""

    model_config = ConfigDict(extra="forbid")

    type: MediaType
    url: str = Field(min_length=1)

    @field_validator("url")
    @classmethod
    def strip_url(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def url_must_be_public_or_image_data(self) -> MediaItem:
        _validate_media_url(self.type, self.url)
        return self


def _validate_media_url(media_type: str, url: str) -> None:
    if url.startswith("data:"):
        if media_type not in IMAGE_TYPES:
            raise ValidationError(
                "data: URLs are only allowed for first_frame, last_frame, "
                "and reference_image"
            )
        _validate_image_data_url(url)
        return
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValidationError(
            f"media url for type {media_type!r} must be a public http(s) URL "
            "or (for images) data:{MIME_type};base64,..."
        )


def _validate_image_data_url(url: str) -> None:
    # Official format: data:{MIME_type};base64,{base64_data}
    try:
        header, _payload = url.split(",", 1)
    except ValueError as exc:
        raise ValidationError(
            "image data URL must be data:{MIME_type};base64,{base64_data}"
        ) from exc
    if not header.startswith("data:"):
        raise ValidationError(
            "image data URL must be data:{MIME_type};base64,{base64_data}"
        )
    rest = header[len("data:") :]
    if ";base64" not in rest:
        raise ValidationError(
            "image data URL must be data:{MIME_type};base64,{base64_data}"
        )
    mime = rest.split(";", 1)[0].strip().lower()
    if mime not in IMAGE_MIMES:
        allowed = ", ".join(sorted(IMAGE_MIMES))
        raise ValidationError(f"image data URL MIME type must be one of: {allowed}")


def validate_duration(duration: int | None, has_video_input: bool) -> None:
    if duration is None:
        return
    if duration == -1:
        return
    if duration < 2 or duration > 30:
        raise ValidationError(
            "parameters.duration must be an integer in [2, 30], or -1 for "
            "smart duration (official default 5)"
        )
    if has_video_input and duration > 30:
        raise ValidationError(
            "with video input, input duration + output duration must be <= 30s"
        )


def validate_media_list(media: list[MediaItem] | None) -> None:
    if not media:
        return
    counts: Counter[str] = Counter()
    types: set[str] = set()
    for item in media:
        _validate_media_url(item.type, item.url)
        counts[item.type] += 1
        types.add(item.type)
        limit = TYPE_LIMITS[item.type]
        if counts[item.type] > limit:
            raise ValidationError(
                f"input.media type {item.type!r} allows at most {limit} item(s)"
            )

    if types & FRAME_TYPES and types & REFERENCE_GROUP:
        raise ValidationError(
            "The two modes are mutually exclusive. Do not pass reference_xx "
            "and first_frame/last_frame at the same time."
        )
    if "file" in types and "link" in types:
        raise ValidationError("type file cannot be used together with type link")


def validate_create_input(
    *,
    prompt: str | None,
    media: list[MediaItem] | None,
    duration: int | None = None,
    seed: int | None = None,
    model: str | None = MODEL_ID,
) -> None:
    if model not in (None, MODEL_ID):
        raise ValidationError(f"model must be {MODEL_ID!r}")
    prompt_text = prompt.strip() if isinstance(prompt, str) else ""
    has_prompt = bool(prompt_text)
    has_media = bool(media)
    if not has_prompt and not has_media:
        raise ValidationError("Either input.prompt or input.media must be provided")
    if prompt is not None and len(prompt) > PROMPT_MAX_CHARS:
        raise ValidationError(
            f"input.prompt must be at most {PROMPT_MAX_CHARS} characters"
        )
    validate_media_list(media)
    has_video = any(item.type == "reference_video" for item in media or [])
    validate_duration(duration, has_video)
    if seed is not None and (seed < 0 or seed > SEED_MAX):
        raise ValidationError(f"parameters.seed must be in [0, {SEED_MAX}]")


def build_create_body(
    *,
    prompt: str | None = None,
    media: list[MediaItem] | None = None,
    resolution: Resolution | None = None,
    ratio: Ratio | None = None,
    duration: int | None = None,
    audio: bool | None = None,
    seed: int | None = None,
    watermark: bool | None = None,
    model: str = MODEL_ID,
) -> dict[str, Any]:
    validate_create_input(
        prompt=prompt,
        media=media,
        duration=duration,
        seed=seed,
        model=model,
    )
    input_obj: dict[str, Any] = {}
    if prompt is not None and prompt.strip():
        input_obj["prompt"] = prompt
    if media:
        input_obj["media"] = [item.model_dump() for item in media]

    parameters: dict[str, Any] = {}
    if resolution is not None:
        parameters["resolution"] = resolution
    if ratio is not None:
        parameters["ratio"] = ratio
    if duration is not None:
        parameters["duration"] = duration
    if audio is not None:
        parameters["audio"] = audio
    if seed is not None:
        parameters["seed"] = seed
    if watermark is not None:
        parameters["watermark"] = watermark

    body: dict[str, Any] = {"model": MODEL_ID, "input": input_obj}
    if parameters:
        body["parameters"] = parameters
    return body
