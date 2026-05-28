# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start

### Environment Setup

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the package + dev dependencies (installs the `confluence-search` console script)
pip install -e .[dev]

# Optional: install full-page HTML→Markdown renderer for `confluence-search read`
pip install -e .[read]

# Configure credentials — interactive
confluence-search setup
# ...or by hand:
cp .env.example ~/.config/confluence-retriever/.env
chmod 600 ~/.config/confluence-retriever/.env
```

### Running Tests

```bash
# Full test suite (156 tests, all HTTP mocked)
pytest

# Single test (example)
pytest tests/test_wiki_answer.py::TestCqlEscape::test_plain_text_unchanged -v
```

### Manual CLI Verification

```bash
# Basic search
confluence-search search --query "deployment process" --limit 5

# Multiple queries and space filter
confluence-search search --query "auth" --query "API" --space MT

# Fetch passages from the top page
confluence-search search --query "release checklist" --depth skim

# Deep mode: parallel title+text + 5 pages + cross-links
confluence-search search --query "release approvals" --depth deep

# Read a single page in full Markdown
confluence-search read 12345 --format markdown

# List child pages
confluence-search children 12345

# Self-diagnose
confluence-search doctor
```

The legacy `python3 scripts/wiki_answer.py …` invocation still works via a shim.

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

- **CLI (`confluence-search` console script, package `confluence_retriever`)** — handles config loading, CQL building, Confluence REST API calls, HTML parsing, ranking, and output formatting across `search`, `read`, `info`, `children`, `setup`, and `doctor` subcommands
- **Host AI** — Claude Code / Copilot / Codex / Gemini / etc. invokes the CLI and synthesises answers from the structured output
- **Skill (`skills/search-wiki.md`)** — Template instructions for the host AI; `install.py` stamps both the project root and the resolved command name into it

The CLI returns deterministic ranked Markdown (or JSON) with no AI logic, making it compatible with any host and shell/IDE/agent.

### File Structure

```
src/confluence_retriever/        # Python package
├── cli.py                       # Click entry point + subcommands
├── config.py                    # .env loader, exit codes
├── client.py                    # ConfluenceAdapter + exception types
├── cql.py                       # cql_escape, build_cql
├── html_utils.py                # html_to_text/markdown, passage extraction,
│                                # heading extraction, cross-link parser, scorer
├── ranking.py                   # score_result, rank_results, expand_queries,
│                                # depth defaults + deprecated-alias map
├── url_parsing.py               # extract_page_id (URL/ID → numeric ID)
└── formatters.py                # Markdown / JSON renderers per subcommand

scripts/wiki_answer.py           # Legacy shim — re-exports the package surface
                                 # so `import wiki_answer as wiki` keeps working

tests/                           # 156 unit tests, all HTTP mocked
├── test_wiki_answer.py          # Search, ranking, config, depth, ultra E2E
├── test_scorer_invariants.py    # Recency must not invert relevance order, etc.
├── test_url_parsing.py          # All four URL shapes + bare ID + bad input
├── test_html_to_markdown.py     # markdownify path + fallback
├── test_cli_subcommands.py      # read, info, children, setup, doctor via Click
└── test_install.py              # Skill installer: paths, command resolution

install.py                       # Cross-platform skill installer
                                 # Placeholders: <PROJECT_ROOT> and {COMMAND}

skills/search-wiki.md            # AI skill template
pyproject.toml                   # Declares `confluence-search` console script
requirements.txt                 # Runtime deps: requests, bs4, python-dotenv, click
requirements-dev.txt             # +pytest, responses, markdownify
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

## CLI Modes (Depth) — v0.2

| Mode | API calls | Purpose |
|------|-----------|---------|
| `--depth links` (default) | 1 search | Quick finding — "where is the page?" |
| `--depth skim` | 1 search + 1 body fetch | "How do I...?" — steps and details from 1 page (capped 1200 chars) |
| `--depth deep` | 2 searches + 5-7 body fetches | Exhaustive research — expanded query variants, parallel title+text search, and first-seen cross-links |

`--depth ultra` is a deprecated alias for `--depth deep`. The pre-0.2
3-page `deep` preset has been removed; pin `--depth skim --body-top 3
--body-chars 2000` to recover that exact midpoint. See [MIGRATION.md](MIGRATION.md).

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
