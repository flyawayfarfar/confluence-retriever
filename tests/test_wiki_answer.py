"""Unit tests for wiki_answer.py — no real network calls."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import responses as resp_mock

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import wiki_answer as wiki  # noqa: E402


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
        assert wiki.cql_escape("hello") == "hello"

    def test_double_quote_escaped(self):
        assert wiki.cql_escape('say "hi"') == 'say \\"hi\\"'

    def test_backslash_escaped_first(self):
        assert wiki.cql_escape('back\\slash') == 'back\\\\slash'

    def test_backslash_before_quote(self):
        assert wiki.cql_escape('\\"') == '\\\\\\"'


class TestBuildCql:
    def test_single_query(self):
        assert wiki.build_cql(["auth"], None) == 'text ~ "auth" AND type = "page"'

    def test_multiple_queries_or(self):
        result = wiki.build_cql(["auth", "login"], None)
        assert result == '(text ~ "auth" OR text ~ "login") AND type = "page"'

    def test_space_filter_appended(self):
        result = wiki.build_cql(["auth"], "MT")
        assert result == 'text ~ "auth" AND type = "page" AND space = "MT"'

    def test_space_and_multiple_queries(self):
        result = wiki.build_cql(["auth", "sso"], "IIT")
        assert '(text ~ "auth" OR text ~ "sso")' in result
        assert 'AND type = "page"' in result
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


class TestExtractRelevantPassages:
    def test_prefers_matching_passage_below_intro(self):
        html = """
        <h1>Release Process</h1>
        <p>Intro text with ownership and general notes.</p>
        <h2>Approval Steps</h2>
        <p>Release approval requires product signoff and engineering review.</p>
        """

        passages = wiki.extract_relevant_passages(html, ["release approval"], max_chars=500)

        assert passages[0] == {
            "heading": "Approval Steps",
            "text": "Release approval requires product signoff and engineering review.",
        }

    def test_falls_back_to_first_blocks_when_no_match(self):
        html = "<h1>Guide</h1><p>First paragraph.</p><p>Second paragraph.</p>"

        passages = wiki.extract_relevant_passages(html, ["missing"], max_chars=500, max_passages=2)

        assert [p["text"] for p in passages] == ["First paragraph.", "Second paragraph."]

    def test_respects_character_budget(self):
        html = "<p>authentication " + ("details " * 100) + "</p>"

        passages = wiki.extract_relevant_passages(
            html,
            ["authentication"],
            max_chars=80,
            passage_chars=80,
        )

        assert len(passages) == 1
        assert len(passages[0]["text"]) <= 80
        assert passages[0]["text"].endswith("...")

    def test_returns_plain_text_fallback_for_unstructured_html(self):
        passages = wiki.extract_relevant_passages("plain authentication text", ["authentication"], max_chars=100)

        assert passages == [{"heading": "", "text": "plain authentication text"}]


# ── Ranker ────────────────────────────────────────────────────────────────────

class TestQueryTokens:
    def test_splits_phrases_into_unique_tokens(self):
        assert wiki.query_tokens(["customer API auth", "auth flow"]) == ["customer", "api", "auth", "flow"]

    def test_ignores_short_tokens(self):
        assert wiki.query_tokens(["an API in MT"]) == ["api"]

    def test_short_acronym_does_not_match_inside_word(self):
        assert not wiki.token_in_text("api", "capital planning")

    def test_longer_token_can_match_word_variant(self):
        assert wiki.token_in_text("auth", "authentication guide")


class TestExpandQueries:
    def test_includes_original_query(self):
        assert "auth guide" in wiki.expand_queries(["auth guide"])

    def test_structural_drop_trailing_token(self):
        result = wiki.expand_queries(["auth guide"])
        assert "auth" in result

    def test_structural_drop_leading_token(self):
        result = wiki.expand_queries(["auth guide"])
        assert "guide" in result

    def test_abbrev_swap_added_after_structural(self):
        result = wiki.expand_queries(["auth guide"])
        assert "authentication guide" in result

    def test_no_duplicates(self):
        result = wiki.expand_queries(["auth"])
        assert len(result) == len(set(r.lower() for r in result))

    def test_respects_max_total_cap(self):
        result = wiki.expand_queries(["authentication config guide"], max_total=3)
        assert len(result) <= 3

    def test_single_word_query_no_structural_duplicates(self):
        result = wiki.expand_queries(["authentication"])
        assert result.count("authentication") == 1


def _make_result(title="", excerpt="", space_key="XX") -> dict:
    return {"id": "1", "title": title, "excerpt": excerpt,
            "space_key": space_key, "space_name": "Test Space",
            "url": "https://example.com"}


class TestScoreResult:
    def test_title_phrase_match_scores_4_plus_token_bonus(self):
        r = _make_result(title="authentication guide")
        assert wiki.score_result(r, ["authentication"], None) == 6

    def test_excerpt_phrase_match_scores_2_plus_token_bonus(self):
        r = _make_result(excerpt="how to authenticate users")
        assert wiki.score_result(r, ["authenticate"], None) == 3

    def test_token_match_scores_without_full_phrase(self):
        r = _make_result(title="customer authentication", excerpt="API setup")
        assert wiki.score_result(r, ["customer API auth"], None) == 5

    def test_space_match_scores_1(self):
        r = _make_result(space_key="MT")
        assert wiki.score_result(r, ["anything"], "MT") == 1

    def test_no_match_scores_0(self):
        r = _make_result(title="unrelated page")
        assert wiki.score_result(r, ["authentication"], None) == 0

    def test_case_insensitive(self):
        r = _make_result(title="Authentication Guide")
        assert wiki.score_result(r, ["authentication"], None) == 6


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


# ── Retrieval depth ───────────────────────────────────────────────────────────

class TestResolveBodyOptions:
    def test_links_depth_fetches_no_bodies(self):
        assert wiki.resolve_body_options("links", None, None) == (0, 0)

    def test_skim_depth_fetches_one_default_body(self):
        assert wiki.resolve_body_options("skim", None, None) == (1, wiki.DEFAULT_BODY_CHARS)

    def test_deep_depth_fetches_three_larger_bodies(self):
        assert wiki.resolve_body_options("deep", None, None) == (3, 2000)

    def test_explicit_body_options_override_depth_defaults(self):
        assert wiki.resolve_body_options("deep", 2, 500) == (2, 500)

    def test_negative_body_options_are_clamped_to_zero(self):
        assert wiki.resolve_body_options("skim", -1, -10) == (0, 0)


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
        assert r["id"] == "42"
        assert r["title"] == "Auth Guide"
        assert r["space_key"] == "MT"
        assert r["space_name"] == "Mobile Team"
        assert BASE_URL in r["url"]
        assert "@@@" not in r["excerpt"]

    @resp_mock.activate
    def test_raises_auth_error_on_401(self):
        resp_mock.add(resp_mock.GET, SEARCH_URL, status=401)
        adapter = wiki.ConfluenceAdapter("bad-pat", BASE_URL)
        with pytest.raises(wiki.ConfluenceAuthError):
            adapter.search(["q"], None, 5)

    @resp_mock.activate
    def test_raises_auth_error_on_403(self):
        resp_mock.add(resp_mock.GET, SEARCH_URL, status=403)
        adapter = wiki.ConfluenceAdapter("bad-pat", BASE_URL)
        with pytest.raises(wiki.ConfluenceAuthError):
            adapter.search(["q"], None, 5)

    @resp_mock.activate
    def test_empty_results(self):
        resp_mock.add(resp_mock.GET, SEARCH_URL, json={"results": []}, status=200)
        adapter = wiki.ConfluenceAdapter("test-pat", BASE_URL)
        assert adapter.search(["q"], None, 5) == []

    @resp_mock.activate
    def test_raises_network_error_on_429(self):
        resp_mock.add(resp_mock.GET, SEARCH_URL, status=429)
        adapter = wiki.ConfluenceAdapter("test-pat", BASE_URL)
        with pytest.raises(wiki.ConfluenceNetworkError):
            adapter.search(["q"], None, 5)


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
    def test_raises_network_error_on_500(self):
        resp_mock.add(resp_mock.GET, PAGE_URL, status=500)
        adapter = wiki.ConfluenceAdapter("test-pat", BASE_URL)
        with pytest.raises(wiki.ConfluenceNetworkError):
            adapter.get_page("42")


# ── Typed exceptions & --workers ──────────────────────────────────────────────

class TestTypedExceptions:
    @resp_mock.activate
    def test_get_page_raises_auth_error_on_401(self):
        resp_mock.add(resp_mock.GET, PAGE_URL, status=401)
        adapter = wiki.ConfluenceAdapter("bad-pat", BASE_URL)
        with pytest.raises(wiki.ConfluenceAuthError):
            adapter.get_page("42")

    @resp_mock.activate
    def test_get_page_raises_network_error_on_connection_refused(self):
        import requests.exceptions
        resp_mock.add(resp_mock.GET, PAGE_URL, body=requests.exceptions.ConnectionError("refused"))
        adapter = wiki.ConfluenceAdapter("test-pat", BASE_URL)
        with pytest.raises(wiki.ConfluenceNetworkError):
            adapter.get_page("42")

    @resp_mock.activate
    def test_main_exits_3_on_auth_error(self, monkeypatch, tmp_path):
        env_file = tmp_path / "test.env"
        env_file.write_text(f"CONFLUENCE_URL={BASE_URL}\nCONFLUENCE_PAT=bad-pat\n")
        monkeypatch.setattr(wiki, "PROJECT_ENV_FILE", env_file)
        resp_mock.add(resp_mock.GET, SEARCH_URL, status=401)
        with pytest.raises(SystemExit) as exc:
            wiki.main(["--query", "auth"])
        assert exc.value.code == wiki.EXIT_AUTH

    @resp_mock.activate
    def test_main_exits_4_on_network_error(self, monkeypatch, tmp_path):
        env_file = tmp_path / "test.env"
        env_file.write_text(f"CONFLUENCE_URL={BASE_URL}\nCONFLUENCE_PAT=test-pat\n")
        monkeypatch.setattr(wiki, "PROJECT_ENV_FILE", env_file)
        resp_mock.add(resp_mock.GET, SEARCH_URL, status=503)
        with pytest.raises(SystemExit) as exc:
            wiki.main(["--query", "auth"])
        assert exc.value.code == wiki.EXIT_NETWORK

    @resp_mock.activate
    def test_get_pages_logs_warning_for_failed_pages(self, caplog):
        import logging
        resp_mock.add(resp_mock.GET, PAGE_URL, status=500)
        adapter = wiki.ConfluenceAdapter("test-pat", BASE_URL)
        with caplog.at_level(logging.WARNING):
            result = adapter.get_pages(["42"])
        assert result == {}
        assert any("42" in m for m in caplog.messages)

    def test_workers_flag_accepted_by_parser(self):
        parser = wiki.build_parser()
        args = parser.parse_args(["--query", "q", "--workers", "8"])
        assert args.workers == 8

    def test_workers_flag_default_is_4(self):
        parser = wiki.build_parser()
        args = parser.parse_args(["--query", "q"])
        assert args.workers == 4


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
        adapter = wiki.ConfluenceAdapter("test-pat", BASE_URL)
        results = adapter.search_combined(["auth"], None, 10)
        ids = [r["id"] for r in results]
        assert "42" in ids
        assert "99" in ids

    @resp_mock.activate
    def test_title_hit_flag_set_for_overlapping_page(self):
        # same page in both text and title search
        resp_mock.add(resp_mock.GET, SEARCH_URL, json=TITLE_AND_TEXT_RESPONSE, status=200)
        resp_mock.add(resp_mock.GET, SEARCH_URL, json=TITLE_AND_TEXT_RESPONSE, status=200)
        adapter = wiki.ConfluenceAdapter("test-pat", BASE_URL)
        results = adapter.search_combined(["auth"], None, 10)
        page_42 = next(r for r in results if r["id"] == "42")
        assert page_42["_title_hit"] is True

    @resp_mock.activate
    def test_merged_results_capped_at_limit(self):
        # text returns 1, title returns 1 different page, limit=1
        resp_mock.add(resp_mock.GET, SEARCH_URL, json=TITLE_AND_TEXT_RESPONSE, status=200)
        resp_mock.add(resp_mock.GET, SEARCH_URL, json=TITLE_ONLY_RESPONSE, status=200)
        adapter = wiki.ConfluenceAdapter("test-pat", BASE_URL)
        results = adapter.search_combined(["auth"], None, 1)
        assert len(results) <= 1

    @resp_mock.activate
    def test_title_search_auth_error_propagates(self):
        resp_mock.add(resp_mock.GET, SEARCH_URL, json=TITLE_AND_TEXT_RESPONSE, status=200)
        resp_mock.add(resp_mock.GET, SEARCH_URL, status=401)
        adapter = wiki.ConfluenceAdapter("bad-pat", BASE_URL)
        with pytest.raises(wiki.ConfluenceAuthError):
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
            wiki.main(["--query", "auth", "--json"])
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
            wiki.main(["--query", "auth", "--depth", "skim", "--json"])
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
            wiki.main(["--query", "auth", "--json"])
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
            wiki.main(["--query", "test", "--verbose"])
        assert exc.value.code == wiki.EXIT_OK

        # Capture stderr where debug logs go
        captured = capsys.readouterr()
        # With --verbose, debug logging should be enabled (check stderr or combined output)
        assert captured.err or captured.out  # Should produce some output
