# Team Demo Script: Confluence Retriever

## Demo Goal

Show how `confluence-retriever` lets AI assistants answer internal wiki questions through a small, deterministic CLI while keeping token usage controlled.

## Opening

"Today I am showing a lightweight Confluence retriever. It does not add another AI layer. It searches Confluence, ranks results, and returns Markdown. Claude Code, Codex, or another assistant then synthesizes the answer from that output."

## Problem

- Internal documentation is spread across Confluence spaces.
- AI assistants cannot reliably answer internal questions without a retrieval tool.
- Fetching entire pages every time wastes tokens and can expose too much irrelevant context.
- We need a predictable way to choose between quick link lookup and deeper page reading.

## Architecture

Explain the flow:

```text
User prompt -> AI assistant -> wiki_answer.py -> Confluence REST API -> ranked Markdown -> assistant answer
```

Key points:

- Credentials stay local in `.env`.
- The CLI is assistant-agnostic.
- Ranking is deterministic and covered by unit tests.
- Page body retrieval is explicit through depth flags.

## Demo 1: Quick Link Lookup

Prompt to assistant:

```text
Find the wiki page for the deployment checklist.
```

Expected assistant behavior:

```bash
python3 scripts/wiki_answer.py \
  --query "deployment checklist" \
  --depth links \
  --limit 5
```

Talk track:

"For find/link/page lookup wording, the assistant uses `--depth links`. That performs one search request and returns title, URL, space, and excerpt only. This is the cheapest mode."

## Demo 2: Read One Page for Steps

Prompt to assistant:

```text
How do I configure customer API authentication according to the wiki?
```

Expected assistant behavior:

```bash
python3 scripts/wiki_answer.py \
  --query "customer API authentication" \
  --query "configure authentication" \
  --depth skim \
  --limit 5
```

Talk track:

"Phrases like 'how do I', 'steps', 'according to the docs', or 'troubleshoot' trigger `--depth skim`. It still searches first, then fetches a capped body snippet from only the top ranked page."

## Demo 3: Deeper Verification

Prompt to assistant:

```text
Deep search the wiki and verify the source of truth for release approvals.
```

Expected assistant behavior:

```bash
python3 scripts/wiki_answer.py \
  --query "release approvals" \
  --query "source of truth" \
  --depth deep \
  --limit 5
```

Talk track:

"For 'deep search', 'verify', 'compare pages', 'source of truth', 'exact wording', or 'think harder', the assistant uses `--depth deep`. That fetches larger snippets from the top three pages. It costs more tokens, so it is reserved for explicit user intent."

## Depth Summary

| Depth | Trigger examples | Behavior |
|-------|------------------|----------|
| `links` | find, where is, link to, docs for, just the link | Search only; title, URL, excerpt |
| `skim` | how do I, show steps, read the page, troubleshoot | Fetch top 1 page snippet |
| `deep` | deep search, verify, compare pages, source of truth, think harder | Fetch top 3 larger snippets |

## Configuration

Show setup:

```bash
cp .env.example ~/.config/confluence-retriever/.env
chmod 600 ~/.config/confluence-retriever/.env
pip install -r requirements.txt
```

Mention:

- The CLI checks `~/.config/confluence-retriever/.env` first.
- It falls back to repo-local `.env`.
- `CONFLUENCE_URL` is the root URL only.

## Assistant Installation

Show install commands:

```bash
python3 install.py --target claude
python3 install.py --target codex
python3 install.py --dest /mnt/c/dev/github/claude/global/skills/search-wiki/SKILL.md
```

Talk track:

"The same skill template can be stamped for Claude Code, Codex, or a custom global skill folder. The installed skill contains the absolute path to this checkout."

## Close

"The main value is controlled retrieval. Most questions stay cheap with links and excerpts. When the user asks for more detail, the assistant can skim one page. When the user explicitly asks for verification or deeper analysis, it can inspect multiple pages. That gives us useful internal-doc answers without fetching whole Confluence pages by default."

## Backup Talking Points

- Tests use `pytest` and `responses`; no real Confluence calls in unit tests.
- CQL is restricted to `type = "page"` to reduce noisy attachment/blog results.
- Ranking combines phrase matches and token matches, so query wording does not need to exactly match the page title.
- Non-auth HTTP failures return compact CLI errors instead of tracebacks.
