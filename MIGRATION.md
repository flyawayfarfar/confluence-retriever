# Migration Guide — 0.1.x → 0.2

confluence-retriever 0.2 is a packaging and UX overhaul. The retrieval engine,
ranking algorithm, and Confluence wire protocol are unchanged. This guide
maps everything that moved.

## TL;DR

- **New invocation:** `confluence-search` (installed by `pip install .`).
- **Old invocation still works:** `python3 scripts/wiki_answer.py …` is a shim.
- **New subcommands:** `read`, `info`, `children`, `setup`, `doctor`.
- **`--depth ultra` renamed to `--depth deep`** (alias retained, deprecation warning).
- **Old `--depth deep` (3-page preset) is gone** — `deep` now means what `ultra` meant.
  Pin `--depth skim --body-top 3 --body-chars 2000` to recover the exact old midpoint.
- **`--json` deprecated in favour of `--format json`** (alias retained).

## Invocation

| 0.1.x | 0.2 |
|-------|-----|
| `python3 scripts/wiki_answer.py --query "X"` | `confluence-search search --query "X"`, or unchanged (shim) |
| `python3 scripts/wiki_answer.py --query "X" --json` | `confluence-search search --query "X" --format json` |
| (no equivalent — must search to find a page) | `confluence-search read <id-or-url> --format markdown` |
| (no equivalent) | `confluence-search info <id-or-url>` |
| (no equivalent) | `confluence-search children <id-or-url>` |
| Hand-edit `~/.config/confluence-retriever/.env` | `confluence-search setup` |
| (no equivalent) | `confluence-search doctor` |

## Depth modes

| 0.1.x | 0.2 | Notes |
|-------|-----|-------|
| `--depth links` | `--depth links` | unchanged |
| `--depth skim` | `--depth skim` | unchanged (1 page, 1200 chars) |
| `--depth deep` | `--depth skim --body-top 3 --body-chars 2000` | old 3-page preset removed |
| `--depth deep` (without overrides) | `--depth deep` (NEW behavior) | now equivalent to what `ultra` was — strictly richer |
| `--depth ultra` | `--depth deep` (deprecation alias) | warns and forwards |

The rename collision on `deep` is intentional: anyone who was calling
`--depth deep` for "more body fetches" now gets **even more**, not less.
Cost-conscious callers can opt down with `--body-top` / `--body-chars`.

## Output format

| 0.1.x | 0.2 |
|-------|-----|
| Default Markdown, `--json` switches to JSON | Default Markdown, `--format json` switches to JSON; `--json` accepted with deprecation warning |

## Package layout

| 0.1.x | 0.2 |
|-------|-----|
| `scripts/wiki_answer.py` (917-line single file) | `src/confluence_retriever/{cli,config,client,cql,html_utils,ranking,url_parsing,formatters}.py` |
| `from wiki_answer import …` | `from confluence_retriever import …` (the shim still re-exports the old symbols) |

## Console scripts

`pyproject.toml` now declares two console scripts:

- `confluence-search` — new, recommended.
- `wiki-answer` — legacy name kept for one release.

Both point at the same Click entry point.

## Imports

If you imported anything from `wiki_answer`:

```python
# Still works (shim):
import wiki_answer as wiki
wiki.build_cql([...], None)

# Preferred:
from confluence_retriever import build_cql
build_cql([...], None)
```

## Removed / changed behavior summary

- `build_parser()` no longer exists (argparse → Click). Tests that need to
  introspect flags now use `click.testing.CliRunner`.
- `--depth deep` no longer means "3 pages." It means "everything `--depth ultra`
  used to do." See the depth table above.
- `confluence-search setup` refuses to prompt when `stdin` is not a TTY,
  to avoid hanging in CI.

## Things that did not change

- CQL queries, scoring algorithm, recency tie-breaker, cross-link discovery,
  parallel HTTP, retry behavior, exit codes 0/2/3/4.
- `.env` file format and lookup order
  (`~/.config/confluence-retriever/.env` → `./.env`).
- `install.py` accepts the same `--target {claude,codex,gemini,copilot,agents}`
  values, the same `--dest`, and the same `--check` flag. It now also accepts
  `--command` to override the invocation stamped into the skill.

## Deprecations to be removed in 0.3

- `--depth ultra` alias.
- `--json` flag (use `--format json`).
- `wiki-answer` console script name (use `confluence-search`).
