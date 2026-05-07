---
name: search-wiki
description: Search a Confluence wiki and synthesize an answer from ranked results. Use when the user asks about internal processes, systems, APIs, team documentation, or anything likely documented on the wiki.
origin: local
---

# Search Wiki (Confluence)

Use the `wiki_answer.py` retrieval CLI to fetch ranked Confluence results, then synthesize a direct answer.

## When to Activate

- User asks how something works internally ("how does X work", "what is Y", "where is Z documented")
- User asks about internal APIs, services, processes, or teams
- User needs a link to a specific page or documentation
- User asks a question that would be answered by internal documentation

## Script Location

```
<PROJECT_ROOT>/scripts/wiki_answer.py
```

## How to Use

### Step 1 — Extract query terms

Break the user's question into 1–3 focused keyword phrases. Prefer nouns and technical terms over stop words.

| User asks | Good queries |
|-----------|-------------|
| "how do I authenticate to the customer API?" | `authentication`, `customer API` |
| "what is the deployment process for microservices?" | `deployment`, `microservice` |
| "who owns the MT space?" | `MT space owner` |

### Step 2 — Choose Retrieval Depth

Default to `--depth links` unless the user's wording asks for more detail.

| Depth | Use when the user says | Behavior |
|-------|------------------------|----------|
| `links` | "find", "search", "where is", "link to", "docs for", "page about", "quick answer", "just the link", "top result" | One search request; title, URL, and excerpt only |
| `skim` | "how do I", "how does", "what are the steps", "show me the steps", "summarise the page", "read the page", "according to the docs", "explain", "details", "setup", "configure", "troubleshoot", "error", "API usage", "example command" | Fetch capped query-relevant passages from the top ranked page |
| `deep` | "deep search", "look deeper", "verify", "double check", "cross-check", "compare pages", "check multiple pages", "source of truth", "exact wording", "policy wording", "think harder", "ultrathink", "be thorough", "investigate", "I need confidence", "don't just give the top result" | Fetch larger passage budgets from the top three ranked pages |

Do not send trigger phrases such as "think harder" to Confluence as query text. Interpret them as depth instructions, then extract the actual wiki search terms separately.

### Step 3 — Run the CLI

```bash
python3 <PROJECT_ROOT>/scripts/wiki_answer.py \
  --query "TERM1" \
  --query "TERM2" \
  --depth links \
  --limit 5
```

Add `--space KEY` when the user mentions a specific space or team (e.g. `--space MT` for Mobile Team).

Use `--depth skim` when the user needs details likely absent from snippets:

```bash
python3 <PROJECT_ROOT>/scripts/wiki_answer.py \
  --query "TERM1" \
  --query "TERM2" \
  --depth skim \
  --limit 5
```

Use `--depth deep` only when the user explicitly asks for verification, comparison, source-of-truth confidence, exact wording, or deeper investigation.

### Step 4 — Synthesize

Read the returned markdown and compose a direct answer:
- Cite the most relevant result(s) by title and URL
- Extract the key fact the user needs — don't dump the raw list
- If multiple results are relevant, summarise across them
- If nothing matches, say so and suggest rephrasing or a broader term

## Flags Reference

| Flag | Default | Purpose |
|------|---------|---------|
| `--query TEXT` | required | Search term (repeat for multiple) |
| `--space KEY` | none | Filter to a Confluence space (e.g. `MT`, `IIT`, `CDBE`) |
| `--limit N` | 5 | Max results to retrieve |
| `--depth links` | `links` | Title, URL, and excerpt only |
| `--depth skim` | `links` | Fetch capped query-relevant passages from the top ranked page |
| `--depth deep` | `links` | Fetch larger passage budgets from the top three ranked pages |
| `--include-body` | off | Compatibility alias for `--depth skim` |
| `--body-top N` | by depth | Override number of top ranked pages to fetch bodies for |
| `--body-chars N` | by depth | Override max passage characters per fetched page |

## Output Format

The CLI returns ranked markdown:

```
# Wiki results for 'query'

## 1. Page Title
- **Space:** Space Name (`KEY`)
- **URL:** https://your-instance/...
- **Excerpt:** ...
- **Headings:** ...
- **Relevant passages:**    # only with --depth skim/deep
  - Heading: matching passage text...
```

Higher-ranked results are more likely to contain the answer. Start from result 1. Avoid `--depth deep` unless the user explicitly asks to compare, verify, or inspect multiple pages.

## Error Handling

| Exit code | Meaning | Action |
|-----------|---------|--------|
| 0 | OK | Results returned |
| 2 | Config error | `.env` missing or `CONFLUENCE_PAT`/`CONFLUENCE_URL` not set — check `<PROJECT_ROOT>/.env` |
| 3 | Auth failed | PAT expired or invalid — regenerate at your Confluence instance |
| 4 | Network error | VPN not connected or Confluence unreachable |

## Example Session

User: "how does the prospect authentication API work?"

```bash
python3 <PROJECT_ROOT>/scripts/wiki_answer.py \
  --query "prospect authentication" \
  --query "authenticate API" \
  --depth skim \
  --limit 5
```

Then synthesize from the returned results.
