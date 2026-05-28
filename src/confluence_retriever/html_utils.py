"""HTML parsing and passage extraction utilities."""

import re
from typing import Optional

from bs4 import BeautifulSoup


_HL_RE = re.compile(r"@@@\w+@@@")
_CROSS_LINK_RE = re.compile(r"/pages/(\d+)(?:/|$|\?|#)")


def strip_highlight_markers(text: str) -> str:
    """Remove Confluence @@@hl@@@ / @@@endhl@@@ excerpt markers."""
    return _HL_RE.sub("", text).strip()


def html_to_text(html: str, max_chars: int = 500) -> str:
    """Strip HTML tags and return plain text, truncated to max_chars."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s{2,}", " ", text)
    return text[:max_chars]


def html_to_markdown(html: str) -> str:
    """Convert HTML to Markdown using markdownify if available.

    Falls back to ``html_to_text(html, max_chars=10**9)`` and emits a warning
    when the optional ``markdownify`` dep is not installed. The fallback
    keeps the command usable; the warning tells the user how to upgrade.
    """
    try:
        from markdownify import markdownify as _md  # type: ignore
    except ImportError:
        import logging

        logging.warning(
            "markdownify not installed; falling back to plain text. "
            "Install with: pip install confluence-retriever[read]"
        )
        return html_to_text(html, max_chars=10**9)

    md = _md(html, heading_style="atx")
    # Collapse runs of 3+ blank lines that markdownify can produce.
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


def extract_headings(html: str) -> list[str]:
    """Return h1–h3 heading texts from a Confluence page body."""
    soup = BeautifulSoup(html, "html.parser")
    return [tag.get_text(strip=True) for tag in soup.find_all(["h1", "h2", "h3"])]


def normalize_text(text: str) -> str:
    """Collapse whitespace in extracted text."""
    return re.sub(r"\s{2,}", " ", text).strip()


def truncate_text(text: str, max_chars: int) -> str:
    """Truncate text at a word boundary when practical."""
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    text_limit = max_chars - 3
    truncated = text[:text_limit].rstrip()
    boundary = truncated.rfind(" ")
    if boundary >= text_limit * 0.7:
        truncated = truncated[:boundary]
    return f"{truncated}..."


def extract_text_blocks(html: str) -> list[dict]:
    """Extract readable text blocks with their nearest preceding h1–h3 heading."""
    soup = BeautifulSoup(html, "html.parser")
    heading_tags = {"h1", "h2", "h3"}
    block_tags = {"p", "li", "pre", "blockquote", "td", "th"}
    current_heading = ""
    blocks: list[dict] = []

    for tag in soup.find_all(list(heading_tags | block_tags)):
        text = normalize_text(tag.get_text(separator=" ", strip=True))
        if not text:
            continue

        if tag.name in heading_tags:
            current_heading = text
            continue

        if tag.name in {"td", "th"} and tag.find(list(block_tags - {"td", "th"})):
            continue

        blocks.append({"heading": current_heading, "text": text})

    return blocks


def extract_cross_links(html: str) -> list[str]:
    """Return Confluence page IDs found in modern internal page links.

    Supports both Server/Data Center ``/pages/{id}`` and Cloud
    ``/wiki/spaces/{space}/pages/{id}`` URL shapes. Legacy ``/display`` links
    do not contain page IDs, so they are intentionally ignored.
    """
    soup = BeautifulSoup(html, "html.parser")
    page_ids: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        m = _CROSS_LINK_RE.search(a["href"])
        if m:
            pid = m.group(1)
            if pid not in seen:
                seen.add(pid)
                page_ids.append(pid)
    return page_ids


def _proximity_bonus(text: str, tokens: list[str]) -> int:
    """Return +2 if any two *distinct* tokens appear within 50 characters of each other."""
    hits: list[tuple[int, int]] = []  # (position, token_index)
    for tok_idx, token in enumerate(tokens):
        pos = 0
        while True:
            idx = text.find(token, pos)
            if idx == -1:
                break
            hits.append((idx, tok_idx))
            pos = idx + 1
    if len(hits) < 2:
        return 0
    hits.sort()
    for i in range(len(hits) - 1):
        pos_a, ti_a = hits[i]
        pos_b, ti_b = hits[i + 1]
        if ti_a != ti_b and pos_b - pos_a <= 50:
            return 2
    return 0


def score_text_block(block: dict, queries: list[str]) -> int:
    """Score a page text block for query relevance."""
    # Local imports break a circular dep with ranking.py
    from confluence_retriever.ranking import query_tokens, token_in_text

    score = 0
    text_lower = block["text"].lower()
    heading_lower = block["heading"].lower()

    for query in queries:
        query_lower = query.lower()
        if query_lower in heading_lower:
            score += 5
        if query_lower in text_lower:
            score += 4

    tokens = query_tokens(queries)
    for token in tokens:
        if token_in_text(token, heading_lower):
            score += 2
        if token_in_text(token, text_lower):
            score += 1

    if len(tokens) >= 2:
        score += _proximity_bonus(text_lower, tokens)

    return score


def extract_relevant_passages(
    html: str,
    queries: list[str],
    max_chars: int,
    max_passages: int = 4,
    passage_chars: int = 450,
) -> list[dict]:
    """Return the most query-relevant page passages within a character budget."""
    if max_chars <= 0 or max_passages <= 0:
        return []

    blocks = extract_text_blocks(html)
    if not blocks:
        fallback = html_to_text(html, max_chars=max_chars)
        return [{"heading": "", "text": fallback}] if fallback else []

    scored = [
        (score_text_block(block, queries), index, block)
        for index, block in enumerate(blocks)
    ]
    matching = [item for item in scored if item[0] > 0]

    if matching:
        candidates = sorted(matching, key=lambda item: (-item[0], item[1]))
    else:
        candidates = scored

    selected: list[dict] = []
    used_indexes: set[int] = set()
    remaining_chars = max_chars

    for _, index, block in candidates:
        if index in used_indexes or len(selected) >= max_passages or remaining_chars <= 0:
            continue

        text = truncate_text(block["text"], min(passage_chars, remaining_chars))
        if not text:
            continue

        selected.append({"heading": block["heading"], "text": text})
        used_indexes.add(index)
        remaining_chars -= len(text)

    return selected
