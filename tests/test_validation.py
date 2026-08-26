import pytest
from pydantic import ValidationError as PydanticValidationError

from wan_mcp.validation import (
    MODEL_ID,
    MediaItem,
    ValidationError,
    build_create_body,
    validate_create_input,
)


def test_text_only_body() -> None:
    body = build_create_body(prompt="A kitten on a rooftop")
    assert body == {
        "model": MODEL_ID,
        "input": {"prompt": "A kitten on a rooftop"},
    }
    assert "enable_thinking" not in body
    assert set(body) <= {"model", "input", "parameters"}


def test_first_frame_ok() -> None:
    body = build_create_body(
        prompt="rap",
        media=[
            MediaItem(
                type="first_frame",
                url="https://example.com/first.png",
            )
        ],
        resolution="480P",
        ratio="adaptive",
        duration=5,
    )
    assert body["parameters"]["resolution"] == "480P"
    assert body["input"]["media"][0]["type"] == "first_frame"


def test_first_and_last_frame_ok() -> None:
    build_create_body(
        prompt="smile to laugh",
        media=[
            MediaItem(type="first_frame", url="https://example.com/a.png"),
            MediaItem(type="last_frame", url="https://example.com/b.jpg"),
        ],
    )


def test_reference_mode_ok() -> None:
    build_create_body(
        prompt="Image 1 holds Image 2",
        media=[
            MediaItem(type="reference_image", url="https://example.com/1.jpg"),
            MediaItem(type="reference_video", url="https://example.com/v.mp4"),
            MediaItem(type="reference_audio", url="https://example.com/a.mp3"),
        ],
        duration=-1,
    )


def test_file_ok() -> None:
    build_create_body(
        prompt="ad",
        media=[MediaItem(type="file", url="https://example.com/deck.pptx")],
    )


def test_prompt_or_media_required() -> None:
    with pytest.raises(ValidationError, match="prompt or input.media"):
        validate_create_input(prompt=None, media=None)


def test_prompt_max_length() -> None:
    with pytest.raises(ValidationError, match="20000"):
        validate_create_input(prompt="x" * 20001, media=None)


def test_mutual_exclusion_reference_and_first_frame() -> None:
    with pytest.raises(ValidationError, match="mutually exclusive"):
        validate_create_input(
            prompt="x",
            media=[
                MediaItem(type="first_frame", url="https://example.com/a.png"),
                MediaItem(type="reference_image", url="https://example.com/b.png"),
            ],
        )


def test_file_and_link_exclusive() -> None:
    with pytest.raises(ValidationError, match="file cannot be used"):
        validate_create_input(
            prompt="x",
            media=[
                MediaItem(type="file", url="https://example.com/a.pdf"),
                MediaItem(type="link", url="https://example.com/article"),
            ],
        )


def test_type_caps() -> None:
    images = [
        MediaItem(type="reference_image", url=f"https://example.com/{i}.png")
        for i in range(11)
    ]
    with pytest.raises(ValidationError, match="at most 10"):
        validate_create_input(prompt="x", media=images)


def test_duration_range() -> None:
    with pytest.raises(ValidationError, match="duration"):
        validate_create_input(prompt="x", media=None, duration=1)
    with pytest.raises(ValidationError, match="duration"):
        validate_create_input(prompt="x", media=None, duration=31)
    validate_create_input(prompt="x", media=None, duration=-1)
    validate_create_input(prompt="x", media=None, duration=2)
    validate_create_input(prompt="x", media=None, duration=30)


def test_seed_range() -> None:
    with pytest.raises(ValidationError, match="seed"):
        validate_create_input(prompt="x", media=None, seed=-1)
    with pytest.raises(ValidationError, match="seed"):
        validate_create_input(prompt="x", media=None, seed=2_147_483_648)


def test_model_fixed() -> None:
    with pytest.raises(ValidationError, match="wan3.0-video"):
        validate_create_input(prompt="x", media=None, model="wan2.2")


def test_data_url_images_only() -> None:
    data = "data:image/png;base64,AAAA"
    MediaItem(type="first_frame", url=data)
    with pytest.raises((ValidationError, PydanticValidationError)):
        MediaItem(type="reference_video", url=data)


def test_http_url_required() -> None:
    with pytest.raises((ValidationError, PydanticValidationError)):
        MediaItem(type="link", url="ftp://example.com/x")


def test_media_rejects_unknown_fields() -> None:
    with pytest.raises(PydanticValidationError):
        MediaItem(
            type="first_frame",
            url="https://example.com/a.png",
            enable_thinking=True,  # type: ignore[call-arg]
        )


def test_parameters_only_official_keys() -> None:
    body = build_create_body(
        prompt="x",
        resolution="720P",
        ratio="16:9",
        duration=10,
        audio=False,
        seed=1,
        watermark=True,
    )
    assert set(body["parameters"]) == {
        "resolution",
        "ratio",
        "duration",
        "audio",
        "seed",
        "watermark",
    }
