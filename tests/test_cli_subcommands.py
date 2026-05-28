"""End-to-end CLI tests for the Click-based subcommands.

All HTTP is mocked via the ``responses`` library; no real network traffic.
"""

import json
import os
import stat
from pathlib import Path

import pytest
import responses as resp_mock
from click.testing import CliRunner

from confluence_retriever import config as cr_config
from confluence_retriever.cli import main as cli_main


BASE_URL = "https://wiki.example.com"
SEARCH_URL = f"{BASE_URL}/rest/api/content/search"
PAGE_URL_RE = f"{BASE_URL}/rest/api/content/12345"
CHILDREN_URL = f"{BASE_URL}/rest/api/content/12345/child/page"


def _seed_env(tmp_path, monkeypatch) -> Path:
    env_file = tmp_path / "test.env"
    env_file.write_text(f"CONFLUENCE_URL={BASE_URL}\nCONFLUENCE_PAT=test-pat\n")
    monkeypatch.setattr(cr_config, "PROJECT_ENV_FILE", env_file)
    monkeypatch.setattr(cr_config, "USER_ENV_FILE", tmp_path / "missing.env")
    return env_file


PAGE_RESPONSE = {
    "id": "12345",
    "title": "Auth Guide",
    "status": "current",
    "space": {"key": "MT", "name": "Mobile Team"},
    "version": {"number": 7, "when": "2026-05-01T10:00:00.000Z"},
    "body": {"storage": {"value": "<h1>Auth Guide</h1><p>Use the PAT.</p>"}},
    "_links": {"webui": "/spaces/MT/pages/12345/Auth+Guide"},
    "children": {
        "attachment": {
            "results": [
                {
                    "id": "att-1",
                    "title": "diagram.png",
                    "extensions": {"fileSize": 2048},
                    "metadata": {"mediaType": "image/png"},
                    "_links": {"download": "/download/attachments/12345/diagram.png"},
                }
            ]
        }
    },
}

CHILDREN_RESPONSE = {
    "results": [
        {
            "id": "999",
            "title": "Sub Page A",
            "space": {"key": "MT", "name": "Mobile Team"},
            "status": "current",
            "version": {"when": "2026-04-30T00:00:00.000Z"},
            "_links": {"webui": "/spaces/MT/pages/999/Sub+Page+A"},
        }
    ],
    "size": 1,
    "limit": 50,
}


# ── read ────────────────────────────────────────────────────────────────────

class TestReadCommand:
    @resp_mock.activate
    def test_read_by_id_markdown(self, tmp_path, monkeypatch):
        _seed_env(tmp_path, monkeypatch)
        resp_mock.add(resp_mock.GET, PAGE_URL_RE, json=PAGE_RESPONSE, status=200)

        runner = CliRunner()
        result = runner.invoke(cli_main, ["read", "12345", "--format", "markdown"])
        assert result.exit_code == 0, result.output
        assert "title: Auth Guide" in result.output
        assert "page_id: 12345" in result.output
        # Body should be rendered (markdownify path falls back to text if not installed)
        assert "Auth Guide" in result.output
        # Attachment listed
        assert "diagram.png" in result.output

    @resp_mock.activate
    def test_read_by_url(self, tmp_path, monkeypatch):
        _seed_env(tmp_path, monkeypatch)
        resp_mock.add(resp_mock.GET, PAGE_URL_RE, json=PAGE_RESPONSE, status=200)

        runner = CliRunner()
        url = f"{BASE_URL}/pages/viewpage.action?pageId=12345"
        result = runner.invoke(cli_main, ["read", url])
        assert result.exit_code == 0, result.output
        assert "Auth Guide" in result.output

    @resp_mock.activate
    def test_read_json_includes_body_html(self, tmp_path, monkeypatch):
        _seed_env(tmp_path, monkeypatch)
        resp_mock.add(resp_mock.GET, PAGE_URL_RE, json=PAGE_RESPONSE, status=200)

        runner = CliRunner()
        result = runner.invoke(cli_main, ["read", "12345", "--format", "json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["id"] == "12345"
        assert payload["title"] == "Auth Guide"
        assert "<h1>Auth Guide</h1>" in payload["body_html"]
        assert len(payload["attachments"]) == 1

    @resp_mock.activate
    def test_read_no_attachments_flag(self, tmp_path, monkeypatch):
        _seed_env(tmp_path, monkeypatch)
        resp_mock.add(resp_mock.GET, PAGE_URL_RE, json=PAGE_RESPONSE, status=200)

        runner = CliRunner()
        result = runner.invoke(
            cli_main, ["read", "12345", "--format", "json", "--no-attachments"]
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert "attachments" not in payload

    def test_read_invalid_page_ref_exits_2(self, tmp_path, monkeypatch):
        _seed_env(tmp_path, monkeypatch)
        runner = CliRunner()
        result = runner.invoke(cli_main, ["read", "not-a-url-or-id"])
        assert result.exit_code == 2
        assert "could not extract" in result.output


# ── info ────────────────────────────────────────────────────────────────────

class TestInfoCommand:
    @resp_mock.activate
    def test_info_returns_metadata_only(self, tmp_path, monkeypatch):
        _seed_env(tmp_path, monkeypatch)
        # info() requests without body.storage; mock the same endpoint
        info_response = {k: v for k, v in PAGE_RESPONSE.items() if k != "body"}
        resp_mock.add(resp_mock.GET, PAGE_URL_RE, json=info_response, status=200)

        runner = CliRunner()
        result = runner.invoke(cli_main, ["info", "12345", "--format", "json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["id"] == "12345"
        assert payload["title"] == "Auth Guide"
        assert "body_html" not in payload  # info never includes body

    @resp_mock.activate
    def test_info_markdown(self, tmp_path, monkeypatch):
        _seed_env(tmp_path, monkeypatch)
        info_response = {k: v for k, v in PAGE_RESPONSE.items() if k != "body"}
        resp_mock.add(resp_mock.GET, PAGE_URL_RE, json=info_response, status=200)

        runner = CliRunner()
        result = runner.invoke(cli_main, ["info", "12345"])
        assert result.exit_code == 0
        assert "Auth Guide" in result.output
        assert "Page ID:" in result.output


# ── children ────────────────────────────────────────────────────────────────

class TestChildrenCommand:
    @resp_mock.activate
    def test_children_markdown(self, tmp_path, monkeypatch):
        _seed_env(tmp_path, monkeypatch)
        resp_mock.add(resp_mock.GET, CHILDREN_URL, json=CHILDREN_RESPONSE, status=200)

        runner = CliRunner()
        result = runner.invoke(cli_main, ["children", "12345"])
        assert result.exit_code == 0
        assert "Sub Page A" in result.output
        assert "Showing 1/1" in result.output

    @resp_mock.activate
    def test_children_json(self, tmp_path, monkeypatch):
        _seed_env(tmp_path, monkeypatch)
        resp_mock.add(resp_mock.GET, CHILDREN_URL, json=CHILDREN_RESPONSE, status=200)

        runner = CliRunner()
        result = runner.invoke(cli_main, ["children", "12345", "--format", "json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["parent_id"] == "12345"
        assert len(payload["results"]) == 1
        assert payload["results"][0]["id"] == "999"
        assert payload["hasMore"] is False


# ── search --page-id fast path ──────────────────────────────────────────────

class TestSearchPageIdFastPath:
    @resp_mock.activate
    def test_page_id_url_skips_search(self, tmp_path, monkeypatch):
        _seed_env(tmp_path, monkeypatch)
        resp_mock.add(resp_mock.GET, PAGE_URL_RE, json=PAGE_RESPONSE, status=200)

        runner = CliRunner()
        url = f"{BASE_URL}/pages/viewpage.action?pageId=12345"
        result = runner.invoke(
            cli_main, ["search", "--page-id", url, "--depth", "skim", "--format", "json"]
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["results"][0]["id"] == "12345"
        # search endpoint must NOT have been called
        called_paths = [c.request.url for c in resp_mock.calls]
        assert not any("/search?" in url_ for url_ in called_paths)


# ── setup ───────────────────────────────────────────────────────────────────

class TestSetupCommand:
    def test_setup_refuses_when_not_a_tty(self, tmp_path, monkeypatch):
        # CliRunner pipes stdin → isatty() is False
        target = tmp_path / ".config" / "confluence-retriever" / ".env"
        monkeypatch.setattr(cr_config, "USER_ENV_FILE", target)
        # Also patch the cli module's reference
        from confluence_retriever import cli as cli_module
        monkeypatch.setattr(cli_module, "USER_ENV_FILE", target)

        runner = CliRunner()
        result = runner.invoke(cli_main, ["setup"], input="\n")
        assert result.exit_code == 2
        assert "interactive terminal" in result.output

    def test_setup_writes_env_with_correct_perms(self, tmp_path, monkeypatch):
        target = tmp_path / ".config" / "confluence-retriever" / ".env"
        from confluence_retriever import cli as cli_module
        monkeypatch.setattr(cli_module, "USER_ENV_FILE", target)
        monkeypatch.setattr(cli_module, "_stdin_is_tty", lambda: True)

        runner = CliRunner()
        result = runner.invoke(
            cli_main, ["setup"], input="https://wiki.example.com\nmy-secret-pat\n"
        )
        assert result.exit_code == 0, result.output
        assert target.exists()
        contents = target.read_text()
        assert "CONFLUENCE_URL=https://wiki.example.com" in contents
        assert "CONFLUENCE_PAT=my-secret-pat" in contents
        # Confirm 0600 perms on POSIX
        if os.name == "posix":
            mode = target.stat().st_mode & 0o777
            assert mode == 0o600, oct(mode)

    def test_setup_rejects_bad_url_scheme(self, tmp_path, monkeypatch):
        target = tmp_path / ".env"
        from confluence_retriever import cli as cli_module
        monkeypatch.setattr(cli_module, "USER_ENV_FILE", target)
        monkeypatch.setattr(cli_module, "_stdin_is_tty", lambda: True)

        runner = CliRunner()
        result = runner.invoke(cli_main, ["setup"], input="wiki.example.com\nfoo\n")
        assert result.exit_code == 2
        assert "must start with" in result.output


# ── doctor ──────────────────────────────────────────────────────────────────

class TestDoctorCommand:
    @resp_mock.activate
    def test_doctor_reports_ok_when_search_succeeds(self, tmp_path, monkeypatch):
        _seed_env(tmp_path, monkeypatch)
        resp_mock.add(
            resp_mock.GET, SEARCH_URL,
            json={"results": [{"id": "1", "title": "T", "space": {"key": "X", "name": "X"},
                              "_links": {"webui": "/"}, "version": {"when": ""}, "excerpt": ""}]},
            status=200,
        )

        runner = CliRunner()
        result = runner.invoke(cli_main, ["doctor"])
        assert result.exit_code == 0, result.output
        assert "All checks passed" in result.output

    @resp_mock.activate
    def test_doctor_fails_loudly_on_401(self, tmp_path, monkeypatch):
        _seed_env(tmp_path, monkeypatch)
        resp_mock.add(resp_mock.GET, SEARCH_URL, status=401)

        runner = CliRunner()
        result = runner.invoke(cli_main, ["doctor"])
        assert result.exit_code == 4
        assert "[fail] auth" in result.output


# ── --depth ultra → deep alias ──────────────────────────────────────────────

class TestDepthAlias:
    @resp_mock.activate
    def test_ultra_alias_warns_and_forwards(self, tmp_path, monkeypatch):
        _seed_env(tmp_path, monkeypatch)
        resp_mock.add(resp_mock.GET, SEARCH_URL, json={"results": []}, status=200)
        resp_mock.add(resp_mock.GET, SEARCH_URL, json={"results": []}, status=200)

        runner = CliRunner()
        result = runner.invoke(
            cli_main, ["search", "--query", "x", "--depth", "ultra"]
        )
        assert result.exit_code == 0, result.output
        assert "--depth ultra is deprecated" in result.output
