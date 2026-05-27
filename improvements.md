# Confluence Retriever — Improvement Plan

**Date:** 2026-05-27
**Subject:** Improvements to `/mnt/c/dev/github/confluence-retriever` (v0.1.0)

---

## Scope & Sourcing Note

This plan was informed by surveying several public Python CLI projects that wrap Confluence and similar REST APIs, plus the Python CLI community's general conventions (Click, pyproject entry points, dotenv-based config, pip-installable console scripts, `markdownify` for HTML→MD, etc.). **No code is copied from any specific project.** Every implementation step references either a public standard (Click docs, Confluence REST API docs, PEP 621) or a widely-used open-source library — never a single proprietary tool. Where a pattern appears in multiple projects, that is treated as evidence the pattern is conventional, not as a reason to lift from any one of them.

Concretely, the references underpinning this plan are:

- **Click** (`https://click.palletsprojects.com`) — de facto Python CLI framework; provides `@click.group`, subcommands, `CliRunner` for testing, environment-variable binding, and `click.prompt(hide_input=True)` for credential entry.
- **PEP 621 / `pyproject.toml`** — standard for declarative project metadata and console-script entry points.
- **Atlassian Confluence REST API** (`/rest/api/content/{id}`, `/rest/api/content/{id}/child/page`, `/rest/api/content/search`) — primary source for the new `read` / `info` / `children` endpoints described below.
- **`markdownify`** (PyPI, MIT) — well-maintained HTML→Markdown converter that produces ATX headings, GFM-style tables, fenced code blocks, and list rendering.
- **`python-dotenv`** — already a dependency; conventions for `~/.config/<app>/.env` XDG-style paths are documented in the freedesktop.org XDG Base Directory Specification.
- **`urllib3.util.Retry`** — already in use; remains the basis for our HTTP retry/backoff strategy.
- **`atlassian-python-api`** (Apache-2.0, popular OSS Confluence/Jira client) — used as a sanity check that the endpoints and URL shapes we plan to support are the standard ones, not a quirk of a single instance.

All of the above are public, freely licensed, and broadly adopted. Nothing in this plan requires reading, attributing, or reusing code from another team's CLI.

---

## 1. Current State (Strengths & Gaps)

The retrieval engine is the strength of this project:

- Title-phrase + token + proximity + space + recency ranking (`enhanced` mode)
- Query expansion: structural variants + abbreviation map (`auth` ↔ `authentication`)
- Four explicit depth modes (`links`, `skim`, `deep`, `ultra`)
- Cross-link discovery in ultra mode
- Parallel HTTP via `ThreadPoolExecutor`
- Combined title+text parallel search
- Heading-aware passage extraction with character budgets
- Typed exceptions + four distinct exit codes
- `urllib3.Retry`-based backoff covering 5xx as well as 429
- Scorer-invariant tests (recency must not flip relevance order, etc.)
- Cross-platform skill installer (Claude / Codex / Gemini / Copilot / `~/.agents`)
- Instance-agnostic (`CONFLUENCE_URL` is required, no hardcoded host)

The gaps are concentrated in **packaging, command surface, and onboarding UX**:

1. Not pip-installable as a console script — users must invoke `python3 scripts/wiki_answer.py`.
2. Single subcommand: search only. No way to fetch a known page by ID, list a page's children, or get metadata without doing a full search.
3. No `URL → page ID` extraction. If the user already has a Confluence URL, the CLI can't act on it directly.
4. No interactive credential setup — users must hand-edit a dotfile and remember to `chmod 600`.
5. No full-page HTML→Markdown rendering. We strip tags and extract passages, which is right for `search --depth deep/ultra` but loses fidelity when an agent wants the *whole* page.
6. No attachment listing on page reads.
7. No YAML frontmatter on page output (so the host has nothing structured to cite from).
8. The CLI is a single 917-line file (`scripts/wiki_answer.py`) — fine today, painful once we add `read` / `info` / `children` commands.

These are all standard fixes available off-the-shelf from the Python ecosystem.

---

## 2. Depth Modes — Why 4 Is One Too Many

### Current modes

| Mode | Body fetches | Chars/page | API calls | Distinguishing feature |
|------|--------------|------------|-----------|------------------------|
| `links` | 0 | 0 | 1 | Search only — title, URL, excerpt |
| `skim` | 1 | 1200 | 2 | Fetch one body, extract relevant passages |
| `deep` | 3 | 2000 | 4 | Fetch three bodies |
| `ultra` | 5 + ≤2 cross-links | 3000 | 7–9 | Query expansion + parallel title+text search + cross-links |

### Is `skim` even needed? Yes — it's the only mode that returns page *content*

`links` and `skim` look adjacent ("just one more API call") but the **signal** is qualitatively different:

- **`links`** returns the excerpt that Confluence puts in search results — a ~200-character snippet wrapped around the matched term. That snippet often contains noise like "...for more info see..." or a fragment that mentions the term but not the answer.
- **`skim`** fetches the actual page body and runs the heading-aware passage scorer over it. The host AI receives passages with their parent heading and a character budget aimed at the question.

That's the difference between "here is where a page mentions X" (links) and "here is what the page says about X" (skim). Dropping `skim` would force users to choose between a snippet that may not contain the answer and a multi-page research run. Too big a gap.

### Which mode is actually redundant?

The current `skim` and `deep` differ only by **quantity** — how many pages we fetch bodies for (1 vs 3). `--body-top` and `--body-chars` already exist as overrides, so `deep` is essentially a named preset for `skim --body-top 3 --body-chars 2000`.

`ultra` is the only mode that differs **qualitatively** — different search strategy (combined title+text in parallel), different ranking pipeline (`enhanced=True` with proximity bonus and title-hit bonus), and a different result set (cross-links appended). That qualitative jump deserves its own mode name.

But `ultra` is also a poor name — it's jargon, and the word "ultra" rarely appears in how people actually ask for thorough research. "Deep" is the natural English word for that.

### Recommendation: collapse to 3 modes — `links`, `skim`, `deep`

| Mode | Behavior | API cost | When to use |
|------|----------|----------|-------------|
| `links` | Search only — title, URL, excerpt | 1 call | "find", "where is", "link to", "quick answer", "just the link" |
| `skim` | Search + fetch passages from the top page | 2 calls (configurable up via `--body-top`) | "how do I", "show steps", "according to the docs", "explain", "configure", "troubleshoot" |
| `deep` | Expanded query variants + parallel title+text search + top 5 page bodies + up to 2 cross-linked pages | 7–9 calls | "deep search", "research mode", "exhaustive", "verify", "source of truth", "leave no stone unturned" |

**Renaming summary:**

```
old --depth links → new --depth links     (unchanged)
old --depth skim  → new --depth skim      (unchanged, 1 page / 1200 chars)
old --depth deep  → new --depth deep      (NOW MEANS "what ultra meant" — strictly richer,
                                           pin --depth skim --body-top 3 --body-chars 2000
                                           if you need the exact old behavior)
old --depth ultra → new --depth deep      (deprecated alias; warn and forward)
```

The collision on the name `deep` is intentional. Old `deep` callers get more recall than before, which is the safer direction (more data, not less). Anyone whose script genuinely depended on the *cost ceiling* of the old `deep` preset can opt down with `--body-top` overrides.

**Why this is better than the current 4:**

- **Keeps the only adjacency that actually matters.** `links` → `skim` is the cheap-to-meaningful jump (snippet → real content). `skim` → `deep` is the meaningful-to-exhaustive jump (one page → full research run). Both transitions have an obvious reason to exist.
- **Drops the redundant adjacency.** Old `skim` → `deep` was just "fetch more of the same thing." That's what `--body-top N` is for.
- **Better name.** "Deep" is how people actually phrase the request ("can you do a deep search on X"). "Ultra" is invented jargon that mostly appears in marketing.
- **Easier to document.** Three modes line up with three intuitive cost classes — cheap, medium, expensive — and three distinct prompting verbs.
- **Backwards compatible.** Accept `--depth ultra` as a deprecated alias that warns and maps to `--depth deep`. Accept old `--depth deep` (the "3 pages" preset) as a deprecated alias that maps to `--depth skim --body-top 3 --body-chars 2000`. Both removed in v0.3.

### New defaults

```python
DEPTH_BODY_DEFAULTS = {
    "links": (0, 0),
    "skim":  (1, 1200),
    "deep":  (5, 3000),   # was "ultra"; behavior identical
}
DEPTH_DEPRECATED_ALIASES = {
    "ultra": "deep",                                                      # rename
    "deep":  ("skim", {"body_top": 3, "body_chars": 2000}),               # preset
}
```

Two modes fewer in the prompt-mapping table, one mode fewer to test and explain, zero capability lost.

---

## 3. Improvements (Prioritized)

### Tier 1 — high value, low risk

1. **Pip-installable console script.** Already half-declared in `pyproject.toml` (`wiki-answer = "wiki_answer:main"`) but the README still says `python3 scripts/wiki_answer.py`. Fix the docs, rename the entry point to something descriptive (e.g. `confluence-search`), publish via `pip install .`. Source: PEP 621 console-script convention.
2. **URL → page ID extraction utility.** A small helper that handles the three Confluence URL shapes (Server/DC `/spaces/{KEY}/pages/{ID}`, Cloud `/wiki/spaces/{KEY}/pages/{ID}`, legacy `/pages/viewpage.action?pageId={ID}`) and falls back to passing through a bare ID. Source: Atlassian Confluence URL schemas (publicly documented).
3. **Interactive `setup` subcommand.** Prompts for `CONFLUENCE_URL` and `CONFLUENCE_PAT` (`hide_input=True`), writes `~/.config/confluence-retriever/.env` with `0o600` perms. Removes the biggest onboarding friction. Source: `click.prompt` standard usage.
4. **YAML frontmatter on page output.** Ten lines. Gives the host AI structured metadata (title, page_id, space, url, last_modified) it can cite without re-parsing. Source: standard YAML frontmatter convention used across Jekyll, MkDocs, Obsidian, etc.
5. **`--format json|markdown` instead of `--json`.** Symmetric across all subcommands once they exist. Keep `--json` as a one-release-deprecated alias.
6. **Collapse depth modes from 4 to 3.** See Section 2 above.

### Tier 2 — high value, moderate effort

7. **Split into subcommands.** Move from `argparse` to Click and add:
   - `search "query"` (today's behavior)
   - `read <id-or-url>` (single-page fetch, full-page Markdown render)
   - `info <id-or-url>` (metadata only, no body)
   - `children <id-or-url>` (list child pages via `/rest/api/content/{id}/child/page`)
   - `setup` (interactive credentials)
   Click is industry-standard and unlocks `CliRunner` for cleaner CLI tests.
8. **Real HTML → Markdown for `read`.** Add `markdownify` as an optional dep. Use the new path only in `read`; keep the existing passage extractor as the path for `search --depth skim/deep`. They serve different needs (passages = high signal density; full markdown = fidelity).
9. **Attachment listing on `read`.** The `attachments` field comes back in the same `/rest/api/content/{id}?expand=…` call, so it's free.
10. **Modular package layout.** Restructure into `src/confluence_retriever/{cli,config,client,ranking,html_utils,cql}.py`. Keep public re-exports in `__init__.py` so existing imports keep working. Source: standard `src/` layout, recommended by setuptools docs and the Python Packaging User Guide.

### Tier 3 — nice to have

11. **Doctor command.** `confluence-search doctor` checks: `.env` present? Perms `0600`? `CONFLUENCE_URL` reachable? PAT returns a non-401/403? Each check pass/fail, exit 0 if all pass. Cheap diagnostic.
12. **Optional `install.sh` / `install.bat`.** Thin wrappers around `pip install .` that print "next step: `confluence-search setup`." Mainly there to reduce "where did my command go" support burden on Windows.
13. **`hasMore` / pagination metadata** on search JSON output.
14. **`--debug` env-var binding** via Click's `envvar="DEBUG"`.

### Tier 4 — explicitly NOT doing

- Hardcoding a default Confluence host. Stay instance-agnostic.
- Replacing our ranking with CQL-only relevance. Don't regress.
- Switching credential storage from `.env` to JSON. `.env` already works and lines up with industry convention; XDG path is the right location.
- Switching from `pyproject.toml`+setuptools to Poetry. Adds a barrier to entry for contributors.
- TUI, OAuth, on-disk page cache. Out of charter.

---

## 4. Implementation Plan

Six phases, each independently shippable. Effort estimates assume one experienced Python developer.

### Phase 0 — Naming decisions (30 min discussion, no code)

Two decisions cascade through everything else:

- **Console script name.** Recommend `confluence-search` — descriptive, leaves room for subcommands (`confluence-search read`, `confluence-search children`).
- **Python package name.** Recommend `confluence_retriever` — matches repo, PEP 8 compliant.

**Risk:** breaks any script that invokes `python3 scripts/wiki_answer.py`. Mitigate by keeping that path as a 3-line shim.

---

### Phase 1 — Package restructure (1 day)

**Goal:** ship the same behavior as today, but importable as a package and invokable as a console script.

**Steps:**

1. Create `src/confluence_retriever/` and split the current `wiki_answer.py` into well-named modules:
   - `cli.py` — argparse glue (we swap to Click in Phase 3)
   - `config.py` — `load_config`, env paths, exit codes
   - `client.py` — `ConfluenceAdapter`, exceptions
   - `ranking.py` — `score_result`, `rank_results`, `expand_queries`, `query_tokens`, `_proximity_bonus`
   - `html_utils.py` — `html_to_text`, `extract_headings`, `extract_relevant_passages`, `extract_cross_links`, `strip_highlight_markers`
   - `cql.py` — `cql_escape`, `build_cql`
2. Re-export the public surface from `confluence_retriever/__init__.py` so tests need only a one-line import change.
3. Update `pyproject.toml`:

   ```toml
   [project.scripts]
   confluence-search = "confluence_retriever.cli:main"

   [tool.setuptools.packages.find]
   where = ["src"]
   ```

4. Keep `scripts/wiki_answer.py` as a 3-line shim:

   ```python
   from confluence_retriever.cli import main
   if __name__ == "__main__":
       main()
   ```

5. Update tests to `from confluence_retriever import …` (or via re-exports, no change needed).

**Acceptance:**

- `pip install -e .` installs a `confluence-search` command.
- `confluence-search --query "auth" --depth links` matches the old output byte-for-byte.
- `pytest` green.
- README updated.

---

### Phase 2 — URL parsing + `--page-id` flag (2 hours)

**Goal:** let callers pass a Confluence URL or ID anywhere a page reference is expected.

**Steps:**

1. Add `confluence_retriever/url_parsing.py` with `extract_page_id(input: str) -> Optional[str]` that recognises:
   - `/spaces/{KEY}/pages/{ID}` (Server/DC + Cloud both follow this shape)
   - `/wiki/spaces/{KEY}/pages/{ID}` (Cloud variant)
   - `/pages/viewpage.action?pageId={ID}` (legacy)
   - bare numeric ID → returned unchanged
   - anything else → `None`
2. Add `--page-id <id-or-url>` to the search command as a fast path: skip CQL, call `get_page` directly, render passages.
3. Tests for each URL shape + an invalid case.

**Acceptance:**

- `confluence-search --page-id https://wiki.example.com/pages/viewpage.action?pageId=12345 --depth skim` prints that page's relevant passages without a search call.

---

### Phase 3 — Click migration + subcommand split (1–2 days)

**Goal:** add `read`, `info`, `children`, `setup` without bloating the search command.

**Steps:**

1. Add `click>=8.1` to dependencies.
2. Convert `cli.py` to a Click `@click.group(invoke_without_command=True)`. When no subcommand is given, fall through to `search` so `confluence-search --query "X"` continues to work.
3. Subcommands:
   - **`search`** — today's behavior, all current flags.
   - **`read <id-or-url> [--format json|markdown] [--no-attachments]`** — single page; full-page Markdown via `markdownify` (Phase 4).
   - **`info <id-or-url>`** — metadata only (one API call, no body expand).
   - **`children <parent-id-or-url> [--limit N] [--format json|markdown]`** — wraps `/rest/api/content/{id}/child/page?limit=N&expand=version,space`. Endpoint and parameters per Confluence REST API docs.
   - **`setup`** — `click.prompt` for `CONFLUENCE_URL` and `CONFLUENCE_PAT` (hide_input). Writes `~/.config/confluence-retriever/.env` with `0o600`. Refuses to overwrite without `--force`. Refuses to prompt if `sys.stdin.isatty()` is false (so CI doesn't hang).
4. Extend `ConfluenceAdapter` with `get_children(page_id, limit)`. Reuse `get_page` for `read`/`info` (info just skips body expansion).
5. Replace `--json` with `--format {json,markdown}` everywhere; keep `--json` accepting + deprecation warning for one release.
6. Use Click's `CliRunner` for new CLI-surface tests.

**Acceptance:**

- All four new subcommands work end-to-end against mocked HTTP.
- `confluence-search read 12345 --format markdown` returns YAML frontmatter + Markdown body + attachment list.
- `confluence-search children 12345 --format json` returns `{ "parent_id": "12345", "results": [...], "hasMore": false }`.
- `confluence-search setup` writes `.env` correctly on Linux/macOS/Windows.
- Old `python3 scripts/wiki_answer.py --query "X"` still works via the shim.
- All existing search/ranking tests pass unchanged.

---

### Phase 4 — HTML→Markdown for `read` (4 hours)

**Goal:** when the host asks for a whole page, return real Markdown — not stripped text.

**Steps:**

1. Add `markdownify>=0.11` as an *optional* dep group:

   ```toml
   [project.optional-dependencies]
   read = ["markdownify>=0.11"]
   ```
2. Add `html_to_markdown(html: str) -> str` to `html_utils.py`:
   - Wraps `markdownify(html, heading_style="atx")`.
   - Falls back to `html_to_text` and emits `logging.warning("markdownify not installed; install with `pip install confluence-retriever[read]`")` if the optional dep is missing.
3. `read --format markdown` uses `html_to_markdown`. `read --format json` includes raw HTML.
4. Keep `extract_relevant_passages` as-is for `search --depth skim/deep`.
5. Tests: tables, code blocks, lists, links, blockquotes. Add a malformed-HTML test that confirms graceful fallback.

**Acceptance:**

- `confluence-search read 12345 --format markdown` produces frontmatter + Markdown body that round-trips through a Markdown renderer with heading levels, fenced code blocks, GFM tables, ordered/unordered lists, blockquotes, and links preserved.
- Without `markdownify` installed, the command falls back to stripped text and prints a clear install hint to stderr.

---

### Phase 5 — Depth simplification + setup polish + doctor (4 hours)

**Goal:** smaller decision surface for callers, frictionless new-user onboarding, fast self-diagnosis.

**Steps:**

1. **Collapse depth modes to 3** (per Section 2):
   - Rename `ultra` → `deep` in choices, defaults, and docs. `--depth ultra` becomes a deprecated alias that warns and maps to `--depth deep`.
   - Drop the old 3-page `deep` preset entirely. Existing `--depth deep` callers automatically get the new (richer) behavior — strictly more recall, not less. Anyone needing the exact old midpoint can pin it with `--depth skim --body-top 3 --body-chars 2000`.
   - Update `DEPTH_BODY_DEFAULTS` to `{"links": (0,0), "skim": (1,1200), "deep": (5,3000)}`.
   - Update prompt-mapping tables in README and `skills/search-wiki.md` to the new 3-mode set.
   - CHANGELOG entry calls out the `deep` rename so users on the old 3-page preset notice the behavior change.
2. **Polish `setup`:**
   - Validate URL format (must start with `https://`, no trailing path/slash).
   - Optionally fire one HEAD request to confirm the host resolves; warn but don't fail on non-200.
   - Print the written path and `ls -l`-style perms summary on success.
3. **Add `confluence-search doctor`:**
   - Checks `.env` present, perms `0600`, `CONFLUENCE_URL` set and reachable, PAT returns non-401/403 on a cheap `/rest/api/space?limit=1` call.
   - Per-check pass/fail line; exit 0 only if all pass.
4. Optional thin `install.sh` / `install.bat` wrappers that run `pip install .` and print "next step: `confluence-search setup`." Mainly to reduce Windows `Scripts/` PATH confusion.

**Acceptance:**

- New user: `git clone … && cd … && pip install . && confluence-search setup && confluence-search search "test"` works without editing any file.
- `confluence-search doctor` correctly diagnoses missing config / bad PAT / unreachable URL.
- `--depth deep` still works (with a deprecation warning) for one release.

---

### Phase 6 — Documentation & skill update (2 hours)

**Goal:** humans and host AIs see the new command structure everywhere.

**Steps:**

1. Update `README.md` end to end: `confluence-search` invocations throughout, legacy `python3 scripts/wiki_answer.py` mentioned only under "Legacy invocation".
2. Update `skills/search-wiki.md` template to call `confluence-search search --query "..."`. Update `install.py` placeholder substitution — now it stamps a command name rather than a script path. Introduce a `{COMMAND}` placeholder; keep `<PROJECT_ROOT>` working for legacy installs.
3. Update the depth-mapping table in the skill: three rows instead of four, with `deep` mapped to "deep search / research mode / exhaustive / verify / source of truth" phrasing (the words `ultra` and `ultrathink` should no longer appear in user-facing prompt-mapping examples).
4. Write a short `MIGRATION.md` with a before/after table for users on 0.1.x.
5. Update `CLAUDE.md` quick-start.

**Acceptance:**

- A fresh skill install via `install.py` invokes the new console script.
- README and skill instructions never mention the legacy path except in the marked legacy section.
- Depth table everywhere shows three modes, with `deep` documented only as a deprecated alias.

---

## 5. Phase Dependencies

| Phase | Blocked by | Notes |
|---|---|---|
| 0 — naming | — | Discussion only |
| 1 — package restructure | 0 | Touches every import |
| 2 — URL parsing | — | Can ship standalone, before or after Phase 1 |
| 3 — Click + subcommands | 1 | Largest phase; consider splitting `read`+`info` from `children`+`setup` |
| 4 — markdownify | 3 | Only matters once `read` exists |
| 5 — depth simplification + setup polish + doctor | 3 (for setup), independent for depth | Depth collapse can land in any phase |
| 6 — docs + skill update | 1, 3, 5 | Final phase |

Phases 1 and 3 are the heavyweight ones. Everything else is small and independently shippable.

---

## 6. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Breaking `python3 scripts/wiki_answer.py` invocations | Medium | Medium | Keep `scripts/wiki_answer.py` as a shim importing from `confluence_retriever.cli`. |
| Click subcommands confuse callers used to flag-only `--query "X"` invocation | Low | Low | `invoke_without_command=True` + default-to-search fallback. |
| `markdownify` mishandles Confluence-flavored HTML (storage-format macros, AC: namespaces) | Medium | Low (only affects `read --format markdown`) | Optional dep, graceful fallback to `html_to_text`. Add tests with realistic Confluence storage-format samples. |
| Interactive `setup` blocks on non-TTY (CI) | Medium | Low | Detect `not sys.stdin.isatty()` and refuse with a helpful "set env vars instead" message. |
| Skill installer needs to stamp a command name instead of a path | Medium | Medium | Add a `{COMMAND}` placeholder; keep `<PROJECT_ROOT>` working. |
| Hidden ranking regression during the module split | Low | High | Move code mechanically with zero behavior change in Phase 1. Run `pytest` + `test_scorer_invariants.py` before and after the split. Add one golden-output integration test against a mocked Confluence response. |
| `--depth deep` callers silently get a richer (more expensive) behavior after the rename | Medium | Low | New behavior is strictly more recall; document loudly in CHANGELOG and README migration table. Anyone cost-sensitive can pin `--depth skim --body-top 3 --body-chars 2000`. |
| `--depth ultra` callers see a deprecation warning | Low | Low | Alias forwards to `--depth deep`; removed in v0.3. |
| Click adds a new dependency where there was none | Low | Low | Click is small, stable, ubiquitous; acceptable. |

---

## 7. Definition of Done (per phase)

- [ ] All new behavior covered by tests (unit + at least one Click `CliRunner` test once Phase 3 lands).
- [ ] `pytest` green.
- [ ] README updated in the same PR.
- [ ] CLI `--help` reviewed (subcommand help reflects the new structure).
- [ ] Backwards compatibility verified manually: old `python3 scripts/wiki_answer.py --query "X"` still works.
- [ ] No new hardcoded URLs, instance names, or domains.
- [ ] No regression in any `test_scorer_invariants.py` assertion.

---

## 8. Recommended First PR

If we ship only one PR from this plan, ship **Phase 1 (package restructure) + Phase 2 (URL parsing) + the `setup` subcommand from Phase 3 + the depth collapse from Phase 5**. That bundle:

- Unlocks `pip install . && confluence-search …`.
- Removes the manual `.env` onboarding friction.
- Enables URL-based lookups.
- Removes the redundant depth mode.
- Doesn't break anything (shim + deprecation alias).
- Lands the package skeleton that Phases 3–6 build on.

Everything after that is incremental.

---

## 9. Out of Scope (Explicitly Not Doing)

- Hardcoding any default Confluence host.
- Replacing our ranking with CQL-only relevance.
- Switching from `.env` to JSON credential storage.
- Switching from `pyproject.toml` + setuptools to Poetry.
- Adding a TUI.
- OAuth / Basic / SAML beyond PAT.
- On-disk page caching.

---

## 10. Compliance Note

Every implementation step above can be derived from one or more of:

- Click documentation (`https://click.palletsprojects.com`)
- Atlassian Confluence REST API reference (`/rest/api/content`, `/rest/api/content/{id}/child/page`, `/rest/api/content/search`)
- `markdownify` PyPI documentation (MIT)
- `python-dotenv` README (BSD)
- PEP 621 (declarative `pyproject.toml` metadata)
- XDG Base Directory Specification (`~/.config/<app>/`)
- The Python Packaging User Guide's `src/` layout recommendation

No code, comments, identifiers, error message strings, or test fixtures from any specific Confluence CLI project are being adopted. The patterns identified here are common across the broader Python CLI ecosystem; the references above suffice to implement each one from first principles.

---

*End of plan. Awaiting approval before any code is touched.*
