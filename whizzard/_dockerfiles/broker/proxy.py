"""Whizzard credential broker — a minimal, single-upstream reverse proxy.

This runs INSIDE the broker sidecar container, on the cell-facing `--internal`
Docker network (the cell's only reachable peer). The flow (bar C / D-183, D-184):

    cell (Hermes)                 broker (this proxy)            Anthropic
    ANTHROPIC_BASE_URL ─http──►  strip placeholder key    ─https─►  api.anthropic.com
    = http://broker:8080         inject the REAL key                (the only upstream)
    ANTHROPIC_API_KEY  = <placeholder, worthless>

Security properties this file is responsible for:

  * Single hardcoded upstream (``api.anthropic.com``). This proxy has exactly
    one destination, so the egress allowlist is inherent — there is no code
    path that forwards anywhere else.
  * The REAL key is loaded once from a file the host bind-mounts read-only into
    THIS container only (never the cell), held in memory, and injected as
    ``x-api-key`` on every upstream request. The cell never receives it.
  * The client's own auth headers (the worthless placeholder) are stripped
    before forwarding, and replaced with the real key.
  * Nothing sensitive is logged: request/response bodies and the key are never
    written out — only method, path, and status.

The plaintext hop is cell→broker on a private ``--internal`` network that is
unobservable from outside and carries only the placeholder; the broker does the
real TLS to Anthropic itself, so no cert/CA plumbing is needed in the cell.
"""

from __future__ import annotations

import logging
import os
import sys

try:
    from aiohttp import ClientSession, ClientTimeout, web
except ImportError:  # pragma: no cover
    # aiohttp ships in the broker image (Debian python3-aiohttp), not the host
    # venv. The pure header/URL helpers below are unit-tested on the host
    # without it; the server functions require it at runtime.
    ClientSession = ClientTimeout = web = None  # type: ignore[assignment,misc]

UPSTREAM_SCHEME = "https"
# The ONLY host this proxy will ever contact. Not user-configurable from the
# cell; overridable only via the broker's own env (host-controlled) so the
# same image can serve a future provider, never to widen egress at runtime.
UPSTREAM_HOST = os.environ.get("BROKER_UPSTREAM_HOST", "api.anthropic.com")
LISTEN_PORT = int(os.environ.get("BROKER_PORT", "8080"))
KEY_FILE = os.environ.get("BROKER_KEY_FILE", "/run/broker/key")

# Hop-by-hop headers (RFC 7230 §6.1) plus length/host — never forwarded as-is;
# the client library recomputes length and we set host to the upstream.
_HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "host",
        "content-length",
    }
)
# Client-supplied credential headers carry only the placeholder; drop them and
# inject the real key ourselves.
_STRIP_CLIENT_AUTH = frozenset({"x-api-key", "authorization"})

log = logging.getLogger("whiz-broker")


def load_key(path: str) -> str:
    """Read the real upstream key from the host-mounted file. Fail loud if
    missing/empty — a broker with no key must not start (fail-closed)."""
    with open(path, encoding="utf-8") as f:
        key = f.read().strip()
    if not key:
        raise RuntimeError(f"broker key file {path!r} is empty")
    return key


def build_upstream_url(path_qs: str) -> str:
    """Map an incoming request path (+query) onto the single allowlisted
    upstream. ``path_qs`` already starts with '/'."""
    return f"{UPSTREAM_SCHEME}://{UPSTREAM_HOST}{path_qs}"


def rewrite_request_headers(headers, real_key: str) -> dict[str, str]:
    """Strip hop-by-hop + client auth headers, inject the real key, and point
    Host at the upstream. Everything else (anthropic-version, anthropic-beta,
    content-type, x-stainless-*, user-agent) passes through unchanged."""
    out: dict[str, str] = {}
    for k, v in headers.items():
        lk = k.lower()
        if lk in _HOP_BY_HOP or lk in _STRIP_CLIENT_AUTH:
            continue
        out[k] = v
    out["x-api-key"] = real_key
    out["host"] = UPSTREAM_HOST
    return out


def filter_response_headers(headers) -> dict[str, str]:
    """Drop hop-by-hop headers from the upstream response before relaying."""
    return {k: v for k, v in headers.items() if k.lower() not in _HOP_BY_HOP}


async def handle(request: web.Request) -> web.StreamResponse:
    real_key: str = request.app["real_key"]
    session: ClientSession = request.app["session"]

    url = build_upstream_url(request.path_qs)
    req_headers = rewrite_request_headers(request.headers, real_key)
    # Read the request body fully (Anthropic requests are JSON, not streamed
    # uploads) so the length is exact; stream only the RESPONSE, which is where
    # SSE / token streaming matters.
    body = await request.read()

    async with session.request(
        request.method,
        url,
        headers=req_headers,
        data=body,
        allow_redirects=False,
    ) as upstream:
        resp = web.StreamResponse(
            status=upstream.status,
            headers=filter_response_headers(upstream.headers),
        )
        await resp.prepare(request)
        # iter_any() yields chunks as they arrive — SSE events flush through
        # without buffering the whole response.
        async for chunk in upstream.content.iter_any():
            await resp.write(chunk)
        await resp.write_eof()
        log.info("%s %s -> %s", request.method, request.path, upstream.status)
        return resp


async def _on_startup(app: web.Application) -> None:
    # No total timeout (streamed responses can run long); bound only the
    # connect and per-read so a wedged upstream can't hang forever.
    app["session"] = ClientSession(
        timeout=ClientTimeout(total=None, sock_connect=30, sock_read=300)
    )


async def _on_cleanup(app: web.Application) -> None:
    await app["session"].close()


def make_app() -> web.Application:
    app = web.Application()
    app["real_key"] = load_key(KEY_FILE)
    app.router.add_route("*", "/{tail:.*}", handle)
    app.on_startup.append(_on_startup)
    app.on_cleanup.append(_on_cleanup)
    return app


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="whiz-broker %(levelname)s %(message)s"
    )
    try:
        app = make_app()
    except (OSError, RuntimeError) as e:
        # Fail closed and loud: without the key the broker must not serve.
        print(f"whiz-broker: refusing to start: {e}", file=sys.stderr)
        return 1
    web.run_app(app, host="0.0.0.0", port=LISTEN_PORT, print=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
