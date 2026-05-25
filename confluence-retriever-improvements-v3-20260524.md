# Confluence Retriever — Improvements Plan v3

**Date:** 2026-05-24
**Status:** Planned. No code yet. Awaiting approval.
**Target repo:** `/mnt/c/dev/github/confluence-retriever/`
**Supersedes:** `confluence-retriever-improvements-20260522.md` (v1, all 8 fixes shipped), `ultra-search-mode-plan.md` (v2, partial — uncommitted code exists)

---

## 1. Why v3

v1 (eight cleanups) shipped end-to-end between 2026-05-22 and 2026-05-23 (commits `5259d68` → `c81036a`). v2 introduced `--depth ultra` and began landing in the working tree, but the diff against `HEAD` for `scripts/wiki_answer.py` contains:

- **1 CRITICAL** correctness/silent-failure bug
- **5 HIGH** bugs (wrong semantics, broken URLs, swallowed errors)
- **4 MEDIUM** issues (incomplete feature, inconsistent logging, race)
- **Zero** new tests for any of the added code

v2 also did not address several architectural blind spots surfaced by independent review: rank stability, PAT-scope asymmetry between search and page-read, lack of a concurrency knob, no rollback path, and undefined cross-link ordering.

v3 = a single forward-looking plan that:

1. Closes the v1 doc tail (two stale references).
2. Lands the uncommitted ultra-mode work in **tested slices**, fixing the audit findings as each slice goes in.
3. Adds the architectural pieces v2 missed.
4. Finishes the v2 doc sweep and re-installs the skill to all five assistant targets.

Each phase is an independently green commit. The order moves invariant tests in **first**, then plumbing, then features, then wiring, then docs.

---

## 2. Ground Truth (as of 2026-05-24)

### 2.1 v1 status — complete with 2 doc tail items

| v1 Fix | State | Evidence |
|---|---|---|
| 1 install.py `import sys` | done | `install.py:18` |
| 2 delete `fixtures/`, `tasks/` | done | `ls` reports absent |
| 3 drop `--include-body` | done | commit `6398370` |
| 4 split `requirements-dev.txt` | done | file exists |
| 5 pin upper bounds | done | `requirements.txt` has `<3`, `<5`, `<2` |
| 6 `--json` mode | done | commit `8fd7eac` |
| 7 `--verbose` flag | done | commit `adedb11` |
| 8 GH Actions CI | done | `.github/workflows/test.yml` |

**v1 tail (not regressions, just cleanup misses):**

- `IMPLEMENTATION_PLAN.md` (if it still exists) references `include-body`, `fixtures`, `tasks` — confirm staleness; if stale, delete.
- `.github/copilot-instructions.md` may still reference `fixtures`/`tasks` per the v1 cross-file sweep — re-verify.
- README CI badge from v1 Fix 8 — re-verify presence.

### 2.2 v2 status — uncommitted, audit-blocked

**Diff against `HEAD` for `scripts/wiki_answer.py`:**

| v2 Phase | What landed (uncommitted) | What is missing |
|---|---|---|
| 0 Foundations | retry adapter, page cache, `get_pages()` parallel fetch | tests; the `sys.exit` inside `get_page()` is a worker-thread footgun |
| 1 Property tests | nothing | the entire file `tests/test_scorer_invariants.py` |
| 2 Query expansion | `expand_queries()` with abbreviation map only | structural variants (drop trailing/leading token) per v2 spec; tests |
| 3 Multi-pass CQL | `search_combined()` flags overlap pages | title-only pages are never appended; `except Exception: pass`; tests |
| 4 Enhanced scorer | `score_result(enhanced=, halflife_days=)` + `_proximity_bonus` | additive ≠ multiplicative (semantic mismatch with v2 spec); same-token false positive; tests |
| 5 Proximity in passages | applied inside `score_text_block` | tests |
| 6 Cross-link expansion | `extract_cross_links()` + wiring in `main()` | invalid URL constructed (`f"{base_url}/pages/{pid}"`); regex misses `/pages/123` and `/display/...`; tests |
| 7 Wire `--depth ultra` | `argparse` choice added, `main()` branch added | end-to-end test; no `--workers` knob; no rollback flag |
| 8 Docs sweep | nothing | README, `skills/search-wiki.md`, `CLAUDE.md`, install rerun |
| 9 Retroactive wins | `get_pages()` already used by main() body fetch | `pyproject.toml` packaging |

### 2.3 Audit findings (CRITICAL / HIGH only)

Citations are file:line in the **new** state of `scripts/wiki_answer.py` after the uncommitted diff is applied. Severities and authoring agent in brackets.

| # | Sev | Where | Issue |
|---|---|---|---|
| A1 | CRITICAL | `wiki_answer.py:447–455` `_title_ids()` | `except Exception: pass` silently swallows auth/network/parse errors. Ultra mode degrades to "no title hits" with zero user signal when PAT expires or network blips. [python-reviewer, silent-failure-hunter] |
| A2 | HIGH | `wiki_answer.py:439–467` `search_combined()` | Title-only pages (the whole point of a title-match query) are never appended to results. Only the overlap is flagged with `_title_hit=True`. Feature delivers half its intent. [python-reviewer] |
| A3 | HIGH | `wiki_answer.py:679` cross-link append in `main()` | Constructs `f"{base_url}/pages/{pid}"`, not a valid Confluence URL. Real path is `/wiki/spaces/{KEY}/pages/{ID}/{Title}` via `_links.webui`. [python-reviewer] |
| A4 | HIGH | `wiki_answer.py:200–217` `_proximity_bonus()` | Pools all token positions into one flat list, so two occurrences of the **same** token close together trip the bonus. `_proximity_bonus("auth and auth", ["auth"])` returns 2 — should be 0. [python-reviewer, silent-failure-hunter] |
| A5 | HIGH | `wiki_answer.py:298` `extract_cross_links()` | Regex `r"/pages/(\d+)/"` requires trailing slash. Misses `/pages/12345` when it is the last path segment. No coverage of `/display/SPACE/Title` legacy URLs. [python-reviewer, silent-failure-hunter] |
| A6 | HIGH | `wiki_answer.py:519` recency in `score_result()` | Implemented as `score += int(10 * exp(-age/halflife))` — additive. v2 §Phase 4 specifies multiplicative `score *= exp(-age/halflife)`. Additive inverts the intent: a fresh edit boosts a low-relevance page by 250 % but a high-relevance page by only 50 %. [python-reviewer] |
| A7 | HIGH | `wiki_answer.py:404–416` `get_page()` + `get_pages()` | `get_page()` calls `sys.exit(EXIT_NETWORK)` from inside a worker thread. `sys.exit` only raises `SystemExit` in that thread; the main thread re-raises via `future.result()`, but the behaviour is non-obvious and the parallel pool may leak partial work. Auth (401) and HTTP non-200 return `None` silently instead of propagating. [silent-failure-hunter] |
| A8 | HIGH | `wiki_answer.py:429–437` `get_pages()` + caller `wiki_answer.py:644–658` | Failed page fetches are silently absent from the returned dict. Caller does `pages_by_id.get(...)` with no warning. With a flaky network the user can see 5 link-only results that look like a `--depth links` run. [python-reviewer, silent-failure-hunter] |

Additional MEDIUM/LOW findings (logging vs `print`, docstring "decay" vs code "boost", regex coverage for Cloud `/wiki/spaces/…/pages/…/`, missing `space_key` on cross-link stubs) are absorbed into the phase-by-phase fixes below.

### 2.4 v2 blind spots (architectural)

- **No `--workers` knob.** Hardcoded `max_workers=4` and `max_workers=2`. Some Confluence instances rate-limit aggressively.
- **No rollback.** Once ultra ranking changes ship, there is no `--legacy-scorer` escape hatch. Three lines of code, saves a future regression triage.
- **Cross-link ordering undefined.** v2 says "+2 pages" but not which 2. Must be deterministic and tested (order-of-appearance).
- **Skill template propagation.** `skills/search-wiki.md` is installed into 5 assistant targets via `install.py`. Updating the template without re-running install leaves every assistant unaware of ultra mode.
- **Rank-stability for tiebreakers.** Recency must break ties, not dominate. Property tests should encode both *strict* invariants (title beats excerpt all-else-equal) and *tie-only* invariants (recency only swaps within ε).

---

## 3. Execution Order

Each row is one commit, each commit is green on its own, each commit lands tests alongside the code it covers.

| # | Title | Type | Risk | Closes |
|---|---|---|---|---|
| **A** | v1 doc tail cleanup | Docs | None | §2.1 tail |
| **B** | Property-test scaffold (against current scorer behaviour) | Tests | None | A4 safety net |
| **C** | Foundations: retry adapter, page cache, fix `sys.exit`-from-thread | Refactor | Low | A7, A8 |
| **D** | Fix `_proximity_bonus` same-token bug | Bug | None | A4 |
| **E** | `expand_queries`: add structural variants + tests | Feature | Low | v2 §Phase 2 gap |
| **F** | `search_combined`: log auth/network errors + include title-only pages + tests | Bug+Feature | Medium | A1, A2 |
| **G** | `extract_cross_links`: fix regex, add Cloud + legacy URL coverage + tests | Bug | Low | A5 |
| **H** | Cross-link append: use real Confluence URL via `_links.webui` + tests | Bug | Low | A3 |
| **I** | Enhanced scorer: multiplicative recency, rename to `--recency-halflife-days` semantics align, `--legacy-scorer` escape hatch + property tests | Feature | Medium | A6, v2 blind spot |
| **J** | Wire `--depth ultra` end-to-end test + `--workers N` flag + smoke checklist | Integration | Low | v2 §Phase 7 + blind spot |
| **K** | Docs sweep: README, `skills/search-wiki.md`, `CLAUDE.md`, implementation notes + re-run `install.py --target` for all 5 | Docs | None | v2 §Phase 8 |
| **L** | `pyproject.toml` + `wiki-answer` entry point | Hardening | Low | v2 §Phase 9 |

Estimated agent time: ~6h. (Slightly under v2's 8h because foundations and code are already written; most of the work is tests and fixes.)

---

## 4. Phase Details

> Each phase format: **Problem · Change · Tests · Verification · Cross-file impact**.

### Phase A — v1 doc tail cleanup

**Problem.** Two doc files may still reference removed items.

**Change.**
- `ls IMPLEMENTATION_PLAN.md` → if present and stale, delete; if relevant, scrub `include-body`, `fixtures`, `tasks` references.
- `grep -nE "include[_-]body|fixtures|tasks" .github/copilot-instructions.md` → remove any hits.
- Verify README contains the CI badge from v1 Fix 8.

**Tests.** None — docs only.

**Verification.**
```
grep -RIn "include[_-]body\|^fixtures\|^tasks" *.md .github/ COPILOT*.md GEMINI*.md
# expect: zero matches
```

**Cross-file impact.** Pure subtraction; no behavioural risk.

---

### Phase B — Property-test scaffold

**Problem.** Phases I and beyond change the scorer. Without invariant tests landing first, regressions are invisible.

**Change.** Create `tests/test_scorer_invariants.py` with the **current** scorer behaviour as the baseline. Each test asserts a property; tests that will only pass after Phase I are marked `pytest.mark.xfail(strict=True, reason="enabled by Phase I")` and flipped to `xpass`-then-pass when Phase I lands.

**Tests (synthetic, no fixtures):**

| Invariant | xfail until |
|---|---|
| Title-phrase match outranks excerpt-only match, all else equal | – (passes today, weight 4 vs 2) |
| Multi-token query: page matching all tokens beats page matching one | – |
| `--space` match adds exactly 1 to score | – |
| Title-hit flag (`_title_hit=True`) adds bonus only when `enhanced=True` | Phase F |
| Co-located 2-token excerpt outscores scattered 2-token excerpt | Phase D + Phase I |
| Recent edit breaks tie between otherwise-equal pages but does **not** dominate a higher-relevance older page | Phase I |
| `--recency-halflife-days 9999999` recovers legacy ranking bit-for-bit | Phase I |
| `--legacy-scorer` recovers legacy ranking bit-for-bit | Phase I |
| Cross-link results carry `"source": "cross-link"` and `"from_page"` fields | Phase J |

**Verification.** `pytest tests/test_scorer_invariants.py -v` runs; xfail markers visible in output.

**Cross-file impact.** None.

---

### Phase C — Foundations (retry, cache, fix worker-thread `sys.exit`)

**Problem.** Closes A7, A8. `get_page()` exits the process from inside a worker thread (`wiki_answer.py:404–416`); `get_pages()` silently drops failures.

**Change.**

1. Remove all `sys.exit(...)` calls from inside `ConfluenceAdapter` methods. Introduce two narrow exception types at module scope:
   ```python
   class ConfluenceAuthError(Exception): ...
   class ConfluenceNetworkError(Exception): ...
   ```
   `get_page()` / `search()` / `_title_ids()` raise these instead of exiting.
2. Top-level `main()` wraps adapter calls in `try/except (ConfluenceAuthError, ConfluenceNetworkError)` and maps to `sys.exit(EXIT_AUTH)` / `sys.exit(EXIT_NETWORK)` exactly as before. Exit codes unchanged.
3. `get_pages()` returns `dict[str, dict]` AND logs a warning listing any IDs absent from the result:
   ```python
   missing = [pid for pid in page_ids if pid not in result]
   if missing:
       logging.warning("page fetch dropped %d/%d pages: %s", len(missing), len(page_ids), missing)
   ```
4. Switch `get_page()`'s `print("WARNING: ...", file=sys.stderr)` calls to `logging.warning(...)`.
5. Add `--workers N` argparse flag (default 4). Plumb through `get_pages()` and `search_combined()`.

**Tests.**
- `test_get_page_raises_auth_error_on_401`
- `test_get_page_raises_network_error_on_connection_refused`
- `test_main_exits_3_on_auth_error`, `test_main_exits_4_on_network_error` (preserve existing contract)
- `test_get_pages_logs_warning_for_failed_pages` (capture `caplog`)
- `test_workers_flag_threads_through_to_get_pages`

**Verification.** Existing `test_install.py` and `test_wiki_answer.py` stay green; new tests pass.

**Cross-file impact.** `scripts/wiki_answer.py`, `tests/test_wiki_answer.py`. CLI surface gains `--workers`; document in Phase K.

---

### Phase D — Fix `_proximity_bonus` same-token bug

**Problem.** A4. Repeated single token within 50 chars trips the bonus.

**Change.** Track positions as `(position, token_index)` tuples. Only credit the bonus when two adjacent sorted positions come from **distinct** token indices.

```python
def _proximity_bonus(text: str, tokens: list[str]) -> int:
    hits: list[tuple[int, int]] = []
    for i, token in enumerate(tokens):
        start = 0
        while (idx := text.find(token, start)) != -1:
            hits.append((idx, i))
            start = idx + 1
    if len({i for _, i in hits}) < 2:
        return 0
    hits.sort()
    for (p1, t1), (p2, t2) in zip(hits, hits[1:]):
        if t1 != t2 and p2 - p1 <= 50:
            return 2
    return 0
```

**Tests.**
- `_proximity_bonus("auth and auth again", ["auth"]) == 0`
- `_proximity_bonus("foo bar", ["foo", "bar"]) == 2`
- `_proximity_bonus("foo " + " " * 60 + "bar", ["foo", "bar"]) == 0`
- `_proximity_bonus("foo foo bar", ["foo", "bar"]) == 2` (token-mix within 50)

**Cross-file impact.** `scripts/wiki_answer.py`, `tests/test_wiki_answer.py`.

---

### Phase E — `expand_queries` structural variants

**Problem.** v2 §Phase 2 promised structural variants (drop trailing token, drop leading noun, longest core token). The uncommitted code does only abbreviation swaps, so a typical 3-word query consumes 1 of 6 slots and yields nothing.

**Change.** Add structural variants **before** abbreviation swaps; preserve original at index 0; cap at `ULTRA_MAX_QUERIES = 6`; deterministic order; dedupe case-insensitively.

```python
def expand_queries(queries: list[str], max_total: int = ULTRA_MAX_QUERIES) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    def add(q: str) -> None:
        key = q.lower().strip()
        if key and key not in seen and len(out) < max_total:
            out.append(q.strip())
            seen.add(key)

    for q in queries:
        add(q)
        toks = [t for t in q.split() if len(t) >= 3]
        if len(toks) >= 2:
            add(" ".join(toks[:-1]))   # drop last
            add(" ".join(toks[1:]))    # drop first
        if toks:
            add(max(toks, key=len))    # longest single token

    for q in list(out):
        for abbrev, expansion in _ABBREV_MAP.items():
            if re.search(rf"\b{re.escape(abbrev)}\b", q, flags=re.IGNORECASE):
                add(re.sub(rf"\b{re.escape(abbrev)}\b", expansion, q, flags=re.IGNORECASE))
    return out
```

**Tests.** `TestExpandQueries` — drop-trailing, drop-leading, single-token longest, abbreviation, dedupe, cap honoured, original always first.

**Cross-file impact.** `scripts/wiki_answer.py`, `tests/test_wiki_answer.py`.

---

### Phase F — `search_combined`: surface errors + include title-only pages

**Problem.** A1 + A2.

**Change.**

1. Replace the bare `except Exception` in `_title_ids` with explicit `(ConfluenceAuthError, ConfluenceNetworkError, ValueError)` handling. Auth errors **propagate** (consistent with text search). Network errors `logging.warning(...)` then degrade gracefully to text-only.
2. Have `_title_ids` return the full result dict list, not just IDs. Append title-only results (IDs in title-search but not text-search) to the merged list. Cap merged length at `limit`.
3. Mark every result with `_title_hit: bool` so the scorer can boost overlap.

**Tests.**
- `test_search_combined_appends_title_only_results`
- `test_search_combined_marks_overlap_as_title_hit`
- `test_search_combined_propagates_auth_error`
- `test_search_combined_degrades_on_network_error_in_title_search`
- `test_search_combined_caps_at_limit_after_merge`

**Cross-file impact.** `scripts/wiki_answer.py`, `tests/test_wiki_answer.py`.

---

### Phase G — `extract_cross_links` regex coverage

**Problem.** A5.

**Change.** Match three URL shapes Confluence emits:
```python
_CROSSLINK_RE = re.compile(
    r"/(?:wiki/spaces/[^/\s\"']+/)?pages/(\d+)"
    r"|/display/[^/\s\"']+/([^\s\"']+)"
)
```
Numeric IDs are returned as-is; `/display/…/Title+With+Plus` legacy URLs return the page slug (caller resolves via search if needed) — or, simpler scope-cut: drop `/display` support, document non-coverage, and only match the first alternative. **Recommendation:** drop `/display`; modern Cloud emits the `/wiki/spaces/.../pages/...` shape. State this explicitly in the docstring.

Add a try/except around the BeautifulSoup parse — return `[]` and `logging.warning(...)` on parse failure.

**Tests.**
- `test_extract_cross_links_no_trailing_slash`
- `test_extract_cross_links_cloud_wiki_spaces_path`
- `test_extract_cross_links_dedupes`
- `test_extract_cross_links_returns_empty_on_malformed_html`

**Cross-file impact.** `scripts/wiki_answer.py`, `tests/test_wiki_answer.py`.

---

### Phase H — Cross-link stub uses real Confluence URL

**Problem.** A3.

**Change.** Add `"_links"` to the `expand` query param in `get_page()`. Store `webui` link in the cached page dict. Cross-link append in `main()` uses `f"{base_url}{xpage.get('webui', '')}"` — falls back to a discoverable URL via search if `webui` is empty, or empty-string with a `logging.warning`.

Also: cross-link stub gains `space_name` field (currently `""`), so any downstream code iterating `ranked` does not raise `KeyError`. Order of cross-links is **first-seen across all top-N body HTMLs**; this is asserted in tests.

**Tests.**
- `test_cross_link_url_uses_webui_path`
- `test_cross_link_order_is_first_seen_across_top_n`
- `test_cross_link_stub_carries_source_and_from_page_fields` — enables the Phase B xfail to pass

**Cross-file impact.** `scripts/wiki_answer.py`, `tests/test_wiki_answer.py`. JSON output schema gains `source` and `from_page` keys only for cross-linked entries — document in Phase K.

---

### Phase I — Enhanced scorer: multiplicative recency + `--legacy-scorer`

**Problem.** A6 + v2 blind spot (no rollback, no tiebreaker discipline).

**Change.**

1. Switch recency to multiplicative, applied **after** all other scoring:
   ```python
   if enhanced and halflife_days and halflife_days > 0 and last_modified:
       try:
           mod_dt = datetime.fromisoformat(last_modified.replace("Z", "+00:00"))
           days_ago = max(0, (datetime.now(tz=timezone.utc) - mod_dt).days)
           score = int(score * math.exp(-days_ago / halflife_days))
       except (ValueError, TypeError):
           logging.debug("recency parse failed for %s: %r", result.get("id"), last_modified)
   ```
2. Update docstring and `--recency-halflife-days` help text: say "decay" everywhere (since the math now actually decays).
3. Add `--legacy-scorer` flag that forces `enhanced=False` even when `--depth ultra`. Documented as a rollback knob.
4. Flip Phase B xfail markers for: tie-breaking recency, `--recency-halflife-days 9999999` parity, `--legacy-scorer` parity.

**Tests.**
- `test_recency_multiplicative_decays_old_pages`
- `test_recency_does_not_invert_relevance_order`
- `test_legacy_scorer_flag_matches_pre_ultra_ranking`
- `test_recency_halflife_infinity_matches_legacy`

**Cross-file impact.** `scripts/wiki_answer.py`, `tests/test_wiki_answer.py`, `tests/test_scorer_invariants.py` (flip xfails).

---

### Phase J — Wire `--depth ultra` end-to-end + smoke checklist

**Problem.** No end-to-end test for ultra mode; no smoke checklist for human signoff (v2 §8 left this implicit).

**Change.**

1. Add an end-to-end test in `tests/test_wiki_answer.py` that mocks all endpoints (search × 2 in parallel + body × 5 + cross-link body × 2) and asserts:
   - Output includes 5 ranked + 2 cross-linked entries
   - Cross-linked entries have `source: "cross-link"`
   - `--json` mode emits valid JSON for the same flow
   - Wall-clock under 2s with mocked responses
2. Manual smoke checklist (added to v3 doc — not a test) listing 5 real queries the maintainer should run before merging:
   - one with an obvious title match
   - one ambiguous query (proves expansion helped)
   - one for a recently-edited topic (proves recency boost)
   - one for an old policy doc (proves recency does not bury it)
   - one query that returns nothing (proves the empty path is clean)
3. `--workers` flag (added in Phase C) documented in `--help`.

**Tests.** As above.

**Cross-file impact.** `scripts/wiki_answer.py`, `tests/test_wiki_answer.py`.

---

### Phase K — Docs sweep + re-install skill

**Problem.** v2 §Phase 8. Skill template propagates to 5 assistant targets; updating in repo without re-installing leaves every installed assistant unaware of ultra mode.

**Change.**

| File | Update |
|---|---|
| `README.md` | Add `ultra` row to depth table; add `--recency-halflife-days`, `--legacy-scorer`, `--workers` to flags table; add "Ultra mode" section explaining cost (3-5s, 2 search calls + 5+2 body fetches) and when to use it |
| `skills/search-wiki.md` | Add `ultra` row + trigger phrases: "ultra search", "research mode", "exhaustive", "leave no stone unturned", "ultrathink the wiki" |
| `CLAUDE.md` | Add ultra row to depth table (currently lists 3 modes) |
| `confluence-retriever-implementation.md` | Extend retrieval-depth section; document new flags |
| `COPILOT_CLI_QUICK_REFERENCE.md` | Add ultra mode + `--verbose` troubleshooting tip (the latter is a v1 carry-over noted in v1 Fix 7 §cross-file) |

After repo files land, re-run for each target:
```
python3 install.py --target claude
python3 install.py --target codex
python3 install.py --target gemini
python3 install.py --target copilot
python3 install.py --target agents
```

**Verification.**
```
grep -l "ultra" ~/.claude/skills/search-wiki/SKILL.md \
                ~/.codex/skills/search-wiki/SKILL.md \
                ~/.gemini/skills/search-wiki/SKILL.md \
                ~/.copilot/skills/search-wiki/SKILL.md \
                ~/.agents/skills/search-wiki/SKILL.md
# expect: all five paths printed
```

**Cross-file impact.** Five doc files + five installed skill files.

---

### Phase L — `pyproject.toml` + entry point

**Problem.** v2 §Phase 9 deferred. Users today must invoke `python3 scripts/wiki_answer.py …` with a full path.

**Change.** Add `pyproject.toml` with:
- Project name `confluence-retriever`
- Runtime deps mirroring `requirements.txt`
- `[project.scripts] wiki-answer = "wiki_answer:main"` (requires moving `scripts/wiki_answer.py` into a package or pointing to a thin shim — recommendation: leave the script in place and add a tiny `src/confluence_retriever/__init__.py` that re-exports `main`).
- Dev deps under `[project.optional-dependencies] dev = [...]` matching `requirements-dev.txt`.

`install.py` must be re-tested to confirm the path it substitutes into the skill template still resolves correctly.

**Tests.** `test_install.py` covers; add one round-trip test that installs in editable mode in a temp venv and runs `wiki-answer --help`.

**Cross-file impact.** New `pyproject.toml`; possible restructure under `src/`; `install.py` path resolution.

---

## 5. Final Verification Pass

After all 12 phases land:

```bash
cd /mnt/c/dev/github/confluence-retriever

# 1. v1 tail is dead
! grep -RIn "include[_-]body\|^fixtures\|^tasks" *.md .github/ && echo "OK"

# 2. Full suite green including new invariants
pytest -q tests/

# 3. No bare excepts in production code
! grep -n "except Exception:\s*pass" scripts/wiki_answer.py && echo "OK"

# 4. Help surface lists every new flag
python3 scripts/wiki_answer.py --help | grep -E "depth.*ultra|recency-halflife-days|legacy-scorer|workers" | wc -l
# expect: 4

# 5. Ultra end-to-end with mocks (covered by pytest above); manual smoke checklist in Phase J §2 must be ticked off by hand

# 6. Skill installed everywhere
for t in claude codex gemini copilot agents; do
  python3 install.py --target $t --check | grep -q ultra || echo "MISSING: $t"
done

# 7. JSON schema includes cross-link fields
python3 scripts/wiki_answer.py --query "anything" --depth ultra --json | python3 -m json.tool >/dev/null && echo "OK"
```

---

## 6. Acceptance Criteria

Ultra mode ships only if all hold:

- [ ] Phases A–L all merged as separate commits, each independently green
- [ ] `pytest tests/` — all existing tests still pass
- [ ] `tests/test_scorer_invariants.py` exists; every xfail flipped to pass by Phase I
- [ ] No `except Exception: pass` in `scripts/`
- [ ] `get_pages()` warns on missing pages; user sees signal when fetches fail
- [ ] Auth failure in `search_combined`'s title call propagates as exit 3 (parity with text search)
- [ ] `--depth links | skim | deep` ranking bit-for-bit identical to pre-v3 (modulo parallel-fetch wall-clock)
- [ ] `--depth ultra --legacy-scorer` recovers legacy ranking exactly
- [ ] `--workers N` plumbed through; default 4
- [ ] `skills/search-wiki.md` reinstalled to all 5 targets; ultra trigger phrases present
- [ ] Manual smoke checklist in Phase J §2 ticked off

---

## 7. Commit Strategy

One commit per phase. Suggested messages (per `~/.claude/rules/common/git-workflow.md`):

```
docs: scrub v1 cleanup tail (include-body, fixtures, tasks references)
test: add scorer-invariant property scaffold with xfail markers
refactor: replace worker-thread sys.exit with typed adapter exceptions; add --workers
fix: _proximity_bonus no longer triggers on a single repeated token
feat: expand_queries gains structural variants (drop-leading, drop-trailing, core token)
fix: search_combined surfaces auth errors and appends title-only results
fix: extract_cross_links matches no-trailing-slash and /wiki/spaces/ paths
fix: cross-link entries use real Confluence webui URL
feat: multiplicative recency decay + --legacy-scorer escape hatch
feat: wire --depth ultra end-to-end with full mocked test
docs: document ultra mode in README, skill template, CLAUDE.md; reinstall skill
feat: pyproject.toml with wiki-answer entry point
```

Do **not** bundle. Phase B (the test scaffold) in particular must land alone so the invariants are auditable in `git log` before any code that relies on them.

---

## 8. Risks & Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Phase I changes ranking for non-ultra paths by mistake | HIGH | Phase B's `--legacy-scorer` parity test + the bit-for-bit clause in §6 acceptance criteria |
| Multiplicative recency overcorrects, all results sink to score 0 for old wiki | MEDIUM | Default `--recency-halflife-days` only applied with `--depth ultra`; default is *off* (None); explicit value required to opt in |
| Reinstalling skill to 5 targets misses one assistant the user hasn't installed | LOW | `install.py` already errors if target directory cannot be created; print summary at end of phase |
| `pyproject.toml` restructure breaks `install.py` path resolution | MEDIUM | Phase L test installs in temp venv and runs `wiki-answer --help`; rolls back if path substitution fails |
| Cross-link expansion silently returns empty for non-Cloud Confluence instances (legacy `/display` URLs) | LOW | Phase G docstring states the non-coverage; if a user reports it, add the second regex alternative |
| Real-world precision regression for an existing query that used to rank well | MEDIUM | Phase J §2 manual smoke checklist + `--legacy-scorer` rollback knob |

---

## 9. Out of Scope (Deferred Intentionally)

- **BM25 / TF-IDF.** Same rationale as v2 §9. Enhanced keyword scorer covers most of the same ground without IDF corpus-stat awkwardness.
- **Embedding rerank.** Would break the dumb-retriever contract. If wanted, build as a sibling tool consuming `--json`.
- **Manually curated precision fixtures.** Same rationale as v2; property tests substitute.
- **Persistent cross-invocation page cache.** Per-run cache is enough for ultra mode itself.
- **Multi-space CQL (`space in (A, B)`).** Pre-existing deferred.
- **BOM-tolerant `.env` parsing.** Pre-existing deferred.
- **`/display/SPACE/Title` legacy cross-link expansion** — explicit non-goal in Phase G; revisit if a Server-edition user reports it.

---

## 10. Files Touched

| File | Phases |
|---|---|
| `scripts/wiki_answer.py` | C, D, E, F, G, H, I, J, L |
| `tests/test_wiki_answer.py` | C, D, E, F, G, H, I, J |
| `tests/test_scorer_invariants.py` (new) | B, I, J |
| `README.md` | K |
| `skills/search-wiki.md` | K |
| `CLAUDE.md` | K |
| `confluence-retriever-implementation.md` | K |
| `COPILOT_CLI_QUICK_REFERENCE.md` | K |
| `.github/copilot-instructions.md` | A |
| `IMPLEMENTATION_PLAN.md` (if extant) | A |
| `pyproject.toml` (new) | L |
| Installed skill files (5 targets) | K |

No upstream dep changes, no schema changes, no breaking changes to existing depths.

---

## 11. What v3 Does Not Do

- Re-derive the v2 scoring philosophy — v2's design principles (algorithmic over AI, properties over benchmarks, opt-in only) are inherited unchanged.
- Re-justify ultra mode's existence — that conversation already happened in v2 §1–3.
- Touch `--depth links | skim | deep` semantics. Only `deep` becomes faster (parallel body fetch, already in the uncommitted code) and only as an observable side effect of Phase C plumbing.
