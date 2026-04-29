"""Unit tests for wiki_answer.py — no real network calls."""

import sys
from pathlib import Path

import pytest
import responses as resp_mock

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import wiki_answer as wiki  # noqa: E402


# ── CQL builder ───────────────────────────────────────────────────────────────

class TestCqlEscape:
    def test_plain_text_unchanged(self):
        assert wiki.cql_escape("hello") == "hello"

    def test_double_quote_escaped(self):
        assert wiki.cql_escape('say "hi"') == 'say \\"hi\\"'

    def test_backslash_escaped_first(self):
        assert wiki.cql_escape('back\\slash') == 'back\\\\slash'

    def test_backslash_before_quote(self):
        assert wiki.cql_escape('\\"') == '\\\\\\"'


class TestBuildCql:
    def test_single_query(self):
        assert wiki.build_cql(["auth"], None) == 'text ~ "auth"'

    def test_multiple_queries_or(self):
        result = wiki.build_cql(["auth", "login"], None)
        assert result == '(text ~ "auth" OR text ~ "login")'

    def test_space_filter_appended(self):
        result = wiki.build_cql(["auth"], "MT")
        assert result == 'text ~ "auth" AND space = "MT"'

    def test_space_and_multiple_queries(self):
        result = wiki.build_cql(["auth", "sso"], "IIT")
        assert '(text ~ "auth" OR text ~ "sso")' in result
        assert 'AND space = "IIT"' in result


# ── HTML utils ────────────────────────────────────────────────────────────────

class TestStripHighlightMarkers:
    def test_removes_hl_markers(self):
        text = "foo @@@hl@@@bar@@@endhl@@@ baz"
        assert wiki.strip_highlight_markers(text) == "foo bar baz"

    def test_no_markers_unchanged(self):
        assert wiki.strip_highlight_markers("plain text") == "plain text"

    def test_empty_string(self):
        assert wiki.strip_highlight_markers("") == ""


class TestHtmlToText:
    def test_strips_tags(self):
        assert wiki.html_to_text("<p>Hello <b>world</b></p>") == "Hello world"

    def test_truncates(self):
        long_html = "<p>" + "a" * 1000 + "</p>"
        assert len(wiki.html_to_text(long_html, max_chars=100)) == 100

    def test_collapses_whitespace(self):
        result = wiki.html_to_text("<p>foo   bar</p>")
        assert "  " not in result


class TestExtractHeadings:
    def test_extracts_h1_h2_h3(self):
        html = "<h1>Title</h1><h2>Section</h2><h3>Sub</h3><h4>Ignored</h4>"
        assert wiki.extract_headings(html) == ["Title", "Section", "Sub"]

    def test_empty_html(self):
        assert wiki.extract_headings("") == []

    def test_no_headings(self):
        assert wiki.extract_headings("<p>Just a paragraph</p>") == []


# ── Ranker ────────────────────────────────────────────────────────────────────

def _make_result(title="", excerpt="", space_key="XX") -> dict:
    return {"id": "1", "title": title, "excerpt": excerpt,
            "space_key": space_key, "space_name": "Test Space",
            "url": "https://example.com"}


class TestScoreResult:
    def test_title_match_scores_2(self):
        r = _make_result(title="authentication guide")
        assert wiki.score_result(r, ["authentication"], None) == 2

    def test_excerpt_match_scores_1(self):
        r = _make_result(excerpt="how to authenticate users")
        assert wiki.score_result(r, ["authenticate"], None) == 1

    def test_space_match_scores_1(self):
        r = _make_result(space_key="MT")
        assert wiki.score_result(r, ["anything"], "MT") == 1

    def test_no_match_scores_0(self):
        r = _make_result(title="unrelated page")
        assert wiki.score_result(r, ["authentication"], None) == 0

    def test_case_insensitive(self):
        r = _make_result(title="Authentication Guide")
        assert wiki.score_result(r, ["authentication"], None) == 2


class TestRankResults:
    def test_higher_scoring_result_comes_first(self):
        low = _make_result(title="unrelated")
        high = _make_result(title="authentication guide")
        ranked = wiki.rank_results([low, high], ["authentication"], None)
        assert ranked[0]["title"] == "authentication guide"

    def test_empty_results(self):
        assert wiki.rank_results([], ["query"], None) == []

    def test_equal_scores_preserve_relative_order(self):
        a = _make_result(title="a page")
        b = _make_result(title="b page")
        ranked = wiki.rank_results([a, b], ["something else"], None)
        assert [r["title"] for r in ranked] == ["a page", "b page"]


# ── Confluence adapter ────────────────────────────────────────────────────────

BASE_URL = "https://wiki.example.com"
SEARCH_URL = f"{BASE_URL}/rest/api/content/search"
PAGE_URL = f"{BASE_URL}/rest/api/content/42"

MOCK_SEARCH_RESPONSE = {
    "results": [
        {
            "id": "99",
            "title": "Auth Guide",
            "space": {"key": "MT", "name": "Mobile Team"},
            "_links": {"webui": "/spaces/MT/pages/99/Auth+Guide"},
            "excerpt": "How to @@@hl@@@authenticate@@@endhl@@@ users",
        }
    ]
}

MOCK_PAGE_RESPONSE = {
    "id": "42",
    "title": "Auth Guide",
    "space": {"key": "MT", "name": "Mobile Team"},
    "body": {"storage": {"value": "<h1>Auth</h1><p>Details here.</p>"}},
}


class TestConfluenceAdapterSearch:
    @resp_mock.activate
    def test_returns_normalised_results(self):
        resp_mock.add(resp_mock.GET, SEARCH_URL, json=MOCK_SEARCH_RESPONSE, status=200)
        adapter = wiki.ConfluenceAdapter("test-pat", BASE_URL)
        results = adapter.search(["auth"], None, 5)

        assert len(results) == 1
        r = results[0]
        assert r["id"] == "99"
        assert r["title"] == "Auth Guide"
        assert r["space_key"] == "MT"
        assert r["space_name"] == "Mobile Team"
        assert BASE_URL in r["url"]
        assert "@@@" not in r["excerpt"]

    @resp_mock.activate
    def test_exits_on_401(self):
        resp_mock.add(resp_mock.GET, SEARCH_URL, status=401)
        adapter = wiki.ConfluenceAdapter("bad-pat", BASE_URL)
        with pytest.raises(SystemExit) as exc:
            adapter.search(["q"], None, 5)
        assert exc.value.code == wiki.EXIT_AUTH

    @resp_mock.activate
    def test_exits_on_403(self):
        resp_mock.add(resp_mock.GET, SEARCH_URL, status=403)
        adapter = wiki.ConfluenceAdapter("bad-pat", BASE_URL)
        with pytest.raises(SystemExit) as exc:
            adapter.search(["q"], None, 5)
        assert exc.value.code == wiki.EXIT_AUTH

    @resp_mock.activate
    def test_empty_results(self):
        resp_mock.add(resp_mock.GET, SEARCH_URL, json={"results": []}, status=200)
        adapter = wiki.ConfluenceAdapter("test-pat", BASE_URL)
        assert adapter.search(["q"], None, 5) == []


class TestConfluenceAdapterGetPage:
    @resp_mock.activate
    def test_returns_page_with_body(self):
        resp_mock.add(resp_mock.GET, PAGE_URL, json=MOCK_PAGE_RESPONSE, status=200)
        adapter = wiki.ConfluenceAdapter("test-pat", BASE_URL)
        page = adapter.get_page("42")

        assert page is not None
        assert page["id"] == "42"
        assert page["title"] == "Auth Guide"
        assert "<h1>" in page["body_html"]

    @resp_mock.activate
    def test_returns_none_on_404(self):
        resp_mock.add(resp_mock.GET, PAGE_URL, status=404)
        adapter = wiki.ConfluenceAdapter("test-pat", BASE_URL)
        assert adapter.get_page("42") is None

    @resp_mock.activate
    def test_returns_none_on_500(self):
        resp_mock.add(resp_mock.GET, PAGE_URL, status=500)
        adapter = wiki.ConfluenceAdapter("test-pat", BASE_URL)
        assert adapter.get_page("42") is None
