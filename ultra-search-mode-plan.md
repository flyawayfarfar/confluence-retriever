# Ultra Search Mode — Implementation Plan

**Date:** 2026-05-22
**Status:** Planned, awaiting execution. No code yet.
**Target repo:** `/mnt/c/dev/github/confluence-retriever/`
**Companion doc:** `confluence-retriever-improvements-20260522.md` (general improvements)

---

## 1. Goal

Add a fourth retrieval depth — `--depth ultra` — that returns measurably better results than `--depth deep` for ambiguous or research-style queries, without breaking the "dumb retriever, smart host" contract.

**Constraints:**
- No LLM, no embedding models, no heavyweight ML dependencies in the CLI
- All scoring stays deterministic, mockable, and testable
- Default depth (`links`) keeps current behaviour and performance
- Existing `skim` / `deep` ranking unchanged unless evidence (precision fixtures) shows the new scorer is better

---

## 2. Current State Audit (Where We Are)

**Strengths to preserve:**
- Clean dumb-retriever architecture (`scripts/wiki_answer.py` is a single, self-contained module)
- 70 tests with mocked HTTP, no real Confluence calls in CI
- 3-tier depth ladder already exists (`links` → `skim` → `deep`)
- Cross-platform skill installer for 5 assistants
- Recent foundational work landed: `--json`, `--verbose`, GH Actions CI, pinned deps

**Real weaknesses driving this plan:**
1. **Single CQL call ceiling** — one search string, one query. If the user's exact wording misses, the whole pipeline misses.
2. **Naive keyword scoring** — counts phrase/token matches only. No proximity, no recency, no title-vs-body weighting in CQL.
3. **Sequential page fetches** — `--depth deep` fetches 3 page bodies one-at-a-time. Easy 2-3× speedup with `concurrent.futures`.
4. **No retry/backoff** — a single transient 429 / 5xx exits the whole process with code 4.
5. **No scorer-invariant regression guard** — the existing tests cover individual functions but don't assert algorithmic properties like "title hit beats excerpt-only hit" or "newer page beats stale page when otherwise equal". A ranking change could silently violate these and we'd never know.

---

## 3. Design Principles for Ultra Mode

| Principle | Why |
|-----------|-----|
| **Algorithmic depth, not AI depth** | Keeps the dumb-retriever contract intact. No model weights, no API keys other than the existing Confluence PAT. |
| **Properties over precision benchmarks** | This is a personal exploration tool. Query distribution is unknowable upfront, so manually curated precision fixtures would be busywork. Instead, assert algorithmic invariants the scorer must hold (title hit beats excerpt hit, recent beats stale, etc.) — these are testable without real-world ground truth. |
| **Opt-in only** | Ultra is a new depth, not a new default. Existing `links` / `skim` / `deep` behaviour unchanged. |
| **Parallel where safe, sequential where not** | Body fetches parallelise cleanly; ranking changes live behind property-test coverage. |

---

## 4. Execution Order

Phases are deliberately reordered so the scorer-invariant property tests land *before* any ranking changes, per global development workflow.

| Phase | Title | Type | Risk | Blocks |
|-------|-------|------|------|--------|
| 0 | Foundations: retry middleware, parallel body fetch helper, per-run page cache | Refactor | Low | All later phases benefit; `deep` mode also gets faster |
| 1 | **Scorer-invariant property tests** (`tests/test_scorer_invariants.py`, synthetic — no manual curation) | Test infra | Low | All ranking changes |
| 2 | Query expansion (deterministic variants, no LLM) | Feature | Low | Phase 4 |
| 3 | Multi-pass CQL: parallel `title ~` + `text ~` with weighted merge | Feature | Medium | Phase 4 |
| 4 | Enhanced keyword scorer: title weighting, proximity bonus, recency decay | Feature | Medium | Phase 6 |
| 5 | Proximity-aware passage scoring (inside `extract_relevant_passages`) | Feature | Low | — |
| 6 | Cross-link expansion (mine internal `<a>` from top pages, +2 hops capped) | Feature | Medium | — |
| 7 | Wire `--depth ultra` end-to-end + flags + skill mapping | Integration | Low | — |
| 8 | Docs sweep: `README.md`, `skills/search-wiki.md`, implementation notes | Docs | None | — |
| 9 | Bonus retroactive wins for non-ultra depths (parallel fetch for `deep`, retry middleware everywhere, `pyproject.toml`) | Hardening | Low | — |

**Validation gate:** Phase 4 ships when its property tests pass — algorithm has the intended invariants. Real-world precision is measured organically: as you use ultra mode, queries that return garbage get captured back into property tests as new constructed cases.

---

## 5. Phase Details

### Phase 0 — Foundations

**Why first:** later phases assume retries and parallel fetching exist. Get the plumbing in once.

**Changes:**
- Add a `requests.Session` adapter with `urllib3.Retry` (backoff on 429, 502, 503, 504; max 3 retries; jitter)
- Add `ConfluenceAdapter.get_pages(page_ids: list[str]) -> dict[str, dict]` that fetches concurrently via `concurrent.futures.ThreadPoolExecutor(max_workers=4)`
- Add a per-invocation in-memory page-body cache keyed by page ID (so cross-link expansion in Phase 6 doesn't re-fetch the same page)

**Tests:**
- Retry middleware on 429 → eventually succeeds (mock with `responses` returning [429, 429, 200])
- Retry middleware exhausted → exits with code 4
- `get_pages([id1, id2, id3])` returns dict with all 3 keys; mock all 3 endpoints
- Cache: calling `get_page(id)` twice in one CLI run only hits the network once

**Files touched:** `scripts/wiki_answer.py`, `tests/test_wiki_answer.py`. No public API change.

---

### Phase 1 — Scorer-Invariant Property Tests

**Why this replaces manual precision fixtures:** this is a personal exploration tool. Query distribution is unknowable upfront, so curating 20 "known good" queries would mean doing the search work ahead of time — defeating the purpose. Instead, test the **properties** the scorer must hold, constructed entirely in code. No Confluence access, no human curation needed.

**What we're testing — the algorithm's invariants:**

| Property | Why it matters |
|----------|----------------|
| Title-match page ranks above excerpt-only match (otherwise equal) | Phase 4 title weighting |
| Recent page ranks above stale page (otherwise equal) | Phase 4 recency decay |
| Page with co-located query terms beats page with scattered terms | Phase 4 + Phase 5 proximity |
| Multi-token query: page matching all tokens beats page matching one | Existing scorer behaviour |
| Title hit + text hit (multi-pass) outranks text-only hit | Phase 3 weighted merge |
| Cross-linked page from top result appears in ultra output, flagged as `source: cross-link` | Phase 6 |
| Disabling recency (`--recency-halflife-days 999999`) restores legacy ranking | Phase 4 configurability |

**Deliverable:** new file `tests/test_scorer_invariants.py` with one test class per property. All test data is synthetic — built in `_make_result(...)` helpers similar to the existing pattern at `tests/test_wiki_answer.py:173`.

**Example:**
```python
class TestTitleBeatsExcerpt:
    def test_title_match_ranks_above_excerpt_match_when_otherwise_equal(self):
        title_page = _make_result(title="deployment process", excerpt="other content")
        excerpt_page = _make_result(title="other page", excerpt="deployment process notes")
        ranked = wiki.rank_results([excerpt_page, title_page], ["deployment process"], None)
        assert ranked[0]["title"] == "deployment process"
```

**Coverage shape:** approximately 1 test class per scoring signal, 2–4 tests per class. ~12–20 tests total covering invariants the ultra mode scorer must satisfy.

**Capturing real-world failures organically:** if you use ultra mode and a real query returns garbage, paste the query + wrong top result + what should have ranked higher. That becomes a new constructed test case in `test_scorer_invariants.py` — derived from real usage, but encoded synthetically so it runs in CI.

**Files touched:** `tests/test_scorer_invariants.py` (new). No production code, no fixtures directory, no manual curation.

**Acceptance criterion:** `pytest tests/test_scorer_invariants.py` runs in CI; all invariant tests pass against the Phase 4 enhanced scorer.

---

### Phase 2 — Query Expansion

**What it does:** Given user queries, generate up to 6 deterministic variants. No LLM, no API.

```python
expand_queries(["customer authentication API"])
# → [
#   "customer authentication API",   # original (highest weight)
#   "customer authentication",        # drop trailing acronym
#   "authentication API",             # drop leading noun
#   "customer auth",                  # known abbreviation
#   "authentication",                 # core token
#   "API",                            # trailing acronym alone
# ]
```

**Rules:**
- Always include the original query verbatim, weighted highest
- Tokenize on whitespace, drop tokens shorter than 3 chars
- Hardcode a small abbreviation map: `authentication ↔ auth`, `documentation ↔ docs`, `configuration ↔ config`, `repository ↔ repo`, `environment ↔ env`
- Cap at 6 variants total (to avoid CQL bloat in Phase 3)
- Deduplicate preserving order

**Tests:** `TestQueryExpansion` — single phrase, multi-word, hyphenated input, already-expanded, abbreviation mapping, dedup, 6-variant cap.

**Files touched:** `scripts/wiki_answer.py` (new function), `tests/test_wiki_answer.py`.

---

### Phase 3 — Multi-Pass CQL (Parallel Title + Text)

**What it does:** For ultra mode, issue two CQL searches in parallel against the same expanded query set:
- `title ~ "..."` — high precision (only matches page titles)
- `text ~ "..."` — high recall (matches title + body, current behaviour)

Merge results by page ID, with title hits weighted 3× text hits.

**Implementation:**
- New method `ConfluenceAdapter.search_combined(queries, space, limit)` runs both via `ThreadPoolExecutor`
- Returns merged result list, each result tagged with `{"title_hit": bool, "text_hit": bool}` for downstream scoring
- Cap at `limit` total results after merge

**Tests:**
- Title-only hit ranks higher than text-only hit when scores otherwise equal
- Page present in both responses appears once in merged output, scored higher
- Both endpoints called concurrently (assert via timing or call-order with `responses` callbacks)
- 401/403 on either endpoint → existing auth exit behaviour

**Files touched:** `scripts/wiki_answer.py`, `tests/test_wiki_answer.py`.

---

### Phase 4 — Enhanced Keyword Scorer

**The actual ranking upgrade.** Skipping BM25 (per scope decision); instead, evolve the existing `score_result()` with three orthogonal signals.

**New scoring components added to `score_result()` (only when `--depth ultra`):**

1. **Title vs body weighting** — title hits already score 4 vs excerpt 2. Bump title weight to 6 when query token *is* the title (full-phrase title match).
2. **Proximity bonus** — if two query tokens appear within 50 chars of each other in the excerpt, add +2. Helps a page about "customer authentication API" beat one that mentions "customer" in one paragraph and "API" in a totally different one.
3. **Recency decay** — multiply final score by `exp(-days_since_edit / halflife_days)`. Default half-life 365 days (configurable via `--recency-halflife-days`). Requires parsing `version.when` from Confluence search response, which the API already returns when `expand=version` is set (already done at `wiki_answer.py:263`).

**Validation:** Phase 1 property tests must pass — title weighting test, recency test, proximity test. These assert the scorer's invariants. Real-world precision is observed by use; regressions found in the wild get captured as new property tests.

**Tests:** `TestEnhancedScorer` with subtests for each signal in isolation + combined, plus the invariant tests in `tests/test_scorer_invariants.py` from Phase 1.

**Files touched:** `scripts/wiki_answer.py`, `tests/test_wiki_answer.py`. Existing `score_result()` for non-ultra depths stays unchanged.

---

### Phase 5 — Proximity-Aware Passage Scoring

**What it does:** Extend `score_text_block()` (the function that scores passages *inside* a fetched page body) with the same proximity bonus as Phase 4. Currently it scores heading hits and token hits independently — a paragraph that mentions both query terms close together should beat one that mentions them in scattered sentences.

**Tests:** `TestProximityScoring` — co-located terms beat scattered terms with same individual counts.

**Files touched:** `scripts/wiki_answer.py`, `tests/test_wiki_answer.py`.

---

### Phase 6 — Cross-Link Expansion

**What it does:** After fetching the top N pages for ultra mode, scan their HTML for internal Confluence links (`<a href="/wiki/spaces/...">` or `/display/SPACE/Page+Title`). Fetch up to 2 *additional* linked pages and include their relevant passages in the output.

**Bounds:**
- Max +2 pages beyond the depth-specified top-N
- Only follow internal links (regex match against Confluence URL patterns)
- Deduplicate against pages already fetched (via Phase 0 cache)
- Linked pages are included in output but flagged: `"source": "cross-link", "from_page": "12345"`

**Tests:**
- Mock page body containing 3 internal + 2 external links → only 2 internal followed
- Already-fetched page in cache → not re-fetched
- Page with no internal links → ultra still works, just no expansion

**Files touched:** `scripts/wiki_answer.py`, `tests/test_wiki_answer.py`.

---

### Phase 7 — Wire `--depth ultra`

**Changes:**
- Add `"ultra"` to argparse choices in `build_parser()`
- Add `"ultra": (5, 3000)` to `DEPTH_BODY_DEFAULTS`
- Add `--recency-halflife-days N` argparse flag (default 365)
- In `main()`, when `depth == "ultra"`: call `search_combined` (Phase 3), apply enhanced scorer (Phase 4), fetch bodies in parallel (Phase 0), apply cross-link expansion (Phase 6)
- For `links` / `skim` / `deep`: keep current code path untouched

**Tests:** end-to-end CLI test with all mocked endpoints, asserting ultra mode output includes title-hit pages and cross-linked pages.

**Files touched:** `scripts/wiki_answer.py`, `tests/test_wiki_answer.py`.

---

### Phase 8 — Documentation & Skill Mapping

**Files updated:**
- `README.md` — add `ultra` row to depth table; new "Ultra mode" section explaining the cost (4-5s wall-clock, 2 search calls + 5+2 page fetches) and when to use it
- `skills/search-wiki.md` — add `ultra` row to the depth table with trigger phrases:
  - "ultra search", "best results", "smartest search", "comprehensive", "exhaustive", "leave no stone unturned", "find everything", "research mode", "ultrathink the wiki"
- `confluence-retriever-implementation.md` — extend § Retrieval Depth with ultra mode
- `confluence-pat-setup.md` — no change (PAT scope unchanged)
- `CLAUDE.md` — add ultra mode to the depth modes table

---

### Phase 9 — Retroactive Wins for Non-Ultra Depths

Now that Phase 0 plumbing exists, apply it to existing depths for free wins:

- **Parallel body fetch for `deep` mode** — switch from sequential `for r in ranked[:body_top]` loop to `adapter.get_pages([r["id"] for r in ranked[:body_top]])`. Expected 2-3× speedup on `--depth deep`.
- **Retry middleware applies globally** — all Confluence calls benefit, not just ultra
- **`pyproject.toml`** — proper packaging, `wiki-answer` on PATH after `pip install -e .`. Deferred item from prior improvements doc.

**Files touched:** `scripts/wiki_answer.py`, `pyproject.toml` (new), `README.md`.

---

## 6. Risks & Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| No real-world precision benchmark — "ultra is smarter" can't be proven, only argued | MEDIUM | Accepted tradeoff. Query distribution is unknowable upfront for this tool, so synthetic precision fixtures would be busywork. Property tests verify the scorer's invariants; real-world quality is observed by use and captured back as new property tests. |
| Recency decay penalises old-but-correct pages (policies, foundational docs) | MEDIUM | Configurable half-life (`--recency-halflife-days`); default 365d is gentle; pass `--recency-halflife-days 999999` to disable |
| `title ~` + `text ~` doubles API calls per ultra query | LOW | Only ultra depth; lower depths unchanged. Phase 0 retry middleware handles any rate-limit edge cases. |
| Cross-link expansion could fan out unbounded | MEDIUM | Hard cap +2 pages, dedupe by ID via Phase 0 cache, only follow `/wiki/spaces/` internal links |
| Ultra mode wall-clock 3-5s feels slow vs `deep` | LOW | Document the cost; only map to explicit "ultra/research mode" trigger phrases |
| Phase 4 scorer regresses existing query quality | MEDIUM | Ultra scorer applies only to ultra mode; existing depths bit-for-bit unchanged. Phase 1 property tests catch invariant violations. Regressions found in use get captured as new property tests. |
| Parallel fetching could trip Confluence rate limits | LOW | `ThreadPoolExecutor(max_workers=4)`; retry middleware handles 429s with backoff |

---

## 7. Estimated Time

| Phase | Time |
|-------|------|
| 0 — Foundations | 1h |
| 1 — Scorer-invariant property tests | 0.5h |
| 2 — Query expansion | 0.5h |
| 3 — Multi-pass CQL | 1h |
| 4 — Enhanced scorer | 1h |
| 5 — Proximity passages | 0.5h |
| 6 — Cross-link expansion | 1h |
| 7 — Wire ultra mode | 0.5h |
| 8 — Docs | 0.5h |
| 9 — Bonus wins | 1.5h |
| **Total** | **~8h agent time, zero human curation** |

---

## 8. Acceptance Criteria

Ultra mode ships only if all of these hold:

- [ ] `pytest tests/` — all 70+ existing tests still pass
- [ ] `pytest tests/test_scorer_invariants.py` — all algorithmic invariants pass (title weight, recency, proximity, multi-pass merge, cross-link sourcing)
- [ ] `python3 scripts/wiki_answer.py --depth ultra --query "test"` returns ranked markdown within 5s wall-clock against a real Confluence instance
- [ ] `python3 scripts/wiki_answer.py --help` lists `ultra` and `--recency-halflife-days`
- [ ] `--depth links` / `skim` / `deep` behaviour bit-for-bit identical to pre-change for the same inputs (except for the Phase 9 parallel-fetch speedup, which is observable only in wall-clock)
- [ ] `skills/search-wiki.md` includes ultra trigger phrases and is installable to all 5 targets via `install.py`

---

## 9. Out of Scope (Intentionally Deferred)

- **BM25 / TF-IDF scoring** — explicitly skipped this round. Enhanced keyword scorer (Phase 4) is simpler and covers most of the same ground without IDF corpus-stat awkwardness.
- **Embedding-based reranking** — would break the dumb-retriever contract. If wanted later, build as a sibling tool (`wiki_rerank.py`) that consumes `wiki_answer.py --json`.
- **Manually curated precision fixtures (real query → expected page ID pairs)** — explicitly skipped. Query distribution is unknowable upfront for a personal exploration tool; pre-writing 20 known-good queries would mean doing the search work ahead of time, which defeats the purpose. Replaced by Phase 1 synthetic property tests. The `confluence-retriever-implementation.md:181-183` note about precision fixtures stands as a future option if usage patterns ever stabilise into recurring queries.
- **Persistent page cache (cross-invocation)** — Phase 0 cache is per-run only. A persistent cache (SQLite, ~/.cache/confluence-retriever/) is a reasonable later add but not needed for ultra mode itself.
- **BOM-tolerant `.env` parsing** — pre-existing deferred item.
- **Multi-space CQL filter (`space in (A, B)`)** — pre-existing deferred item.

---

## 10. Commit Strategy

One commit per phase. Each commit independently passes `pytest -q tests/`. Suggested messages:

```
chore: add retry middleware and parallel body-fetch helper
test: add scorer-invariant property tests
feat: add deterministic query expansion
feat: add multi-pass CQL search (title + text)
feat: add enhanced keyword scorer (title, proximity, recency)
feat: add proximity-aware passage scoring
feat: add cross-link expansion for ultra mode
feat: wire --depth ultra end-to-end
docs: document ultra mode in README, skill, and implementation notes
perf: parallel body fetch in deep mode + pyproject.toml packaging
```

Do **not** bundle. The property-test commit (Phase 1) in particular must land alone so the invariants are auditable in git history before the scorer changes that rely on them.

---

## 11. Files Touched (Summary)

| File | Phases |
|------|--------|
| `scripts/wiki_answer.py` | 0, 2, 3, 4, 5, 6, 7, 9 |
| `tests/test_wiki_answer.py` | 0, 2, 3, 4, 5, 6, 7 |
| `tests/test_scorer_invariants.py` (new) | 1 |
| `README.md` | 8, 9 |
| `skills/search-wiki.md` | 8 |
| `confluence-retriever-implementation.md` | 8 |
| `CLAUDE.md` | 8 |
| `pyproject.toml` (new) | 9 |

No upstream dependency changes beyond optional `pyproject.toml`. No schema changes. No breaking changes to existing depths.
