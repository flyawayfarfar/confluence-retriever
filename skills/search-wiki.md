---
name: search-wiki
description: Search a Confluence wiki and synthesize an answer from ranked results. Use when the user asks about internal processes, systems, APIs, team documentation, or anything likely documented on the wiki.
origin: local
---

# Search Wiki (Confluence)

Use the `confluence-search` console script to fetch ranked Confluence results,
then synthesize a direct answer.

Use `evals.md` as the final grounding check. Skip the eval loop for simple
requests that only ask for a page link.

## When to Activate

- User asks how something works internally ("how does X work", "what is Y", "where is Z documented")
- User asks about internal APIs, services, processes, or teams
- User needs a link to a specific page or documentation
- User asks a question that would be answered by internal documentation

## Command

```
{COMMAND}
```

Recommended install: `pip install .` exposes the `confluence-search` console
script.

## How to Use

### Step 1 — Pick a subcommand

| User intent | Subcommand |
|-------------|-----------|
| Search for pages by topic | `{COMMAND} search ...` |
| Read a specific page in full | `{COMMAND} read <id-or-url>` |
| Metadata only (title, version, space) | `{COMMAND} info <id-or-url>` |
| List child pages under a parent | `{COMMAND} children <id-or-url>` |

Default `search` is implied if you only have a `--query` and no subcommand:
`{COMMAND} --query "auth"` still works.

### Step 2 — Extract query terms (search only)

Break the user's question into 1–3 focused keyword phrases. Prefer nouns and
technical terms over stop words.

| User asks | Good queries |
|-----------|-------------|
| "how do I authenticate to the customer API?" | `authentication`, `customer API` |
| "what is the deployment process for microservices?" | `deployment`, `microservice` |
| "who owns the MT space?" | `MT space owner` |

### Step 3 — Choose Retrieval Depth (search only)

Default to `--depth links` unless the user's wording asks for more detail.

| Depth | Use when the user says | Behavior |
|-------|------------------------|----------|
| `links` | "find", "search", "where is", "link to", "docs for", "page about", "quick answer", "just the link", "top result" | One search request; title, URL, and excerpt only |
| `skim` | "how do I", "how does", "what are the steps", "summarise the page", "read the page", "according to the docs", "explain", "details", "setup", "configure", "troubleshoot", "error", "API usage", "example command" | Fetch capped query-relevant passages from the top ranked page |
| `deep` | "deep search", "research mode", "exhaustive", "leave no stone unturned", "verify", "compare pages", "source of truth", "exact wording", "think harder", "be thorough", "investigate", "I need confidence" | Expanded title+text search, top five page bodies, and up to two first-seen cross-linked pages |

Do not send trigger phrases such as "think harder" or "deep search" to
Confluence as query text. Interpret them as depth instructions, then extract
the actual wiki search terms separately.

Note: `--depth ultra` is a deprecated alias for `--depth deep` and will be
removed in a future release.

### Step 4 — Run the command

```bash
{COMMAND} search \
  --query "TERM1" \
  --query "TERM2" \
  --depth links \
  --limit 5
```

Add `--space KEY` when the user mentions a specific space or team
(e.g. `--space MT` for Mobile Team).

If the user already supplied a Confluence URL or page ID, skip the search and
use the fast path:

```bash
{COMMAND} search --page-id <ID-OR-URL> --depth skim
# or, for the whole page rendered as Markdown:
{COMMAND} read <ID-OR-URL> --format markdown
```

Use `--depth skim` when the user needs details likely absent from snippets.
Use `--depth deep` for exhaustive research, verification, or cross-page
comparison. Deep mode costs more API calls (two search calls plus five to
seven body fetches).

### Step 5 — Synthesize

Read the returned markdown and compose a direct answer:
- Cite the most relevant result(s) by title and the complete raw URL shown in the `URL` line
- Do not format wiki citations as markdown hyperlinks like `[Title](URL)`; write the full URL as visible text so users can copy/open it even when the client does not render links
- Extract the key fact the user needs — don't dump the raw list
- If multiple results are relevant, summarise across them
- If nothing matches, say so and suggest rephrasing or a broader term

### Step 6 — Check the answer

For substantive answers, run the checks in `evals.md` before responding. If a
check fails, revise once using only the retrieved results. Remove claims that
the returned titles, excerpts, headings, or passages do not support.

## Flags Reference (search)

| Flag | Default | Purpose |
|------|---------|---------|
| `--query TEXT` | required* | Search term (repeat for multiple) |
| `--page-id ID-OR-URL` | none | Skip search and fetch this page directly (*replaces `--query`) |
| `--space KEY` | none | Filter to a Confluence space (e.g. `MT`, `IIT`, `CDBE`) |
| `--limit N` | 5 | Max results to retrieve |
| `--depth links` | `links` | Title, URL, and excerpt only |
| `--depth skim` | `links` | Fetch capped query-relevant passages from the top ranked page |
| `--depth deep` | `links` | Expanded title+text search, five page bodies, and up to two cross-linked pages |
| `--workers N` | 4 | Maximum parallel HTTP workers for page fetches |
| `--recency-halflife-days DAYS` | none | Deep-only recency tie-breaker |
| `--legacy-scorer` | off | Use pre-deep ranking with `--depth deep` |
| `--body-top N` | by depth | Override number of top ranked pages to fetch bodies for |
| `--body-chars N` | by depth | Override max passage characters per fetched page |
| `--format json\|markdown` | `markdown` | Output format (`--json` is a deprecated alias for `--format json`) |

## Output Format

The default markdown output looks like:

```
# Wiki results for 'query'

## 1. Page Title
- **Space:** Space Name (`KEY`)
- **URL:** https://your-instance/...
- **Source:** Cross-link from Source Page (https://your-instance/...)    # only for deep cross-linked pages
- **Excerpt:** ...
- **Headings:** ...
- **Relevant passages:**    # only with --depth skim/deep
  - Heading: matching passage text...
```

Higher-ranked results are more likely to contain the answer. Start from
result 1. Avoid `--depth deep` unless the user explicitly asks to compare,
verify, inspect multiple pages, or search exhaustively.

Every result includes a full raw URL. In deep mode, appended cross-linked
pages are labeled with the source page title and full raw source URL. When
answering, preserve URLs as visible text and do not hide them behind
linked titles.

> **Note:** The `--format json` flag exists for programmatic use, but this
> skill defaults to Markdown for human-readable synthesis.

## Error Handling

| Exit code | Meaning | Action |
|-----------|---------|--------|
| 0 | OK | Results returned |
| 2 | Config error | `.env` missing or `CONFLUENCE_PAT`/`CONFLUENCE_URL` not set — run `{COMMAND} setup` |
| 3 | Auth failed | PAT expired or invalid — regenerate at your Confluence instance |
| 4 | Network error | VPN not connected or Confluence unreachable |

## Example Session

User: "how does the prospect authentication API work?"

```bash
{COMMAND} search \
  --query "prospect authentication" \
  --query "authenticate API" \
  --depth skim \
  --limit 5
```

Then synthesize from the returned results.
