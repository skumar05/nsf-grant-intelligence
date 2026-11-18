import asyncio

import httpx

import pytest
from pydantic import ValidationError

from nsf_grant_intelligence import api, sampling, server, transform


# --- helpers ---------------------------------------------------------------

def test_to_int():
    assert transform.to_int("417136") == 417136
    assert transform.to_int("12.9") == 12
    assert transform.to_int(None) is None
    assert transform.to_int("n/a") is None


def test_year():
    assert transform.year_of("03/15/2027") == 2027
    assert transform.year_of(None) is None
    assert transform.year_of("bad") is None


def test_page_params_clamps_and_offsets():
    assert api.page_params(1, 10) == {"rpp": 10, "offset": 0}
    assert api.page_params(3, 10) == {"rpp": 10, "offset": 20}
    assert api.page_params(0, 100) == {"rpp": 25, "offset": 0}


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
    out = transform.trim_award(a, abstract_len=10)
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
            r = next(it)
            if isinstance(r, Exception):
                raise r
            return r

        monkeypatch.setattr(api, "request", _api)
        return calls

    return install


def test_search_awards_maps_params(fake_api):
    calls = fake_api([{"metadata": {"totalCount": "3"}, "award": [{"id": "9"}]}])
    out = asyncio.run(server.search_awards(keyword="ai", active_only=True, page=2))
    assert calls[0]["keyword"] == "ai"
    assert calls[0]["ActiveAwards"] == "true"
    assert calls[0]["offset"] == 10
    assert out.total_count == 3
    assert out.awards[0].award_id == "9"


def test_search_awards_surfaces_errors(fake_api):
    fake_api([api.NSFAPIError("boom")])
    with pytest.raises(api.NSFAPIError, match="boom"):
        asyncio.run(server.search_awards(keyword="x"))


def test_get_award_not_found(fake_api):
    fake_api([{"award": []}])
    with pytest.raises(api.NSFAPIError, match="No award found"):
        asyncio.run(server.get_award("123"))


def test_funding_trends_queries_each_year(fake_api):
    calls = fake_api([
        {"metadata": {"totalCount": "300"},
         "award": [{"fundsObligatedAmt": "100"}, {"fundsObligatedAmt": "50"}]},
        {"metadata": {"totalCount": "0"}, "award": []},
        {"metadata": {"totalCount": "7"}, "award": [{"fundsObligatedAmt": "10"}]},
    ])
    out = asyncio.run(server.funding_trends(keyword="ai", from_year=2024, to_year=2026))
    assert [c["startDateStart"] for c in calls] == ["01/01/2024", "01/01/2025", "01/01/2026"]
    assert {y: v.model_dump() for y, v in out.years.items()} == {
        2024: {"awards": 300, "sampled_awards": 2, "sampled_funds_obligated_usd": 150},
        2026: {"awards": 7, "sampled_awards": 1, "sampled_funds_obligated_usd": 10},
    }
    assert out.awards_scanned == 3


def test_funding_trends_surfaces_errors(fake_api):
    fake_api([api.NSFAPIError("boom")])
    with pytest.raises(api.NSFAPIError):
        asyncio.run(server.funding_trends(keyword="ai", from_year=2025, to_year=2025))


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
    assert transform.pi_name({"piFirstName": "Ada", "piLastName": "L"}) == "Ada L"
    assert transform.pi_name({"pdPIName": "Prog Dir"}) == "Prog Dir"
    assert transform.pi_name({}) == "Unknown"


def test_stats_summarizes_awards():
    awards = [_award(1, 100), _award(2, 300, prog="Prog B", year=2026), _award(3, 200)]
    s = transform.award_stats(awards)
    assert s["awards_analyzed"] == 3
    assert s["total_funds_obligated_usd"] == 600
    assert s["median_award_usd"] == 200
    assert s["top_programs"][0] == ("Prog A", 2)
    assert s["awards_by_start_year"] == {2025: 2, 2026: 1}


def test_stats_empty():
    s = transform.award_stats([])
    assert s["median_award_usd"] is None
    assert s["total_funds_obligated_usd"] == 0


def test_collect_spreads_quota_across_years(fake_api):
    calls = fake_api([
        {"award": [_award(i, 1, year=2025) for i in range(25)]},
        {"award": [_award(i, 1, year=2026) for i in range(25)]},
    ])
    out = asyncio.run(sampling.collect("ai", from_year=2025, max_awards=10, to_year=2026))
    assert len(out) == 10
    # one request per year, each restricted to that year
    assert [(c["startDateStart"], c["startDateEnd"]) for c in calls] == [
        ("01/01/2025", "12/31/2025"),
        ("01/01/2026", "12/31/2026"),
    ]
    assert calls[0]["keyword"] == "ai"
    assert [_year_of(a) for a in out] == [2025] * 5 + [2026] * 5


def _year_of(a):
    return transform.year_of(a["startDate"])


def test_collect_pages_within_year_zero_based(fake_api):
    calls = fake_api([
        {"award": [_award(i, 1) for i in range(25)]},
        {"award": [_award(99, 1)]},
    ])
    out = asyncio.run(sampling.collect("ai", from_year=2025, max_awards=100, to_year=2025))
    assert len(out) == 26
    assert [c["offset"] for c in calls] == [0, 25]


def test_collect_moves_on_when_a_year_is_empty(fake_api):
    calls = fake_api([{"award": []}, {"award": [_award(1, 1, year=2026)]}])
    out = asyncio.run(sampling.collect("ai", from_year=2025, max_awards=20, to_year=2026))
    assert len(out) == 1
    assert len(calls) == 2


def test_collect_defaults_to_next_year(fake_api, monkeypatch):
    class FakeDate:
        @staticmethod
        def today():
            import datetime
            return datetime.date(2026, 11, 16)

    monkeypatch.setattr(sampling, "date", FakeDate)
    calls = fake_api([{"award": []}] * 3)
    asyncio.run(sampling.collect("ai", from_year=2025, max_awards=30))
    assert [c["startDateStart"] for c in calls] == ["01/01/2025", "01/01/2026", "01/01/2027"]


def test_collect_surfaces_errors(fake_api):
    fake_api([api.NSFAPIError("boom")])
    with pytest.raises(api.NSFAPIError):
        asyncio.run(sampling.collect("ai", to_year=2025))


def test_analyze_topic(fake_api):
    fake_api(_first_year_only({"award": [_award(1, 100), _award(2, 50)]}))
    out = asyncio.run(server.analyze_topic("ai", from_year=2025))
    assert out.keyword == "ai"
    assert out.total_funds_obligated_usd == 150
    assert out.from_year == 2025


def test_analyze_topic_surfaces_errors(fake_api):
    fake_api([api.NSFAPIError("boom")])
    with pytest.raises(api.NSFAPIError):
        asyncio.run(server.analyze_topic("ai"))


def test_sample_winning_abstracts_sorted_by_funding(fake_api):
    fake_api(_first_year_only({"award": [
        _award(1, 10, abstract=" small "),
        _award(2, 999, abstract="big"),
        _award(3, 500, abstract="mid"),
    ]}))
    out = asyncio.run(server.sample_winning_abstracts("ai", n=2))
    assert [s.award_id for s in out.samples] == ["2", "3"]
    assert out.samples[0].abstract == "big"


def test_compare_funding_by_program_ranks_by_dollars(fake_api):
    fake_api(_first_year_only({"award": [
        _award(1, 100, prog="A"),
        _award(2, 100, prog="A"),
        _award(3, 500, prog="B"),
    ]}))
    out = asyncio.run(server.compare_funding_by_program("ai"))
    assert out.programs[0].model_dump() == {"program": "B", "awards": 1, "funds_obligated_usd": 500}
    assert out.programs[1].awards == 2
    assert out.awards_scanned == 3


def test_pi_track_record(fake_api):
    calls = fake_api([{
        "metadata": {"totalCount": "40"},
        "award": [_award(1, 100, year=2019), _award(2, 200, year=2024)],
    }])
    out = asyncio.run(server.pi_track_record("Lovelace", "Ada"))
    assert calls[0]["piLastName"] == "Lovelace"
    assert calls[0]["piFirstName"] == "Ada"
    assert calls[0]["offset"] == 0
    assert out.total_funds_obligated_usd == 300
    assert out.year_span == [2019, 2024]
    assert out.total_matching_awards == 40
    assert [a.title for a in out.recent_awards] == ["T1", "T2"]


def test_pi_track_record_no_awards(fake_api):
    fake_api([{"award": []}])
    out = asyncio.run(server.pi_track_record("Nobody"))
    assert out.awards_found == 0
    assert out.year_span is None


def test_extract_themes_counts_terms_and_skips_stopwords(fake_api):
    fake_api(_first_year_only({"award": [
        _award(1, 1, abstract="Quantum sensing and quantum networks"),
        _award(2, 1, abstract="The quantum research of sensing"),
    ]}))
    out = asyncio.run(server.extract_themes("quantum"))
    terms = {t.name: t.count for t in out.top_terms}
    assert terms["quantum"] == 3
    assert terms["sensing"] == 2
    assert "the" not in terms and "research" not in terms
    assert out.abstracts_scanned == 2


# --- MCP surface: schemas, validation, annotations ---------------------------

def test_every_tool_is_read_only_and_described():
    tools = asyncio.run(server.mcp.list_tools())
    assert len(tools) == 9
    for t in tools:
        assert t.annotations.read_only_hint is True
        assert len(t.description) > 40, t.name
        for name, prop in t.input_schema["properties"].items():
            assert prop.get("description"), f"{t.name}.{name} lacks a description"


@pytest.mark.parametrize(
    "tool,args",
    [
        ("search_awards", {"per_page": 500}),
        ("search_awards", {"start_date_start": "2024-01-01"}),
        ("search_awards", {"awardee_state_code": "Pennsylvania"}),
        ("analyze_topic", {"keyword": "ai", "max_awards": 100000}),
        ("analyze_topic", {"keyword": ""}),
        ("funding_trends", {"from_year": 1800}),
        ("get_award", {"award_id": ""}),
    ],
)
def test_invalid_arguments_are_rejected_before_any_api_call(tool, args, fake_api):
    calls = fake_api([])
    with pytest.raises(Exception, match="validation error"):
        asyncio.run(server.mcp.call_tool(tool, args))
    assert calls == []


def test_tool_returns_structured_output(fake_api):
    fake_api([{"metadata": {"totalCount": "1"}, "award": [{"id": "9", "title": "T"}]}])
    result = asyncio.run(server.mcp.call_tool("search_awards", {"keyword": "ai"}))
    assert result.structured_content["awards"][0]["award_id"] == "9"


# --- _api: retries, bad bodies, NSF's 200-with-error convention ----------------

@pytest.fixture
def http(monkeypatch):
    """Route api.request through a scripted httpx transport; returns the call log."""
    monkeypatch.setattr(api, "RETRY_BASE_DELAY", 0)

    def install(*steps):
        it = iter(steps)
        log = []

        def handler(request):
            log.append(request)
            step = next(it)
            if isinstance(step, Exception):
                raise step
            return step

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        monkeypatch.setattr(api, "_get_client", lambda: client)
        return log

    return install


def _ok(body):
    return httpx.Response(200, json={"response": body})


def test_api_retries_transient_status_then_succeeds(http):
    log = http(httpx.Response(503), httpx.Response(429, headers={"Retry-After": "0"}), _ok({"award": []}))
    assert asyncio.run(api.request({})) == {"award": []}
    assert len(log) == 3


def test_api_retries_timeouts_then_gives_up(http):
    log = http(*[httpx.ReadTimeout("slow")] * 3)
    with pytest.raises(api.NSFAPIError, match="unreachable"):
        asyncio.run(api.request({}))
    assert len(log) == api.MAX_ATTEMPTS


def test_api_does_not_retry_client_errors(http):
    log = http(httpx.Response(400))
    with pytest.raises(api.NSFAPIError, match="HTTP 400"):
        asyncio.run(api.request({}))
    assert len(log) == 1


def test_api_rejects_non_json_body(http):
    http(httpx.Response(200, text="<html>maintenance</html>"))
    with pytest.raises(api.NSFAPIError, match="not valid JSON"):
        asyncio.run(api.request({}))


def test_api_surfaces_service_notification(http):
    http(_ok({"serviceNotification": [{"notificationCode": "AwardAPI-004"}]}))
    with pytest.raises(api.NSFAPIError, match="AwardAPI-004"):
        asyncio.run(api.request({}))


# --- year-range guard & PI ambiguity -----------------------------------------

def test_year_range_rejects_reversed_and_huge_spans():
    assert sampling.year_range(2024, 2026) == [2024, 2025, 2026]
    with pytest.raises(api.NSFAPIError, match="before"):
        sampling.year_range(2026, 2024)
    with pytest.raises(api.NSFAPIError, match="too wide"):
        sampling.year_range(1990, 2026)


def test_pi_track_record_pages_and_flags_ambiguous_names(fake_api):
    calls = fake_api([
        {"metadata": {"totalCount": "30"},
         "award": [_award(i, 1, pi=("Ada", "Smith")) for i in range(25)]},
        {"award": [_award(99, 1, pi=("Bob", "Smith"))]},
    ])
    out = asyncio.run(server.pi_track_record("Smith"))
    assert [c["offset"] for c in calls] == [0, 25]
    assert out.awards_found == 26
    assert {n.name for n in out.pi_names_matched} == {"Ada Smith", "Bob Smith"}


def test_institution_profile_filters_by_awardee_and_summarizes(fake_api):
    calls = fake_api(_first_year_only({"award": [
        _award(1, 100, pi=("Ada", "Lovelace")),
        _award(2, 50, pi=("Ada", "Lovelace")),
    ]}))
    out = asyncio.run(server.institution_profile("Univ", keyword="robotics", from_year=2025))
    assert all(c["awardeeName"] == '"Univ"' and c["keyword"] == "robotics" for c in calls)
    assert out.total_funds_obligated_usd == 150
    assert out.top_pis[0].name == "Ada Lovelace" and out.top_pis[0].count == 2
    assert out.institution_names_matched[0].name == "Univ"


def test_overlapping_wrapper_tools_are_gone():
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert not {"awards_by_pi", "awards_by_institution"} & names
    assert {"search_awards", "pi_track_record", "institution_profile"} <= names


def test_institution_names_are_sent_as_quoted_phrases(fake_api):
    calls = fake_api([{"award": []}] * 4)
    asyncio.run(server.search_awards(awardee_name="Carnegie Mellon University"))
    asyncio.run(server.search_awards(awardee_name='"Johns Hopkins"'))
    asyncio.run(server.institution_profile("Rochester", from_year=2027, max_awards=1))
    assert calls[0]["awardeeName"] == '"Carnegie Mellon University"'
    assert calls[1]["awardeeName"] == '"Johns Hopkins"'
    assert calls[2]["awardeeName"] == '"Rochester"'


def test_health_endpoint_reports_healthy():
    from starlette.testclient import TestClient

    with TestClient(server.mcp.streamable_http_app()) as client:
        r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "healthy", "service": "nsf-grant-intelligence"}


def test_version_endpoint_reports_package_version():
    from starlette.testclient import TestClient

    from nsf_grant_intelligence import __version__

    with TestClient(server.mcp.streamable_http_app()) as client:
        r = client.get("/version")
    assert r.status_code == 200 and r.json() == {"version": __version__}


def test_every_tool_has_a_title_and_safe_annotations():
    for tool in asyncio.run(server.mcp.list_tools()):
        a = tool.annotations
        assert a.title, tool.name
        assert a.read_only_hint and a.idempotent_hint and a.open_world_hint, tool.name
        assert a.destructive_hint is False, tool.name


def test_api_rejects_oversized_response(http):
    http(httpx.Response(200, content=b"x" * (api.MAX_RESPONSE_BYTES + 1)))
    with pytest.raises(api.NSFAPIError, match="too large"):
        asyncio.run(api.request({}))


def test_real_client_ignores_proxies_and_redirects():
    async def build():
        return api._get_client()

    client = asyncio.run(build())
    assert client.follow_redirects is False
    assert client._trust_env is False


def test_httpx_request_logging_is_quiet():
    import logging

    assert logging.getLogger("httpx").level >= logging.WARNING


def test_landing_page_lists_tools_and_the_mcp_url():
    from starlette.testclient import TestClient

    with TestClient(server.mcp.streamable_http_app(), base_url="https://demo.example.com") as client:
        r = client.get("/", headers={"x-forwarded-proto": "https"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "https://demo.example.com/mcp" in r.text
    names = [t.name for t in asyncio.run(server.mcp.list_tools())]
    assert all(f"<code>{n}</code>" in r.text for n in names)


def test_landing_page_escapes_host_header():
    from starlette.testclient import TestClient

    with TestClient(server.mcp.streamable_http_app()) as client:
        r = client.get("/", headers={"host": "x\"><script>alert(1)</script>"})
    assert "<script>alert(1)" not in r.text


def test_landing_page_descriptions_are_whole_sentences():
    from starlette.testclient import TestClient

    with TestClient(server.mcp.streamable_http_app()) as client:
        r = client.get("/")
    for tool in asyncio.run(server.mcp.list_tools()):
        first = " ".join(tool.description.strip().split("\n\n")[0].split())
        assert first.replace("'", "&#x27;") in r.text, tool.name
