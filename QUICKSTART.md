# Quickstart

From clone to a connected client in about five minutes. Requires Python 3.13+.

## 1. Install

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

## 2. Run the server

```bash
.venv/bin/python -m nsf_grant_intelligence
```

It starts in **stdio** mode and waits for a client to launch it, so it prints nothing. That is
expected. Press `Ctrl-C` to stop.

## 3. Connect a client

Use the full path to the venv's Python as the command.

**Claude Code** (`.mcp.json`, already in this repo) or **Claude Desktop**
(`~/Library/Application Support/Claude/claude_desktop_config.json`, then quit and reopen the app):

```json
{
  "mcpServers": {
    "nsf-grant-intelligence": {
      "command": "/absolute/path/to/this/repo/.venv/bin/python",
      "args": ["-m", "nsf_grant_intelligence"]
    }
  }
}
```

Then ask: "What is the full abstract of NSF award 1753742?"

## 4. Verify

```bash
.venv/bin/python -m pytest      # offline tests
.venv/bin/python -m ruff check . # lint
```

## 5. Try HTTP mode

```bash
MCP_TRANSPORT=streamable-http .venv/bin/python -m nsf_grant_intelligence   # listens on MCP_HOST:MCP_PORT (0.0.0.0:8000)
# or, as a hosting platform does it: any PORT value switches the server to HTTP
PORT=8080 .venv/bin/python -m nsf_grant_intelligence
curl http://localhost:8000/health    # {"status":"healthy","service":"nsf-grant-intelligence"}
curl http://localhost:8000/version
```

If `PORT` happens to be set in your shell, the server runs HTTP instead of stdio and a local MCP client
will not connect. Unset it (`unset PORT`) for local use.

## Next steps

- Deploy: [DEPLOYMENT.md](DEPLOYMENT.md) (runtime contract for any host).
- Evaluate: [eval/RESULTS.md](eval/RESULTS.md) and `eval/run_eval.py`.
