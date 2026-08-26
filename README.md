# wan-mcp

Private **stdio** MCP server for HomeBooks [Alibaba Wan 3.0 video](https://www.alibabacloud.com/help/en/model-studio/wan3-video-generation-api-reference) via the **official Model Studio API only**. No AceDataCloud reseller. Tests never make a live paid generate call.

Official source of truth: [Wan 3.0 video generation API reference](https://www.alibabacloud.com/help/en/model-studio/wan3-video-generation-api-reference). Tool schemas expose **only** fields on that page (no `enable_thinking`).

## Local install target

After merge, copy this repo to:

```text
/home/box/mcp-servers/wan/
```

```bash
cd /home/box/mcp-servers/wan
python3 -m venv .venv
.venv/bin/pip install -e .
```

`run.py` loads connector secrets into the environment, then execs the `wan-mcp` console script (or `python -m wan_mcp` if the script is not on PATH). Same pattern as MiniMax: read secret JSON, set env, exec the Python MCP server.

### AddMcpServer

```text
name: wan
command: /home/box/mcp-servers/wan/.venv/bin/python
args: ["/home/box/mcp-servers/wan/run.py"]
```

JSON equivalent:

```json
{
  "mcpServers": {
    "wan": {
      "command": "/home/box/mcp-servers/wan/.venv/bin/python",
      "args": ["/home/box/mcp-servers/wan/run.py"]
    }
  }
}
```

## Secrets (never commit keys)

Resolution order (do **not** hardcode an agent id):

1. Environment: `DASHSCOPE_API_KEY` / `WAN_WORKSPACE_ID` / `WAN_REGION`
2. `/home/box/agent-data/connector-secrets/<agent-id>/wan.json` if `WAN_AGENT_ID` is set
3. any `/home/box/agent-data/connector-secrets/*/wan.json` (exactly one file; several files without `WAN_AGENT_ID` is an error)

Secret file shape (no keys in this repo):

```json
{
  "api_key": "...",
  "workspace_id": "...",
  "region": "singapore"
}
```

`region` is `singapore` | `beijing`. If still unset after env + files, the server uses `singapore` (the region used by the official sample).

Optional:

| Env | Meaning |
| --- | --- |
| `WAN_OUTPUT_DIR` | Where SUCCEEDED mp4 files are written. Default `/workspace/wan-output/` |
| `WAN_TEST_MODE=1` | Refuses live Model Studio HTTP unless an httpx client is injected. Set in unit tests. |

## Endpoints (official)

- Singapore create: `POST https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis`
- Beijing create: `POST https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis`
- Poll: `GET https://{WorkspaceId}.{region-host}.maas.aliyuncs.com/api/v1/tasks/{task_id}` every ~15s

Headers:

- `Authorization: Bearer $DASHSCOPE_API_KEY`
- `X-DashScope-Async: enable` (required on **create**; missing → sync-not-supported error)
- `Content-Type: application/json`

Model is fixed: `wan3.0-video`.

Poll statuses: `PENDING` `RUNNING` `SUCCEEDED` `FAILED` `CANCELED` `UNKNOWN`. On `SUCCEEDED`, `video_url` lives 24h — `wan_wait_for_video` downloads the mp4 to `WAN_OUTPUT_DIR` and returns the local path.

## MCP tools

1. `wan_create_video` — official create-task surface (`prompt`, `media[]` with `type`+`url`, `resolution`, `ratio`, `duration`, `audio`, `seed`, `watermark`, `model`). Schema + runtime reject illegal combos (type caps, file vs link, `reference_*`/`file`/`link` vs `first_frame`/`last_frame`, duration `-1` or 2–30, seed range, prompt ≤ 20000).
2. `wan_get_task` — `task_id` → status + usage + `video_url`
3. `wan_wait_for_video` — poll ~15s until terminal, download mp4, return `local_path` + official usage/output

## Tests

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

HTTP is mocked. There is **no** live paid generate call in CI or smoke tests.

## License

Private HomeBooks use.
