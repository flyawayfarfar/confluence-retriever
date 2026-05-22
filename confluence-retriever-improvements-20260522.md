# Confluence Retriever — Improvements Plan

**Date:** 2026-05-22
**Author:** Drafted via codebase audit during the forge-retriever feasibility exercise.
**Status:** Planned. Each fix is independently safe and verifiable; execute in order.
**Target repo:** `/mnt/c/dev/github/confluence-retriever/`

---

## 1. Context

While auditing `confluence-retriever` as the reference implementation for a parallel `forge-retriever` project, eight issues surfaced that are worth fixing in `confluence-retriever` first — partly because the forge-retriever effort was shelved (no PAT path to The Forge's project search endpoints), partly because every issue improves the existing tool on its own merits.

The fixes are grouped by leverage. **High-leverage** ones are bugs or dead weight that should not exist; **medium-leverage** ones are real ergonomic improvements with low risk. None of them change the core "dumb retriever, smart host" contract or the CLI's externally observable behaviour for default invocations.

Each fix is laid out as:
- **Problem** — concrete file:line citation
- **Change** — specific code/file edits required
- **Verification** — one-line check that proves the fix landed
- **Cross-file impact** — anything else that needs updating in lockstep

---

## 2. Execution Order

Execute top-to-bottom. The order moves from "pure subtraction" (safe deletes, bug fixes) toward "additive changes" (new flags, new CI). Each fix is a separate commit.

| # | Fix | Risk | Type |
|---|---|---|---|
| 1 | Fix `install.py` missing `import sys` | None | Bug |
| 2 | Remove empty `fixtures/` and `tasks/` directories | None | Cleanup |
| 3 | Drop the `--include-body` legacy alias | Low | Subtraction |
| 4 | Split `requirements.txt` into runtime vs dev | Low | Refactor |
| 5 | Pin dependency upper bounds | Low | Hardening |
| 6 | Add `--json` output mode | Low | Feature |
| 7 | Add `--verbose` / `-v` logging flag | Low | Feature |
| 8 | Add GitHub Actions CI workflow | Low | Infra |

Estimated total time: ~2 hours for an agent doing all eight in sequence.

---

## 3. Fix 1 — `install.py` missing `import sys`

### Problem
`install.py:55-56` calls `sys.exit(1)` inside the "skill template not found" error path, but `sys` is never imported at the top of the file. If `skills/search-wiki.md` is ever missing, the error handler itself crashes with `NameError: name 'sys' is not defined` instead of printing the helpful error message.

```python
# install.py:1-18 — current imports
import argparse
import os
from pathlib import Path
# ← sys is not here

# install.py:55-56 — references sys without import
print(f"ERROR: skill template not found at {SKILL_TEMPLATE}", file=sys.stderr)
sys.exit(1)
```

### Change
Add one line to the import block at the top of `install.py`:

```python
import argparse
import os
import sys                       # ← add this line
from pathlib import Path
```

### Verification
```bash
mv skills/search-wiki.md skills/search-wiki.md.bak
python3 install.py --check       # should print clean error + exit 1, NOT a traceback
mv skills/search-wiki.md.bak skills/search-wiki.md
```

### Cross-file impact
None.

---

## 4. Fix 2 — Remove empty `fixtures/` and `tasks/` directories

### Problem
Both directories are committed but empty. They appear in the project tree, the README/AGENTS docs reference them implicitly via the structure, and contributors waste cycles wondering what should go in them.

`confluence-retriever-implementation.md:182` mentions `precision-fixtures.json` as a "useful regression guard" but explicitly notes "not yet written". `tasks/` has no documented purpose at all.

### Change
Option A (recommended): **Delete both directories**.

```bash
rmdir fixtures tasks
```

Option B: **Document their intended purpose** with a placeholder `README.md` in each, if you genuinely intend to populate them within the next sprint.

If choosing Option A, also audit `README.md` (file tree section) and `confluence-retriever-implementation.md` to remove any references to the deleted directories.

### Verification
```bash
ls -la fixtures tasks 2>&1   # should report "No such file or directory"
git status                    # should show two directories removed
```

### Cross-file impact
- `README.md` — remove the two lines from the file tree.
- `confluence-retriever-implementation.md` — §12 ("Precision Fixtures") can stay as a forward-looking note, but rephrase to "would live under a `fixtures/` directory (not yet created)".

---

## 5. Fix 3 — Drop the `--include-body` legacy alias

### Problem
`wiki_answer.py:394-397` defines `--include-body` as a "compatibility alias for `--depth skim`". The project is one month old (started 2026-04-29 per `confluence-retriever-implementation.md`) — there is no legacy to preserve. The flag adds three things that all cost something:

1. A second argparse entry on the help text (~80 chars of clutter)
2. A branch in `resolve_body_options()` at `wiki_answer.py:364`: `effective_depth = "skim" if include_body and depth == "links" else depth`
3. A line in the skill prompt at `skills/search-wiki.md:90` that AI assistants might propagate

### Change

**In `scripts/wiki_answer.py`:**

Delete lines 394-397 (the argparse block):
```python
parser.add_argument(
    "--include-body", action="store_true",
    help="Alias for --depth skim. Kept for compatibility.",
)
```

Update `resolve_body_options()` signature at `wiki_answer.py:357-368` to remove the `include_body` parameter:
```python
def resolve_body_options(
    depth: str,
    body_top: Optional[int],
    body_chars: Optional[int],
) -> tuple[int, int]:
    """Return the number of page bodies to fetch and characters per body."""
    default_top, default_chars = DEPTH_BODY_DEFAULTS[depth]
    resolved_top = default_top if body_top is None else body_top
    resolved_chars = default_chars if body_chars is None else body_chars
    return max(0, resolved_top), max(0, resolved_chars)
```

Update the call site at `wiki_answer.py:426`:
```python
body_top, body_chars = resolve_body_options(args.depth, args.body_top, args.body_chars)
```

**In `skills/search-wiki.md`:**

Delete the `--include-body` row from the flags reference table (line ~90).

**In `tests/test_wiki_answer.py`:**

Update `TestResolveBodyOptions` to drop the `include_body=False/True` parameter from all its calls.

### Verification
```bash
grep -n "include[_-]body" scripts/wiki_answer.py skills/search-wiki.md tests/  # should return nothing
python3 scripts/wiki_answer.py --help | grep -i include  # should return nothing
pytest -q tests/                                          # all tests still green
```

### Cross-file impact
- `scripts/wiki_answer.py` — 3 edits (delete argparse entry, simplify signature, simplify call site)
- `skills/search-wiki.md` — 1 line removed
- `tests/test_wiki_answer.py` — update `TestResolveBodyOptions` cases
- `confluence-retriever-implementation.md:72` — remove the `--include-body` row from the CLI flags table
- `COPILOT_CLI_SETUP.md` — search for `include-body` and remove any references
- `.github/copilot-instructions.md` — search for `include-body` and remove any references

---

## 6. Fix 4 — Split `requirements.txt` into runtime vs dev

### Problem
`requirements.txt` currently bundles test-only dependencies (`pytest`, `responses`) with runtime ones. End users who install the CLI pull a test framework they will never run. This is also the wrong shape for a future `pyproject.toml`.

```
# requirements.txt — current
requests>=2.28.0
beautifulsoup4>=4.11.0
python-dotenv>=1.0.0
pytest>=7.0           ← dev-only
responses>=0.20.0     ← dev-only
```

### Change

Rewrite `requirements.txt` to runtime-only:
```
requests>=2.28.0
beautifulsoup4>=4.11.0
python-dotenv>=1.0.0
```

Create new file `requirements-dev.txt`:
```
-r requirements.txt
pytest>=7.0
responses>=0.20.0
```

The `-r requirements.txt` line means `pip install -r requirements-dev.txt` installs everything (runtime + dev). End users run `pip install -r requirements.txt` for a leaner install.

### Verification
```bash
# Fresh venv test
python3 -m venv /tmp/cr-runtime && /tmp/cr-runtime/bin/pip install -r requirements.txt
# Confirm pytest NOT installed
/tmp/cr-runtime/bin/pip show pytest 2>&1 | grep -q "not found" && echo "OK"

python3 -m venv /tmp/cr-dev && /tmp/cr-dev/bin/pip install -r requirements-dev.txt
# Confirm both pytest AND requests installed
/tmp/cr-dev/bin/pip show pytest >/dev/null && /tmp/cr-dev/bin/pip show requests >/dev/null && echo "OK"
```

### Cross-file impact
- `README.md` — update install instructions to show both forms (runtime vs dev).
- `AGENTS.md` — update the "Build commands" section to use `requirements-dev.txt` for the test workflow.
- `GEMINI_SETUP.md`, `COPILOT_CLI_SETUP.md` — these are end-user docs; they should keep recommending `requirements.txt` (runtime).
- `.github/copilot-instructions.md` — update the dev environment setup section.
- `.github/workflows/test.yml` (created in Fix 8) — should install `requirements-dev.txt`.

---

## 7. Fix 5 — Pin dependency upper bounds

### Problem
Current `requirements.txt` uses only lower bounds (`>=2.28.0`). When `requests` ships v3 or `beautifulsoup4` ships v5 with breaking changes, every fresh install of the tool will silently break.

### Change

Update **both** `requirements.txt` and `requirements-dev.txt` (after Fix 4) to add upper bounds aligned with the current major versions:

`requirements.txt`:
```
requests>=2.28,<3
beautifulsoup4>=4.11,<5
python-dotenv>=1.0,<2
```

`requirements-dev.txt`:
```
-r requirements.txt
pytest>=7.0,<9
responses>=0.20,<1
```

### Verification
```bash
pip install -r requirements-dev.txt --dry-run 2>&1 | grep -E "requests|beautifulsoup4|python-dotenv|pytest|responses"
# All five lines should show resolved versions within the pinned ranges
pytest -q tests/   # full suite still green
```

### Cross-file impact
None — only `requirements*.txt` change.

---

## 8. Fix 6 — Add `--json` output mode

### Problem
The CLI emits Markdown only. This is fine for the AI-host pattern but limiting in two ways:
1. **Golden-file testing is brittle** — testing Markdown output requires string-comparing fragile formatting.
2. **Non-AI callers can't compose it** — a future shell script or downstream tool that wants to pipe `wiki_answer.py` output into `jq` or another processor can't.

### Change

In `scripts/wiki_answer.py:build_parser()`, add:
```python
parser.add_argument(
    "--json", action="store_true",
    help="Emit results as JSON instead of Markdown",
)
```

In `main()`, branch the output:
```python
import json   # add to imports at top of file

# After body fetching, before the Markdown loop:
if args.json:
    payload = {
        "queries": args.query,
        "space": args.space,
        "depth": args.depth,
        "results": [
            {
                "rank": i + 1,
                "id": r["id"],
                "title": r["title"],
                "url": r["url"],
                "space_key": r["space_key"],
                "space_name": r["space_name"],
                "excerpt": r["excerpt"],
                **(body_by_id.get(r["id"], {})),
            }
            for i, r in enumerate(ranked)
        ],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    sys.exit(EXIT_OK)

# Otherwise fall through to existing Markdown code
```

### Verification
```bash
python3 scripts/wiki_answer.py --query "test" --limit 2 --json | python3 -m json.tool >/dev/null && echo "Valid JSON"
python3 scripts/wiki_answer.py --query "test" --limit 2          # still emits Markdown
```

Add a `TestJsonOutput` test class in `tests/test_wiki_answer.py` with at least:
- `test_json_mode_outputs_valid_json`
- `test_json_mode_includes_body_passages_when_depth_skim`
- `test_json_mode_excludes_markdown_artifacts`

### Cross-file impact
- `tests/test_wiki_answer.py` — new test class.
- `README.md` — add `--json` to the flags table.
- `skills/search-wiki.md` — add a note that `--json` exists but the skill should normally use the default Markdown output (so AI assistants don't switch to JSON unnecessarily).
- `confluence-retriever-implementation.md` — add `--json` to the CLI flags table in §6.

---

## 9. Fix 7 — Add `--verbose` / `-v` logging flag

### Problem
When the CLI fails in the field (a 401, a malformed CQL string, a slow API call, an unexpected response shape), debugging requires the user to either run with `set -x` or for the maintainer to insert `print()` statements. There's no in-tool way to see the constructed CQL, the request URL, or response timing.

### Change

In `scripts/wiki_answer.py`, add at the top of the file:
```python
import logging
```

Add to `build_parser()`:
```python
parser.add_argument(
    "-v", "--verbose", action="store_true",
    help="Emit diagnostic logging to stderr (CQL, request URLs, timings)",
)
```

At the top of `main()`:
```python
logging.basicConfig(
    level=logging.DEBUG if args.verbose else logging.WARNING,
    format="[%(levelname)s] %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("wiki_answer")
```

Wire `log.debug(...)` calls into the obvious places:
- `build_cql()` — log the constructed CQL string
- `ConfluenceAdapter.search()` — log the URL + status code + result count + elapsed time
- `ConfluenceAdapter.get_page()` — log page ID + status code + body size
- `rank_results()` — log per-result score breakdown (only at DEBUG)
- `resolve_body_options()` — log resolved (top, chars) tuple
- Body-fetch loop in `main()` — log each page being fetched

### Verification
```bash
python3 scripts/wiki_answer.py --query "test" --limit 2 --verbose 2>&1 1>/dev/null | grep -E "DEBUG.*CQL|DEBUG.*search"
# Should show CQL construction + search call logs

python3 scripts/wiki_answer.py --query "test" --limit 2 2>&1 1>/dev/null
# Should be silent (default level WARNING)
```

### Cross-file impact
- `tests/test_wiki_answer.py` — add minimal test verifying that `--verbose` doesn't crash; existing tests should not need changes since logging defaults to WARNING.
- `README.md` — add `-v` / `--verbose` to the flags table.
- `confluence-retriever-implementation.md` — add to §6 CLI flags table.
- `COPILOT_CLI_QUICK_REFERENCE.md` — add troubleshooting tip pointing to `--verbose`.

---

## 10. Fix 8 — Add GitHub Actions CI workflow

### Problem
Tests exist (`tests/test_wiki_answer.py`, `tests/test_install.py`) but nothing enforces them. A contributor could break the suite and merge without anyone noticing until the next manual `pytest` run.

### Change

Create `.github/workflows/test.yml`:

```yaml
name: tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  pytest:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.9", "3.10", "3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip

      - name: Install dependencies
        run: pip install -r requirements-dev.txt

      - name: Run pytest
        run: pytest -q tests/

      - name: Verify install.py dry-run
        run: python3 install.py --check >/dev/null
```

### Verification
After push to a branch:
```bash
gh workflow list                                            # should show "tests"
gh run list --workflow=test.yml --limit=1                   # should show a run within a minute
gh run view --log $(gh run list --workflow=test.yml --limit=1 --json databaseId -q '.[0].databaseId')
# should end with "X passed in Y.YYs"
```

Confirm matrix expansion: four jobs (Python 3.9 / 3.10 / 3.11 / 3.12) should appear in the run summary.

### Cross-file impact
- `README.md` — add a CI status badge near the top:
  ```markdown
  ![tests](https://github.com/<owner>/confluence-retriever/actions/workflows/test.yml/badge.svg)
  ```
  (Resolve the `<owner>` placeholder against the actual repo URL.)
- This fix depends on **Fix 4** (the workflow installs `requirements-dev.txt`). Do Fix 4 first.

---

## 11. Verification Pass (Run After All Eight)

End-to-end sanity check, in order. Each must succeed.

```bash
cd /mnt/c/dev/github/confluence-retriever

# 1. No traceback on missing skill template
mv skills/search-wiki.md skills/search-wiki.md.bak && python3 install.py --check
mv skills/search-wiki.md.bak skills/search-wiki.md

# 2. Empty dirs gone
[ ! -d fixtures ] && [ ! -d tasks ] && echo "OK"

# 3. --include-body extinct
! grep -RIn "include[_-]body" scripts/ skills/ tests/ *.md && echo "OK"

# 4. Runtime install lean
python3 -m venv /tmp/cr-check && /tmp/cr-check/bin/pip install -q -r requirements.txt
/tmp/cr-check/bin/pip show pytest 2>&1 | grep -q "WARNING: Package(s) not found" && echo "OK"

# 5. Pins enforced
grep -E "<3|<5|<2|<9|<1" requirements.txt requirements-dev.txt | wc -l   # expect ≥ 5

# 6. JSON mode
python3 scripts/wiki_answer.py --query "test" --limit 1 --json | python3 -m json.tool >/dev/null && echo "OK"

# 7. Verbose logging
python3 scripts/wiki_answer.py --query "test" --limit 1 --verbose 2>&1 1>/dev/null | grep -q "DEBUG" && echo "OK"

# 8. Pytest still green (with dev deps)
/tmp/cr-check/bin/pip install -q -r requirements-dev.txt
/tmp/cr-check/bin/pytest -q tests/

# 9. CI workflow valid YAML
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/test.yml'))" && echo "OK"
```

---

## 12. Commit Strategy

One commit per fix, in execution order. Commit message format (per `~/.claude/rules/common/git-workflow.md`):

```
fix: add missing sys import to install.py error path
chore: remove unused fixtures and tasks directories
refactor: drop --include-body legacy alias
chore: split runtime and dev dependencies
chore: pin dependency upper bounds
feat: add --json output mode
feat: add --verbose logging flag
ci: add GitHub Actions test workflow
```

Do **not** bundle. Each commit should pass `pytest -q tests/` independently. This makes bisecting future regressions trivial and lets a reviewer skip-read commits that don't interest them.

---

## 13. Out of Scope (Intentionally Deferred)

These were considered during the audit and rejected for this round:

- **`pyproject.toml` + `[project.scripts]` packaging** — would let users `pip install -e .` and get `wiki-answer` on PATH. Real win, but a structural change touching the install story, the skill template path resolution, and the docs. Worth its own dedicated plan.
- **Retry/backoff on transient 429/5xx** — currently a 429 exits 4. A bounded retry with jitter would be more robust. Not urgent because Confluence rate limits are generous; can be added when first encountered in practice.
- **BOM-tolerant `.env` parsing** — Notepad on Windows can save `.env` with a UTF-8 BOM that breaks `python-dotenv` silently. Edge case; defer until a user reports it.
- **Multi-space CQL filter (`space in (A, B)`)** — current `--space` accepts one key only. YAGNI until requested.
- **Token-threshold off-by-one in `query_tokens()` vs `token_in_text()`** — `query_tokens` skips tokens shorter than 3 chars; `token_in_text` uses word-boundary matching for tokens of length ≤ 3. Tokens of exactly 3 chars are in both branches' "edge" case. Low impact in practice; track but don't fix this round.
- **`install.py --no-clobber` / backup mode** — currently overwrites silently. The template is the source of truth so this is intentional; only revisit if users start hand-editing installed skill files.

---

## 14. Critical Files Touched (Summary)

| File | Fix(es) |
|---|---|
| `install.py` | 1 |
| `fixtures/`, `tasks/` (deleted) | 2 |
| `scripts/wiki_answer.py` | 3, 6, 7 |
| `skills/search-wiki.md` | 3, 6 |
| `tests/test_wiki_answer.py` | 3, 6, 7 |
| `requirements.txt` | 4, 5 |
| `requirements-dev.txt` (new) | 4, 5 |
| `README.md` | 2, 4, 6, 7, 8 |
| `AGENTS.md` | 4 |
| `GEMINI_SETUP.md` | 4 |
| `COPILOT_CLI_SETUP.md` | 3, 4 |
| `COPILOT_CLI_QUICK_REFERENCE.md` | 7 |
| `.github/copilot-instructions.md` | 3, 4 |
| `.github/workflows/test.yml` (new) | 8 |
| `confluence-retriever-implementation.md` | 2, 3, 6, 7 |

No upstream dependencies, no schema migrations, no public API changes that would warrant a version bump. Safe to land sequentially against `main`.
