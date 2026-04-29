# confluence-retriever

A lightweight Confluence search CLI that retrieves ranked results from any Confluence instance. Designed as a "dumb retriever" — it fetches and ranks results, and your AI assistant (Claude Code, Codex, Gemini, etc.) synthesises the answer.

## How it works

```
You → AI assistant → wiki_answer.py → Confluence REST API → ranked markdown → AI synthesises answer
```

The CLI queries Confluence CQL, normalises results to `{title, url, excerpt}`, and returns ranked markdown. No AI logic lives in the script — it stays compatible with any host assistant.

## Requirements

- Python 3.9+
- A Confluence Personal Access Token (PAT)
- Network access to your Confluence instance

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure credentials

Copy the template and fill it in:

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

This ships a `search-wiki` skill that tells your AI assistant how to invoke the CLI. Run once per machine:

```bash
# Works on Windows, macOS, Linux
python install.py
```

This stamps the absolute path to `wiki_answer.py` into `~/.claude/skills/search-wiki/SKILL.md`. After that, Claude Code (and compatible assistants) will automatically invoke the CLI when you ask internal wiki questions.

## Usage

Run directly:

```bash
python3 scripts/wiki_answer.py --query "deployment process" --limit 5
python3 scripts/wiki_answer.py --query "authentication" --query "API" --space MT
```

Or let your AI assistant call it automatically after installing the skill.

## CLI flags

| Flag | Default | Purpose |
|------|---------|---------|
| `--query TEXT` | required | Search term (repeat for multiple) |
| `--space KEY` | none | Filter to a Confluence space (e.g. `MT`, `IIT`) |
| `--limit N` | 5 | Max results |

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
│   └── test_wiki_answer.py   # Unit tests (no real network calls)
├── install.py                # Cross-platform skill installer
├── requirements.txt
├── .env.example              # Credential template (commit this)
├── confluence-pat-setup.md   # PAT generation guide
└── confluence-retriever-implementation.md  # Design notes
```
