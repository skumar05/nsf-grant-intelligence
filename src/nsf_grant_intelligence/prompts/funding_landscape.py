"""Prompt: a research plan for understanding the NSF funding landscape on a topic."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer


def funding_landscape(topic: str, from_year: int = 2020) -> str:
    """Plan a proposal's funding research: programs, who gets funded, and how winners write."""
    return (
        f"I am preparing an NSF proposal on '{topic}'. Using the NSF tools, build a funding "
        f"landscape for awards starting {from_year} or later:\n"
        f"1. compare_funding_by_program: which programs fund '{topic}' most, to choose where to submit.\n"
        f"2. analyze_topic: total and median award size, top institutions and PIs.\n"
        f"3. funding_trends: how the number of awards changed year by year.\n"
        f"4. sample_winning_abstracts and extract_themes: how funded proposals describe the work.\n"
        "Finish with a short summary: the best-fit programs, a typical award size, who the "
        "competition is, and the vocabulary to reuse. Say clearly where numbers come from "
        "samples rather than exact counts."
    )


def register(mcp: MCPServer) -> None:
    mcp.prompt(name="funding_landscape", title="NSF funding landscape for a topic")(funding_landscape)
