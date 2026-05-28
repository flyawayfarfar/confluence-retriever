#!/usr/bin/env python3
"""Legacy shim — re-exports the ``confluence_retriever`` package surface.

Prefer the ``confluence-search`` console script installed by ``pip install .``.
This file is kept so that callers using the old ``python3 scripts/wiki_answer.py``
path or ``import wiki_answer`` in tests continue to work unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path

# When run directly (not pip-installed), make the in-tree src/ importable.
_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# ── re-export the package's public surface ──────────────────────────────────

from confluence_retriever.client import (  # noqa: E402,F401
    ConfluenceAdapter,
    ConfluenceAuthError,
    ConfluenceNetworkError,
    ConfluencePageNotFoundError,
)
from confluence_retriever.config import (  # noqa: E402,F401
    EXIT_OK,
    EXIT_CONFIG,
    EXIT_AUTH,
    EXIT_NETWORK,
    TIMEOUT_SECONDS,
    load_config,
)
from confluence_retriever import config as _config_module  # noqa: E402
from confluence_retriever.cql import build_cql, cql_escape  # noqa: E402,F401
from confluence_retriever.html_utils import (  # noqa: E402,F401
    _proximity_bonus,
    extract_cross_links,
    extract_headings,
    extract_relevant_passages,
    extract_text_blocks,
    html_to_markdown,
    html_to_text,
    normalize_text,
    score_text_block,
    strip_highlight_markers,
    truncate_text,
)
from confluence_retriever.ranking import (  # noqa: E402,F401
    DEFAULT_BODY_CHARS,
    DEPTH_BODY_DEFAULTS,
    DEPTH_DEPRECATED_ALIASES,
    ULTRA_CROSSLINK_EXTRA,
    ULTRA_MAX_QUERIES,
    _structural_variants,
    expand_queries,
    page_url,
    query_tokens,
    rank_results,
    resolve_body_options,
    score_result,
    token_in_text,
)
from confluence_retriever.url_parsing import extract_page_id  # noqa: E402,F401
from confluence_retriever.cli import main_entry  # noqa: E402


# ── monkey-patch friendliness ───────────────────────────────────────────────
#
# Tests do `monkeypatch.setattr(wiki, "PROJECT_ENV_FILE", path)`. To keep that
# working we expose them as module attributes here AND mirror writes back to
# the ``confluence_retriever.config`` module via __setattr__-on-module trick.

PROJECT_ENV_FILE = _config_module.PROJECT_ENV_FILE
USER_ENV_FILE = _config_module.USER_ENV_FILE


def __getattr__(name: str):
    # Forward unknown lookups (e.g. attributes mutated via monkeypatch.setattr
    # on the original module) so the package and the shim stay in sync.
    if name in ("PROJECT_ENV_FILE", "USER_ENV_FILE"):
        return getattr(_config_module, name)
    raise AttributeError(name)


def __setattr_proxy(name: str, value) -> None:  # not actually used; left for docs
    raise NotImplementedError


# Python module-level __setattr__ isn't a built-in — we instead provide a
# helper class so `monkeypatch.setattr(wiki, "PROJECT_ENV_FILE", x)` writes
# through. Approach: replace the module's class with one that proxies writes.
import sys as _sys  # noqa: E402
import types as _types  # noqa: E402


class _ShimModule(_types.ModuleType):
    def __setattr__(self, name, value):
        if name in ("PROJECT_ENV_FILE", "USER_ENV_FILE"):
            setattr(_config_module, name, value)
        super().__setattr__(name, value)


_sys.modules[__name__].__class__ = _ShimModule


# ── CLI entry points ────────────────────────────────────────────────────────

def main(argv=None):
    """Legacy entry point: forwards to the Click CLI with backward-compat flag injection."""
    main_entry(argv)


if __name__ == "__main__":
    main()
