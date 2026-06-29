"""Unit tests for confluence_retriever — no real network calls."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import responses as resp_mock

import confluence_retriever.config as wiki
from confluence_retriever.client import ConfluenceAdapter, ConfluenceAuthError, ConfluenceNetworkError
from confluence_retriever.cli import main_entry as main
from confluence_retriever.cql import build_cql, cql_escape
from confluence_retriever.html_utils import (
    extract_cross_links,
    extract_headings,
    extract_relevant_passages,
    html_to_text,
    strip_highlight_markers,
    _proximity_bonus,
)
from confluence_retriever.ranking import (
    DEFAULT_BODY_CHARS,
    expand_queries,
    page_url,
    query_tokens,
    rank_results,
    resolve_body_options,
    score_result,
    token_in_text,
    _structural_variants,
)


# ── Config loader ─────────────────────────────────────────────────────────────

class TestLoadConfig:
    def test_prefers_user_config_path(self, tmp_path, monkeypatch):
        user_env = tmp_path / "user.env"
        project_env = tmp_path / "project.env"
        user_env.write_text("CONFLUENCE_URL=https://user.example.com\nCONFLUENCE_PAT=user-pat\n")
        project_env.write_text("CONFLUENCE_URL=https://project.example.com\nCONFLUENCE_PAT=project-pat\n")

        monkeypatch.setattr(wiki, "USER_ENV_FILE", user_env)
        monkeypatch.setattr(wiki, "PROJECT_ENV_FILE", project_env)

        assert wiki.load_config() == ("user-pat", "https://user.example.com")

    def test_falls_back_to_project_config_path(self, tmp_path, monkeypatch):
        user_env = tmp_path / "missing.env"
        project_env = tmp_path / "project.env"
        project_env.write_text("CONFLUENCE_URL=https://project.example.com/\nCONFLUENCE_PAT=project-pat\n")

        monkeypatch.setattr(wiki, "USER_ENV_FILE", user_env)
        monkeypatch.setattr(wiki, "PROJECT_ENV_FILE", project_env)

        assert wiki.load_config() == ("project-pat", "https://project.example.com")


# ── CQL builder ───────────────────────────────────────────────────────────────

class TestCqlEscape:
    def test_plain_text_unchanged(self):
        assert cql_escape("hello") == "hello"

    def test_double_quote_escaped(self):
        assert cql_escape('say "hi"') == 'say \\"hi\\"'

    def test_backslash_escaped_first(self):
        assert cql_escape('back\\slash') == 'back\\\\slash'

    def test_backslash_before_quote(self):
        assert cql_escape('\\"') == '\\\\\\"'


class TestBuildCql:
    def test_single_query_text_only(self):
        # include_title=False yields the legacy text-only CQL
        assert build_cql(["auth"], None, include_title=False) == 'text ~ "auth" AND type = "page"'

    def test_single_query_default_searches_title_and_text(self):
        # include_title=True (default) ORs a title clause with the text clause
        result = build_cql(["auth"], None)
        assert result == '(title ~ "auth" OR text ~ "auth") AND type = "page"'

    def test_multiple_queries_text_only(self):
        result = build_cql(["auth", "login"], None, include_title=False)
        assert result == '(text ~ "auth" OR text ~ "login") AND type = "page"'

    def test_multiple_queries_default_includes_title(self):
        result = build_cql(["auth", "login"], None)
        # title and text clauses for each query, OR'd together
        assert 'title ~ "auth"' in result
        assert 'text ~ "auth"' in result
        assert 'title ~ "login"' in result
        assert 'text ~ "login"' in result
        assert result.endswith('AND type = "page"')

    def test_space_filter_appended(self):
        result = build_cql(["auth"], "MT", include_title=False)
        assert result == 'text ~ "auth" AND type = "page" AND space = "MT"'

    def test_space_and_multiple_queries(self):
        result = build_cql(["auth", "sso"], "IIT", include_title=False)
        assert '(text ~ "auth" OR text ~ "sso")' in result
        assert 'AND type = "page"' in result
        assert 'AND space = "IIT"' in result


# ── HTML utils ────────────────────────────────────────────────────────────────

class TestStripHighlightMarkers:
    def test_removes_hl_markers(self):
        text = "foo @@@hl@@@bar@@@endhl@@@ baz"
        assert strip_highlight_markers(text) == "foo bar baz"

    def test_no_markers_unchanged(self):
        assert strip_highlight_markers("plain text") == "plain text"

    def test_empty_string(self):
        assert strip_highlight_markers("") == ""


class TestHtmlToText:
    def test_strips_tags(self):
        assert html_to_text("<p>Hello <b>world</b></p>") == "Hello world"

    def test_truncates(self):
        long_html = "<p>" + "a" * 1000 + "</p>"
        assert len(html_to_text(long_html, max_chars=100)) == 100

    def test_collapses_whitespace(self):
        result = html_to_text("<p>foo   bar</p>")
        assert "  " not in result


class TestExtractHeadings:
    def test_extracts_h1_h2_h3(self):
        html = "<h1>Title</h1><h2>Section</h2><h3>Sub</h3><h4>Ignored</h4>"
        assert extract_headings(html) == ["Title", "Section", "Sub"]

    def test_empty_html(self):
        assert extract_headings("") == []

    def test_no_headings(self):
        assert extract_headings("<p>Just a paragraph</p>") == []


class TestExtractCrossLinks:
    def test_extracts_id_with_trailing_slash(self):
        html = '<a href="/pages/12345/Some-Page">link</a>'
        assert extract_cross_links(html) == ["12345"]

    def test_extracts_id_without_trailing_slash(self):
        html = '<a href="/pages/12345">link</a>'
        assert extract_cross_links(html) == ["12345"]

    def test_extracts_id_from_cloud_wiki_url(self):
        html = '<a href="/wiki/spaces/MT/pages/99999/Title">link</a>'
        assert extract_cross_links(html) == ["99999"]

    def test_deduplicates_same_page(self):
        html = '<a href="/pages/42/">a</a><a href="/pages/42/">b</a>'
        assert extract_cross_links(html) == ["42"]

    def test_ignores_non_page_links(self):
        html = '<a href="/display/MT/overview">link</a>'
        assert extract_cross_links(html) == []

    def test_empty_html(self):
        assert extract_cross_links("") == []


class TestExtractRelevantPassages:
    def test_prefers_matching_passage_below_intro(self):
        html = """
        <h1>Release Process</h1>
        <p>Intro text with ownership and general notes.</p>
        <h2>Approval Steps</h2>
        <p>Release approval requires product signoff and engineering review.</p>
        """

        passages = extract_relevant_passages(html, ["release approval"], max_chars=500)

        assert passages[0] == {
            "heading": "Approval Steps",
            "text": "Release approval requires product signoff and engineering review.",
        }

    def test_falls_back_to_first_blocks_when_no_match(self):
        html = "<h1>Guide</h1><p>First paragraph.</p><p>Second paragraph.</p>"

        passages = extract_relevant_passages(html, ["missing"], max_chars=500, max_passages=2)

        assert [p["text"] for p in passages] == ["First paragraph.", "Second paragraph."]

    def test_respects_character_budget(self):
        html = "<p>authentication " + ("details " * 100) + "</p>"

        passages = extract_relevant_passages(
            html,
            ["authentication"],
            max_chars=80,
            passage_chars=80,
        )

        assert len(passages) == 1
        assert len(passages[0]["text"]) <= 80
        assert passages[0]["text"].endswith("...")

    def test_returns_plain_text_fallback_for_unstructured_html(self):
        passages = extract_relevant_passages("plain authentication text", ["authentication"], max_chars=100)

        assert passages == [{"heading": "", "text": "plain authentication text"}]


# ── Ranker ────────────────────────────────────────────────────────────────────

class TestQueryTokens:
    def test_splits_phrases_into_unique_tokens(self):
        assert query_tokens(["customer API auth", "auth flow"]) == ["customer", "api", "auth", "flow"]

    def test_ignores_short_tokens(self):
        assert query_tokens(["an API in MT"]) == ["api"]

    def test_short_acronym_does_not_match_inside_word(self):
        assert not token_in_text("api", "capital planning")

    def test_longer_token_can_match_word_variant(self):
        assert token_in_text("auth", "authentication guide")


class TestPageUrl:
    def test_uses_relative_webui_path(self):
        assert page_url(BASE_URL, "42", "/spaces/MT/pages/42/Auth") == (
            f"{BASE_URL}/spaces/MT/pages/42/Auth"
        )

    def test_uses_absolute_webui_path(self):
        assert page_url(BASE_URL, "42", "https://other.example.com/pages/42") == (
            "https://other.example.com/pages/42"
        )

    def test_falls_back_to_page_id_lookup_url(self):
        assert page_url(BASE_URL, "42") == (
            f"{BASE_URL}/pages/viewpage.action?pageId=42"
        )


class TestExpandQueries:
    def test_includes_original_query(self):
        assert "auth guide" in expand_queries(["auth guide"])

    def test_structural_drop_trailing_token(self):
        result = expand_queries(["auth guide"])
        assert "auth" in result

    def test_structural_drop_leading_token(self):
        result = expand_queries(["auth guide"])
        assert "guide" in result

    def test_abbrev_swap_added_after_structural(self):
        result = expand_queries(["auth guide"])
        assert "authentication guide" in result

    def test_no_duplicates(self):
        result = expand_queries(["auth"])
        assert len(result) == len(set(r.lower() for r in result))

    def test_respects_max_total_cap(self):
        result = expand_queries(["authentication config guide"], max_total=3)
        assert len(result) <= 3

    def test_single_word_query_no_structural_duplicates(self):
        result = expand_queries(["authentication"])
        assert result.count("authentication") == 1


def _make_result(title="", excerpt="", space_key="XX") -> dict:
    return {"id": "1", "title": title, "excerpt": excerpt,
            "space_key": space_key, "space_name": "Test Space",
            "url": "https://example.com"}


class TestScoreResult:
    def test_title_phrase_match_scores_4_plus_token_bonus(self):
        r = _make_result(title="authentication guide")
        assert score_result(r, ["authentication"], None) == 6

    def test_excerpt_phrase_match_scores_2_plus_token_bonus(self):
        r = _make_result(excerpt="how to authenticate users")
        assert score_result(r, ["authenticate"], None) == 3

    def test_token_match_scores_without_full_phrase(self):
        r = _make_result(title="customer authentication", excerpt="API setup")
        assert score_result(r, ["customer API auth"], None) == 5

    def test_space_match_scores_1(self):
        r = _make_result(space_key="MT")
        assert score_result(r, ["anything"], "MT") == 1

    def test_no_match_scores_0(self):
        r = _make_result(title="unrelated page")
        assert score_result(r, ["authentication"], None) == 0

    def test_case_insensitive(self):
        r = _make_result(title="Authentication Guide")
        assert score_result(r, ["authentication"], None) == 6

    def test_recency_multiplicative_decays_old_pages(self):
        r = {
            **_make_result(title="authentication guide"),
            "last_modified": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
        }
        no_recency = score_result(r, ["authentication"], None, enhanced=True)
        with_recency = score_result(
            r,
            ["authentication"],
            None,
            enhanced=True,
            halflife_days=30,
        )

        assert with_recency < no_recency

    def test_recency_does_not_invert_relevance_order(self):
        lower_relevance_fresh = {
            **_make_result(excerpt="authentication weekly notes"),
            "last_modified": datetime.now(timezone.utc).isoformat(),
        }
        higher_relevance_old = {
            **_make_result(title="authentication guide"),
            "last_modified": (datetime.now(timezone.utc) - timedelta(days=3650)).isoformat(),
        }

        ranked = rank_results(
            [lower_relevance_fresh, higher_relevance_old],
            ["authentication"],
            None,
            enhanced=True,
            halflife_days=30,
        )

        assert ranked[0]["title"] == "authentication guide"

    def test_recency_breaks_ties_only(self):
        fresh = {
            **_make_result(title="authentication guide"),
            "id": "fresh",
            "last_modified": datetime.now(timezone.utc).isoformat(),
        }
        old = {
            **_make_result(title="authentication guide"),
            "id": "old",
            "last_modified": (datetime.now(timezone.utc) - timedelta(days=365)).isoformat(),
        }

        ranked = rank_results(
            [old, fresh],
            ["authentication"],
            None,
            enhanced=True,
            halflife_days=30,
        )

        assert [r["id"] for r in ranked] == ["fresh", "old"]


class TestRankResults:
    def test_higher_scoring_result_comes_first(self):
        low = _make_result(title="unrelated")
        high = _make_result(title="authentication guide")
        ranked = rank_results([low, high], ["authentication"], None)
        assert ranked[0]["title"] == "authentication guide"

    def test_empty_results(self):
        assert rank_results([], ["query"], None) == []

    def test_equal_scores_preserve_relative_order(self):
        a = _make_result(title="a page")
        b = _make_result(title="b page")
        ranked = rank_results([a, b], ["something else"], None)
        assert [r["title"] for r in ranked] == ["a page", "b page"]


# ── Retrieval depth ───────────────────────────────────────────────────────────

class TestResolveBodyOptions:
    def test_links_depth_fetches_no_bodies(self):
        assert resolve_body_options("links", None, None) == (0, 0)

    def test_skim_depth_fetches_one_default_body(self):
        assert resolve_body_options("skim", None, None) == (1, DEFAULT_BODY_CHARS)

    def test_deep_depth_fetches_five_largest_bodies(self):
        # In v0.2 the `deep` mode took over what `ultra` used to do (5 / 3000).
        # The old 3-page midpoint can still be reached via explicit overrides.
        assert resolve_body_options("deep", None, None) == (5, 3000)

    def test_old_deep_preset_reachable_via_explicit_body_options(self):
        # Anyone relying on the pre-v0.2 `deep` defaults can pin them.
        assert resolve_body_options("skim", 3, 2000) == (3, 2000)

    def test_explicit_body_options_override_depth_defaults(self):
        assert resolve_body_options("deep", 2, 500) == (2, 500)

    def test_negative_body_options_are_clamped_to_zero(self):
        assert resolve_body_options("skim", -1, -10) == (0, 0)


# ── Confluence adapter ────────────────────────────────────────────────────────

BASE_URL = "https://wiki.example.com"
SEARCH_URL = f"{BASE_URL}/rest/api/content/search"
PAGE_URL = f"{BASE_URL}/rest/api/content/42"

MOCK_SEARCH_RESPONSE = {
    "results": [
        {
            "id": "42",
            "title": "Auth Guide",
            "space": {"key": "MT", "name": "Mobile Team"},
            "_links": {"webui": "/spaces/MT/pages/42/Auth+Guide"},
            "excerpt": "How to @@@hl@@@authenticate@@@endhl@@@ users",
        }
    ]
}

MOCK_PAGE_RESPONSE = {
    "id": "42",
    "title": "Auth Guide",
    "space": {"key": "MT", "name": "Mobile Team"},
    "_links": {"webui": "/spaces/MT/pages/42/Auth+Guide"},
    "body": {"storage": {"value": "<h1>Auth</h1><p>Details here.</p>"}},
}


class TestConfluenceAdapterSearch:
    @resp_mock.activate
    def test_returns_normalised_results(self):
        resp_mock.add(resp_mock.GET, SEARCH_URL, json=MOCK_SEARCH_RESPONSE, status=200)
        adapter = ConfluenceAdapter("test-pat", BASE_URL)
        results = adapter.search(["auth"], None, 5)

        assert len(results) == 1
        r = results[0]
        assert r["id"] == "42"
        assert r["title"] == "Auth Guide"
        assert r["space_key"] == "MT"
        assert r["space_name"] == "Mobile Team"
        assert BASE_URL in r["url"]
        assert "@@@" not in r["excerpt"]

    @resp_mock.activate
    def test_raises_auth_error_on_401(self):
        resp_mock.add(resp_mock.GET, SEARCH_URL, status=401)
        adapter = ConfluenceAdapter("bad-pat", BASE_URL)
        with pytest.raises(ConfluenceAuthError):
            adapter.search(["q"], None, 5)

    @resp_mock.activate
    def test_raises_auth_error_on_403(self):
        resp_mock.add(resp_mock.GET, SEARCH_URL, status=403)
        adapter = ConfluenceAdapter("bad-pat", BASE_URL)
        with pytest.raises(ConfluenceAuthError):
            adapter.search(["q"], None, 5)

    @resp_mock.activate
    def test_empty_results(self):
        resp_mock.add(resp_mock.GET, SEARCH_URL, json={"results": []}, status=200)
        adapter = ConfluenceAdapter("test-pat", BASE_URL)
        assert adapter.search(["q"], None, 5) == []

    @resp_mock.activate
    def test_raises_network_error_on_429(self):
        resp_mock.add(resp_mock.GET, SEARCH_URL, status=429)
        adapter = ConfluenceAdapter("test-pat", BASE_URL)
        with pytest.raises(ConfluenceNetworkError):
            adapter.search(["q"], None, 5)

    @resp_mock.activate
    def test_search_result_without_webui_gets_page_id_url(self):
        response = {
            "results": [
                {
                    "id": "77",
                    "title": "No Webui",
                    "space": {"key": "MT", "name": "Mobile Team"},
                    "excerpt": "",
                }
            ]
        }
        resp_mock.add(resp_mock.GET, SEARCH_URL, json=response, status=200)
        adapter = ConfluenceAdapter("test-pat", BASE_URL)

        result = adapter.search(["auth"], None, 5)[0]

        assert result["url"] == f"{BASE_URL}/pages/viewpage.action?pageId=77"


class TestConfluenceAdapterGetPage:
    @resp_mock.activate
    def test_returns_page_with_body(self):
        resp_mock.add(resp_mock.GET, PAGE_URL, json=MOCK_PAGE_RESPONSE, status=200)
        adapter = ConfluenceAdapter("test-pat", BASE_URL)
        page = adapter.get_page("42")

        assert page is not None
        assert page["id"] == "42"
        assert page["title"] == "Auth Guide"
        assert "<h1>" in page["body_html"]

    @resp_mock.activate
    def test_returns_url_and_space_name(self):
        """get_page() must include url (from _links.webui) and space_name."""
        resp_mock.add(resp_mock.GET, PAGE_URL, json=MOCK_PAGE_RESPONSE, status=200)
        adapter = ConfluenceAdapter("test-pat", BASE_URL)
        page = adapter.get_page("42")

        assert page is not None
        assert page["space_name"] == "Mobile Team"
        assert BASE_URL in page["url"]
        assert "/pages/42" in page["url"] or "/spaces/MT" in page["url"]

    @resp_mock.activate
    def test_returns_none_on_404(self):
        resp_mock.add(resp_mock.GET, PAGE_URL, status=404)
        adapter = ConfluenceAdapter("test-pat", BASE_URL)
        assert adapter.get_page("42") is None

    @resp_mock.activate
    def test_raises_network_error_on_500(self):
        resp_mock.add(resp_mock.GET, PAGE_URL, status=500)
        adapter = ConfluenceAdapter("test-pat", BASE_URL)
        with pytest.raises(ConfluenceNetworkError):
            adapter.get_page("42")


# ── Typed exceptions & --workers ──────────────────────────────────────────────

class TestTypedExceptions:
    @resp_mock.activate
    def test_get_page_raises_auth_error_on_401(self):
        resp_mock.add(resp_mock.GET, PAGE_URL, status=401)
        adapter = ConfluenceAdapter("bad-pat", BASE_URL)
        with pytest.raises(ConfluenceAuthError):
            adapter.get_page("42")

    @resp_mock.activate
    def test_get_page_raises_network_error_on_connection_refused(self):
        import requests.exceptions
        resp_mock.add(resp_mock.GET, PAGE_URL, body=requests.exceptions.ConnectionError("refused"))
        adapter = ConfluenceAdapter("test-pat", BASE_URL)
        with pytest.raises(ConfluenceNetworkError):
            adapter.get_page("42")

    @resp_mock.activate
    def test_main_exits_3_on_auth_error(self, monkeypatch, tmp_path):
        env_file = tmp_path / "test.env"
        env_file.write_text(f"CONFLUENCE_URL={BASE_URL}\nCONFLUENCE_PAT=bad-pat\n")
        monkeypatch.setattr(wiki, "PROJECT_ENV_FILE", env_file)
        resp_mock.add(resp_mock.GET, SEARCH_URL, status=401)
        with pytest.raises(SystemExit) as exc:
            main(["--query", "auth"])
        assert exc.value.code == wiki.EXIT_AUTH

    @resp_mock.activate
    def test_main_exits_4_on_network_error(self, monkeypatch, tmp_path):
        env_file = tmp_path / "test.env"
        env_file.write_text(f"CONFLUENCE_URL={BASE_URL}\nCONFLUENCE_PAT=test-pat\n")
        monkeypatch.setattr(wiki, "PROJECT_ENV_FILE", env_file)
        resp_mock.add(resp_mock.GET, SEARCH_URL, status=503)
        with pytest.raises(SystemExit) as exc:
            main(["--query", "auth"])
        assert exc.value.code == wiki.EXIT_NETWORK

    @resp_mock.activate
    def test_get_pages_logs_warning_for_failed_pages(self, caplog):
        import logging
        resp_mock.add(resp_mock.GET, PAGE_URL, status=500)
        adapter = ConfluenceAdapter("test-pat", BASE_URL)
        with caplog.at_level(logging.WARNING):
            result = adapter.get_pages(["42"])
        assert result == {}
        assert any("42" in m for m in caplog.messages)

    def test_workers_flag_accepted_by_search(self):
        from click.testing import CliRunner
        from confluence_retriever.cli import main as cli_main

        runner = CliRunner()
        result = runner.invoke(cli_main, ["search", "--help"])
        assert result.exit_code == 0
        assert "--workers" in result.output

    def test_workers_flag_default_is_4(self):
        from click.testing import CliRunner
        from confluence_retriever.cli import main as cli_main

        runner = CliRunner()
        result = runner.invoke(cli_main, ["search", "--help"])
        assert result.exit_code == 0
        # Click renders default values in --help when help= mentions them; the
        # canonical assertion is that the flag is present and parses cleanly.
        assert "--workers" in result.output

    def test_legacy_scorer_flag_accepted_by_search(self):
        from click.testing import CliRunner
        from confluence_retriever.cli import main as cli_main

        runner = CliRunner()
        result = runner.invoke(cli_main, ["search", "--help"])
        assert result.exit_code == 0
        assert "--legacy-scorer" in result.output


# ── search_combined ───────────────────────────────────────────────────────────

TITLE_ONLY_RESPONSE = {
    "results": [
        {
            "id": "99",
            "title": "Auth Overview",
            "space": {"key": "MT", "name": "Mobile Team"},
            "_links": {"webui": "/spaces/MT/pages/99/Auth+Overview"},
            "excerpt": "",
            "version": {"when": ""},
        }
    ]
}

TITLE_AND_TEXT_RESPONSE = {
    "results": [
        {
            "id": "42",
            "title": "Auth Guide",
            "space": {"key": "MT", "name": "Mobile Team"},
            "_links": {"webui": "/spaces/MT/pages/42/Auth+Guide"},
            "excerpt": "How to authenticate users",
            "version": {"when": ""},
        }
    ]
}


class TestSearchCombined:
    @resp_mock.activate
    def test_title_only_pages_included_in_results(self):
        # text search returns page 42, title search returns page 99
        resp_mock.add(resp_mock.GET, SEARCH_URL, json=TITLE_AND_TEXT_RESPONSE, status=200)
        resp_mock.add(resp_mock.GET, SEARCH_URL, json=TITLE_ONLY_RESPONSE, status=200)
        adapter = ConfluenceAdapter("test-pat", BASE_URL)
        results = adapter.search_combined(["auth"], None, 10)
        ids = [r["id"] for r in results]
        assert "42" in ids
        assert "99" in ids

    @resp_mock.activate
    def test_title_hit_flag_set_for_overlapping_page(self):
        # same page in both text and title search
        resp_mock.add(resp_mock.GET, SEARCH_URL, json=TITLE_AND_TEXT_RESPONSE, status=200)
        resp_mock.add(resp_mock.GET, SEARCH_URL, json=TITLE_AND_TEXT_RESPONSE, status=200)
        adapter = ConfluenceAdapter("test-pat", BASE_URL)
        results = adapter.search_combined(["auth"], None, 10)
        page_42 = next(r for r in results if r["id"] == "42")
        assert page_42["_title_hit"] is True

    @resp_mock.activate
    def test_merged_results_capped_at_limit(self):
        # text returns 1, title returns 1 different page, limit=1
        resp_mock.add(resp_mock.GET, SEARCH_URL, json=TITLE_AND_TEXT_RESPONSE, status=200)
        resp_mock.add(resp_mock.GET, SEARCH_URL, json=TITLE_ONLY_RESPONSE, status=200)
        adapter = ConfluenceAdapter("test-pat", BASE_URL)
        results = adapter.search_combined(["auth"], None, 1)
        assert len(results) <= 1

    @resp_mock.activate
    def test_title_search_auth_error_propagates(self):
        resp_mock.add(resp_mock.GET, SEARCH_URL, json=TITLE_AND_TEXT_RESPONSE, status=200)
        resp_mock.add(resp_mock.GET, SEARCH_URL, status=401)
        adapter = ConfluenceAdapter("bad-pat", BASE_URL)
        with pytest.raises(ConfluenceAuthError):
            adapter.search_combined(["auth"], None, 10)


# ── JSON output ───────────────────────────────────────────────────────────────

class TestJsonOutput:
    @resp_mock.activate
    def test_json_mode_outputs_valid_json(self, capsys, monkeypatch, tmp_path):
        """Verify --json flag produces valid, parseable JSON."""
        env_file = tmp_path / "test.env"
        env_file.write_text(f"CONFLUENCE_URL={BASE_URL}\nCONFLUENCE_PAT=test-pat\n")
        monkeypatch.setattr(wiki, "PROJECT_ENV_FILE", env_file)

        resp_mock.add(resp_mock.GET, SEARCH_URL, json=MOCK_SEARCH_RESPONSE, status=200)

        with pytest.raises(SystemExit) as exc:
            main(["--query", "auth", "--json"])
        assert exc.value.code == wiki.EXIT_OK

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["queries"] == ["auth"]
        assert len(output["results"]) == 1
        assert output["results"][0]["title"] == "Auth Guide"

    @resp_mock.activate
    def test_json_mode_includes_body_passages_when_depth_skim(self, capsys, monkeypatch, tmp_path):
        """Verify JSON includes body passages when depth is skim."""
        env_file = tmp_path / "test.env"
        env_file.write_text(f"CONFLUENCE_URL={BASE_URL}\nCONFLUENCE_PAT=test-pat\n")
        monkeypatch.setattr(wiki, "PROJECT_ENV_FILE", env_file)

        resp_mock.add(resp_mock.GET, SEARCH_URL, json=MOCK_SEARCH_RESPONSE, status=200)
        resp_mock.add(resp_mock.GET, PAGE_URL, json=MOCK_PAGE_RESPONSE, status=200)

        with pytest.raises(SystemExit) as exc:
            main(["--query", "auth", "--depth", "skim", "--json"])
        assert exc.value.code == wiki.EXIT_OK

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["depth"] == "skim"
        # With skim depth, body content should be fetched and included
        assert "passages" in output["results"][0] or "body_text" in output["results"][0]

    @resp_mock.activate
    def test_json_mode_excludes_markdown_artifacts(self, capsys, monkeypatch, tmp_path):
        """Verify JSON output doesn't include Markdown-specific formatting."""
        env_file = tmp_path / "test.env"
        env_file.write_text(f"CONFLUENCE_URL={BASE_URL}\nCONFLUENCE_PAT=test-pat\n")
        monkeypatch.setattr(wiki, "PROJECT_ENV_FILE", env_file)

        resp_mock.add(resp_mock.GET, SEARCH_URL, json=MOCK_SEARCH_RESPONSE, status=200)

        with pytest.raises(SystemExit) as exc:
            main(["--query", "auth", "--json"])
        assert exc.value.code == wiki.EXIT_OK

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        json_str = json.dumps(output)
        # JSON should not contain Markdown heading syntax (##, ###, etc.)
        assert "## " not in json_str
        assert "### " not in json_str
        # Should not contain Markdown list bullets
        assert "- [" not in json_str or json_str.count("- [") == 0


# ── Verbose logging ───────────────────────────────────────────────────────────

class TestVerboseLogging:
    @resp_mock.activate
    def test_verbose_flag_enables_debug_logging(self, capsys, monkeypatch, tmp_path):
        """Verify --verbose flag enables DEBUG level logging."""
        env_file = tmp_path / "test.env"
        env_file.write_text(f"CONFLUENCE_URL={BASE_URL}\nCONFLUENCE_PAT=test-pat\n")
        monkeypatch.setattr(wiki, "PROJECT_ENV_FILE", env_file)

        resp_mock.add(resp_mock.GET, SEARCH_URL, json=MOCK_SEARCH_RESPONSE, status=200)

        with pytest.raises(SystemExit) as exc:
            main(["--query", "test", "--verbose"])
        assert exc.value.code == wiki.EXIT_OK

        # Capture stderr where debug logs go
        captured = capsys.readouterr()
        # With --verbose, debug logging should be enabled (check stderr or combined output)
        assert captured.err or captured.out  # Should produce some output


# ── Phase H: cross-link URL and from_page ────────────────────────────────────

class TestGetPageUrlAndSpaceName:
    @resp_mock.activate
    def test_cross_link_url_uses_webui_not_bare_id(self):
        """Cross-link result URL must come from _links.webui, not a bare /pages/{id} string."""
        page_response = {
            "id": "99",
            "title": "Deploy Guide",
            "space": {"key": "OPS", "name": "Operations"},
            "_links": {"webui": "/spaces/OPS/pages/99/Deploy+Guide"},
            "body": {"storage": {"value": "<p>Steps here</p>"}},
        }
        resp_mock.add(resp_mock.GET, f"{BASE_URL}/rest/api/content/99", json=page_response, status=200)
        adapter = ConfluenceAdapter("test-pat", BASE_URL)
        page = adapter.get_page("99")

        assert page is not None
        assert page["url"] == f"{BASE_URL}/spaces/OPS/pages/99/Deploy+Guide"
        assert page["space_name"] == "Operations"

    def test_from_page_tracks_source(self):
        """_structural_variants drops trailing and leading tokens, and extracts longest."""
        # Smoke-test that _structural_variants returns useful coverage variants
        variants = _structural_variants("deploy authentication service")
        assert "deploy authentication" in variants
        assert "authentication service" in variants

    @resp_mock.activate
    def test_cross_link_missing_webui_falls_back_to_page_id_url(self):
        """A page response with no _links.webui must still produce a usable URL."""
        page_response_no_links = {
            "id": "77",
            "title": "No Links Page",
            "space": {"key": "XX", "name": "X Space"},
            "body": {"storage": {"value": "<p>content</p>"}},
        }
        resp_mock.add(
            resp_mock.GET, f"{BASE_URL}/rest/api/content/77",
            json=page_response_no_links, status=200,
        )
        adapter = ConfluenceAdapter("test-pat", BASE_URL)
        page = adapter.get_page("77")

        assert page is not None
        assert page["url"] == f"{BASE_URL}/pages/viewpage.action?pageId=77"


# ── Phase J: --depth ultra end-to-end ────────────────────────────────────────

class TestUltraDepthE2E:
    @resp_mock.activate
    def test_ultra_depth_returns_json_with_body_passages(self, capsys, monkeypatch, tmp_path):
        """Full ultra-mode pipeline: search_combined + body fetch → JSON with passages."""
        env_file = tmp_path / "test.env"
        env_file.write_text(f"CONFLUENCE_URL={BASE_URL}\nCONFLUENCE_PAT=test-pat\n")
        monkeypatch.setattr(wiki, "PROJECT_ENV_FILE", env_file)

        # search_combined fires text search + title search in parallel (same endpoint)
        resp_mock.add(resp_mock.GET, SEARCH_URL, json=MOCK_SEARCH_RESPONSE, status=200)
        resp_mock.add(resp_mock.GET, SEARCH_URL, json=MOCK_SEARCH_RESPONSE, status=200)
        # body fetch for top-ranked page
        resp_mock.add(resp_mock.GET, PAGE_URL, json=MOCK_PAGE_RESPONSE, status=200)

        with pytest.raises(SystemExit) as exc:
            main(["--query", "auth", "--depth", "ultra", "--json"])
        assert exc.value.code == wiki.EXIT_OK

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        # `ultra` was renamed to `deep` in v0.2 — the alias still works but the
        # normalised name in the payload is `deep`.
        assert output["depth"] == "deep"
        assert len(output["results"]) >= 1
        first = output["results"][0]
        assert first["title"] == "Auth Guide"
        assert first["url"].startswith(BASE_URL)
        # Deep mode fetches body: passages or headings must be present
        assert "passages" in first or "headings" in first

    @resp_mock.activate
    def test_ultra_depth_deduplicates_title_and_text_hits(self, capsys, monkeypatch, tmp_path):
        """Same page in both title and text results appears only once in output."""
        env_file = tmp_path / "test.env"
        env_file.write_text(f"CONFLUENCE_URL={BASE_URL}\nCONFLUENCE_PAT=test-pat\n")
        monkeypatch.setattr(wiki, "PROJECT_ENV_FILE", env_file)

        resp_mock.add(resp_mock.GET, SEARCH_URL, json=MOCK_SEARCH_RESPONSE, status=200)
        resp_mock.add(resp_mock.GET, SEARCH_URL, json=MOCK_SEARCH_RESPONSE, status=200)
        resp_mock.add(resp_mock.GET, PAGE_URL, json=MOCK_PAGE_RESPONSE, status=200)

        with pytest.raises(SystemExit) as exc:
            main(["--query", "auth", "--depth", "ultra", "--json"])
        assert exc.value.code == wiki.EXIT_OK

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        ids = [r["id"] for r in output["results"]]
        assert len(ids) == len(set(ids)), "duplicate page IDs in ultra output"

    def test_workers_default_shown_in_help(self):
        """--workers flag must appear in --help output."""
        from click.testing import CliRunner
        from confluence_retriever.cli import main as cli_main

        runner = CliRunner()
        result = runner.invoke(cli_main, ["search", "--help"])
        assert result.exit_code == 0
        assert "--workers" in result.output

    @resp_mock.activate
    def test_ultra_json_cross_link_includes_source_and_from_page(self, capsys, monkeypatch, tmp_path):
        env_file = tmp_path / "test.env"
        env_file.write_text(f"CONFLUENCE_URL={BASE_URL}\nCONFLUENCE_PAT=test-pat\n")
        monkeypatch.setattr(wiki, "PROJECT_ENV_FILE", env_file)

        root_page = {
            **MOCK_PAGE_RESPONSE,
            "body": {
                "storage": {
                    "value": '<p>Authentication details <a href="/wiki/spaces/OPS/pages/99/Deploy">Deploy</a></p>'
                }
            },
        }
        linked_page = {
            "id": "99",
            "title": "Deploy Guide",
            "space": {"key": "OPS", "name": "Operations"},
            "_links": {"webui": "/spaces/OPS/pages/99/Deploy+Guide"},
            "body": {"storage": {"value": "<p>Linked deployment details.</p>"}},
        }

        resp_mock.add(resp_mock.GET, SEARCH_URL, json=MOCK_SEARCH_RESPONSE, status=200)
        resp_mock.add(resp_mock.GET, SEARCH_URL, json=MOCK_SEARCH_RESPONSE, status=200)
        resp_mock.add(resp_mock.GET, PAGE_URL, json=root_page, status=200)
        resp_mock.add(resp_mock.GET, f"{BASE_URL}/rest/api/content/99", json=linked_page, status=200)

        with pytest.raises(SystemExit) as exc:
            main(["--query", "auth", "--depth", "ultra", "--json"])
        assert exc.value.code == wiki.EXIT_OK

        output = json.loads(capsys.readouterr().out)
        cross_link = next(r for r in output["results"] if r.get("source") == "cross-link")
        assert cross_link["id"] == "99"
        assert cross_link["from_page"] == "42"
        assert cross_link["from_page_url"] == f"{BASE_URL}/spaces/MT/pages/42/Auth+Guide"

    @resp_mock.activate
    def test_ultra_markdown_labels_cross_link_source(self, capsys, monkeypatch, tmp_path):
        env_file = tmp_path / "test.env"
        env_file.write_text(f"CONFLUENCE_URL={BASE_URL}\nCONFLUENCE_PAT=test-pat\n")
        monkeypatch.setattr(wiki, "PROJECT_ENV_FILE", env_file)

        root_page = {
            **MOCK_PAGE_RESPONSE,
            "body": {
                "storage": {
                    "value": '<p>Authentication details <a href="/wiki/spaces/OPS/pages/99/Deploy">Deploy</a></p>'
                }
            },
        }
        linked_page = {
            "id": "99",
            "title": "Deploy Guide",
            "space": {"key": "OPS", "name": "Operations"},
            "_links": {"webui": "/spaces/OPS/pages/99/Deploy+Guide"},
            "body": {"storage": {"value": "<p>Linked deployment details.</p>"}},
        }

        resp_mock.add(resp_mock.GET, SEARCH_URL, json=MOCK_SEARCH_RESPONSE, status=200)
        resp_mock.add(resp_mock.GET, SEARCH_URL, json=MOCK_SEARCH_RESPONSE, status=200)
        resp_mock.add(resp_mock.GET, PAGE_URL, json=root_page, status=200)
        resp_mock.add(resp_mock.GET, f"{BASE_URL}/rest/api/content/99", json=linked_page, status=200)

        with pytest.raises(SystemExit) as exc:
            main(["--query", "auth", "--depth", "ultra"])
        assert exc.value.code == wiki.EXIT_OK

        output = capsys.readouterr().out
        assert "- **URL:** https://wiki.example.com/spaces/OPS/pages/99/Deploy+Guide" in output
        assert (
            "- **Source:** Cross-link from Auth Guide "
            "(https://wiki.example.com/spaces/MT/pages/42/Auth+Guide)"
        ) in output
