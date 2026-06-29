# Copilot Instructions for confluence-retriever

## Architecture

**confluence-retriever** is a lightweight Python CLI that retrieves ranked search results from Confluence. The design follows a "dumb retriever, smart host" pattern:

- **CLI (`confluence-search` console script, package `confluence_retriever`)** — handles configuration, CQL query building, API calls to Confluence, HTML parsing, result ranking, and markdown output formatting
- **Host AI** — the AI assistant (Claude Code, Copilot, Codex, Gemini, Antigravity, etc.) that calls the CLI and synthesizes answers from the output

The CLI is stateless, returns deterministic ranked markdown, and has no AI reasoning logic. This allows any host AI and any shell/IDE/agent to use it.

## Build & Test

### Environment Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

### Run Tests

```bash
# Full suite
pytest

# Single test
pytest tests/test_wiki_answer.py::TestCqlEscape::test_plain_text_unchanged -v

# Watch for changes (if pytest-watch installed)
ptw
```

### Manual CLI Verification

```bash
# After configuring credentials
confluence-search search --query "test" --limit 3
confluence-search doctor
```

### Linting & Type Checks

This repo uses no formal linter or type checker. Follow the style conventions listed below.

## Code Structure

### `src/confluence_retriever/` package

Modules and their responsibilities:

1. **`config.py`** — `.env` loading, exit code constants
2. **`cql.py`** (`build_cql()`, `cql_escape()`) — Confluence CQL query construction with proper escaping
3. **`html_utils.py`** (`html_to_text()`, `extract_headings()`, `extract_relevant_passages()`, `strip_highlight_markers()`) — HTML parsing and query-relevant passage extraction
4. **`ranking.py`** (`score_result()`, `rank_results()`) — keyword scoring (title matches outrank excerpt matches)
5. **`client.py`** (`ConfluenceAdapter`) — HTTP calls to `/rest/api/content/search` and `/rest/api/content/{id}?expand=body.storage`
6. **`formatters.py`** — Markdown and JSON renderers per subcommand
7. **`url_parsing.py`** — extracts numeric page ID from URL or bare ID
8. **`cli.py`** (`main_entry()` via Click) — wires everything together, handles exit codes

### `tests/test_wiki_answer.py`

46 unit tests using `pytest` and `responses` (mocked HTTP). Test classes follow the pattern `Test<FunctionName>` or `Test<ClassName>`. All real network calls are mocked with `responses` library.

### `install.py`

Cross-platform skill installer (Claude Code, Codex, Gemini, Antigravity, Copilot, agents). Stamps `confluence-search` into the `{COMMAND}` placeholder in `skills/search-wiki.md` and writes to the target skill location.

### `skills/search-wiki.md`

Template with instructions for the AI assistant on how to invoke the CLI. The `{COMMAND}` placeholder is stamped by `install.py`.

## Style & Conventions

- **Python 3.9+** — use standard library features before adding dependencies
- **Type hints** — on public helper functions and class methods (not required for CLI main)
- **Docstrings** — short module/class/function docstrings, one-liner summaries preferred
- **Constants** — `UPPER_SNAKE_CASE`
- **Functions/variables** — `snake_case`
- **Test classes** — `PascalCase` (e.g., `TestCqlEscape`)
- **Indentation** — 4 spaces
- **Exit codes** — explicit and documented (0=ok, 2=config, 3=auth, 4=network)
- **Comments** — minimal; only clarify non-obvious logic

## Configuration

### `.env` File

Never committed. Lookup order:
1. `~/.config/confluence-retriever/.env` (user config)
2. `./.env` in repo root (project config, gitignored)

Format:
```
CONFLUENCE_URL=https://your-instance.atlassian.net
CONFLUENCE_PAT=your_personal_access_token
```

**Important:** `CONFLUENCE_URL` is the base instance URL only — the CLI appends `/rest/api/content/search` itself.

### Exit Codes

| Code | Meaning | Cause |
|------|---------|-------|
| 0 | Success | Query completed |
| 2 | Config error | Missing `.env` or `CONFLUENCE_PAT`/`CONFLUENCE_URL` not set |
| 3 | Auth failed | PAT expired or invalid (401/403) |
| 4 | Network error | Confluence unreachable or timeout |

## CLI Flags & Features

### Basic Usage

```bash
confluence-search search --query "deployment process" --limit 5
confluence-search search --query "auth" --query "API" --space MT --limit 10
```

### Depth Modes

| Mode | API calls | Body fetched | Use case |
|------|-----------|-------------|----------|
| `--depth links` (default) | 1 search | No | Quick finding — "where is the page?" |
| `--depth skim` | 1 search + 1 body fetch | 1 page, capped 1200 relevant passage chars | "How do I...?" steps and details |
| `--depth deep` | 1 search + 3 body fetches | 3 pages, 2000 relevant passage chars each | Deep verification, compare pages |
| `--depth ultra` | (deprecated alias for `--depth deep`) | | |

Override body fetch count and character limits:
```bash
--body-top 2              # Fetch top 2 pages
--body-chars 500          # Cap each page to 500 chars
```

### Output Format

Markdown with sections per result:
```
# Wiki results for 'query'

## 1. Page Title
- **Space:** Space Name (`KEY`)
- **URL:** https://...
- **Excerpt:** ...
- **Relevant passages:**
  - Heading: matching passage text...

## 2. Another Page
...
```

## Testing Guidelines

- Tests use `pytest` and the `responses` library (no real HTTP calls)
- When changing CQL generation, HTML parsing, ranking, or API behavior, add or update tests in `tests/test_wiki_answer.py`
- Name test methods `test_<expected_behavior>`
- Confluence API behavior should have success + error case coverage
- Mock both success responses (200 with results) and failures (401/403 auth, 4xx/5xx network errors)

Example test structure:
```python
class TestSomethingNew:
    def test_expected_behavior(self):
        # arrange
        input_data = ...
        # act
        result = some_function(input_data)
        # assert
        assert result == expected
    
    @responses.activate
    def test_api_call_handling(self):
        responses.add(responses.GET, "https://...", json={...}, status=200)
        # test code
```

## Common Tasks

### Adding a New CLI Flag

1. Add argument to Click in `src/confluence_retriever/cli.py`
2. Thread the value through to relevant functions (typically `ConfluenceAdapter` or output functions)
3. Add tests for the flag parsing and behavior in `tests/test_wiki_answer.py`
4. Update the CLI reference table in README.md

### Changing CQL Query Logic

1. Modify `build_cql()` or `cql_escape()`
2. Add tests to `TestBuildCql` or `TestCqlEscape`
3. Test end-to-end with `--query` containing edge cases (quotes, backslashes, special chars)
4. Verify ranking still works as expected

### Adding HTML/Body Parsing Features

1. Modify `html_to_text()` or `extract_headings()` or create new helpers
2. Add tests to `TestHtmlToText` or `TestExtractHeadings`
3. Consider HTML injection and whitespace edge cases
4. Test with representative Confluence page HTML embedded directly in tests

### Modifying Ranking

1. Update `score_result()` or `rank_results()` logic
2. Add tests to `TestScoreResult` or `TestRankResults`
3. Consider the ranking impact on user queries — higher-scoring results should be more relevant
4. If changing defaults, consider backward compatibility and skill/CLI documentation updates

## Commit Messages

Keep commit messages short and descriptive in imperative or past-tense form:
- ✅ `add page body retrieval tests`
- ✅ `fix CQL escaping for backslash+quote`
- ✅ `bump requests to 2.28.1 for security`
- ❌ `I added tests for body retrieval`
- ❌ `misc updates`

Include a note in PRs for any changes affecting credentials, `.env`, API behavior, or CLI output format.

## Dependencies

- `requests` — HTTP calls to Confluence REST API
- `beautifulsoup4` — HTML parsing for page headings and relevant passages
- `python-dotenv` — `.env` file loading
- `pytest` — test framework
- `responses` — HTTP mocking for tests

Add new dependencies sparingly. Prefer standard library features first.

## Security & Configuration

- Never commit `.env` files (they contain PATs); `.env.example` is the template
- `.gitignore` covers `.env` and `.venv`
- When modifying `install.py`, preserve cross-platform behavior (Windows, macOS, Linux, WSL2)
- Keep `CONFLUENCE_URL` as root instance URL only; do not hardcode API paths in config

## Useful Links

- **PAT Setup:** [docs/setup/confluence-pat-setup.md](../docs/setup/confluence-pat-setup.md) — How to generate a Confluence PAT
- **README:** [README.md](../README.md) — User-facing feature overview and usage examples
