# confluence-retriever

A lightweight Confluence CLI that searches, reads, and explores pages on any
Confluence instance. Designed as a "dumb retriever" — it fetches, ranks, and
renders, and your AI assistant (GitHub Copilot, etc.) synthesises the answer.

## How it works

```
You → AI assistant → confluence-search → Confluence REST API → ranked output → AI synthesises answer
```

The CLI queries Confluence CQL, normalises results, ranks by keyword match,
and returns Markdown or JSON. No AI logic lives in the script — it stays
compatible with any host assistant or shell automation.

For shallow searches it returns only links and excerpts. For detailed
questions it can fetch page bodies from the top ranked results and extract
query-relevant passages under a fixed character budget.

## Requirements

- Python 3.9+
- A Confluence Personal Access Token (PAT)
- Network access to your Confluence instance

## Setup

### 1. Install the package

```bash
# Recommended — exposes the `confluence-search` console script
pip install .

# Or for development (auto-reload from src/)
pip install -e .[dev]

# Optional extra for full-page HTML→Markdown rendering in `read`
pip install -e .[read]
```

### 2. Configure credentials

The fastest path is the interactive wizard:

```bash
confluence-search setup
```

It prompts for `CONFLUENCE_URL` and `CONFLUENCE_PAT` (input hidden) and
writes `~/.config/confluence-retriever/.env` with `0600` permissions.

If you prefer to write the dotfile by hand:

```bash
mkdir -p ~/.config/confluence-retriever
cp .env.example ~/.config/confluence-retriever/.env
chmod 600 ~/.config/confluence-retriever/.env
# edit the file:
#   CONFLUENCE_URL=https://your-confluence-instance.com
#   CONFLUENCE_PAT=your_personal_access_token
```

`CONFLUENCE_URL` is the root URL only — no path. The script appends
`/rest/api/content/...` automatically. This works for both Cloud and
Server / Data Center deployments.

For how to generate a PAT, see [docs/setup/confluence-pat-setup.md](docs/setup/confluence-pat-setup.md).

### 3. Verify

```bash
confluence-search doctor
```

Runs through each requirement (config present, perms OK, URL reachable,
PAT accepted by Confluence) and prints a per-check pass/fail report.

### 4. Install the AI skill (optional)

This ships a `search-wiki` skill that tells your AI assistant how to invoke
the CLI. Install it once per assistant:

```bash
# Claude Code (default)
python3 install.py

# GitHub Copilot (VS Code or CLI)
python3 install.py --target copilot

# Gemini CLI
python3 install.py --target gemini

# Antigravity (agy)
python3 install.py --target antigravity

# Codex
python3 install.py --target codex

# Shared agent-standard location
python3 install.py --target agents

# Dry run
python3 install.py --check
```

The installer auto-detects `confluence-search` on PATH and stamps it into the
skill. Override with `--command` if needed.

For the full VS Code Copilot Chat setup (settings, Windows/WSL paths,
troubleshooting), see [VSCODE_COPILOT_CHAT_SETUP.md](VSCODE_COPILOT_CHAT_SETUP.md).

## Usage

### Subcommands

```bash
# Search (default subcommand — `--query` without a subcommand still works)
confluence-search search --query "deployment process" --limit 5
confluence-search search --query "authentication" --query "API" --space MT

# Fetch a single page as full Markdown (recommended: pip install -e .[read])
confluence-search read 12345 --format markdown
confluence-search read "https://wiki.example.com/spaces/MT/pages/12345/Auth+Guide"

# Page metadata only (title, space, version) — one cheap API call
confluence-search info 12345

# List child pages of a parent
confluence-search children 12345

# Interactive credential setup
confluence-search setup

# Diagnostic self-check
confluence-search doctor
```

### Search depth

| Depth | API cost | Use for |
|-------|----------|---------|
| `links` (default) | 1 call | "find", "where is", "link to", "quick answer" |
| `skim` | 1 + 1 calls | "how do I", "show steps", "according to the docs", "configure", "troubleshoot" |
| `deep` | 7–9 calls | "deep search", "verify", "compare pages", "exhaustive", "source of truth" |

```bash
# Search with content from the top page
confluence-search search --query "release checklist" --depth skim

# Deep research — expanded query variants, parallel title+text search, cross-links
confluence-search search --query "release approvals" --depth deep

# Tune for rate-limited instances
confluence-search search --query "release approvals" --depth deep --workers 2
```

Note: `--depth ultra` is a deprecated alias for `--depth deep` and will be
removed in a future release.

### Direct page lookup (skip search)

If you already have a Confluence URL or page ID:

```bash
confluence-search search --page-id 12345 --depth skim
confluence-search search --page-id "https://wiki.example.com/pages/viewpage.action?pageId=12345"
confluence-search read 12345 --format markdown
```

## CLI flags (search)

| Flag | Default | Purpose |
|------|---------|---------|
| `--query TEXT` | required* | Search term (repeat for multiple) |
| `--page-id ID-OR-URL` | none | Skip search; fetch this page directly (*replaces `--query`) |
| `--space KEY` | none | Filter to a Confluence space (e.g. `MT`, `IIT`) |
| `--limit N` | 5 | Max results |
| `--depth links\|skim\|deep` | `links` | Retrieval depth |
| `--workers N` | 4 | Maximum parallel HTTP workers for page fetches |
| `--recency-halflife-days DAYS` | none | Deep-only recency tie-breaker |
| `--legacy-scorer` | off | Use the pre-deep ranking formula with `--depth deep` |
| `--body-top N` | by depth | Override number of top pages to fetch bodies for |
| `--body-chars N` | by depth | Override max passage characters per page |
| `--format json\|markdown` | `markdown` | Output format |
| `-v`, `--verbose` | off | Emit diagnostic logging to stderr |

By default, the CLI performs one search request and returns compact title,
URL, and excerpt results. Use `--depth skim` when the user needs details
likely absent from snippets, such as process steps, troubleshooting, or
API usage. Use `--depth deep` for exhaustive wiki research: it expands
query variants, runs text and title searches in parallel, fetches relevant
passages from the top five pages, and appends up to two first-seen
cross-linked pages.

Defaults: `links` = no body, `skim` = 1 page with up to 1200 relevant
passage characters, `deep` = 5 pages with up to 3000 chars each plus
cross-links. JSON output includes `source: "cross-link"` and `from_page`
for appended cross-linked results.

Every result includes a complete raw Confluence URL. When Confluence omits
its canonical page path, the CLI falls back to a page-id lookup URL.
Deep-mode Markdown also labels appended cross-linked pages with the source
page title and complete raw source URL.

## Platform support

| Environment | Works? | Notes |
|-------------|--------|-------|
| macOS / Linux | Yes | Native |
| WSL2 (Windows) | Yes | Native on WSL2 |
| Windows PowerShell / CMD | Yes | Direct use or GitHub Copilot |

`install.py` is a plain Python script — no bash required, so it works on
native Windows without WSL.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | OK |
| 2 | Config / usage error — `.env` missing or unrecognised page reference |
| 3 | Auth failed — PAT expired or invalid |
| 4 | Network error — Confluence unreachable, or non-2xx response |

## Files

```
confluence-retriever/
├── src/confluence_retriever/    # Python package
│   ├── cli.py                   # Click entry point + subcommands
│   ├── config.py                # .env loader, exit codes
│   ├── client.py                # ConfluenceAdapter
│   ├── cql.py                   # CQL builder and escaping
│   ├── html_utils.py            # HTML parsing, passages, markdown
│   ├── ranking.py               # Scoring, query expansion, depth defaults
│   ├── url_parsing.py           # Extract page ID from URL/ID
│   └── formatters.py            # Markdown / JSON renderers per subcommand
├── skills/
│   └── search-wiki.md           # AI skill template
├── tests/                       # pytest suite, no real network calls
├── install.py                   # Cross-platform skill installer
├── pyproject.toml               # Package + console-script declaration
├── requirements.txt
└── .env.example
```
