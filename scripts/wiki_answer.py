#!/usr/bin/env python3
"""Confluence wiki retrieval CLI — queries Confluence and returns ranked results."""

import argparse
import concurrent.futures
import json
import logging
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ── Config ────────────────────────────────────────────────────────────────────

PROJECT_ENV_FILE = Path(__file__).parent.parent / ".env"
USER_ENV_FILE = Path.home() / ".config" / "confluence-retriever" / ".env"
TIMEOUT_SECONDS = 10
DEFAULT_BODY_CHARS = 1200
DEFAULT_PASSAGE_CHARS = 450
MAX_PASSAGES_PER_PAGE = 4
DEPTH_BODY_DEFAULTS = {
    "links": (0, 0),
    "skim": (1, DEFAULT_BODY_CHARS),
    "deep": (3, 2000),
    "ultra": (5, 3000),
}
ULTRA_CROSSLINK_EXTRA = 2  # max additional cross-linked pages in ultra mode
ULTRA_MAX_QUERIES = 6      # cap for expand_queries()

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_AUTH = 3
EXIT_NETWORK = 4


class ConfluenceAuthError(Exception):
    """Raised when Confluence returns 401 or 403."""


class ConfluenceNetworkError(Exception):
    """Raised when Confluence is unreachable or returns an unexpected HTTP error."""

# ── PAT loader ────────────────────────────────────────────────────────────────

def load_config() -> tuple[str, str]:
    """Load CONFLUENCE_PAT and CONFLUENCE_URL. Returns (pat, base_url)."""
    env_file = USER_ENV_FILE if USER_ENV_FILE.exists() else PROJECT_ENV_FILE
    if not env_file.exists():
        print("ERROR: Config file not found.", file=sys.stderr)
        print(f"Checked: {USER_ENV_FILE}", file=sys.stderr)
        print(f"Checked: {PROJECT_ENV_FILE}", file=sys.stderr)
        print("Copy .env.example to one of those paths and fill in CONFLUENCE_PAT.", file=sys.stderr)
        sys.exit(EXIT_CONFIG)

    from dotenv import dotenv_values
    config = dotenv_values(env_file)
    pat = config.get("CONFLUENCE_PAT", "").strip()

    if not pat:
        print(f"ERROR: CONFLUENCE_PAT is not set in {env_file}", file=sys.stderr)
        sys.exit(EXIT_CONFIG)

    base_url = config.get("CONFLUENCE_URL", "").rstrip("/")
    if not base_url:
        print(f"ERROR: CONFLUENCE_URL is not set in {env_file}", file=sys.stderr)
        sys.exit(EXIT_CONFIG)
    return pat, base_url

# ── CQL builder ───────────────────────────────────────────────────────────────

def cql_escape(text: str) -> str:
    """Escape special characters in a CQL string literal."""
    # Escape backslash first, then double-quote
    return text.replace("\\", "\\\\").replace('"', '\\"')


def build_cql(queries: list[str], space: Optional[str]) -> str:
    """Build a CQL query string from one or more query terms and an optional space filter.

    Multiple queries are OR'd: (text ~ "q1" OR text ~ "q2")
    Space filter is AND'd: ... AND space = "SPACE"
    """
    terms = [f'text ~ "{cql_escape(q)}"' for q in queries]
    if len(terms) == 1:
        cql = terms[0]
    else:
        cql = "(" + " OR ".join(terms) + ")"

    cql += ' AND type = "page"'

    if space:
        cql += f' AND space = "{cql_escape(space)}"'

    logging.debug(f"Built CQL query: {cql}")
    return cql

# ── Query expansion ───────────────────────────────────────────────────────────

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


# ── HTML utils ───────────────────────────────────────────────────────────────

_HL_RE = re.compile(r"@@@\w+@@@")


def strip_highlight_markers(text: str) -> str:
    """Remove Confluence @@@hl@@@ / @@@endhl@@@ excerpt markers."""
    return _HL_RE.sub("", text).strip()


def html_to_text(html: str, max_chars: int = 500) -> str:
    """Strip HTML tags and return plain text, truncated to max_chars."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s{2,}", " ", text)
    return text[:max_chars]


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
    max_passages: int = MAX_PASSAGES_PER_PAGE,
    passage_chars: int = DEFAULT_PASSAGE_CHARS,
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


def extract_cross_links(html: str) -> list[str]:
    """Return Confluence page IDs found in internal links within page HTML."""
    soup = BeautifulSoup(html, "html.parser")
    page_ids: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        m = re.search(r"/pages/(\d+)/", a["href"])
        if m:
            pid = m.group(1)
            if pid not in seen:
                seen.add(pid)
                page_ids.append(pid)
    return page_ids


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


# ── Confluence adapter ────────────────────────────────────────────────────────

class ConfluenceAdapter:
    def __init__(self, pat: str, base_url: str) -> None:
        self._base_url = base_url
        self._search_endpoint = f"{base_url}/rest/api/content/search"
        self._page_endpoint = f"{base_url}/rest/api/content/{{page_id}}"
        self._page_cache: dict[str, dict] = {}
        self._session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist={429, 502, 503, 504},
            allowed_methods={"GET"},
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)
        self._session.headers.update({
            "Authorization": f"Bearer {pat}",
            "Accept": "application/json",
        })

    def search(self, queries: list[str], space: Optional[str], limit: int) -> list[dict]:
        """Search Confluence via CQL. Returns list of result dicts."""
        cql = build_cql(queries, space)
        params = {
            "cql": cql,
            "limit": limit,
            "expand": "space,version",
        }

        try:
            response = self._session.get(self._search_endpoint, params=params, timeout=TIMEOUT_SECONDS)
        except requests.exceptions.ConnectionError as e:
            raise ConfluenceNetworkError(f"Cannot reach {self._base_url}: {e}") from e
        except requests.exceptions.Timeout:
            raise ConfluenceNetworkError(f"Request timed out after {TIMEOUT_SECONDS}s")

        if response.status_code in (401, 403):
            raise ConfluenceAuthError(
                f"Auth failed ({response.status_code}). Check your CONFLUENCE_PAT."
            )

        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            raise ConfluenceNetworkError(
                f"Confluence returned HTTP {response.status_code}"
            ) from None
        data = response.json()

        results = []
        for item in data.get("results", []):
            results.append({
                "id": item.get("id"),
                "title": item.get("title", ""),
                "space_key": item.get("space", {}).get("key", ""),
                "space_name": item.get("space", {}).get("name", ""),
                "url": f"{self._base_url}{item.get('_links', {}).get('webui', '')}",
                "excerpt": strip_highlight_markers(item.get("excerpt", "")),
                "last_modified": item.get("version", {}).get("when", ""),
                "_title_hit": False,
            })

        logging.debug(f"Confluence search returned {len(results)} results")
        return results

    def get_page(self, page_id: str) -> Optional[dict]:
        """Fetch a single page's body and metadata. Returns None on error."""
        if page_id in self._page_cache:
            return self._page_cache[page_id]

        url = self._page_endpoint.format(page_id=page_id)
        params = {"expand": "body.storage,space"}

        try:
            response = self._session.get(url, params=params, timeout=TIMEOUT_SECONDS)
        except requests.exceptions.RequestException as e:
            raise ConfluenceNetworkError(f"Failed to fetch page {page_id}: {e}") from e

        if response.status_code in (401, 403):
            raise ConfluenceAuthError(
                f"Auth failed fetching page {page_id} ({response.status_code}). Check your CONFLUENCE_PAT."
            )

        if response.status_code == 404:
            logging.warning("page %s not found", page_id)
            return None

        if not response.ok:
            raise ConfluenceNetworkError(f"Page {page_id} returned HTTP {response.status_code}")

        item = response.json()
        logging.debug(f"Fetched page {page_id}: {item.get('title', 'untitled')}")
        result = {
            "id": item.get("id"),
            "title": item.get("title", ""),
            "space_key": item.get("space", {}).get("key", ""),
            "body_html": item.get("body", {}).get("storage", {}).get("value", ""),
        }
        self._page_cache[page_id] = result
        return result

    def get_pages(self, page_ids: list[str], workers: int = 4) -> dict[str, dict]:
        """Fetch multiple pages in parallel. Returns mapping of page_id → page dict."""
        uncached = [pid for pid in page_ids if pid not in self._page_cache]
        if uncached:
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(self.get_page, pid): pid for pid in uncached}
                for future in concurrent.futures.as_completed(futures):
                    pid = futures[future]
                    try:
                        future.result()  # cache updated inside get_page()
                    except ConfluenceAuthError:
                        raise
                    except ConfluenceNetworkError as e:
                        logging.warning("page fetch failed for %s: %s", pid, e)
        result = {pid: self._page_cache[pid] for pid in page_ids if pid in self._page_cache}
        missing = [pid for pid in page_ids if pid not in result]
        if missing:
            logging.warning(
                "page fetch dropped %d/%d pages: %s", len(missing), len(page_ids), missing
            )
        return result

    def search_combined(
        self, queries: list[str], space: Optional[str], limit: int, workers: int = 4
    ) -> list[dict]:
        """Parallel title + text CQL searches merged by page ID. Title hits marked with _title_hit=True."""
        title_terms = [f'title ~ "{cql_escape(q)}"' for q in queries]
        title_cql = ("(" + " OR ".join(title_terms) + ")" if len(title_terms) > 1 else title_terms[0])
        title_cql += ' AND type = "page"'
        if space:
            title_cql += f' AND space = "{cql_escape(space)}"'

        def _title_results() -> list[dict]:
            try:
                params = {"cql": title_cql, "limit": limit, "expand": "space,version"}
                resp = self._session.get(self._search_endpoint, params=params, timeout=TIMEOUT_SECONDS)
                if resp.ok:
                    return [
                        {
                            "id": item.get("id"),
                            "title": item.get("title", ""),
                            "space_key": item.get("space", {}).get("key", ""),
                            "space_name": item.get("space", {}).get("name", ""),
                            "url": f"{self._base_url}{item.get('_links', {}).get('webui', '')}",
                            "excerpt": strip_highlight_markers(item.get("excerpt", "")),
                            "last_modified": item.get("version", {}).get("when", ""),
                            "_title_hit": True,
                        }
                        for item in resp.json().get("results", [])
                    ]
                if resp.status_code in (401, 403):
                    raise ConfluenceAuthError(
                        f"Auth failed in title search ({resp.status_code}). Check your CONFLUENCE_PAT."
                    )
            except ConfluenceAuthError:
                raise
            except (requests.exceptions.RequestException, ValueError) as e:
                logging.warning("title search failed, continuing without title hits: %s", e)
            return []

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(2, workers)) as pool:
            text_future = pool.submit(self.search, queries, space, limit)
            title_future = pool.submit(_title_results)
            text_results = text_future.result()
            title_hit_list = title_future.result()

        title_hit_ids = {r["id"] for r in title_hit_list}
        for r in text_results:
            r["_title_hit"] = r["id"] in title_hit_ids

        # Append title-only pages not already in text results
        text_ids = {r["id"] for r in text_results}
        merged = list(text_results)
        for r in title_hit_list:
            if r["id"] not in text_ids:
                merged.append(r)

        merged = merged[:limit]
        logging.debug(
            "search_combined: %d text, %d title hits, %d merged",
            len(text_results), len(title_hit_list), len(merged),
        )
        return merged


# ── Ranker ───────────────────────────────────────────────────────────────────

def score_result(
    result: dict,
    queries: list[str],
    space: Optional[str],
    *,
    enhanced: bool = False,
    halflife_days: Optional[int] = None,
) -> int:
    """Score a result for relevance. Higher is better.

    With enhanced=True (ultra mode): title phrase weight 6, proximity bonus,
    title-hit bonus, and optional recency decay.
    """
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
                score += int(10 * math.exp(-days_ago / halflife_days))
            except (ValueError, TypeError):
                pass

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
    scored = [
        (score_result(r, queries, space, enhanced=enhanced, halflife_days=halflife_days), r)
        for r in results
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    ranked = [r for _, r in scored]
    logging.debug(f"Ranked {len(ranked)} results by relevance score")
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
    logging.debug(f"Body options for depth={depth}: fetch {result[0]} pages, {result[1]} chars/page")
    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wiki_answer.py",
        description="Search Confluence and return ranked results.",
    )
    parser.add_argument(
        "--query", action="append", required=True, metavar="TEXT",
        help="Search query (can be repeated to combine terms)",
    )
    parser.add_argument(
        "--space", default=None, metavar="KEY",
        help="Filter by Confluence space key, e.g. MT",
    )
    parser.add_argument(
        "--limit", type=int, default=5, metavar="N",
        help="Maximum number of results (default: 5)",
    )
    parser.add_argument(
        "--depth", choices=("links", "skim", "deep", "ultra"), default="links",
        help="Retrieval depth: links=title/URL/excerpt only, skim=top 1 page passages, "
             "deep=top 3 pages, ultra=5 pages + query expansion + cross-links (default: links)",
    )
    parser.add_argument(
        "--recency-halflife-days", type=int, default=None, metavar="DAYS",
        help="(ultra only) Boost recently modified pages; score decays by e^(-age/DAYS)",
    )
    parser.add_argument(
        "--body-top", type=int, default=None, metavar="N",
        help="Override the number of top ranked pages to fetch bodies for",
    )
    parser.add_argument(
        "--body-chars", type=int, default=None, metavar="N",
        help="Override maximum relevant passage characters per page",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit results as JSON instead of Markdown",
    )
    parser.add_argument(
        "--workers", type=int, default=4, metavar="N",
        help="Maximum parallel HTTP workers for page fetches (default: 4)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable verbose debug logging",
    )
    return parser

# ── Entry point ───────────────────────────────────────────────────────────────

def main(argv: Optional[list[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(name)s [%(levelname)s] %(message)s"
    )
    log = logging.getLogger("wiki_answer")

    pat, base_url = load_config()
    adapter = ConfluenceAdapter(pat, base_url)

    is_ultra = args.depth == "ultra"
    active_queries = expand_queries(args.query) if is_ultra else args.query

    try:
        if is_ultra:
            results = adapter.search_combined(active_queries, args.space, args.limit, workers=args.workers)
            ranked = rank_results(
                results, active_queries, args.space,
                enhanced=True, halflife_days=args.recency_halflife_days,
            )
        else:
            results = adapter.search(args.query, args.space, args.limit)
            ranked = rank_results(results, args.query, args.space)
    except ConfluenceAuthError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(EXIT_AUTH)
    except ConfluenceNetworkError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(EXIT_NETWORK)

    if not ranked:
        print("No results found.")
        sys.exit(EXIT_OK)

    if not args.json:
        print(f"# Wiki results for {', '.join(repr(q) for q in args.query)}\n")

    body_by_id: dict[str, dict] = {}
    body_top, body_chars = resolve_body_options(args.depth, args.body_top, args.body_chars)

    if body_top and body_chars:
        ids_to_fetch = [r["id"] for r in ranked[:body_top]]
        pages_by_id = adapter.get_pages(ids_to_fetch, workers=args.workers)

        for result in ranked[:body_top]:
            page = pages_by_id.get(result["id"])
            if page and page["body_html"]:
                body_by_id[result["id"]] = {
                    "headings": extract_headings(page["body_html"])[:8],
                    "passages": extract_relevant_passages(
                        page["body_html"],
                        active_queries,
                        max_chars=body_chars,
                    ),
                }

        if is_ultra:
            seen_ids = {r["id"] for r in ranked}
            cross_ids: list[str] = []
            for result in ranked[:body_top]:
                page = pages_by_id.get(result["id"])
                if page and page["body_html"]:
                    for link_id in extract_cross_links(page["body_html"]):
                        if link_id not in seen_ids and len(cross_ids) < ULTRA_CROSSLINK_EXTRA:
                            cross_ids.append(link_id)
                            seen_ids.add(link_id)

            if cross_ids:
                extra_pages = adapter.get_pages(cross_ids, workers=args.workers)
                for pid, xpage in extra_pages.items():
                    ranked.append({
                        "id": pid,
                        "title": xpage.get("title", ""),
                        "space_key": xpage.get("space_key", ""),
                        "space_name": "",
                        "url": f"{base_url}/pages/{pid}",
                        "excerpt": "",
                        "last_modified": "",
                        "_title_hit": False,
                        "source": "cross-link",
                    })
                    if xpage.get("body_html"):
                        body_by_id[pid] = {
                            "headings": extract_headings(xpage["body_html"])[:8],
                            "passages": extract_relevant_passages(
                                xpage["body_html"],
                                active_queries,
                                max_chars=body_chars,
                            ),
                        }

        logging.debug(f"Extracted body passages from {len(body_by_id)} pages")

    if args.json:
        payload = {
            "queries": args.query,
            "space": args.space,
            "depth": args.depth,
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
                    **(body_by_id.get(r["id"], {})),
                }
                for i, r in enumerate(ranked)
            ],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        sys.exit(EXIT_OK)

    for i, r in enumerate(ranked, 1):
        print(f"## {i}. {r['title']}")
        print(f"- **Space:** {r['space_name']} (`{r['space_key']}`)")
        print(f"- **URL:** {r['url']}")
        if r["excerpt"]:
            print(f"- **Excerpt:** {r['excerpt'][:200]}")
        body = body_by_id.get(r["id"])
        if body:
            if body["headings"]:
                print(f"- **Headings:** {', '.join(body['headings'])}")
            if body["passages"]:
                print("- **Relevant passages:**")
                for passage in body["passages"]:
                    prefix = f"{passage['heading']}: " if passage["heading"] else ""
                    print(f"  - {prefix}{passage['text']}")
        print()

    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
