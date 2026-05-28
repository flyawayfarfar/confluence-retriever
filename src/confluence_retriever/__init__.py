"""Confluence Retriever — search and rank Confluence pages from the command line.

Public surface re-exported here so external imports stay short:

    from confluence_retriever import ConfluenceAdapter, build_cql, score_result
"""

from confluence_retriever.client import (
    ConfluenceAdapter,
    ConfluenceAuthError,
    ConfluenceNetworkError,
)
from confluence_retriever.config import (
    EXIT_OK,
    EXIT_CONFIG,
    EXIT_AUTH,
    EXIT_NETWORK,
    PROJECT_ENV_FILE,
    USER_ENV_FILE,
    TIMEOUT_SECONDS,
    load_config,
)
from confluence_retriever.cql import build_cql, cql_escape
from confluence_retriever.html_utils import (
    extract_cross_links,
    extract_headings,
    extract_relevant_passages,
    extract_text_blocks,
    html_to_text,
    normalize_text,
    score_text_block,
    strip_highlight_markers,
    truncate_text,
)
from confluence_retriever.ranking import (
    DEPTH_BODY_DEFAULTS,
    ULTRA_CROSSLINK_EXTRA,
    ULTRA_MAX_QUERIES,
    expand_queries,
    page_url,
    query_tokens,
    rank_results,
    resolve_body_options,
    score_result,
    token_in_text,
)

__all__ = [
    "ConfluenceAdapter",
    "ConfluenceAuthError",
    "ConfluenceNetworkError",
    "DEPTH_BODY_DEFAULTS",
    "EXIT_AUTH",
    "EXIT_CONFIG",
    "EXIT_NETWORK",
    "EXIT_OK",
    "PROJECT_ENV_FILE",
    "TIMEOUT_SECONDS",
    "ULTRA_CROSSLINK_EXTRA",
    "ULTRA_MAX_QUERIES",
    "USER_ENV_FILE",
    "build_cql",
    "cql_escape",
    "expand_queries",
    "extract_cross_links",
    "extract_headings",
    "extract_relevant_passages",
    "extract_text_blocks",
    "html_to_text",
    "load_config",
    "normalize_text",
    "page_url",
    "query_tokens",
    "rank_results",
    "resolve_body_options",
    "score_result",
    "score_text_block",
    "strip_highlight_markers",
    "token_in_text",
    "truncate_text",
]
