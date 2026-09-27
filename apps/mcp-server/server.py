#!/usr/bin/env python3
"""MCP server for NT IP-MPLS network operations.

Exposes three databases to any MCP client through one server:

    Tools      actions the model can invoke  (tools/)
    Resources  context the model can read    (resources/)
    Prompts    reusable investigation recipes (prompts/)

Run it:
    python apps/mcp-server/server.py                     # stdio, for Claude Desktop / Cursor
    python apps/mcp-server/server.py --transport streamable-http --port 9000

Transport note: this server uses Streamable HTTP, which replaced the older
HTTP+SSE transport in the 2025-03-26 revision of the specification. Sample code
found online may still show the two-endpoint SSE pattern - that is the
deprecated shape. Run `make protocol-version` to print the spec revision the
installed SDK actually implements.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Allow `python apps/mcp-server/server.py` to import sibling modules without
# requiring the package to be installed.
sys.path.insert(0, str(Path(__file__).parent))

from config import settings  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402

from prompts import templates  # noqa: E402
from resources import clock_resource, files, schemas  # noqa: E402
from security.guardrails import GuardrailViolation  # noqa: E402
from tools import logs, network, reports, tickets  # noqa: E402

from tools import logs, network, reports, tickets, notifications  # เพิ่ม notifications ต่อท้าย

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
    stream=sys.stderr,  # stdout belongs to the protocol when running over stdio
)
log = logging.getLogger("mcp.server")


INSTRUCTIONS = """\
Network operations assistant for the NT IP-MPLS backbone.

You have read-only access to three systems:
  PostgreSQL  - trouble tickets, device configuration, circuits, customers
  Neo4j       - physical topology and routing adjacencies
  OpenSearch  - device logs and operational documentation

Before answering anything that involves time, read the resource clock://now.
"Now" is defined by the newest record in the system, not by your own idea of
today's date, and the data window moves each time the dataset is refreshed.

Before your first query in a session, read schema://overview. It tells you
which store answers which kind of question.

Four rules that matter more than speed:

1. The network contains exactly the devices returned by list_devices, at the
   sites BKK and NBI. Anything else does not exist. Say so plainly rather than
   producing a plausible answer.

2. Severe logs are not automatically an incident. Planned maintenance produces
   logs indistinguishable from an outage. Check for a maintenance ticket
   covering the same window before you call anything a fault.

3. When several customers on different access devices report the same symptom,
   look for a shared upstream device before concluding they are unrelated. The
   tickets will never name that device.

4. Cite which system each conclusion came from. An operator has to be able to
   verify what you said before acting on it.
"""


def build_server() -> FastMCP:
    mcp = FastMCP(name=settings().server_name, instructions=INSTRUCTIONS)

    # Tools: three groups, one server. A single server means one entry in the
    # client configuration and one tool list for the model to reason over,
    # which measurably improves cross-system planning.
    tickets.register(mcp)
    network.register(mcp)
    logs.register(mcp)
    reports.register(mcp)
    notifications.register(mcp)  # เพิ่มบรรทัดนี้ลงไป
    
    # Resources: what the model reads before it acts.
    schemas.register(mcp)
    clock_resource.register(mcp)
    files.register(mcp)

    # Prompts: investigation recipes offered to the user by the client.
    templates.register(mcp)

    return mcp


def main() -> int:
    parser = argparse.ArgumentParser(description="NT IP-MPLS MCP server")
    parser.add_argument(
        "--transport",
        default=settings().transport,
        choices=["stdio", "streamable-http", "sse"],
        help="stdio for desktop clients, streamable-http for networked clients",
    )
    parser.add_argument("--port", type=int, default=settings().port)
    args = parser.parse_args()

    mcp = build_server()

    if args.transport == "stdio":
        log.info("starting on stdio as '%s'", settings().server_name)
        mcp.run(transport="stdio")
    elif args.transport == "streamable-http":
        # mcp.run(transport="streamable-http") serves the SDK's ASGI app
        # unwrapped - no CORS. A browser-based client (the MCP Inspector web
        # UI, or any future browser tool) talks to this server from a
        # different origin (different port), so it sends a CORS preflight
        # (OPTIONS) before the real POST. Without CORSMiddleware that
        # preflight gets a bare 405 and the browser blocks the real request
        # before it ever reaches the MCP handshake - connect fails with no
        # clue that it was CORS, not the protocol, that broke it.
        import uvicorn
        from starlette.middleware.cors import CORSMiddleware

        mcp.settings.port = args.port
        app = mcp.streamable_http_app()
        app.add_middleware(
            CORSMiddleware,
            # Wildcard is fine here specifically: transport_security above
            # already restricts which Host header is accepted to loopback,
            # so this still only serves 127.0.0.1/localhost regardless of
            # which origin the CORS layer waves through. Pin this to a real
            # origin list before this server ever binds beyond loopback.
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
            # A browser only lets JS read response headers a CORS response
            # explicitly exposes - everything else is invisible even though
            # it arrived. `mcp-session-id` (mcp.server.streamable_http.
            # MCP_SESSION_ID_HEADER) carries the session the client must echo
            # back on every later request; without exposing it here, a
            # browser client re-sends no session id, the server treats every
            # request as a fresh connection, and non-initialize methods on
            # that "new" session fail with 400 - fixing the preflight alone
            # (allow_origins/methods/headers above) is not enough on its own.
            expose_headers=["mcp-session-id"],
        )
        log.info("starting on %s port %s as '%s'",
                 args.transport, args.port, settings().server_name)
        uvicorn.run(app, host=mcp.settings.host, port=args.port,
                    log_level=mcp.settings.log_level.lower())
    else:
        log.warning(
            "SSE transport is the deprecated pre-2025-03-26 shape. "
            "Use streamable-http unless you must support an old client."
        )
        mcp.settings.port = args.port
        log.info("starting on %s port %s as '%s'",
                 args.transport, args.port, settings().server_name)
        mcp.run(transport=args.transport)
    return 0


if __name__ == "__main__":
    sys.exit(main())
