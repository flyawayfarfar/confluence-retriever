"""Ranking, query expansion, and depth-mode defaults."""

import logging
import math
import re
from datetime import datetime, timezone
from typing import Optional


DEFAULT_BODY_CHARS = 1200

# Depth modes — see improvements.md Section 2.
# `links`  - search only, no body fetches
# `skim`   - fetch 1 page body, extract relevant passages
# `deep`   - expanded title+text search + 5 page bodies + cross-links (was "ultra")
DEPTH_BODY_DEFAULTS: dict[str, tuple[int, int]] = {
    "links": (0, 0),
    "skim": (1, DEFAULT_BODY_CHARS),
    "deep": (5, 3000),
}

# Deprecated names accepted with a warning. See cli.py for the warn-and-forward.
DEPTH_DEPRECATED_ALIASES = {
    # `ultra` was renamed to `deep` (identical behavior).
    "ultra": "deep",
}

ULTRA_CROSSLINK_EXTRA = 2  # max additional cross-linked pages in deep mode
ULTRA_MAX_QUERIES = 6      # cap for expand_queries()


_ABBREV_MAP: dict[str, str] = {
    "auth": "authentication",
    "authentication": "auth",
    "docs": "documentation",
    "documentation": "docs",
    "config": "configuration",
    "configuration": "config",
    "repo": "repository",
    "repository": "repo",
    "env": "environment",
    "environment": "env",
    "deploy": "deployment",
    "deployment": "deploy",
}


def _structural_variants(query: str) -> list[str]:
    """Return structural sub-queries: drop trailing token, drop leading token, longest single token."""
    words = query.split()
    variants: list[str] = []
    if len(words) >= 2:
        variants.append(" ".join(words[:-1]))   # drop trailing token
        variants.append(" ".join(words[1:]))    # drop leading token
    if words:
        longest = max(words, key=len)
        if longest not in variants and longest != query:
            variants.append(longest)
    return variants


def expand_queries(queries: list[str], max_total: int = ULTRA_MAX_QUERIES) -> list[str]:
    """Return queries plus structural and abbreviation variants, capped at max_total."""
    expanded = list(queries)
    seen = {q.lower() for q in queries}

    # Structural variants first (higher relevance than abbrev swaps)
    for query in queries:
        for variant in _structural_variants(query):
            if len(expanded) >= max_total:
                break
            if variant.lower() not in seen:
                expanded.append(variant)
                seen.add(variant.lower())
        if len(expanded) >= max_total:
            break

    for query in queries:
        if len(expanded) >= max_total:
            break
        for abbrev, expansion in _ABBREV_MAP.items():
            if len(expanded) >= max_total:
                break
            if re.search(rf"\b{re.escape(abbrev)}\b", query, flags=re.IGNORECASE):
                variant = re.sub(rf"\b{re.escape(abbrev)}\b", expansion, query, flags=re.IGNORECASE)
                if variant.lower() not in seen:
                    expanded.append(variant)
                    seen.add(variant.lower())
    return expanded


def query_tokens(queries: list[str]) -> list[str]:
    """Return unique searchable tokens from query phrases."""
    tokens: list[str] = []
    seen = set()
    for query in queries:
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", query.lower()):
            if len(token) < 3 or token in seen:
                continue
            seen.add(token)
            tokens.append(token)
    return tokens


def token_in_text(token: str, text: str) -> bool:
    """Return whether a token appears in text without overmatching short acronyms."""
    if len(token) <= 3:
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])", text) is not None
    return token in text


def page_url(base_url: str, page_id: Optional[str], webui: str = "") -> str:
    """Return a usable Confluence page URL, falling back to a page-id lookup URL."""
    if webui:
        if webui.startswith(("http://", "https://")):
            return webui
        return f"{base_url}{webui}"
    if page_id:
        return f"{base_url}/pages/viewpage.action?pageId={page_id}"
    return base_url


def score_result(
    result: dict,
    queries: list[str],
    space: Optional[str],
    *,
    enhanced: bool = False,
    halflife_days: Optional[int] = None,
) -> int:
    """Score a result for relevance. Higher is better.

    With enhanced=True (deep mode): title phrase weight 6, proximity bonus,
    title-hit bonus, and optional recency decay.
    """
    # Local import breaks circular dep with html_utils (which imports
    # query_tokens/token_in_text from us, and we use _proximity_bonus from it).
    from confluence_retriever.html_utils import _proximity_bonus

    score = 0
    title_lower = result["title"].lower()
    excerpt_lower = result["excerpt"].lower()
    title_phrase_weight = 6 if enhanced else 4

    for q in queries:
        q_lower = q.lower()
        if q_lower in title_lower:
            score += title_phrase_weight
        if q_lower in excerpt_lower:
            score += 2

    tokens = query_tokens(queries)
    for token in tokens:
        if token_in_text(token, title_lower):
            score += 2
        if token_in_text(token, excerpt_lower):
            score += 1

    if enhanced:
        if len(tokens) >= 2:
            score += _proximity_bonus(title_lower + " " + excerpt_lower, tokens)
        if result.get("_title_hit"):
            score += 3

    if space and result["space_key"].upper() == space.upper():
        score += 1

    if enhanced and halflife_days and halflife_days > 0:
        last_modified = result.get("last_modified")
        if last_modified:
            try:
                mod_dt = datetime.fromisoformat(last_modified.replace("Z", "+00:00"))
                days_ago = max(0, (datetime.now(tz=timezone.utc) - mod_dt).days)
                score = round(score * math.exp(-days_ago / halflife_days))
            except (ValueError, TypeError):
                logging.debug(
                    "recency parse failed for %s: %r",
                    result.get("id"),
                    last_modified,
                )

    return score


def rank_results(
    results: list[dict],
    queries: list[str],
    space: Optional[str],
    *,
    enhanced: bool = False,
    halflife_days: Optional[int] = None,
) -> list[dict]:
    """Return results sorted by descending relevance score."""
    if enhanced and halflife_days and halflife_days > 0:
        scored = [
            (
                score_result(r, queries, space, enhanced=enhanced),
                score_result(r, queries, space, enhanced=enhanced, halflife_days=halflife_days),
                r,
            )
            for r in results
        ]
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        ranked = [r for _, _, r in scored]
    else:
        scored = [
            (score_result(r, queries, space, enhanced=enhanced), r)
            for r in results
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        ranked = [r for _, r in scored]
    logging.debug("Ranked %d results by relevance score", len(ranked))
    return ranked


def resolve_body_options(
    depth: str,
    body_top: Optional[int],
    body_chars: Optional[int],
) -> tuple[int, int]:
    """Return the number of page bodies to fetch and characters per body."""
    default_top, default_chars = DEPTH_BODY_DEFAULTS[depth]
    resolved_top = default_top if body_top is None else body_top
    resolved_chars = default_chars if body_chars is None else body_chars
    result = max(0, resolved_top), max(0, resolved_chars)
    logging.debug(
        "Body options for depth=%s: fetch %d pages, %d chars/page",
        depth, result[0], result[1],
    )
    return result
