"""Output formatters — Markdown and JSON renderers for each subcommand."""

import json
from typing import Optional


# ── search ───────────────────────────────────────────────────────────────────

def format_search_markdown(
    *,
    queries: list[str],
    ranked: list[dict],
    body_by_id: dict[str, dict],
) -> str:
    """Render search results as Markdown (same format the CLI has always emitted)."""
    lines: list[str] = []
    lines.append(f"# Wiki results for {', '.join(repr(q) for q in queries)}")
    lines.append("")

    title_by_id = {r["id"]: r["title"] for r in ranked}

    for i, r in enumerate(ranked, 1):
        lines.append(f"## {i}. {r['title']}")
        lines.append(f"- **Space:** {r['space_name']} (`{r['space_key']}`)")
        lines.append(f"- **URL:** {r['url']}")
        if r.get("source") == "cross-link":
            from_page = r.get("from_page", "")
            from_title = title_by_id.get(from_page, from_page)
            from_url = r.get("from_page_url", "")
            if from_url:
                lines.append(f"- **Source:** Cross-link from {from_title} ({from_url})")
            else:
                lines.append(f"- **Source:** Cross-link from {from_title}")
        if r.get("excerpt"):
            lines.append(f"- **Excerpt:** {r['excerpt'][:200]}")
        body = body_by_id.get(r["id"])
        if body:
            if body.get("headings"):
                lines.append(f"- **Headings:** {', '.join(body['headings'])}")
            if body.get("passages"):
                lines.append("- **Relevant passages:**")
                for passage in body["passages"]:
                    prefix = f"{passage['heading']}: " if passage["heading"] else ""
                    lines.append(f"  - {prefix}{passage['text']}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def format_search_json(
    *,
    queries: list[str],
    space: Optional[str],
    depth: str,
    ranked: list[dict],
    body_by_id: dict[str, dict],
) -> str:
    payload = {
        "queries": queries,
        "space": space,
        "depth": depth,
        "results": [
            {
                "rank": i + 1,
                "id": r["id"],
                "title": r["title"],
                "url": r["url"],
                "space_key": r["space_key"],
                "space_name": r["space_name"],
                "excerpt": r["excerpt"],
                **({"source": r["source"]} if r.get("source") else {}),
                **({"from_page": r["from_page"]} if r.get("from_page") else {}),
                **({"from_page_url": r["from_page_url"]} if r.get("from_page_url") else {}),
                **(body_by_id.get(r["id"], {})),
            }
            for i, r in enumerate(ranked)
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


# ── read (full page) ─────────────────────────────────────────────────────────

def format_page_markdown(page: dict, *, include_attachments: bool = True) -> str:
    """Render a single page as YAML-frontmatter Markdown.

    YAML frontmatter is a widely-used convention (Jekyll/MkDocs/Obsidian).
    """
    from confluence_retriever.html_utils import html_to_markdown

    title = page.get("title", "Untitled")
    page_id = page.get("id", "")
    space_name = page.get("space_name", "")
    space_key = page.get("space_key", "")
    url = page.get("url", "")
    last_modified = page.get("last_modified", "")

    fm_lines = [
        "---",
        f"title: {title}",
        f"page_id: {page_id}",
        f"space: {space_name}",
        f"space_key: {space_key}",
        f"url: {url}",
        f"last_modified: {last_modified}",
        "---",
        "",
    ]

    body_html = page.get("body_html") or ""
    if body_html:
        body_md = html_to_markdown(body_html)
        body_block = ["# " + title, "", body_md, ""]
    else:
        body_block = ["# " + title, "", "_No body content available._", ""]

    parts = list(fm_lines) + body_block

    attachments = page.get("attachments", []) if include_attachments else []
    if attachments:
        parts.append("## Attachments")
        parts.append("")
        for att in attachments:
            name = att.get("title") or att.get("filename") or att.get("id", "attachment")
            size = att.get("size", 0)
            att_url = att.get("url", "")
            size_str = _format_size(size) if size else ""
            suffix = f" ({size_str})" if size_str else ""
            if att_url:
                parts.append(f"- [{name}]({att_url}){suffix}")
            else:
                parts.append(f"- {name}{suffix}")
        parts.append("")

    return "\n".join(parts).rstrip() + "\n"


def format_page_json(page: dict, *, include_attachments: bool = True) -> str:
    payload = {
        "id": page.get("id"),
        "title": page.get("title"),
        "space_key": page.get("space_key"),
        "space_name": page.get("space_name"),
        "url": page.get("url"),
        "last_modified": page.get("last_modified"),
        "version": page.get("version"),
        "status": page.get("status"),
        "body_html": page.get("body_html", ""),
    }
    if include_attachments:
        payload["attachments"] = page.get("attachments", [])
    return json.dumps(payload, indent=2, ensure_ascii=False)


# ── info (metadata only) ─────────────────────────────────────────────────────

def format_info_markdown(page: dict) -> str:
    lines = [
        f"# {page.get('title', 'Untitled')}",
        "",
        f"- **Page ID:** {page.get('id', '')}",
        f"- **Space:** {page.get('space_name', '')} (`{page.get('space_key', '')}`)",
        f"- **Status:** {page.get('status', '')}",
        f"- **Version:** {page.get('version', '')}",
        f"- **Last modified:** {page.get('last_modified', '')}",
        f"- **URL:** {page.get('url', '')}",
        "",
    ]
    return "\n".join(lines)


def format_info_json(page: dict) -> str:
    payload = {
        "id": page.get("id"),
        "title": page.get("title"),
        "space_key": page.get("space_key"),
        "space_name": page.get("space_name"),
        "status": page.get("status"),
        "version": page.get("version"),
        "last_modified": page.get("last_modified"),
        "url": page.get("url"),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


# ── children ─────────────────────────────────────────────────────────────────

def format_children_markdown(children: dict) -> str:
    parent_id = children.get("parent_id", "")
    rows = children.get("results", [])
    lines = [
        f"# Child pages of {parent_id}",
        "",
    ]
    if not rows:
        lines.append("_No child pages._")
        lines.append("")
        return "\n".join(lines)

    lines.append("| Title | Space | Last modified | URL |")
    lines.append("|-------|-------|---------------|-----|")
    for child in rows:
        title = (child.get("title", "") or "").replace("|", "\\|")
        space_key = child.get("space_key", "")
        modified = (child.get("last_modified") or "")[:10]
        url = child.get("url", "")
        lines.append(f"| {title} | {space_key} | {modified} | {url} |")
    lines.append("")
    lines.append(
        f"Showing {children.get('size', len(rows))}/"
        f"{children.get('totalSize', len(rows))} child page(s)."
    )
    lines.append("")
    return "\n".join(lines)


def format_children_json(children: dict) -> str:
    return json.dumps(children, indent=2, ensure_ascii=False)


# ── helpers ──────────────────────────────────────────────────────────────────

def _format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
