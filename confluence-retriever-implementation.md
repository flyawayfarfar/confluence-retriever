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

Config file lookup order:
1. `~/.config/confluence-retriever/.env`
2. `.env` in the project root (gitignored)

See `confluence-pat-setup.md` for setup steps.

Variables:
- `CONFLUENCE_URL` — base URL, e.g. `https://your-instance.atlassian.net`
- `CONFLUENCE_PAT` — Personal Access Token

The CLI reads both at startup via `python-dotenv`. Missing either causes exit code 2.

---

## CLI Reference

**Script:** `scripts/wiki_answer.py`

```bash
python3 scripts/wiki_answer.py --query "TERM" [--query "TERM2"] [--space KEY] [--limit N] [--depth links|skim|deep|ultra]
```

| Flag | Default | Purpose |
|------|---------|---------|
| `--query TEXT` | required | Search term (repeat for OR) |
| `--space KEY` | none | Filter to a space key |
| `--limit N` | 5 | Max results |
| `--depth links` | `links` | Title, URL, and excerpt only |
| `--depth skim` | `links` | Fetch capped query-relevant passages from the top ranked page |
| `--depth deep` | `links` | Fetch larger passage budgets from the top three ranked pages |
| `--depth ultra` | `links` | Expanded title+text search, five page bodies, and up to two cross-linked pages |
| `--workers N` | 4 | Maximum parallel HTTP workers for page fetches |
| `--recency-halflife-days DAYS` | none | Ultra-only recency tie-breaker |
| `--legacy-scorer` | off | Use pre-ultra ranking with `--depth ultra` |
| `--body-top N` | by depth | Override number of pages to fetch bodies for |
| `--body-chars N` | by depth | Override max passage characters per page |
| `--json` | off | Emit results as JSON instead of Markdown |
| `-v`, `--verbose` | off | Emit diagnostic logging to stderr (CQL, request URLs, timings) |

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
- `ConfluenceAdapter.get_page()` — optional page body fetch for `--depth skim`, `--depth deep`, and `--depth ultra`
- `build_cql()` — CQL builder with escaping and `type = "page"` filtering
- `strip_highlight_markers()` — removes `@@@hl@@@` / `@@@endhl@@@` markers from excerpts

### Phase 3 — Ranking ✓
- `score_result()` — phrase and token matching; title matches score higher than excerpt matches
- `rank_results()` — stable sort by descending score

### Phase 4 — HTML Extraction ✓
- `html_to_text()` — BeautifulSoup tag stripping, whitespace collapse, truncation
- `extract_headings()` — h1–h3 heading list from page HTML
- `extract_relevant_passages()` — query-aware passage selection within the depth character budget

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
50 unit tests in `tests/test_wiki_answer.py`. No real API calls — HTTP mocked with the `responses` library.

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

## Retrieval Depth

### Optional Body Retrieval

By default, the CLI does a single search call and returns ranked excerpts. Retrieval depth is explicit so assistants can control token cost from the user prompt:

| Depth | API behavior | Token profile |
|-------|--------------|---------------|
| `links` | Search only; title, URL, excerpt | Lowest |
| `skim` | Search plus top 1 page with capped relevant passages | Moderate |
| `deep` | Search plus top 3 pages with larger passage budgets | Highest |
| `ultra` | Expanded text/title search plus top 5 pages and up to 2 cross-linked pages | Highest API cost, best recall |

Body retrieval performs a bounded skim pass:

1. **Search pass** — run CQL search, get ranked excerpt list (current behaviour)
2. **Skim pass** — for the top N ranked results, fetch page bodies with `--body-top N`
3. **Passage selection** — score page text blocks against query phrases and tokens, then emit the best passages under `--body-chars`
4. **Ultra cross-link pass** — in ultra mode only, append up to two first-seen linked pages not already ranked
5. **Synthesis** — host AI uses headings and capped relevant passages to answer without dumping whole pages

Prompt mapping for assistant skills:
- `links`: "find", "search", "where is", "link to", "docs for", "quick answer", "just the link"
- `skim`: "how do I", "show steps", "read the page", "according to the docs", "setup", "configure", "troubleshoot", "API usage"
- `deep`: "deep search", "verify", "compare pages", "source of truth", "exact wording", "think harder", "be thorough"
- `ultra`: "ultra search", "research mode", "exhaustive", "leave no stone unturned", "ultrathink the wiki"

The main cost is latency (one extra API call per page fetched) and token cost. Defaults are no body text for `links`, 1 page with up to 1200 relevant passage characters for `skim`, 3 pages with up to 2000 relevant passage characters each for `deep`, and 5 pages with up to 3000 relevant passage characters each plus up to 2 cross-linked pages for `ultra`.

```bash
python3 scripts/wiki_answer.py --query "release process" --depth skim
```

This keeps the dumb-retriever contract — the CLI still returns text, the host AI still synthesises — while giving the model richer signal only when needed.

### Precision Fixtures

A future precision corpus with 10 known query to expected page-id pairs would let you measure retrieval quality without an LLM. Keep it outside the committed tree until it contains real, sanitized examples.
