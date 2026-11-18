"""Tool: Get an NSF award."""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from .. import api
from ..models import AwardDetail
from ..transform import trim_award
from ._common import read_only


async def get_award(
    award_id: Annotated[str, Field(min_length=1, description='NSF award ID, e.g. "1753742".')],
) -> AwardDetail:
    """Full detail for one NSF award: complete abstract, directorate and award type."""
    resp = await api.request({"id": award_id, "printFields": api.DETAIL_FIELDS})
    awards = resp.get("award", [])
    if not awards:
        raise api.NSFAPIError(f"No award found with ID {award_id}")
    a = awards[0]
    return AwardDetail(
        **trim_award(a, abstract_len=0),
        abstract=a.get("abstractText"),
        program_detail=a.get("program"),
        nsf_directorate=a.get("orgLongName"),
        award_type=a.get("transType"),
    )


def register(mcp: MCPServer) -> None:
    mcp.tool(annotations=read_only("Get an NSF award"))(get_award)
