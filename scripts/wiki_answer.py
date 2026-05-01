#!/usr/bin/env python3
"""Confluence wiki retrieval CLI — queries Confluence and returns ranked results."""

import argparse
import re
import sys
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

# ── Config ────────────────────────────────────────────────────────────────────

PROJECT_ENV_FILE = Path(__file__).parent.parent / ".env"
USER_ENV_FILE = Path.home() / ".config" / "confluence-retriever" / ".env"
TIMEOUT_SECONDS = 10
DEFAULT_BODY_CHARS = 1200
DEPTH_BODY_DEFAULTS = {
    "links": (0, 0),
    "skim": (1, DEFAULT_BODY_CHARS),
    "deep": (3, 2000),
}

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_AUTH = 3
EXIT_NETWORK = 4

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

    return cql

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
        self._session = requests.Session()
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
            print(f"ERROR: Cannot reach {self._base_url}: {e}", file=sys.stderr)
            sys.exit(EXIT_NETWORK)
        except requests.exceptions.Timeout:
            print(f"ERROR: Request timed out after {TIMEOUT_SECONDS}s", file=sys.stderr)
            sys.exit(EXIT_NETWORK)

        if response.status_code in (401, 403):
            print(f"ERROR: Auth failed ({response.status_code}). Check your CONFLUENCE_PAT.", file=sys.stderr)
            sys.exit(EXIT_AUTH)

        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            print(f"ERROR: Confluence returned HTTP {response.status_code}", file=sys.stderr)
            sys.exit(EXIT_NETWORK)
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
            })

        return results

    def get_page(self, page_id: str) -> Optional[dict]:
        """Fetch a single page's body and metadata. Returns None on error."""
        url = self._page_endpoint.format(page_id=page_id)
        params = {"expand": "body.storage,space"}

        try:
            response = self._session.get(url, params=params, timeout=TIMEOUT_SECONDS)
        except requests.exceptions.RequestException as e:
            print(f"WARNING: Failed to fetch page {page_id}: {e}", file=sys.stderr)
            return None

        if response.status_code == 404:
            print(f"WARNING: Page {page_id} not found", file=sys.stderr)
            return None

        if not response.ok:
            print(f"WARNING: Page {page_id} returned HTTP {response.status_code}", file=sys.stderr)
            return None

        item = response.json()
        return {
            "id": item.get("id"),
            "title": item.get("title", ""),
            "space_key": item.get("space", {}).get("key", ""),
            "body_html": item.get("body", {}).get("storage", {}).get("value", ""),
        }

# ── Ranker ───────────────────────────────────────────────────────────────────

def score_result(result: dict, queries: list[str], space: Optional[str]) -> int:
    """Score a result for relevance. Higher is better."""
    score = 0
    title_lower = result["title"].lower()
    excerpt_lower = result["excerpt"].lower()

    for q in queries:
        q_lower = q.lower()
        if q_lower in title_lower:
            score += 4
        if q_lower in excerpt_lower:
            score += 2

    for token in query_tokens(queries):
        if token_in_text(token, title_lower):
            score += 2
        if token_in_text(token, excerpt_lower):
            score += 1

    if space and result["space_key"].upper() == space.upper():
        score += 1

    return score


def rank_results(results: list[dict], queries: list[str], space: Optional[str]) -> list[dict]:
    """Return results sorted by descending relevance score."""
    scored = [(score_result(r, queries, space), r) for r in results]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored]


def resolve_body_options(
    depth: str,
    include_body: bool,
    body_top: Optional[int],
    body_chars: Optional[int],
) -> tuple[int, int]:
    """Return the number of page bodies to fetch and characters per body."""
    effective_depth = "skim" if include_body and depth == "links" else depth
    default_top, default_chars = DEPTH_BODY_DEFAULTS[effective_depth]
    resolved_top = default_top if body_top is None else body_top
    resolved_chars = default_chars if body_chars is None else body_chars
    return max(0, resolved_top), max(0, resolved_chars)


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
        "--depth", choices=("links", "skim", "deep"), default="links",
        help="Retrieval depth: links=title/URL/excerpt only, skim=top 1 body snippet, deep=top 3 larger snippets (default: links)",
    )
    parser.add_argument(
        "--include-body", action="store_true",
        help="Alias for --depth skim. Kept for compatibility.",
    )
    parser.add_argument(
        "--body-top", type=int, default=None, metavar="N",
        help="Override the number of top ranked pages to fetch bodies for",
    )
    parser.add_argument(
        "--body-chars", type=int, default=None, metavar="N",
        help="Override maximum body snippet characters per page",
    )
    return parser

# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    pat, base_url = load_config()
    adapter = ConfluenceAdapter(pat, base_url)

    results = adapter.search(args.query, args.space, args.limit)
    ranked = rank_results(results, args.query, args.space)

    if not ranked:
        print("No results found.")
        sys.exit(EXIT_OK)

    print(f"# Wiki results for {', '.join(repr(q) for q in args.query)}\n")
    body_by_id = {}
    body_top, body_chars = resolve_body_options(args.depth, args.include_body, args.body_top, args.body_chars)
    if body_top and body_chars:
        for result in ranked[:body_top]:
            page = adapter.get_page(result["id"])
            if page and page["body_html"]:
                body_by_id[result["id"]] = {
                    "headings": extract_headings(page["body_html"])[:8],
                    "body": html_to_text(page["body_html"], max_chars=body_chars),
                }

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
            if body["body"]:
                print(f"- **Body snippet:** {body['body']}")
        print()

    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
