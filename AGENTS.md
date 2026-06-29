# Repository Guidelines

## Project Structure & Module Organization

This repository is a Python CLI for searching Confluence and returning ranked Markdown results. The main entry point is the `confluence-search` console script, backed by the `confluence_retriever` package under `src/`. Key modules: `cli.py` (Click entry point), `client.py` (Confluence API adapter), `cql.py` (query builder), `html_utils.py` (HTML parsing and passage extraction), `ranking.py` (scoring and depth defaults), `formatters.py` (Markdown/JSON output). Unit tests live in `tests/` and use mocked HTTP calls only. Assistant skill installation is handled by `install.py`, using the template in `skills/search-wiki.md`. Keep credentials out of source control; `.env.example` is the committed template and local `.env` files are ignored.

## Build, Test, and Development Commands

Create an environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

Run the full test suite:

```bash
pytest
```

Run the CLI locally after configuring credentials:

```bash
confluence-search search --query "deployment process" --limit 5
confluence-search search --query "authentication" --space MT
```

Check the assistant skill installer without writing files:

```bash
python3 install.py --check
```

## Coding Style & Naming Conventions

Use Python 3.9+ and standard library features before adding new dependencies. Follow the existing style: 4-space indentation, type hints on public helpers, short docstrings for modules/classes/functions, and constants in `UPPER_SNAKE_CASE`. Use `snake_case` for functions and variables, and `PascalCase` for test classes. Keep CLI behavior explicit, including exit codes and stderr messages for failures.

## Testing Guidelines

Tests use `pytest` and `responses` to avoid real network calls. Add or update tests in `tests/test_wiki_answer.py` when changing CQL generation, HTML parsing, ranking, configuration, or HTTP behavior. Name test methods `test_<expected_behavior>`. New Confluence API behavior should be covered with mocked responses for success and relevant error cases.

## Commit & Pull Request Guidelines

The current history uses short, descriptive commit messages. Prefer concise imperative or past-tense summaries, for example `add page body retrieval tests` or `fix auth error handling`. Pull requests should include a clear description, commands run such as `pytest`, and notes for any credential, `.env`, or Confluence API changes. Link related issues when available and include CLI output examples for user-visible behavior changes.

## Security & Configuration Tips

Never commit personal access tokens or generated local `.env` files. The CLI checks `~/.config/confluence-retriever/.env` first, then repo-local `.env`. Keep `CONFLUENCE_URL` as the root instance URL only; the script appends REST paths itself. When editing installer logic, preserve cross-platform behavior for Windows, macOS, Linux, and WSL2.
