"""Helpers shared by the tool modules."""

from __future__ import annotations

from mcp.types import ToolAnnotations

from ..models import NamedCount


def read_only(title: str) -> ToolAnnotations:
    """Every tool only reads from a public third-party API."""
    return ToolAnnotations(
        title=title, readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True
    )


def counts(pairs: list[tuple[str, int]]) -> list[NamedCount]:
    return [NamedCount(name=n, count=c) for n, c in pairs]
