#!/usr/bin/env python3
"""Workshop 3: Customer Directory MCP Server - one tool, one validation rule.

    uv run python workshop3_customer_directory.py

This is the reference solution for the short (45-minute) warm-up before
Workshop 4. It is deliberately tiny: one MCP server, one tool,
list_customers_by_segment, that reads the real `customers` table (the same
database Workshop 4 uses) and returns every customer in one segment.

The point of this workshop is not the query - it is validating `segment`
in code BEFORE it ever reaches the database, and rejecting anything that is
not exactly "Enterprise", "SME" or "Government" with a clear message. The
database also enforces this shape (see the CHECK constraint on
customers.segment in docker/postgres/init/02_schema.sql.template), but that
is not a reason to skip the check here: a validation error raised in the
tool is a clear, model-readable message; a raw CheckViolation from
PostgreSQL is not, and reaching the database at all for input the tool
already knows is invalid wastes a round trip for nothing. This is the same
"validate before you touch the resource" principle taught in Module 10,
applied to a single string argument instead of a whole SQL statement.
"""

from __future__ import annotations

import os

import psycopg
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from psycopg.rows import dict_row

load_dotenv()

PG_DSN = os.getenv(
    "PG_DSN", "postgresql://mcp_reader:mcp_reader_password@localhost:5432/mplsdb"
)

# Exactly the three values the customers.segment CHECK constraint allows.
ALLOWED_SEGMENTS = ("Enterprise", "SME", "Government")

mcp = FastMCP(name="customer-directory-workshop3")


@mcp.tool(
    annotations={
        "title": "List customers by segment",
        "readOnlyHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
def list_customers_by_segment(segment: str) -> dict:
    """List every customer in one segment.

    Use this to answer questions like "how many Enterprise customers do we
    have" or "list all Government customers". Do NOT use this to look up a
    single customer by name or ID - there is no tool for that in this
    workshop; this one only filters by segment.

    Args:
        segment: exactly one of "Enterprise", "SME", "Government"
            (case-sensitive - "enterprise" or "ENTERPRISE" are rejected)
    """
    if segment not in ALLOWED_SEGMENTS:
        return {
            "ok": False,
            "error": f"segment ต้องเป็นหนึ่งใน {ALLOWED_SEGMENTS} เท่านั้น ได้รับมา: {repr(segment)}",
        }

    with psycopg.connect(PG_DSN, row_factory=dict_row) as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT customer_id, name, segment, contact_email
               FROM customers WHERE segment = %s ORDER BY name""",
            (segment,),
        )
        rows = cur.fetchall()

    return {"ok": True, "segment": segment, "count": len(rows), "customers": rows}


if __name__ == "__main__":
    mcp.run(transport="stdio")
