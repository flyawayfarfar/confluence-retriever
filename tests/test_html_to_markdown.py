"""Tests for the HTML → Markdown converter used by `confluence-search read`."""

import importlib
import sys

import pytest

from confluence_retriever import html_utils


# Skip the "with markdownify" tests when the optional dep is absent. The
# "without markdownify" test forces an ImportError via monkeypatching, so
# it runs regardless.

try:
    import markdownify  # noqa: F401
    HAS_MD = True
except ImportError:
    HAS_MD = False


@pytest.mark.skipif(not HAS_MD, reason="markdownify not installed")
class TestHtmlToMarkdownWithLibrary:
    def test_headings_become_atx(self):
        out = html_utils.html_to_markdown("<h1>Title</h1><h2>Sub</h2>")
        assert "# Title" in out
        assert "## Sub" in out

    def test_unordered_list(self):
        out = html_utils.html_to_markdown("<ul><li>a</li><li>b</li></ul>")
        # markdownify uses either - or * for list bullets depending on version
        assert ("- a" in out or "* a" in out)
        assert ("- b" in out or "* b" in out)

    def test_inline_link_preserved(self):
        out = html_utils.html_to_markdown('<p>see <a href="https://x.example">docs</a></p>')
        assert "[docs](https://x.example)" in out

    def test_code_block_preserved(self):
        out = html_utils.html_to_markdown("<pre><code>hello()</code></pre>")
        assert "hello()" in out

    def test_blockquote(self):
        out = html_utils.html_to_markdown("<blockquote><p>quoted</p></blockquote>")
        assert "> quoted" in out

    def test_malformed_html_does_not_crash(self):
        out = html_utils.html_to_markdown("<p>unclosed <strong>tag")
        assert "unclosed" in out
        assert "tag" in out


class TestHtmlToMarkdownFallback:
    def test_warns_and_falls_back_when_markdownify_missing(self, monkeypatch, caplog):
        """When markdownify is not importable the function must fall back, not raise."""
        # Force ImportError on the in-function import by stubbing the module.
        monkeypatch.setitem(sys.modules, "markdownify", None)

        import logging
        with caplog.at_level(logging.WARNING):
            out = html_utils.html_to_markdown("<p>hello <b>world</b></p>")

        assert "hello world" in out
        assert any("markdownify" in m for m in caplog.messages)
