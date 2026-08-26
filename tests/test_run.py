import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_run_py_does_not_hardcode_agent_id() -> None:
    text = (ROOT / "run.py").read_text(encoding="utf-8")
    tree = ast.parse(text)
    constants: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            constants.append(node.value)
    # No UUID-looking hardcoded agent ids.
    for value in constants:
        assert "mcp-servers/wan" in value or not _looks_like_agent_id(value)


def _looks_like_agent_id(value: str) -> bool:
    stripped = value.strip()
    if len(stripped) < 8:
        return False
    return stripped.replace("-", "").isalnum() and "-" in stripped and len(stripped) > 20


def test_run_py_execs_server() -> None:
    text = (ROOT / "run.py").read_text(encoding="utf-8")
    assert "os.execv" in text
    assert "apply_secrets_to_env" in text
    assert "wan-mcp" in text
