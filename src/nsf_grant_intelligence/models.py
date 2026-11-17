"""Pydantic models: validated tool inputs and structured tool outputs."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

# --- reusable input types ---------------------------------------------------

Keyword = Annotated[
    str,
    Field(
        description="Free-text topic. Matching is loose (any text in the award record), "
        "so broad terms over-match; combine with fund_program_name to be precise."
    ),
]
ProgramName = Annotated[
    str,
    Field(description='NSF program name filter, e.g. "Robust Intelligence". Optional.'),
]
FromYear = Annotated[
    int, Field(ge=1950, le=2100, description="First award start year to include.")
]
Page = Annotated[int, Field(ge=1, description="1-based page number.")]
PerPage = Annotated[int, Field(ge=1, le=25, description="Results per page (NSF caps this at 25).")]
LastName = Annotated[str, Field(min_length=1, description="Principal investigator's last name.")]
FirstName = Annotated[str, Field(description="PI first name; narrows the match. Optional.")]
DateMMDDYYYY = Annotated[
    str,
    Field(pattern=r"^(\d{2}/\d{2}/\d{4})?$", description="Date as MM/DD/YYYY. Optional."),
]
StateCode = Annotated[
    str,
    Field(pattern=r"^([A-Za-z]{2})?$", description='Two-letter US state code, e.g. "PA". Optional.'),
]


# --- outputs ----------------------------------------------------------------


class NamedCount(BaseModel):
    name: str
    count: int


class AwardSummary(BaseModel):
    award_id: str | None
    title: str | None
    pi: str | None
    institution: str | None
    location: str
    funds_obligated_usd: int | None
    estimated_total_usd: int | None
    start_date: str | None
    end_date: str | None
    program: str | None = Field(description="Program name; the NSF API truncates long names.")
    abstract_snippet: str | None = None


class AwardDetail(AwardSummary):
    abstract: str | None
    program_detail: str | None
    nsf_directorate: str | None
    award_type: str | None


class AwardSearchResult(BaseModel):
    page: int
    per_page: int
    total_count: int | None = Field(description="Total matches (the API caps this at 10,000).")
    results_on_page: int
    awards: list[AwardSummary]


class YearFunding(BaseModel):
    awards: int = Field(description="Exact number of awards starting that year (max 10,000).")
    sampled_awards: int
    sampled_funds_obligated_usd: int = Field(description="Dollars across the sampled awards only.")


class FundingTrends(BaseModel):
    keyword: str | None
    fund_program_name: str | None
    years: dict[int, YearFunding]
    awards_scanned: int
    note: str


class TopicAnalysis(BaseModel):
    keyword: str
    fund_program_name: str | None
    from_year: int
    awards_analyzed: int
    total_funds_obligated_usd: int
    median_award_usd: int | None
    top_programs: list[NamedCount]
    top_institutions: list[NamedCount]
    top_pis: list[NamedCount]
    awards_by_start_year: dict[int, int]


class WinningAbstract(BaseModel):
    award_id: str | None
    title: str | None
    pi: str
    institution: str | None
    funds_obligated_usd: int | None
    program: str | None
    start_date: str | None
    abstract: str


class WinningAbstracts(BaseModel):
    keyword: str
    samples: list[WinningAbstract]


class ProgramFunding(BaseModel):
    program: str
    awards: int
    funds_obligated_usd: int


class ProgramComparison(BaseModel):
    keyword: str
    from_year: int
    awards_scanned: int
    programs: list[ProgramFunding]


class PITrackRecord(BaseModel):
    pi: str
    awards_found: int
    total_matching_awards: int | None
    total_funds_obligated_usd: int
    pi_names_matched: list[NamedCount] = Field(
        description="Distinct PI names in the matches; more than one means the name is ambiguous."
    )
    programs: list[NamedCount]
    institutions: list[NamedCount]
    year_span: list[int] | None
    recent_titles: list[str | None]


class Themes(BaseModel):
    keyword: str
    abstracts_scanned: int
    top_terms: list[NamedCount]
