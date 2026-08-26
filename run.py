#!/usr/bin/env python3
"""Load HomeBooks connector secrets and exec the Wan MCP stdio server.

Local install target after merge: /home/box/mcp-servers/wan/

AddMcpServer:
  name: wan
  command: /home/box/mcp-servers/wan/.venv/bin/python
  args: ["/home/box/mcp-servers/wan/run.py"]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
if _SRC.is_dir():
    sys.path.insert(0, str(_SRC))

from wan_mcp.config import ConfigError, apply_secrets_to_env  # noqa: E402


def _exec_server() -> None:
    python = sys.executable
    bindir = Path(python).resolve().parent
    binary = bindir / "wan-mcp"
    if binary.is_file():
        os.execv(str(binary), [str(binary)])
    pythonpath = os.environ.get("PYTHONPATH", "")
    parts = [str(_SRC)] + ([pythonpath] if pythonpath else [])
    os.environ["PYTHONPATH"] = os.pathsep.join(parts)
    os.execv(python, [python, "-m", "wan_mcp"])


def main() -> None:
    try:
        apply_secrets_to_env()
    except ConfigError as exc:
        sys.stderr.write(f"{exc}\n")
        raise SystemExit(1) from exc
    _exec_server()


if __name__ == "__main__":
    main()
