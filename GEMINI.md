# Confluence Retriever Project Instructions

This project provides a CLI tool (`scripts/wiki_answer.py`) to search and retrieve content from Confluence.

## Key Components

- **Retrieval Script:** `scripts/wiki_answer.py` - Queries Confluence CQL and returns ranked results.
- **Skills:** The `search-wiki` skill (located in `skills/search-wiki.md`) allows an AI assistant to use this tool.
- **Setup:** See `GEMINI_SETUP.md` for installation instructions.

## Developer Workflows

### Running Tests
Use `pytest` to run the test suite. Tests are located in the `tests/` directory and use mocks for network calls.

### Using the Search Tool
You can run the script directly:
```bash
python3 scripts/wiki_answer.py --query "your search term"
```

### Depth Modes
- `links`: (Default) Returns titles, URLs, and excerpts.
- `skim`: Fetches the body of the top result.
- `deep`: Fetches the bodies of the top 3 results.

## Conventions
- Follow PEP 8 for Python code.
- Use `responses` for mocking HTTP requests in tests.
- Keep credentials in `.env` (not committed).
