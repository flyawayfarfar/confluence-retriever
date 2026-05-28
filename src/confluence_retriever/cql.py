"""CQL builder helpers for Confluence searches."""

import logging
from typing import Optional


def cql_escape(text: str) -> str:
    """Escape special characters in a CQL string literal."""
    # Escape backslash first, then double-quote
    return text.replace("\\", "\\\\").replace('"', '\\"')


def build_cql(queries: list[str], space: Optional[str], include_title: bool = True) -> str:
    """Build a CQL query string from one or more query terms and an optional space filter.

    Multiple queries are OR'd: (title ~ "q1" OR text ~ "q1" OR title ~ "q2" OR text ~ "q2")
    Space filter is AND'd: ... AND space = "SPACE"

    Args:
        queries: List of search terms.
        space: Optional Confluence space key to filter results.
        include_title: If True, search both title and text fields for better matches.
    """
    if include_title:
        # Search both title and text for each query term - title matches often more relevant
        terms = []
        for q in queries:
            escaped = cql_escape(q)
            terms.append(f'title ~ "{escaped}"')
            terms.append(f'text ~ "{escaped}"')
    else:
        terms = [f'text ~ "{cql_escape(q)}"' for q in queries]

    if len(terms) == 1:
        cql = terms[0]
    else:
        cql = "(" + " OR ".join(terms) + ")"

    cql += ' AND type = "page"'

    if space:
        cql += f' AND space = "{cql_escape(space)}"'

    logging.debug("Built CQL query: %s", cql)
    return cql
