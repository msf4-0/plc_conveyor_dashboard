"""MCP server for chatbots / external AI agents (n8n MCP Client Tool).

Mounted in-process by `app.main`; serves the Streamable HTTP transport at
the single endpoint `/mcp`. Read-only surface: exactly two tools.

- `get_iq_data`: current I/Q data from the live data source snapshot
  (the same SourceManager state the dashboard uses).
- `get_latest_oee`: latest OEE row read directly from OEE_DATABASE_URL,
  independent of the dashboard's UI-connected OEE database.
"""

import logging
from typing import Callable

from mcp.server.fastmcp import FastMCP

from app.db import latest_oee_row
from app.tags import TAGS

log = logging.getLogger(__name__)

OEE_EMPTY = {
    "timestamp": None,
    "availability": None,
    "performance": None,
    "quality": None,
    "oee": None,
}

DESCRIPTIONS = {name: tag.description for name, tag in TAGS.items()}


def create_mcp_server(
    snapshot_fn: Callable[[], dict],
    oee_database_url: str | None,
) -> FastMCP:
    """Build the MCP server wired to the dashboard's live state.

    `snapshot_fn` is the SourceManager's `snapshot()` (injected to avoid a
    circular import with `app.main`); `oee_database_url` comes from config
    and may be `None` (the tool then reports "not configured").
    """

    mcp = FastMCP("plc-conveyor")

    @mcp.tool()
    def get_iq_data() -> dict:
        """Current I/Q data for the conveyor line: a boolean value for each
        of the 14 PLC tags (inputs I: ESO, S1-S3, B1-B4; outputs Q: K1-K3,
        P1-P3), with tag descriptions and the connection status of the
        active data source (direct PLC or MQTT)."""
        try:
            snap = snapshot_fn()
        except Exception:
            log.exception("get_iq_data: snapshot failed")
            return {
                "connected": False,
                "stale": True,
                "source": None,
                "connection": None,
                "values": None,
                "descriptions": DESCRIPTIONS,
                "message": "failed to read the data source snapshot",
            }
        values = snap.get("raw")
        payload = {
            "connected": snap.get("connected", False),
            "stale": snap.get("stale", False),
            "source": snap.get("source"),
            "connection": snap.get("broker") or snap.get("line_ip"),
            "values": values,
            "descriptions": DESCRIPTIONS,
        }
        if values is None:
            if snap.get("connecting"):
                payload["message"] = (
                    "no tag values yet: the mqtt source is active but no "
                    "broker address has been submitted"
                )
            else:
                payload["message"] = (
                    "no tag values available: the data source is not connected"
                )
        return payload

    @mcp.tool()
    def get_latest_oee() -> dict:
        """Latest OEE data for the conveyor line: the most recent row
        (timestamp, availability, performance, quality, oee percentages)
        from the recorder's `oee` PostgreSQL database."""
        if not oee_database_url:
            return {
                "connected": False,
                "error": "OEE_DATABASE_URL is not configured; no OEE data source",
                **OEE_EMPTY,
            }
        try:
            row = latest_oee_row(oee_database_url)
        except Exception:
            log.exception("get_latest_oee: OEE database read failed")
            return {
                "connected": False,
                "error": "OEE database unreachable",
                **OEE_EMPTY,
            }
        if row is None:
            return {"connected": True, "error": "no OEE data recorded yet", **OEE_EMPTY}
        return {"connected": True, "error": None, **row}

    return mcp
