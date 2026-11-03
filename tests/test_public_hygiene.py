from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = (
    "HomeBooks",
    "homebooks",
    "/home/box",
    "/workspace/wan-output",
)
SCAN_PATHS = [
    ROOT / "src",
    ROOT / "run.py",
    ROOT / "README.md",
    ROOT / "pyproject.toml",
    ROOT / ".env.example",
    ROOT / ".github",
]


def _iter_text_files():
    for start in SCAN_PATHS:
        if start.is_file():
            yield start
            continue
        if not start.is_dir():
            continue
        for path in start.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".md", ".toml", ".yml", ".yaml", ".example", ".txt"}:
                yield path


def test_no_homebooks_or_machine_paths() -> None:
    hits: list[str] = []
    for path in _iter_text_files():
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN:
            if token in text:
                hits.append(f"{path.relative_to(ROOT)}: {token}")
    assert hits == []


def test_readme_cover_and_subtitle() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert text.startswith("![wan-mcp](assets/cover.png)\n")
    assert "Wan video generation for AI assistants" in text
    assert "\u2014" not in text
    assert "\u2013" not in text
    assert (ROOT / "assets" / "cover.png").is_file()
    assert not (ROOT / "assets" / ".gitkeep").exists()


def test_gitignore_covers_dotenv() -> None:
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in text
    assert ".env.*" in text
    assert "!.env.example" in text


def test_license_mit() -> None:
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in text
    assert "Copyright (c) 2026 Matin Rahimi" in text


def test_import_and_tools_smoke() -> None:
    from wan_mcp import __version__
    from wan_mcp.server import mcp

    assert __version__
    assert mcp is not None

