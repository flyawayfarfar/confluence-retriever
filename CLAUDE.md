# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start

### Environment Setup

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure credentials
cp .env.example ~/.config/confluence-retriever/.env
chmod 600 ~/.config/confluence-retriever/.env
# Edit ~/.config/confluence-retriever/.env with CONFLUENCE_URL and CONFLUENCE_PAT
```

### Running Tests

```bash
# Full test suite
pytest

# Single test (example)
pytest tests/test_wiki_answer.py::TestCqlEscape::test_plain_text_unchanged -v

# Run with output
pytest -v
```

### Manual CLI Verification

```bash
# Basic search (after .env is configured)
python3 scripts/wiki_answer.py --query "deployment process" --limit 5

# With multiple queries and space filter
python3 scripts/wiki_answer.py --query "auth" --query "API" --space MT

# With page body content (skim or deep)
python3 scripts/wiki_answer.py --query "release checklist" --depth skim
```

### Skill Installer Testing

```bash
# Dry run (print destination without writing)
python3 install.py --check

# Install to Claude Code
python3 install.py --target claude

# Install to other assistants
python3 install.py --target gemini
python3 install.py --target copilot
python3 install.py --target agents
```

## Architecture Overview

**confluence-retriever** is a "dumb retriever, smart host" design:

- **CLI (`scripts/wiki_answer.py`)** — Single stateless module handling: config loading, CQL query building, Confluence REST API calls, HTML parsing, result ranking, and markdown output formatting
- **Host AI** — The AI assistant (Claude Code, Copilot, Codex, Gemini, etc.) calls the CLI and synthesizes answers from the output
- **Skill (`skills/search-wiki.md`)** — Template instructions for the AI on how to invoke the CLI; `install.py` stamps the absolute path into it

The CLI returns deterministic ranked markdown with no AI logic, making it compatible with any host and shell/IDE/agent.

### File Structure

```
scripts/wiki_answer.py     # Single-file CLI with 7 logical sections:
                           # Config, Config Loader, CQL Builder, HTML Utils,
                           # Ranking, ConfluenceAdapter (HTTP wrapper), CLI (argparse)

tests/test_wiki_answer.py  # 46+ unit tests with pytest + responses (mocked HTTP)
                           # Test classes: TestCqlEscape, TestBuildCql, TestHtmlToText,
                           # TestExtractHeadings, TestScoreResult, TestRankResults, etc.

install.py                 # Cross-platform skill installer (Windows/macOS/Linux/WSL2)
                           # Substitutes absolute wiki_answer.py path into skill template

skills/search-wiki.md      # AI skill template with placeholder {WIKI_ANSWER_PATH}

requirements.txt           # Minimal deps: requests, beautifulsoup4, python-dotenv,
                           # pytest, responses
```

## Configuration

### `.env` File

- Never committed (contains PAT)
- Lookup order: `~/.config/confluence-retriever/.env` → `./.env` (repo-local, gitignored)
- Format:
  ```
  CONFLUENCE_URL=https://your-instance.atlassian.net
  CONFLUENCE_PAT=your_personal_access_token
  ```
- **Critical:** `CONFLUENCE_URL` is the BASE INSTANCE URL only; the CLI appends `/rest/api/content/search` itself

### Exit Codes

| Code | Meaning | Cause |
|------|---------|-------|
| 0 | Success | Query completed |
| 2 | Config error | Missing `.env` or `CONFLUENCE_PAT`/`CONFLUENCE_URL` not set |
| 3 | Auth failed | PAT expired or invalid (401/403) |
| 4 | Network error | Confluence unreachable or timeout |

## CLI Modes (Depth)

| Mode | API calls | Purpose |
|------|-----------|---------|
| `--depth links` (default) | 1 search | Quick finding — "where is the page?" |
| `--depth skim` | 1 search + 1 body fetch | "How do I...?" — steps and details from 1 page (capped 1200 chars) |
| `--depth deep` | 1 search + 3 body fetches | Deep verification — details from 3 pages (2000 chars each) |
| `--depth ultra` | 2 searches + 5-7 body fetches | Exhaustive research — expanded query variants, title matches, and first-seen cross-links |

The depth modes affect cost (API calls) and completeness. Shallow queries return only links/excerpts; deeper queries fetch capped query-relevant passages from top-ranked pages.

## Common Development Tasks

### Adding a CLI Flag

1. Add argument to `argparse` in `main()`
2. Thread the value through to relevant functions (typically `ConfluenceAdapter` or output)
3. Add tests in `tests/test_wiki_answer.py`
4. Update CLI reference table in README.md and `confluence-retriever-implementation.md`

### Modifying CQL or Ranking

1. Edit `build_cql()`, `cql_escape()`, `score_result()`, or `rank_results()`
2. Add/update tests in `tests/test_wiki_answer.py` with edge cases (quotes, backslashes, special chars)
3. Test end-to-end: `python3 scripts/wiki_answer.py --query "test query"`

### Changing HTML Parsing

1. Modify `html_to_text()`, `extract_headings()`, or `extract_relevant_passages()`
2. Add tests to `TestHtmlToText` or `TestExtractHeadings`
3. Consider HTML injection, whitespace, and entity escaping edge cases
4. Test with real Confluence page HTML samples

### Installing Skills

The installer is cross-platform:
- Reads `skills/search-wiki.md` template
- Substitutes absolute path to `wiki_answer.py` 
- Writes to target location (Claude Code, Copilot, Codex, Gemini, or custom path)
- Maintains Windows/macOS/Linux/WSL2 compatibility

## Testing Practices

- **Framework:** pytest + responses (all HTTP calls mocked, no real network)
- **Test structure:** Arrange-Act-Assert pattern
- **Naming:** `test_<expected_behavior>`
- **Coverage:** 46+ tests covering CQL escaping, query building, HTML parsing, ranking, API error handling, and config loading
- **No fixture directories:** Keep mocked responses explicit and readable inside tests

When adding features, write tests first (RED), then implement (GREEN), then verify coverage.

## Key Design Decisions

- **Single file CLI** — all logic in `wiki_answer.py` reduces deployment complexity and keeps skill installer simple
- **No AI in CLI** — ranking is keyword-based, output is deterministic markdown; AI reasoning lives in the host
- **Mocked HTTP** — tests use `responses` library for speed and determinism; no real Confluence calls in test suite
- **XDG config path** — `.env` lookup checks `~/.config/confluence-retriever/` first, following standard conventions
- **Exit codes explicit** — different codes for config (2), auth (3), network (4) errors help scripting and debugging
- **Cross-platform skill installer** — `install.py` is pure Python (no bash), works on native Windows

## Commits & PRs

- Keep messages short, descriptive, imperative or past-tense (e.g., `fix CQL escaping for backslash+quote`)
- Include CLI output examples for user-visible changes
- Note any changes affecting credentials, `.env`, API behavior, or output format
- Link related issues when available

## References

- **User Guide:** [README.md](README.md) — Features, setup, CLI flags, platform support
- **Setup Guide:** [confluence-pat-setup.md](confluence-pat-setup.md) — How to generate a Confluence PAT
- **Implementation Notes:** [confluence-retriever-implementation.md](confluence-retriever-implementation.md) — Architecture, phases, ranking algorithm
- **Copilot Instructions:** [.github/copilot-instructions.md](.github/copilot-instructions.md) — Detailed structure and testing guidelines
- **Repository Guidelines:** [AGENTS.md](AGENTS.md) — Build/test commands, coding style, common tasks
