import asyncio

import pytest

from nsf_grant_intelligence import server


# --- helpers ---------------------------------------------------------------

def test_to_int():
    assert server._to_int("417136") == 417136
    assert server._to_int("12.9") == 12
    assert server._to_int(None) is None
    assert server._to_int("n/a") is None


def test_year():
    assert server._year("03/15/2027") == 2027
    assert server._year(None) is None
    assert server._year("bad") is None


def test_page_params_clamps_and_offsets():
    assert server._page_params(1, 10) == {"rpp": 10, "offset": 0}
    assert server._page_params(3, 10) == {"rpp": 10, "offset": 20}
    assert server._page_params(0, 100) == {"rpp": 25, "offset": 0}


def test_trim_builds_compact_record():
    a = {
        "id": "1",
        "title": "T",
        "piFirstName": "Ada",
        "piLastName": "Lovelace",
        "awardeeName": "U",
        "awardeeCity": "X",
        "awardeeStateCode": "CA",
        "fundsObligatedAmt": "100",
        "abstractText": "abc " * 200,
    }
    out = server._trim(a, abstract_len=10)
    assert out["pi"] == "Ada Lovelace"
    assert out["location"] == "X, CA"
    assert out["funds_obligated_usd"] == 100
    assert len(out["abstract_snippet"]) <= 10


# --- tools (API mocked) ----------------------------------------------------

@pytest.fixture
def fake_api(monkeypatch):
    calls = []

    def install(responses):
        it = iter(responses)

        async def _api(params):
            calls.append(params)
            return next(it)

        monkeypatch.setattr(server, "_api", _api)
        return calls

    return install


def test_search_awards_maps_params(fake_api):
    calls = fake_api([{"metadata": {"totalCount": "3"}, "award": [{"id": "9"}]}])
    out = asyncio.run(server.search_awards(keyword="ai", active_only=True, page=2))
    assert calls[0]["keyword"] == "ai"
    assert calls[0]["ActiveAwards"] == "true"
    assert calls[0]["offset"] == 10
    assert out["total_count"] == 3
    assert out["awards"][0]["award_id"] == "9"


def test_search_awards_surfaces_errors(fake_api):
    fake_api([{"_error": "boom"}])
    assert asyncio.run(server.search_awards(keyword="x")) == {"error": "boom"}


def test_get_award_not_found(fake_api):
    fake_api([{"award": []}])
    assert "error" in asyncio.run(server.get_award("123"))


def test_funding_trends_aggregates_by_year(fake_api):
    fake_api([{
        "metadata": {"totalCount": "3"},
        "award": [
            {"startDate": "01/01/2025", "fundsObligatedAmt": "100"},
            {"startDate": "06/01/2025", "fundsObligatedAmt": "50"},
            {"startDate": "02/01/2026", "fundsObligatedAmt": "10"},
        ],
    }])
    out = asyncio.run(server.funding_trends(keyword="ai", from_year=2025, to_year=2026))
    assert out["years"] == {
        2025: {"awards": 2, "funds_obligated_usd": 150},
        2026: {"awards": 1, "funds_obligated_usd": 10},
    }
    assert out["awards_scanned"] == 3


# --- proposal-analysis helpers & tools --------------------------------------

def _award(i, amt, prog="Prog A", year=2025, pi=("Ada", "Lovelace"), abstract="x"):
    return {
        "id": str(i),
        "title": f"T{i}",
        "piFirstName": pi[0],
        "piLastName": pi[1],
        "awardeeName": "Univ",
        "fundsObligatedAmt": str(amt),
        "startDate": f"01/01/{year}",
        "fundProgramName": prog,
        "abstractText": abstract,
    }


def _first_year_only(resp):
    """Mock responses for the tools that query one slice per year."""
    return [resp] + [{"award": []}] * 20


def test_pi_name_falls_back():
    assert server._pi_name({"piFirstName": "Ada", "piLastName": "L"}) == "Ada L"
    assert server._pi_name({"pdPIName": "Prog Dir"}) == "Prog Dir"
    assert server._pi_name({}) == "Unknown"


def test_stats_summarizes_awards():
    awards = [_award(1, 100), _award(2, 300, prog="Prog B", year=2026), _award(3, 200)]
    s = server._stats(awards)
    assert s["awards_analyzed"] == 3
    assert s["total_funds_obligated_usd"] == 600
    assert s["median_award_usd"] == 200
    assert s["top_programs"][0] == ("Prog A", 2)
    assert s["awards_by_start_year"] == {2025: 2, 2026: 1}


def test_stats_empty():
    s = server._stats([])
    assert s["median_award_usd"] is None
    assert s["total_funds_obligated_usd"] == 0


def test_collect_spreads_quota_across_years(fake_api):
    calls = fake_api([
        {"award": [_award(i, 1, year=2025) for i in range(25)]},
        {"award": [_award(i, 1, year=2026) for i in range(25)]},
    ])
    out = asyncio.run(server._collect("ai", from_year=2025, max_awards=10, to_year=2026))
    assert len(out) == 10
    # one request per year, each restricted to that year
    assert [(c["startDateStart"], c["startDateEnd"]) for c in calls] == [
        ("01/01/2025", "12/31/2025"),
        ("01/01/2026", "12/31/2026"),
    ]
    assert calls[0]["keyword"] == "ai"
    assert [_year_of(a) for a in out] == [2025] * 5 + [2026] * 5


def _year_of(a):
    return server._year(a["startDate"])


def test_collect_pages_within_year_zero_based(fake_api):
    calls = fake_api([
        {"award": [_award(i, 1) for i in range(25)]},
        {"award": [_award(99, 1)]},
    ])
    out = asyncio.run(server._collect("ai", from_year=2025, max_awards=100, to_year=2025))
    assert len(out) == 26
    assert [c["offset"] for c in calls] == [0, 25]


def test_collect_moves_on_when_a_year_is_empty(fake_api):
    calls = fake_api([{"award": []}, {"award": [_award(1, 1, year=2026)]}])
    out = asyncio.run(server._collect("ai", from_year=2025, max_awards=20, to_year=2026))
    assert len(out) == 1
    assert len(calls) == 2


def test_collect_defaults_to_next_year(fake_api, monkeypatch):
    class FakeDate:
        @staticmethod
        def today():
            import datetime
            return datetime.date(2026, 11, 16)

    monkeypatch.setattr(server, "date", FakeDate)
    calls = fake_api([{"award": []}] * 3)
    asyncio.run(server._collect("ai", from_year=2025, max_awards=30))
    assert [c["startDateStart"] for c in calls] == ["01/01/2025", "01/01/2026", "01/01/2027"]


def test_collect_surfaces_errors(fake_api):
    fake_api([{"_error": "boom"}])
    assert asyncio.run(server._collect("ai", to_year=2025)) == {"error": "boom"}


def test_analyze_topic(fake_api):
    fake_api(_first_year_only({"award": [_award(1, 100), _award(2, 50)]}))
    out = asyncio.run(server.analyze_topic("ai", from_year=2025))
    assert out["keyword"] == "ai"
    assert out["total_funds_obligated_usd"] == 150
    assert out["from_year"] == 2025


def test_analyze_topic_surfaces_errors(fake_api):
    fake_api([{"_error": "boom"}])
    assert asyncio.run(server.analyze_topic("ai")) == {"error": "boom"}


def test_sample_winning_abstracts_sorted_by_funding(fake_api):
    fake_api(_first_year_only({"award": [
        _award(1, 10, abstract=" small "),
        _award(2, 999, abstract="big"),
        _award(3, 500, abstract="mid"),
    ]}))
    out = asyncio.run(server.sample_winning_abstracts("ai", n=2))
    assert [s["award_id"] for s in out["samples"]] == ["2", "3"]
    assert out["samples"][0]["abstract"] == "big"


def test_compare_funding_by_program_ranks_by_dollars(fake_api):
    fake_api(_first_year_only({"award": [
        _award(1, 100, prog="A"),
        _award(2, 100, prog="A"),
        _award(3, 500, prog="B"),
    ]}))
    out = asyncio.run(server.compare_funding_by_program("ai"))
    assert out["programs"][0] == {"program": "B", "awards": 1, "funds_obligated_usd": 500}
    assert out["programs"][1]["awards"] == 2
    assert out["awards_scanned"] == 3


def test_pi_track_record(fake_api):
    calls = fake_api([{
        "metadata": {"totalCount": "40"},
        "award": [_award(1, 100, year=2019), _award(2, 200, year=2024)],
    }])
    out = asyncio.run(server.pi_track_record("Lovelace", "Ada"))
    assert calls[0]["piLastName"] == "Lovelace"
    assert calls[0]["piFirstName"] == "Ada"
    assert calls[0]["offset"] == 0
    assert out["total_funds_obligated_usd"] == 300
    assert out["year_span"] == [2019, 2024]
    assert out["total_matching_awards"] == 40
    assert out["recent_titles"] == ["T1", "T2"]


def test_pi_track_record_no_awards(fake_api):
    fake_api([{"award": []}])
    out = asyncio.run(server.pi_track_record("Nobody"))
    assert out["awards_found"] == 0
    assert out["year_span"] is None


def test_extract_themes_counts_terms_and_skips_stopwords(fake_api):
    fake_api(_first_year_only({"award": [
        _award(1, 1, abstract="Quantum sensing and quantum networks"),
        _award(2, 1, abstract="The quantum research of sensing"),
    ]}))
    out = asyncio.run(server.extract_themes("quantum"))
    terms = dict(out["top_terms"])
    assert terms["quantum"] == 3
    assert terms["sensing"] == 2
    assert "the" not in terms and "research" not in terms
    assert out["abstracts_scanned"] == 2
