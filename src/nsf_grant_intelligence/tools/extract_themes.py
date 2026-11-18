"""Tool: Extract abstract themes."""

from __future__ import annotations

import re
from collections import Counter
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from .. import sampling
from ..models import FromYear, ProgramName, Themes
from ..transform import STOPWORDS
from ._common import counts, read_only


async def extract_themes(
    keyword: Annotated[str, Field(min_length=1, description="Topic to mine abstracts for.")],
    fund_program_name: ProgramName = "",
    from_year: FromYear = 2020,
    n: Annotated[int, Field(ge=1, le=100, description="Number of abstracts to scan.")] = 40,
) -> Themes:
    """Most frequent substantive terms across funded abstracts on a topic:
    the vocabulary successful proposals share."""
    awards = await sampling.collect(keyword, fund_program_name, from_year, max_awards=n)
    term_counts: Counter = Counter()
    for a in awards:
        text = (a.get("abstractText") or "").lower()
        for tok in re.findall(r"[a-z]{3,}", text):
            if tok not in STOPWORDS:
                term_counts[tok] += 1
    return Themes(
        keyword=keyword,
        abstracts_scanned=len(awards),
        top_terms=counts(term_counts.most_common(25)),
    )


def register(mcp: MCPServer) -> None:
    mcp.tool(annotations=read_only("Extract abstract themes"))(extract_themes)
