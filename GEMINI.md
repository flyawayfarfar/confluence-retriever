# Confluence Retriever Project Instructions

This project provides a CLI tool (`confluence-search`) to search and retrieve content from Confluence.

## Key Components

- **CLI:** `confluence-search` console script (package `confluence_retriever` under `src/`) — queries Confluence CQL and returns ranked results.
- **Skills:** The `search-wiki` skill (in `skills/search-wiki.md`) tells an AI assistant how to invoke the CLI.
- **Setup:** Run `confluence-search setup` interactively, or see `docs/setup/confluence-pat-setup.md`.

## Developer Workflows

### Running Tests
```bash
pytest
```
Tests are in `tests/` and mock all HTTP calls — no real Confluence needed.

### Using the Search Tool
```bash
confluence-search search --query "your search term"
confluence-search search --query "auth" --space MT --depth skim
confluence-search doctor    # verify config + connectivity
```

### Depth Modes
- `links` (default): Returns titles, URLs, and excerpts (1 API call).
- `skim`: Fetches query-relevant passages from the top page (2 API calls).
- `deep`: Expanded query variants, 5 page bodies, and cross-links (7-9 API calls).

### Installing the Skill
```bash
python3 install.py --target gemini    # writes to ~/.gemini/skills/search-wiki/SKILL.md
python3 install.py --check            # dry run
```

## Conventions
- Follow PEP 8 for Python code.
- Use `responses` for mocking HTTP requests in tests.
- Keep credentials in `~/.config/confluence-retriever/.env` (not committed).
