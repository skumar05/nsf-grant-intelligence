# Security

## Reporting a vulnerability

Please report suspected vulnerabilities privately to the repository owner (use the
repository's private vulnerability reporting, or contact the owner directly) rather than
opening a public issue. Include steps to reproduce and the affected version.

## Hackathon posture

- The `/mcp` endpoint is served **without authentication**, which matches a public-data
  hackathon. All data comes from the public NSF Award API (published award titles, abstracts,
  PI names and institutions). Before any non-hackathon use, put the endpoint behind
  authentication and review the data classification.
- All nine tools are read-only; none can modify anything.
- Never commit secrets. The server needs no API key. The evaluation's `ANTHROPIC_API_KEY`
  lives in a git-ignored `.env` (see `.env.example`).

## Outbound requests

- The server calls one fixed origin (`https://api.nsf.gov/services/v1/`). The origin is
  set in code, never taken from a tool argument.
- Redirects are not followed and environment proxy settings are ignored.
- Response bodies above a fixed size cap are rejected.
- Timeouts and bounded retries (429 and 5xx, exponential backoff) apply to every call.

## Untrusted content

Tool arguments are validated (types, ranges, date and state-code formats) before any API
call. Award abstracts are written by third parties and are untrusted: they could contain
text aimed at an agent. The current evaluation does not yet include an injection that
arrives inside a tool result.

## Logging

The server does not log request URLs or search terms: the HTTP client's request logging is
set to WARNING. Do not add logging of upstream response bodies, full URLs or query strings.
