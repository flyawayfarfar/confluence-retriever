"""Extract a Confluence page ID from any of the documented URL shapes.

Reference: Atlassian Confluence REST API and URL conventions (public docs).
Accepts:

    Server / Data Center : /spaces/{KEY}/pages/{ID}[/title]
    Cloud                : /wiki/spaces/{KEY}/pages/{ID}[/title]
    Legacy viewpage      : /pages/viewpage.action?pageId={ID}
    Legacy details       : /pages/viewpage/details/{ID}
    Bare numeric ID      : "12345"  -> returned unchanged

Anything else returns ``None``.
"""

import re
from typing import Optional
from urllib.parse import parse_qs, urlparse


_SPACES_PAGES_RE = re.compile(r"/(?:wiki/)?spaces/[^/]+/pages/(\d+)")
_DETAILS_RE = re.compile(r"/pages/viewpage/details/(\d+)")
_BARE_NUMERIC_RE = re.compile(r"^\d+$")


def extract_page_id(value: str) -> Optional[str]:
    """Return the page ID parsed from ``value`` or ``None`` if not recognised."""
    if not value:
        return None

    text = value.strip()

    # Bare numeric ID: pass through.
    if _BARE_NUMERIC_RE.match(text):
        return text

    # Anything that isn't a URL and isn't bare numeric is not a page ref.
    if not text.startswith(("http://", "https://", "/")):
        return None

    # /spaces/KEY/pages/ID  or  /wiki/spaces/KEY/pages/ID
    m = _SPACES_PAGES_RE.search(text)
    if m:
        return m.group(1)

    # /pages/viewpage/details/ID
    m = _DETAILS_RE.search(text)
    if m:
        return m.group(1)

    # /pages/viewpage.action?pageId=ID
    parsed = urlparse(text)
    qs = parse_qs(parsed.query)
    if "pageId" in qs and qs["pageId"]:
        candidate = qs["pageId"][0]
        if _BARE_NUMERIC_RE.match(candidate):
            return candidate

    return None
