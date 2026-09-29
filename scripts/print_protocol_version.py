#!/usr/bin/env python3
"""Print the MCP protocol version the installed SDK implements.

Documentation that hardcodes a version number goes stale the moment the SDK
updates. Instructions reference the output of this script instead, so the
workshop always describes the version participants are actually running.
"""

from __future__ import annotations

import importlib.metadata


def main() -> None:
    try:
        import mcp
        from mcp.types import LATEST_PROTOCOL_VERSION
    except ImportError:
        print("The `mcp` package is not installed. Run: make install")
        return

    # The `mcp` package does not set a module-level `__version__` - only
    # `importlib.metadata` (reading the installed distribution's own metadata)
    # reliably reports it. Falling back to "unknown" when that lookup also
    # fails is a real "something is wrong here", not the expected case.
    sdk_version = getattr(mcp, "__version__", None)
    if sdk_version is None:
        try:
            sdk_version = importlib.metadata.version("mcp")
        except importlib.metadata.PackageNotFoundError:
            sdk_version = "unknown"

    print()
    print(f"  MCP Python SDK version : {sdk_version}")
    print(f"  Protocol revision      : {LATEST_PROTOCOL_VERSION}")
    print()
    print("  MCP versions are dates, not release numbers. Notable changes:")
    print("    2025-03-26  Streamable HTTP replaces HTTP+SSE; tool annotations; OAuth 2.1")
    print("    2025-06-18  Structured tool output; elicitation; JSON-RPC batching removed")
    print()
    print("  If sample code you find online uses two endpoints for SSE,")
    print("  it predates the transport change. Use streamable-http.")
    print()


if __name__ == "__main__":
    main()
