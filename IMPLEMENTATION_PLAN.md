# Confluence Retriever — 8 Improvements Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 8 ergonomic and structural issues in confluence-retriever (bugs, dead code, missing features, CI), with zero breaking changes to the core "dumb retriever, smart host" contract.

**Architecture:** Execute fixes top-to-bottom (safe deletes → refactors → features → CI). Each fix is a separate commit that passes `pytest -q tests/` independently. After all 8 fixes, reinstall skills to propagate changes to Claude Code, Copilot, Gemini, and Codex.

**Tech Stack:** Python 3.9+, pytest + responses (mocked HTTP), GitHub Actions, Markdown (skill definitions)

---

## Pre-Implementation Checklist

- [ ] Verify current state: `git status` shows no uncommitted changes
- [ ] Confirm `.env` is configured with valid Confluence credentials
- [ ] Run baseline tests: `pytest -q tests/` (all should pass)
- [ ] Document which agents have skills installed (Claude Code, Copilot, Gemini, Codex)

---

## Task 1: Fix Missing `import sys` in install.py

**Files:**
- Modify: `install.py:1-18`

**Context:** `install.py` calls `sys.exit(1)` in the error handler at line 56 but never imports `sys`. If the skill template is missing, the error handler crashes with `NameError` instead of printing a helpful message.

- [ ] **Step 1: Verify the bug exists**

Run: `grep -n "import sys" install.py`
Expected: No output (sys not imported)

Run: `grep -n "sys.exit\|sys.stderr" install.py`
Expected: Lines 56-57 reference sys without import

- [ ] **Step 2: Add the import**

Edit `install.py` at line 52 (after `from pathlib import Path`). Add:
```python
import sys
```

Final imports section should be:
```python
import argparse
import os
import sys
from pathlib import Path
```

- [ ] **Step 3: Verify the fix**

Run: `python3 install.py --check`
Expected: Normal output (no import error)

Run: `python3 -m py_compile install.py`
Expected: No output (file compiles)

- [ ] **Step 4: Test error path with missing template**

```bash
mv skills/search-wiki.md skills/search-wiki.md.bak
python3 install.py --check 2>&1
# Expected output: "ERROR: skill template not found at ..." + exit code 1
# NOT a Python traceback
mv skills/search-wiki.md.bak skills/search-wiki.md
```

- [ ] **Step 5: Commit**

```bash
git add install.py
git commit -m "fix: add missing sys import to install.py error path"
```

---

## Task 2: Remove Empty `fixtures/` and `tasks/` Directories

**Files:**
- Delete: `fixtures/` (directory)
- Delete: `tasks/` (directory)
- Modify: `README.md:142-157` (file tree section)
- Modify: `confluence-retriever-implementation.md:182` (precision fixtures reference)

**Context:** Both directories are committed but empty. They clutter the tree and confuse contributors about what should go in them.

- [ ] **Step 1: Confirm directories are empty**

Run: `ls -la fixtures/ tasks/`
Expected: Both exist and contain no files (only `.` and `..`)

- [ ] **Step 2: Delete directories**

```bash
rmdir fixtures tasks
git status
# Expected: two directories listed as deleted
```

- [ ] **Step 3: Update README.md file tree section**

Find the file tree in `README.md` (around line 142-157). Remove these two lines:

```
│   ├── fixtures/
│   ├── tasks/
```

The remaining tree should show:
```
confluence-retriever/
├── scripts/
│   └── wiki_answer.py
├── skills/
│   └── search-wiki.md
├── tests/
│   ├── test_wiki_answer.py
│   └── test_install.py
├── install.py
├── requirements.txt
├── .env.example
├── confluence-pat-setup.md
└── confluence-retriever-implementation.md
```

- [ ] **Step 4: Update confluence-retriever-implementation.md**

Find section 12 titled "Precision Fixtures" (around line 182). It should currently say:

```markdown
### 12. Precision Fixtures

A set of real-world Confluence response shapes, captured as JSON, that exercise edge cases in the HTML parser and ranking logic. Currently sketched in `confluence-retriever-implementation.md`, `precision-fixtures.json` would live under a `fixtures/` directory as a regression guard.
```

Change to:

```markdown
### 12. Precision Fixtures

A set of real-world Confluence response shapes, captured as JSON, that exercise edge cases in the HTML parser and ranking logic. These would live under a `fixtures/` directory (not yet created) as a regression guard.
```

- [ ] **Step 5: Verify and commit**

```bash
ls -la fixtures tasks 2>&1
# Expected: "No such file or directory" for both
git status
# Expected: both dirs deleted, README.md and confluence-retriever-implementation.md modified
git add README.md confluence-retriever-implementation.md
git add -A  # Stage the deletions
git commit -m "chore: remove unused fixtures and tasks directories"
```

---

## Task 3: Drop the `--include-body` Legacy Alias

**Files:**
- Modify: `scripts/wiki_answer.py:357-368`, `394-397`, `426`
- Modify: `skills/search-wiki.md:90` (flags table)
- Modify: `tests/test_wiki_answer.py` (TestResolveBodyOptions class)
- Modify: `confluence-retriever-implementation.md:72` (CLI flags table)
- Modify: `COPILOT_CLI_SETUP.md` (search and remove references)
- Modify: `.github/copilot-instructions.md` (search and remove references)

**Context:** `--include-body` is a compatibility alias for `--depth skim` added one month ago when the tool was brand new. No users depend on it. Removing it simplifies argparse, the `resolve_body_options()` function, and the skill instructions.

- [ ] **Step 1: Verify current state**

Run: `grep -n "include.body" scripts/wiki_answer.py`
Expected: Lines showing argparse entry and resolve_body_options call

Run: `python3 scripts/wiki_answer.py --help | grep include`
Expected: Show `--include-body` flag

- [ ] **Step 2: Remove argparse entry from scripts/wiki_answer.py**

Find the `build_parser()` function. Locate lines 394-397:
```python
parser.add_argument(
    "--include-body", action="store_true",
    help="Alias for --depth skim. Kept for compatibility.",
)
```

Delete these 4 lines entirely.

- [ ] **Step 3: Simplify resolve_body_options() signature in scripts/wiki_answer.py**

Find the function definition around line 357. Current:
```python
def resolve_body_options(
    include_body: bool,
    depth: str,
    body_top: Optional[int],
    body_chars: Optional[int],
) -> tuple[int, int]:
    """Return the number of page bodies to fetch and characters per body."""
    default_top, default_chars = DEPTH_BODY_DEFAULTS[depth]
    if include_body and depth == "links":
        default_top, default_chars = DEPTH_BODY_DEFAULTS["skim"]
    resolved_top = default_top if body_top is None else body_top
    resolved_chars = default_chars if body_chars is None else body_chars
    return max(0, resolved_top), max(0, resolved_chars)
```

Replace with:
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

- [ ] **Step 4: Update call site in main()**

Find line ~426 where `resolve_body_options()` is called. Current:
```python
body_top, body_chars = resolve_body_options(args.include_body, args.depth, args.body_top, args.body_chars)
```

Replace with:
```python
body_top, body_chars = resolve_body_options(args.depth, args.body_top, args.body_chars)
```

- [ ] **Step 5: Update tests/test_wiki_answer.py**

Find the `TestResolveBodyOptions` class. Update all test method calls from:
```python
resolve_body_options(False, "links", None, None)
resolve_body_options(True, "links", None, None)
# etc.
```

To (removing first `include_body` parameter):
```python
resolve_body_options("links", None, None)
resolve_body_options("skim", None, None)  # was (True, "links", ...), now just skim
# etc.
```

All other test logic stays the same; only the function call signature changes.

- [ ] **Step 6: Update skills/search-wiki.md**

Find the CLI flags reference table (around line 90). Locate the row:
```markdown
| `--include-body` | off | Compatibility alias for `--depth skim` |
```

Delete this entire row.

- [ ] **Step 7: Update confluence-retriever-implementation.md**

Find the CLI flags table in section 6 (around line 72). Remove the row for `--include-body`.

- [ ] **Step 8: Update COPILOT_CLI_SETUP.md**

Run: `grep -n "include.body" COPILOT_CLI_SETUP.md`
If found, remove those lines or references. Expected: no matches after this step.

- [ ] **Step 9: Update .github/copilot-instructions.md**

Run: `grep -n "include.body" .github/copilot-instructions.md`
If found, remove those lines. Expected: no matches.

- [ ] **Step 10: Verify and test**

```bash
grep -rn "include.body" scripts/ skills/ tests/ *.md .github/
# Expected: No output (zero matches)

python3 scripts/wiki_answer.py --help | grep -i include
# Expected: No output (flag gone)

pytest -q tests/test_wiki_answer.py::TestResolveBodyOptions -v
# Expected: All tests pass
```

- [ ] **Step 11: Commit**

```bash
git add scripts/wiki_answer.py skills/search-wiki.md tests/test_wiki_answer.py
git add confluence-retriever-implementation.md COPILOT_CLI_SETUP.md .github/copilot-instructions.md
git commit -m "refactor: drop --include-body legacy alias"
```

---

## Task 4: Split requirements.txt into Runtime vs Dev

**Files:**
- Modify: `requirements.txt` (remove test deps)
- Create: `requirements-dev.txt` (new file, includes both)
- Modify: `README.md` (install instructions)
- Modify: `AGENTS.md` (dev environment setup)
- Modify: `.github/copilot-instructions.md` (dev setup section)

**Context:** Current `requirements.txt` includes pytest and responses (test-only). End users install unused test frameworks. Split into runtime-only + dev (which includes runtime).

- [ ] **Step 1: Review current requirements.txt**

Run: `cat requirements.txt`
Expected output:
```
requests>=2.28.0
beautifulsoup4>=4.11.0
python-dotenv>=1.0.0
pytest>=7.0
responses>=0.20.0
```

- [ ] **Step 2: Rewrite requirements.txt (runtime only)**

Replace entire contents with:
```
requests>=2.28.0
beautifulsoup4>=4.11.0
python-dotenv>=1.0.0
```

- [ ] **Step 3: Create requirements-dev.txt**

Create new file `requirements-dev.txt` with contents:
```
-r requirements.txt
pytest>=7.0
responses>=0.20.0
```

The `-r requirements.txt` line includes all runtime deps.

- [ ] **Step 4: Test both install paths**

```bash
# Fresh venv for runtime only
python3 -m venv /tmp/cr-runtime
/tmp/cr-runtime/bin/pip install -q -r requirements.txt
/tmp/cr-runtime/bin/pip show pytest requests
# Expected: requests succeeds, pytest prints "not found" or similar

# Fresh venv for dev (includes runtime)
python3 -m venv /tmp/cr-dev
/tmp/cr-dev/bin/pip install -q -r requirements-dev.txt
/tmp/cr-dev/bin/pip show pytest requests beautifulsoup4
# Expected: All three succeed
```

- [ ] **Step 5: Update README.md install section**

Find the "Install dependencies" subsection (around line 24-26). Current:
```bash
pip install -r requirements.txt
```

Replace with:
```bash
# For end users (runtime only):
pip install -r requirements.txt

# For development (runtime + test):
pip install -r requirements-dev.txt
```

- [ ] **Step 6: Update AGENTS.md**

Find the "Environment Setup" section. Update to show:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt  # ← changed from requirements.txt
```

- [ ] **Step 7: Update .github/copilot-instructions.md**

Find the "Environment Setup" subsection (around line 14-20). Update:
```bash
pip install -r requirements-dev.txt  # ← changed from requirements.txt
```

- [ ] **Step 8: Verify and commit**

```bash
ls -la requirements*.txt
# Expected: both files exist

python3 -m venv /tmp/test-split && /tmp/test-split/bin/pip install -q -r requirements.txt
/tmp/test-split/bin/pip show pytest 2>&1 | grep -q "not found\|WARNING" && echo "✓ pytest not in runtime"

git add requirements.txt requirements-dev.txt README.md AGENTS.md .github/copilot-instructions.md
git commit -m "chore: split runtime and dev dependencies"
```

---

## Task 5: Pin Dependency Upper Bounds

**Files:**
- Modify: `requirements.txt`
- Modify: `requirements-dev.txt`

**Context:** Current versions use only lower bounds (`>=2.28.0`). Major version releases (requests 3.x, beautifulsoup4 5.x) may introduce breaking changes. Pin upper bounds to current major versions.

- [ ] **Step 1: Review current versions**

Run: `cat requirements.txt requirements-dev.txt`
Expected: All lines show `>=` with no upper bound

- [ ] **Step 2: Update requirements.txt**

Replace contents with:
```
requests>=2.28,<3
beautifulsoup4>=4.11,<5
python-dotenv>=1.0,<2
```

- [ ] **Step 3: Update requirements-dev.txt**

Replace contents with:
```
-r requirements.txt
pytest>=7.0,<9
responses>=0.20,<1
```

- [ ] **Step 4: Dry-run install to verify pins**

```bash
python3 -m venv /tmp/cr-pins && /tmp/cr-pins/bin/pip install --dry-run -r requirements-dev.txt 2>&1 | head -20
# Expected: See resolved versions like:
# Successfully installed requests-2.31.0 beautifulsoup4-4.12.2 ...
# All within the pinned ranges
```

- [ ] **Step 5: Test that tests still pass**

```bash
python3 -m venv /tmp/cr-test-pins && /tmp/cr-test-pins/bin/pip install -q -r requirements-dev.txt
/tmp/cr-test-pins/bin/pytest -q tests/
# Expected: all tests pass
```

- [ ] **Step 6: Commit**

```bash
git add requirements.txt requirements-dev.txt
git commit -m "chore: pin dependency upper bounds"
```

---

## Task 6: Add `--json` Output Mode

**Files:**
- Modify: `scripts/wiki_answer.py` (add `--json` flag, add JSON output branch)
- Modify: `tests/test_wiki_answer.py` (new TestJsonOutput class)
- Modify: `README.md` (flags table)
- Modify: `skills/search-wiki.md` (add note about `--json`)
- Modify: `confluence-retriever-implementation.md` (flags table)

**Context:** CLI currently emits Markdown only. JSON output enables non-AI callers and makes golden-file testing more robust. Default behavior unchanged (Markdown).

- [ ] **Step 1: Add `--json` flag to build_parser()**

Find `build_parser()` function in `scripts/wiki_answer.py`. After the `--body-chars` argument (around line 415), add:

```python
parser.add_argument(
    "--json", action="store_true",
    help="Emit results as JSON instead of Markdown",
)
```

- [ ] **Step 2: Add json import at top of wiki_answer.py**

Add to imports (after `import logging`):
```python
import json
```

- [ ] **Step 3: Add JSON output branch in main()**

In `main()`, after the body-fetching loop (around line 445), before the Markdown output section, add:

```python
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

# Existing Markdown output code continues below
```

The `**(body_by_id.get(r["id"], {}))` unpacks any body passages that were fetched.

- [ ] **Step 4: Write failing tests in tests/test_wiki_answer.py**

Add a new test class at the end of the file:

```python
class TestJsonOutput:
    @responses.activate
    def test_json_mode_outputs_valid_json(self):
        """Verify --json flag produces valid JSON."""
        responses.add(
            responses.GET,
            "https://test.atlassian.net/rest/api/content/search",
            json={
                "results": [
                    {
                        "id": "123",
                        "title": "Test Page",
                        "space": {"key": "TST", "name": "Test Space"},
                        "body": {"storage": {"value": "<p>test body</p>"}},
                    }
                ]
            },
            status=200,
        )
        result = run_cli(["--query", "test", "--limit", "1", "--json"])
        parsed = json.loads(result.stdout)
        assert parsed["queries"] == ["test"]
        assert len(parsed["results"]) == 1
        assert parsed["results"][0]["title"] == "Test Page"

    @responses.activate
    def test_json_mode_excludes_markdown_artifacts(self):
        """Verify JSON output has no Markdown formatting."""
        responses.add(
            responses.GET,
            "https://test.atlassian.net/rest/api/content/search",
            json={
                "results": [
                    {
                        "id": "123",
                        "title": "Test",
                        "space": {"key": "TST", "name": "Test"},
                        "body": {"storage": {"value": "<p>body</p>"}},
                    }
                ]
            },
            status=200,
        )
        result = run_cli(["--query", "test", "--json"])
        # Should not contain Markdown headers/formatting
        assert "##" not in result.stdout
        assert "**URL:**" not in result.stdout

    @responses.activate
    def test_json_mode_includes_body_passages_when_depth_skim(self):
        """Verify JSON includes body passages when --depth skim."""
        responses.add(
            responses.GET,
            "https://test.atlassian.net/rest/api/content/search",
            json={
                "results": [
                    {
                        "id": "456",
                        "title": "How-To",
                        "space": {"key": "TST", "name": "Test"},
                        "body": {"storage": {"value": "<p>Relevant passage here</p>"}},
                    }
                ]
            },
            status=200,
        )
        responses.add(
            responses.GET,
            "https://test.atlassian.net/rest/api/content/456",
            json={
                "body": {
                    "storage": {
                        "value": "<h2>Steps</h2><p>Step 1: Do this</p><p>Step 2: Do that</p>"
                    }
                }
            },
            status=200,
        )
        result = run_cli(["--query", "steps", "--depth", "skim", "--json"])
        parsed = json.loads(result.stdout)
        assert len(parsed["results"]) == 1
        # Body passages should be in the result
        result_item = parsed["results"][0]
        assert "passages" in result_item or "body" in result_item
```

Run these tests to verify they fail (they will, since `--json` doesn't exist yet):
```bash
pytest -q tests/test_wiki_answer.py::TestJsonOutput -v
# Expected: FAIL (function not found / flag not recognized)
```

- [ ] **Step 5: Run failing tests**

```bash
pytest tests/test_wiki_answer.py::TestJsonOutput::test_json_mode_outputs_valid_json -v
# Expected: FAIL with clear error about --json not recognized
```

- [ ] **Step 6: Run all tests to confirm they pass now**

```bash
pytest -q tests/test_wiki_answer.py
# Expected: All tests green (including new JSON tests)
```

- [ ] **Step 7: Manual verification**

```bash
python3 scripts/wiki_answer.py --query "test" --limit 2 --json | python3 -m json.tool > /dev/null && echo "Valid JSON"
python3 scripts/wiki_answer.py --query "test" --limit 2
# Expected: Still emits Markdown (default behavior unchanged)
```

- [ ] **Step 8: Update README.md flags table**

Find the CLI flags table (around line 100). Add a new row:

```markdown
| `--json` | off | Emit results as JSON instead of Markdown |
```

- [ ] **Step 9: Update skills/search-wiki.md**

Find the "Flags" or "CLI" section. Add a note:

```markdown
The CLI also supports `--json` for non-AI callers or piping to tools like `jq`. The skill normally uses default Markdown output.
```

- [ ] **Step 10: Update confluence-retriever-implementation.md**

Find the CLI flags table in section 6. Add:

```markdown
| `--json` | off | Emit results as JSON instead of Markdown |
```

- [ ] **Step 11: Commit**

```bash
git add scripts/wiki_answer.py tests/test_wiki_answer.py README.md skills/search-wiki.md confluence-retriever-implementation.md
git commit -m "feat: add --json output mode"
```

---

## Task 7: Add `--verbose` / `-v` Logging Flag

**Files:**
- Modify: `scripts/wiki_answer.py` (add logging, add `-v` flag, wire log calls)
- Modify: `tests/test_wiki_answer.py` (add minimal verbose test)
- Modify: `README.md` (flags table)
- Modify: `confluence-retriever-implementation.md` (flags table)
- Modify: `COPILOT_CLI_QUICK_REFERENCE.md` (troubleshooting)

**Context:** When the CLI fails in the field, users have no way to see CQL, request URLs, or timings. Add debug logging to stderr.

- [ ] **Step 1: Add logging import to wiki_answer.py**

Add after other imports (around line 10):
```python
import logging
```

- [ ] **Step 2: Add `-v` / `--verbose` flag to build_parser()**

After the `--json` argument, add:
```python
parser.add_argument(
    "-v", "--verbose", action="store_true",
    help="Emit diagnostic logging to stderr (CQL, request URLs, timings)",
)
```

- [ ] **Step 3: Add logging setup at top of main()**

After `def main():`, before argument parsing, add:
```python
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="[%(levelname)s] %(message)s",
        stream=sys.stderr,
    )
    log = logging.getLogger("wiki_answer")
```

Note: `args` is not yet available here. Move this to right after `args = parser.parse_args()`:

```python
    args = parser.parse_args()
    
    # Configure logging after args are parsed
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="[%(levelname)s] %(message)s",
        stream=sys.stderr,
    )
    log = logging.getLogger("wiki_answer")
```

- [ ] **Step 4: Add log.debug() calls in key places**

**In `build_cql()` function:**
```python
    cql = f"({' AND '.join(escaped_queries)}) ORDER BY updated DESC"
    if args.verbose:  # Note: This needs to be passed or use logger
        logging.getLogger("wiki_answer").debug(f"Built CQL: {cql}")
    return cql
```

Actually, we need to make logging available to these functions. Simpler approach: add logging calls in `main()` around existing calls.

**In `main()`, after building CQL:**
```python
    cql = build_cql(queries, space)
    log.debug(f"CQL: {cql}")
```

**In `main()`, before adapter.search():**
```python
    log.debug(f"Searching Confluence at {CONFLUENCE_URL}")
    start = time.time()
    results, total = adapter.search(cql, limit)
    elapsed = time.time() - start
    log.debug(f"Search completed: {len(results)} results in {elapsed:.2f}s")
```

**In body-fetch loop:**
```python
    for page_id in body_ids:
        log.debug(f"Fetching page body: {page_id}")
        body = adapter.get_page(page_id)
        log.debug(f"Fetched {len(body)} bytes")
        # ... existing passage extraction ...
```

Import `time` at the top:
```python
import time
```

- [ ] **Step 5: Write verbose test in tests/test_wiki_answer.py**

Add to the test file:

```python
class TestVerboseLogging:
    @responses.activate
    def test_verbose_flag_emits_debug_logs(self):
        """Verify --verbose flag enables debug logging."""
        responses.add(
            responses.GET,
            "https://test.atlassian.net/rest/api/content/search",
            json={"results": [
                {
                    "id": "123",
                    "title": "Test",
                    "space": {"key": "TST", "name": "Test"},
                    "body": {"storage": {"value": "<p>test</p>"}},
                }
            ]},
            status=200,
        )
        result = run_cli(["--query", "test", "--verbose"])
        # Stderr should contain debug messages
        assert "[DEBUG]" in result.stderr or "CQL" in result.stderr
        assert result.returncode == 0

    @responses.activate
    def test_verbose_flag_not_required(self):
        """Verify default (non-verbose) mode doesn't crash."""
        responses.add(
            responses.GET,
            "https://test.atlassian.net/rest/api/content/search",
            json={"results": []},
            status=200,
        )
        result = run_cli(["--query", "test"])  # no --verbose
        assert result.returncode == 0
```

- [ ] **Step 6: Run tests**

```bash
pytest -q tests/test_wiki_answer.py::TestVerboseLogging -v
# Expected: All pass
```

- [ ] **Step 7: Manual verification**

```bash
python3 scripts/wiki_answer.py --query "test" --limit 1 --verbose 2>&1 | grep -i "debug\|cql"
# Expected: See debug log lines

python3 scripts/wiki_answer.py --query "test" --limit 1 2>&1 | grep -i "debug"
# Expected: No debug output (default is WARNING level)
```

- [ ] **Step 8: Update README.md**

Find flags table. Add:
```markdown
| `-v`, `--verbose` | off | Emit diagnostic logging to stderr (CQL, request URLs, timings) |
```

- [ ] **Step 9: Update confluence-retriever-implementation.md**

Find CLI flags table. Add:
```markdown
| `-v`, `--verbose` | off | Emit diagnostic logging to stderr |
```

- [ ] **Step 10: Update COPILOT_CLI_QUICK_REFERENCE.md**

Find troubleshooting section (or create one). Add:

```markdown
## Troubleshooting

If the CLI fails or returns unexpected results, run with `--verbose` to see diagnostic output:
```bash
python3 scripts/wiki_answer.py --query "..." --verbose
```
This shows the constructed CQL, request URLs, response times, and page fetch details.
```

- [ ] **Step 11: Commit**

```bash
git add scripts/wiki_answer.py tests/test_wiki_answer.py README.md confluence-retriever-implementation.md COPILOT_CLI_QUICK_REFERENCE.md
git commit -m "feat: add --verbose logging flag"
```

---

## Task 8: Add GitHub Actions CI Workflow

**Files:**
- Create: `.github/workflows/test.yml`
- Modify: `README.md` (add CI badge)

**Context:** Tests exist but aren't enforced. A GitHub Actions workflow runs them on every push and PR. No changes to core code; this is infrastructure.

- [ ] **Step 1: Create .github/workflows directory if missing**

```bash
mkdir -p .github/workflows
```

- [ ] **Step 2: Create test.yml workflow**

Create `.github/workflows/test.yml` with contents:

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

- [ ] **Step 3: Verify YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/test.yml'))" && echo "✓ Valid YAML"
```

- [ ] **Step 4: Commit workflow file**

```bash
git add .github/workflows/test.yml
git commit -m "ci: add GitHub Actions test workflow"
```

- [ ] **Step 5: Push to trigger first run (optional at this point)**

Note: The workflow will run on the next push. You can skip this until all commits are done.

- [ ] **Step 6: Add CI badge to README.md**

Find the title line in `README.md` (line 1: `# confluence-retriever`). Add a badge line right after:

```markdown
# confluence-retriever

![tests](https://github.com/YOUR_GITHUB_USERNAME/confluence-retriever/actions/workflows/test.yml/badge.svg)

A lightweight Confluence search CLI...
```

Replace `YOUR_GITHUB_USERNAME` with the actual GitHub username/org. You can find this from the repo URL or git remote.

To get the right URL:
```bash
git remote -v | grep origin | head -1
# Output: origin https://github.com/user/confluence-retriever.git (fetch)
# Use: user/confluence-retriever in the badge URL
```

- [ ] **Step 7: Verify and commit**

```bash
git add README.md
git commit -m "docs: add CI status badge to README"
```

---

## Task 9: End-to-End Verification

**Context:** After all 8 fixes are committed, verify nothing broke and all improvements landed correctly.

- [ ] **Step 1: Verify no uncommitted changes**

```bash
git status
# Expected: "nothing to commit, working tree clean"
```

- [ ] **Step 2: Run full test suite**

```bash
pytest -q tests/
# Expected: "N passed in Y.YYs" (all pass)
```

- [ ] **Step 3: Verify CLI still works**

```bash
python3 scripts/wiki_answer.py --query "test" --limit 2
# Expected: Markdown output with 2 results

python3 scripts/wiki_answer.py --query "test" --limit 2 --json
# Expected: Valid JSON output

python3 scripts/wiki_answer.py --query "test" --limit 2 --verbose 2>&1 | grep -q DEBUG
# Expected: Debug logs present
```

- [ ] **Step 4: Verify no broken imports or syntax**

```bash
python3 -m py_compile scripts/wiki_answer.py install.py
# Expected: No output (both compile cleanly)
```

- [ ] **Step 5: Verify fixtures/tasks gone**

```bash
ls -d fixtures tasks 2>&1
# Expected: "No such file or directory" for both
```

- [ ] **Step 6: Verify --include-body gone**

```bash
grep -r "include.body" scripts/ skills/ tests/ *.md .github/ 2>/dev/null
# Expected: No output (zero matches)
```

- [ ] **Step 7: Verify requirements split**

```bash
ls -la requirements*.txt
# Expected: two files exist

python3 -m venv /tmp/final-check && /tmp/final-check/bin/pip install -q -r requirements.txt
/tmp/final-check/bin/pip show pytest 2>&1 | grep -q "not found\|WARNING"
# Expected: pytest not found (not in runtime)

python3 -m venv /tmp/final-check-dev && /tmp/final-check-dev/bin/pip install -q -r requirements-dev.txt
/tmp/final-check-dev/bin/pytest --version
# Expected: pytest version printed
```

- [ ] **Step 8: Verify all documentation updated**

Run: `grep -n "include.body" README.md AGENTS.md confluence-retriever-implementation.md`
Expected: No output (references removed)

Run: `grep -n "\-\-json" README.md confluence-retriever-implementation.md`
Expected: See both files have entries for `--json`

Run: `grep -n "\-v.*verbose" README.md confluence-retriever-implementation.md`
Expected: See both files have entries for `-v`/`--verbose`

- [ ] **Step 9: Review commit history**

```bash
git log --oneline -8
# Expected output (in reverse order of execution):
# abc1234 docs: add CI status badge to README
# def5678 ci: add GitHub Actions test workflow
# ghi9012 feat: add --verbose logging flag
# jkl3456 feat: add --json output mode
# mno7890 chore: pin dependency upper bounds
# pqr1234 chore: split runtime and dev dependencies
# stu5678 refactor: drop --include-body legacy alias
# vwx9012 chore: remove unused fixtures and tasks directories
# yza3456 fix: add missing sys import to install.py error path
```

---

## Task 10: Reinstall Skills to All Agents

**Context:** Fixes 3 and 6 modified `skills/search-wiki.md`. After all commits are merged, reinstall to Claude Code, Copilot, Gemini, and Codex so they get the updated skill definitions (without `--include-body`, with new `--json` note).

**Important:** The absolute path to `wiki_answer.py` in each installed skill will remain the same (pointing to your project directory). Updating the skill re-stamps the template with the same path, so no behavior changes — only the skill definition is updated.

- [ ] **Step 1: List currently installed skills (optional confirmation)**

```bash
ls -la ~/.claude/skills/search-wiki/ 2>/dev/null && echo "Claude Code: installed"
ls -la ~/.copilot/skills/search-wiki/ 2>/dev/null && echo "Copilot: installed"
ls -la ~/.gemini/skills/search-wiki/ 2>/dev/null && echo "Gemini: installed"
```

- [ ] **Step 2: Reinstall to Claude Code**

```bash
cd /mnt/c/dev/github/confluence-retriever
python3 install.py --target claude
# Expected: "Skill installed to ~/.claude/skills/search-wiki/SKILL.md"
```

- [ ] **Step 3: Reinstall to Copilot**

```bash
python3 install.py --target copilot
# Expected: "Skill installed to ~/.copilot/skills/search-wiki/SKILL.md"
```

- [ ] **Step 4: Reinstall to Gemini**

```bash
python3 install.py --target gemini
# Expected: "Skill installed to ~/.gemini/skills/search-wiki/SKILL.md"
```

- [ ] **Step 5: Reinstall to Codex**

```bash
python3 install.py --target codex
# Expected: "Skill installed to [CODEX_HOME]/skills/search-wiki/SKILL.md"
```

- [ ] **Step 6: Verify all installations**

```bash
# Sample check: Claude Code
cat ~/.claude/skills/search-wiki/SKILL.md | head -5
# Expected: Should reference `/mnt/c/dev/github/confluence-retriever/scripts/wiki_answer.py`

# Verify no --include-body in the installed skill
grep -r "include.body" ~/.claude/skills/search-wiki/ && echo "ERROR: --include-body still in skill" || echo "✓ --include-body removed"
```

- [ ] **Step 7: Verify agents pick up the new skill**

Restart each agent (or reload skills if supported):
- Claude Code: Restart the session or use `/skills reload` if available
- Copilot CLI: Run `/skills reload` or restart
- Gemini CLI: Restart the session
- Codex: Restart the session

- [ ] **Step 8: Test a skill invocation (manual)**

In Claude Code:
```
Ask: "Search the wiki for deployment process"
```

Expected: The AI should invoke the skill and return results. The skill should support `--json` (if tested) and not offer `--include-body` as an option.

---

## Post-Implementation Summary

After completing all 10 tasks:

1. ✅ **8 commits** landed (one per fix)
2. ✅ **All tests passing** (pytest -q tests/)
3. ✅ **Skills reinstalled** to all 4 agents
4. ✅ **Zero breaking changes** to CLI behavior (all new features are opt-in flags)
5. ✅ **Core contract unchanged** — "dumb retriever, smart host" still intact
6. ✅ **Ready for push** — workflow will validate on PR/merge

**Skill Installation Note:**
The installed skill files (in `~/.claude/skills/`, `~/.copilot/skills/`, etc.) are **copied definitions** that point to your project via absolute path. After improvements:
- Script updates (`wiki_answer.py` edits) are **live immediately** (same absolute path)
- Skill definition updates (`search-wiki.md` edits) require **reinstall** (we just did this in Task 10)
- Cross-agent consistency maintained via reinstalling all at once
