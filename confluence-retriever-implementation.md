# Confluence Retriever CLI — Implementation

**Status:** Complete (Phases 1–6 done)  
**Started:** 2026-04-29  
**Location:** `/mnt/c/dev/github/confluence-retriever/`

---

## Architecture: Dumb Retriever, Smart Host

The CLI is deliberately a thin retriever, not a reasoner:

- **CLI (`wiki_answer.py`)** — searches Confluence via CQL, normalises results, ranks by keyword match, prints ranked markdown
- **Host AI (Claude Code, Copilot, etc.)** — reads the markdown output and synthesises the actual answer

This split means:
- No duplicate Confluence API credentials across AI tools — they all call the same CLI
- The CLI can be used from any shell, any IDE extension, any AI agent
- The ranking is deterministic and testable; the synthesis stays with the model that has context

---

## Project Structure

```
confluence-retriever/
├── confluence-retriever-implementation.md  (this file)
├── confluence-pat-setup.md                 (PAT configuration guide)
├── scripts/
│   └── wiki_answer.py                      (single-file CLI)
├── tests/
│   └── test_wiki_answer.py                 (32 unit tests, no real API calls)
├── requirements.txt                        (Python dependencies)
├── .env                                    (gitignored — your actual credentials)
└── .env.example                            (committed — credential template)
```

---

## Authentication

Config file: `.env` in the project root (gitignored).

See `confluence-pat-setup.md` for setup steps.

Variables:
- `CONFLUENCE_URL` — base URL, e.g. `https://your-instance.atlassian.net`
- `CONFLUENCE_PAT` — Personal Access Token

The CLI reads both at startup via `python-dotenv`. Missing either causes exit code 2.

---

## CLI Reference

**Script:** `scripts/wiki_answer.py`

```bash
python3 scripts/wiki_answer.py --query "TERM" [--query "TERM2"] [--space KEY] [--limit N]
```

| Flag | Default | Purpose |
|------|---------|---------|
| `--query TEXT` | required | Search term (repeat for OR) |
| `--space KEY` | none | Filter to a space key |
| `--limit N` | 5 | Max results |

**Exit codes:**

| Code | Meaning |
|------|---------|
| 0 | Success |
| 2 | Config error (missing `.env` or variables) |
| 3 | Auth failed (401/403) |
| 4 | Network error (timeout, unreachable) |

---

## Implementation Phases (Complete)

### Phase 1 — CLI Skeleton ✓
argparse, PAT/URL loader, exit codes, basic structure.

### Phase 2 — Confluence Adapter ✓
- `ConfluenceAdapter.search()` — CQL search, response normalisation
- `ConfluenceAdapter.get_page()` — page body fetch (for future use)
- `build_cql()` — CQL builder with escaping
- `strip_highlight_markers()` — removes `@@@hl@@@` / `@@@endhl@@@` markers from excerpts

### Phase 3 — Ranking ✓
- `score_result()` — title match +2, excerpt match +1, space match +1
- `rank_results()` — stable sort by descending score

### Phase 4 — HTML Extraction ✓
- `html_to_text()` — BeautifulSoup tag stripping, whitespace collapse, truncation
- `extract_headings()` — h1–h3 heading list from page HTML

### Phase 5 — Output ✓
Ranked markdown, one block per result:
```
# Wiki results for 'query'

## 1. Page Title
- **Space:** Space Name (`KEY`)
- **URL:** https://your-instance/...
- **Excerpt:** ...
```

### Phase 6 — Test Suite ✓
32 unit tests in `tests/test_wiki_answer.py`. No real API calls — HTTP mocked with the `responses` library.

Test classes: `TestCqlEscape`, `TestBuildCql`, `TestStripHighlightMarkers`, `TestHtmlToText`, `TestExtractHeadings`, `TestScoreResult`, `TestRankResults`, `TestConfluenceAdapterSearch`, `TestConfluenceAdapterGetPage`.

Run:
```bash
cd confluence-retriever
python3 -m pytest tests/ -v
```

---

## Dependencies

```
requests>=2.28.0
beautifulsoup4>=4.11.0
python-dotenv>=1.0.0
pytest>=7.0
responses>=0.20.0
```

Install:
```bash
pip install -r requirements.txt
```

---

## Future Features

### Iterative Retrieval (not yet implemented)

Currently the CLI does a single search call and returns ranked excerpts. A richer pattern — inspired by Andrej Karpathy's llm-wiki approach — would add a second retrieval pass:

1. **Search pass** — run CQL search, get ranked excerpt list (current behaviour)
2. **Skim pass** — for the top N results, fetch the full page body (`get_page()` is already implemented)
3. **Re-rank or re-query** — if the body reveals the user's question is not answered by the top result, extract headings/keywords and issue a second targeted search

When to do the second pass:
- Excerpt confidence is low (no query term in any excerpt)
- User question requires a specific procedure (steps, commands) that excerpts don't contain
- Top result's headings suggest the answer is in a child page

The `get_page()` method and `html_to_text()` / `extract_headings()` helpers are already in place to support this. The main cost is latency (one extra API call per page fetched) and token cost (page body is 500–2000 chars of text vs 150-char excerpt).

**Implementation sketch:**
```python
results = adapter.search(queries, space, limit=5)
ranked = rank_results(results, queries, space)

top = ranked[0]
if needs_deep_read(top, queries):          # heuristic: low excerpt score
    page = adapter.get_page(top["id"])
    body_text = html_to_text(page["body_html"], max_chars=1500)
    headings = extract_headings(page["body_html"])
    # include body_text in output for the host AI to synthesise from
```

This keeps the dumb-retriever contract — the CLI still returns text, the host AI still synthesises — but gives the model richer signal when excerpts are insufficient.

### Precision Fixtures

A `precision-fixtures.json` with 10 known query → expected page-id pairs would let you measure retrieval quality without an LLM. Not yet written; would be a useful regression guard after any ranking changes.
