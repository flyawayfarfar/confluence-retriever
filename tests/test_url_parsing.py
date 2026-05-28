"""Tests for confluence_retriever.url_parsing."""

import pytest

from confluence_retriever.url_parsing import extract_page_id


class TestExtractPageId:
    def test_bare_numeric_id_passthrough(self):
        assert extract_page_id("12345") == "12345"

    def test_bare_numeric_id_with_whitespace(self):
        assert extract_page_id("  12345  ") == "12345"

    @pytest.mark.parametrize("url", [
        "https://wiki.example.com/spaces/MT/pages/12345/Auth+Guide",
        "https://wiki.example.com/spaces/MT/pages/12345",
        "/spaces/MT/pages/12345/Auth+Guide",
    ])
    def test_server_dc_spaces_pages_url(self, url):
        assert extract_page_id(url) == "12345"

    @pytest.mark.parametrize("url", [
        "https://example.atlassian.net/wiki/spaces/MT/pages/98765/Setup",
        "/wiki/spaces/MT/pages/98765",
    ])
    def test_cloud_wiki_spaces_pages_url(self, url):
        assert extract_page_id(url) == "98765"

    def test_legacy_viewpage_action(self):
        url = "https://wiki.example.com/pages/viewpage.action?pageId=42"
        assert extract_page_id(url) == "42"

    def test_legacy_details_path(self):
        url = "https://wiki.example.com/pages/viewpage/details/777"
        assert extract_page_id(url) == "777"

    def test_unrecognised_url_returns_none(self):
        assert extract_page_id("https://wiki.example.com/random/path") is None

    def test_non_url_non_numeric_returns_none(self):
        assert extract_page_id("not a url") is None

    def test_empty_string_returns_none(self):
        assert extract_page_id("") is None

    def test_pageid_with_non_numeric_value_returns_none(self):
        url = "https://wiki.example.com/pages/viewpage.action?pageId=abc"
        assert extract_page_id(url) is None
