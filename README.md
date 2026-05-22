# confluence-retriever

A lightweight Confluence search CLI that retrieves ranked results from any Confluence instance. Designed as a "dumb retriever" — it fetches and ranks results, and your AI assistant (Claude Code, Codex, Gemini, etc.) synthesises the answer.

## How it works

```
You → AI assistant → wiki_answer.py → Confluence REST API → ranked markdown → AI synthesises answer
```

The CLI queries Confluence CQL, normalises results to `{title, url, excerpt}`, and returns ranked markdown. No AI logic lives in the script — it stays compatible with any host assistant.

For shallow searches it returns only links and excerpts. For detailed questions it can fetch page bodies from the top ranked results and extract query-relevant passages under a fixed character budget.

## Requirements

- Python 3.9+
- A Confluence Personal Access Token (PAT)
- Network access to your Confluence instance

## Setup

### 1. Install dependencies

For end users running the CLI:

```bash
pip install -r requirements.txt
```

For developers contributing to the project:

```bash
pip install -r requirements-dev.txt
```

### 2. Configure credentials

Copy the template and fill it in. The CLI checks `~/.config/confluence-retriever/.env` first, then falls back to `.env` in this repository:

```bash
cp .env.example ~/.config/confluence-retriever/.env
chmod 600 ~/.config/confluence-retriever/.env
```

Edit the file:

```
CONFLUENCE_URL=https://yourcompany.atlassian.net
CONFLUENCE_PAT=your_personal_access_token
```

`CONFLUENCE_URL` is the root URL only — no path. The script appends `/rest/api/content/search` automatically. This works for all standard Confluence deployments (Cloud and Server/Data Center).

For how to generate a PAT, see [confluence-pat-setup.md](confluence-pat-setup.md).

### 3. Install the AI skill (optional)

This ships a `search-wiki` skill that tells your AI assistant how to invoke the CLI. Install it once per assistant:

```bash
# Claude Code, writes to ~/.claude/skills/search-wiki/SKILL.md
python3 install.py --target claude

# Gemini CLI, writes to ~/.gemini/skills/search-wiki/SKILL.md
python3 install.py --target gemini

# GitHub Copilot CLI, writes to ~/.copilot/skills/search-wiki/SKILL.md
python3 install.py --target copilot

# Shared agent-standard location, writes to ~/.agents/skills/search-wiki/SKILL.md
python3 install.py --target agents

# Codex, writes to $CODEX_HOME/skills/search-wiki/SKILL.md or ~/.codex/skills/search-wiki/SKILL.md
python3 install.py --target codex

# Custom/global skill path, for example a Claude Code global directory
python3 install.py --dest /mnt/c/dev/github/claude/global/skills/search-wiki/SKILL.md

# Dry run: print the destination and generated skill without writing
python3 install.py --check
```

`python3 install.py` defaults to Claude Code. The installer stamps the absolute path to `wiki_answer.py` into the skill file. After that, the configured assistant can invoke the CLI when you ask internal wiki questions. For an already-running Copilot CLI session, run `/skills reload` or restart the session after installing or updating skills.

For detailed GitHub Copilot CLI setup instructions, see [COPILOT_CLI_SETUP.md](COPILOT_CLI_SETUP.md).

## Usage

Run directly:

```bash
# Basic search: one Confluence search request, compact title/URL/excerpt output
python3 scripts/wiki_answer.py --query "deployment process" --limit 5
python3 scripts/wiki_answer.py --query "authentication" --query "API" --space MT

# Detail search: also fetch capped query-relevant passages from the top ranked page
python3 scripts/wiki_answer.py --query "release checklist" --depth skim

# Deeper search: fetch larger passage budgets from the top three ranked pages
python3 scripts/wiki_answer.py --query "release approvals" --depth deep
```

Or let your AI assistant call it automatically after installing the skill.

## CLI flags

| Flag | Default | Purpose |
|------|---------|---------|
| `--query TEXT` | required | Search term (repeat for multiple) |
| `--space KEY` | none | Filter to a Confluence space (e.g. `MT`, `IIT`) |
| `--limit N` | 5 | Max results |
| `--depth links` | `links` | Title, URL, and excerpt only; cheapest mode |
| `--depth skim` | `links` | Fetch capped query-relevant passages from the top ranked page |
| `--depth deep` | `links` | Fetch larger passage budgets from the top three ranked pages |
| `--body-top N` | by depth | Override number of top ranked pages to fetch bodies for |
| `--body-chars N` | by depth | Override max passage characters per fetched page |
| `--json` | off | Emit results as JSON instead of Markdown |

By default, the CLI performs one search request and returns compact title, URL, and excerpt results. Use `--depth skim` when the user needs details likely absent from snippets, such as process steps, troubleshooting, or API usage. Use `--depth deep` only for explicit requests to verify, compare, or inspect multiple pages. Defaults are `links` = no body text, `skim` = 1 page with up to 1200 relevant passage characters, and `deep` = 3 pages with up to 2000 relevant passage characters each.

Assistant skills should map user phrasing to depth:

| User phrasing | Suggested depth |
|---------------|-----------------|
| "find", "where is", "link to", "docs for", "just the link" | `links` |
| "how do I", "show steps", "read the page", "according to the docs", "troubleshoot" | `skim` |
| "deep search", "verify", "compare pages", "source of truth", "exact wording", "think harder" | `deep` |

## Platform support

| Environment | Works? | Notes |
|-------------|--------|-------|
| macOS / Linux | Yes | Native |
| WSL2 (Windows) | Yes | Required for Claude Code on Windows |
| Windows PowerShell / CMD | Yes | For Codex, Gemini, or direct use |

`install.py` is a plain Python script — no bash required, so it works on native Windows without WSL.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | OK |
| 2 | Config error — `.env` missing or variables not set |
| 3 | Auth failed — PAT expired or invalid |
| 4 | Network error — Confluence unreachable |

## Files

```
confluence-retriever/
├── scripts/
│   └── wiki_answer.py        # CLI entrypoint
├── skills/
│   └── search-wiki.md        # AI skill template (placeholder paths)
├── tests/
│   ├── test_wiki_answer.py   # CLI/search/ranking tests (no real network calls)
│   └── test_install.py       # Installer destination/content tests
├── install.py                # Cross-platform skill installer
├── requirements.txt
├── .env.example              # Credential template (commit this)
├── confluence-pat-setup.md   # PAT generation guide
└── confluence-retriever-implementation.md  # Design notes
```
