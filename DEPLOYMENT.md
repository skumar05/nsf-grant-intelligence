# Deploying NSF Grant Intelligence MCP

A stateless HTTP service in one container. It needs no secrets, no database and no persistent storage.
The only outside dependency is the public NSF Award API (`https://api.nsf.gov`).

## What you need

Build context: `Dockerfile`, `pyproject.toml`, `README.md` and the `src/` folder. Nothing else is required
(`eval/`, `tests/`, `deploy/` and `presentation/` are not used by the image).

```bash
# Build for x86-64 (use linux/arm64 instead if your platform runs ARM)
docker build --platform linux/amd64 -t nsf-grant-intelligence .
```

The image is based on `python:3.13-slim` and runs as the non-root user `nobody`.

## Runtime contract

| Setting | Value |
|---|---|
| Port | `8000` (read from the `PORT` environment variable) |
| Environment variables | None required. The image sets `MCP_TRANSPORT=streamable-http` and `PORT=8000`. Optional: `HOST` (default `0.0.0.0`) |
| MCP endpoint | `POST /mcp` |
| Health check | `GET /health`, returns `200` and `{"status":"ok"}` |
| Landing page | `GET /` returns an HTML page (not a health check) |
| Outbound network | HTTPS (443) to `api.nsf.gov` |
| Size | 0.25 vCPU and 512 MB is enough |
| Scaling | Stateless: run any number of copies behind a load balancer, no sticky sessions |
| Secrets | None |
| Authentication | None built in. The service is public unless you put a gateway in front |

### Health check

Use **HTTP `GET /health`**, expecting status 200. Do not use `/` (it is an HTML page) or `/mcp` (it does not
answer a plain `GET`; a browser request to it hangs). Suggested settings: interval 10 s, timeout 5 s,
healthy threshold 2, unhealthy threshold 3. The container started answering within about 6 seconds in our tests.

### Proxy and timeout settings

MCP responses are sent as server-sent events (`Content-Type: text/event-stream`), so the load balancer or
proxy must not buffer responses. Single lookups answer in well under a second. The sampling tools
(`analyze_topic`, `institution_profile`, `compare_funding_by_program`, `sample_winning_abstracts`,
`extract_themes`, `funding_trends`) make many calls to NSF and took up to about 5 seconds in our tests.
Set the request timeout and idle timeout to at least 60 seconds, which leaves room for a slow NSF
response or the server's built-in retries.

## Verify a deployment

Replace `$URL` with the service's public HTTPS address.

```bash
# 1. Health
curl -s $URL/health
# expect: {"status":"ok"}

# 2. The 9 tools are listed
curl -s -X POST $URL/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# 3. A real call that reaches the NSF API
curl -s -X POST $URL/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_award","arguments":{"award_id":"1753742"}}}'
# expect the award's PI "Keith Nehrke", institution "University of Rochester", funds_obligated_usd 493206
```

Open `$URL/` in a browser to see the landing page, which shows the MCP endpoint and the tool list.

To try the image locally first:

```bash
docker run --rm -p 8000:8000 nsf-grant-intelligence
curl -s localhost:8000/health
```

## Connecting a client

```bash
claude mcp add --transport http nsf-grant-intelligence $URL/mcp
```

Any MCP client that supports streamable HTTP can use `$URL/mcp`.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Container is marked unhealthy | Health check points at `/` or `/mcp`. It must be `/health` on port 8000. |
| `exec format error` at startup | Image built for the wrong CPU architecture. Rebuild with `--platform` set to match the host. |
| Requests to `/mcp` hang or time out | Proxy buffers responses or has a short timeout. Allow streaming and a 60 s or longer timeout. |
| Tools return "NSF API unreachable" | The container cannot reach `api.nsf.gov` over HTTPS. Check egress rules. |
| `404 Not found` at `/` on an older build | That build predates the landing page. Redeploy the latest image. |

## Security notes

- The data is public NSF award data and the tools are read-only, but anyone who can reach the URL can call
  them, and each call makes requests to NSF from the service's IP address. Restrict access with your own
  gateway or allow-list if the service should not be open.
- Do not send the project's `.env` file. It only holds an API key used by the local evaluation scripts
  and is not needed to run the service.
