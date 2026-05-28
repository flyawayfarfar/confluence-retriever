"""Click-based CLI for Confluence Retriever.

Commands:
    confluence-search                  # legacy/default: invokes `search`
    confluence-search search ...
    confluence-search read   <id|url>
    confluence-search info   <id|url>
    confluence-search children <id|url>
    confluence-search setup
    confluence-search doctor
"""

from __future__ import annotations

import logging
import os
import stat
import sys
from pathlib import Path
from typing import Optional

import click

from confluence_retriever.client import (
    ConfluenceAdapter,
    ConfluenceAuthError,
    ConfluenceNetworkError,
    ConfluencePageNotFoundError,
)
from confluence_retriever.config import (
    EXIT_AUTH,
    EXIT_CONFIG,
    EXIT_NETWORK,
    EXIT_OK,
    PROJECT_ENV_FILE,
    USER_ENV_FILE,
    load_config,
)
from confluence_retriever.formatters import (
    format_children_json,
    format_children_markdown,
    format_info_json,
    format_info_markdown,
    format_page_json,
    format_page_markdown,
    format_search_json,
    format_search_markdown,
)
from confluence_retriever.html_utils import (
    extract_cross_links,
    extract_headings,
    extract_relevant_passages,
)
from confluence_retriever.ranking import (
    DEPTH_BODY_DEFAULTS,
    DEPTH_DEPRECATED_ALIASES,
    ULTRA_CROSSLINK_EXTRA,
    expand_queries,
    rank_results,
    resolve_body_options,
)
from confluence_retriever.url_parsing import extract_page_id


VALID_DEPTHS = tuple(DEPTH_BODY_DEFAULTS)


# ── helpers ──────────────────────────────────────────────────────────────────

def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(name)s [%(levelname)s] %(message)s")


def _stdin_is_tty() -> bool:
    """Indirection so tests can monkey-patch via ``confluence_retriever.cli._stdin_is_tty``."""
    return sys.stdin.isatty()


def _normalise_depth(depth: str) -> str:
    """Map deprecated `--depth` aliases to current names with a warning."""
    if depth in DEPTH_BODY_DEFAULTS:
        return depth
    if depth in DEPTH_DEPRECATED_ALIASES:
        new_name = DEPTH_DEPRECATED_ALIASES[depth]
        click.echo(
            f"WARNING: --depth {depth} is deprecated; use --depth {new_name} instead.",
            err=True,
        )
        return new_name
    raise click.BadParameter(
        f"invalid choice: {depth} (choose from {', '.join(VALID_DEPTHS)})"
    )


def _resolve_page_ref(value: str) -> str:
    """Return a page ID from a URL or bare ID; exit with a friendly error otherwise."""
    page_id = extract_page_id(value)
    if not page_id:
        click.echo(
            f"ERROR: could not extract a Confluence page ID from {value!r}. "
            "Expected a numeric ID or a Confluence page URL.",
            err=True,
        )
        sys.exit(EXIT_CONFIG)
    return page_id


def _connect() -> ConfluenceAdapter:
    pat, base_url = load_config()
    return ConfluenceAdapter(pat, base_url)


def _handle_api(fn):
    """Wrap a function that may raise Confluence{Auth,Network,…}Error → exit code."""
    try:
        return fn()
    except ConfluenceAuthError as e:
        click.echo(f"ERROR: {e}", err=True)
        sys.exit(EXIT_AUTH)
    except ConfluencePageNotFoundError as e:
        click.echo(f"ERROR: {e}", err=True)
        sys.exit(EXIT_NETWORK)
    except ConfluenceNetworkError as e:
        click.echo(f"ERROR: {e}", err=True)
        sys.exit(EXIT_NETWORK)


# ── group ────────────────────────────────────────────────────────────────────

@click.group(
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.pass_context
def main(ctx: click.Context) -> None:
    """Search and read pages from a Confluence instance.

    With no subcommand, runs `search` for backward compatibility with the
    legacy `wiki_answer.py --query "..."` invocation.
    """
    if ctx.invoked_subcommand is None:
        # Fall through to `search` so old flag-only invocations keep working.
        ctx.invoke(search_cmd, **_default_search_kwargs(ctx))


def _default_search_kwargs(_ctx: click.Context) -> dict:
    # The legacy fallthrough is only useful if --query was given. Click will
    # then re-parse via `ctx.invoke`. We can't easily forward unparsed argv,
    # so just bail with the help text when no subcommand is given without args.
    click.echo(main.get_help(_ctx), err=True)
    sys.exit(EXIT_CONFIG)


# ── search ──────────────────────────────────────────────────────────────────

@main.command("search")
@click.option(
    "--query", "queries", multiple=True, required=False, metavar="TEXT",
    help="Search query (repeat to combine terms). Required unless --page-id is given.",
)
@click.option(
    "--page-id", "page_ref", default=None, metavar="ID-OR-URL",
    help="Skip search; fetch this page directly (numeric ID or Confluence URL).",
)
@click.option("--space", default=None, metavar="KEY", help="Filter by Confluence space key.")
@click.option("--limit", type=int, default=5, metavar="N", help="Maximum number of results.")
@click.option(
    "--depth", default="links", metavar="MODE",
    help=f"Retrieval depth: {', '.join(VALID_DEPTHS)} (default: links). "
         "`ultra` is a deprecated alias for `deep`.",
)
@click.option(
    "--recency-halflife-days", type=int, default=None, metavar="DAYS",
    help="(deep only) Use recency decay as a tie-breaker.",
)
@click.option(
    "--legacy-scorer", is_flag=True,
    help="Use the pre-deep ranking formula, even with --depth deep.",
)
@click.option("--body-top", type=int, default=None, metavar="N",
              help="Override number of top pages to fetch bodies for.")
@click.option("--body-chars", type=int, default=None, metavar="N",
              help="Override max passage characters per page.")
@click.option(
    "--format", "output_format",
    type=click.Choice(["markdown", "json"], case_sensitive=False),
    default="markdown",
    help="Output format (default: markdown).",
)
@click.option(
    "--json", "json_flag", is_flag=True,
    help="(Deprecated) Equivalent to --format json.",
)
@click.option("--workers", type=int, default=4, metavar="N",
              help="Maximum parallel HTTP workers for page fetches.")
@click.option("-v", "--verbose", is_flag=True, help="Verbose debug logging.")
def search_cmd(
    queries: tuple[str, ...],
    page_ref: Optional[str],
    space: Optional[str],
    limit: int,
    depth: str,
    recency_halflife_days: Optional[int],
    legacy_scorer: bool,
    body_top: Optional[int],
    body_chars: Optional[int],
    output_format: str,
    json_flag: bool,
    workers: int,
    verbose: bool,
) -> None:
    """Search Confluence and return ranked results (default subcommand)."""
    _setup_logging(verbose)
    depth = _normalise_depth(depth)
    if json_flag:
        click.echo("WARNING: --json is deprecated; use --format json instead.", err=True)
        output_format = "json"

    if not queries and not page_ref:
        raise click.UsageError("at least one --query or a --page-id is required")

    adapter = _connect()

    # ── --page-id fast path: skip search entirely ─────────────────────────
    if page_ref:
        pid = _resolve_page_ref(page_ref)
        page = _handle_api(lambda: adapter.get_page(pid, with_body=True))
        if page is None:
            click.echo(f"ERROR: page {pid} not found.", err=True)
            sys.exit(EXIT_NETWORK)

        ranked = [{
            "id": page["id"],
            "title": page["title"],
            "space_key": page["space_key"],
            "space_name": page["space_name"],
            "url": page["url"],
            "excerpt": "",
            "last_modified": page.get("last_modified", ""),
            "_title_hit": False,
        }]
        body_by_id: dict[str, dict] = {}
        if page.get("body_html"):
            top_n, char_budget = resolve_body_options(depth, body_top, body_chars)
            if top_n == 0:
                char_budget = char_budget or 1200
            body_by_id[page["id"]] = {
                "headings": extract_headings(page["body_html"])[:8],
                "passages": extract_relevant_passages(
                    page["body_html"], list(queries) or [page["title"]],
                    max_chars=max(char_budget, 800),
                ),
            }
        _emit_search(
            output_format, list(queries) or [page["title"]], space, depth, ranked, body_by_id,
        )
        return

    # ── normal search path ────────────────────────────────────────────────
    is_deep = depth == "deep"
    active_queries = expand_queries(list(queries)) if is_deep else list(queries)

    def _run_search() -> list[dict]:
        if is_deep:
            results = adapter.search_combined(active_queries, space, limit, workers=workers)
            enhanced = not legacy_scorer
            scoring_queries = active_queries if enhanced else list(queries)
            return rank_results(
                results, scoring_queries, space,
                enhanced=enhanced,
                halflife_days=recency_halflife_days if enhanced else None,
            )
        results = adapter.search(list(queries), space, limit)
        return rank_results(results, list(queries), space)

    ranked = _handle_api(_run_search)
    if not ranked:
        click.echo("No results found.")
        return

    body_by_id = {}
    body_top_n, body_chars_n = resolve_body_options(depth, body_top, body_chars)

    if body_top_n and body_chars_n:
        ids_to_fetch = [r["id"] for r in ranked[:body_top_n]]
        pages_by_id = _handle_api(lambda: adapter.get_pages(ids_to_fetch, workers=workers))
        for result in ranked[:body_top_n]:
            page = pages_by_id.get(result["id"])
            if page and page.get("body_html"):
                body_by_id[result["id"]] = {
                    "headings": extract_headings(page["body_html"])[:8],
                    "passages": extract_relevant_passages(
                        page["body_html"], active_queries, max_chars=body_chars_n,
                    ),
                }

        if is_deep:
            seen_ids = {r["id"] for r in ranked}
            cross_pairs: list[tuple[str, str, str]] = []
            for result in ranked[:body_top_n]:
                page = pages_by_id.get(result["id"])
                if page and page.get("body_html"):
                    for link_id in extract_cross_links(page["body_html"]):
                        if link_id not in seen_ids and len(cross_pairs) < ULTRA_CROSSLINK_EXTRA:
                            cross_pairs.append((link_id, result["id"], result["url"]))
                            seen_ids.add(link_id)
            if cross_pairs:
                cross_ids = [pid for pid, _, _ in cross_pairs]
                from_page_map = {pid: src for pid, src, _ in cross_pairs}
                from_page_url_map = {pid: src_url for pid, _, src_url in cross_pairs}
                extra_pages = _handle_api(
                    lambda: adapter.get_pages(cross_ids, workers=workers)
                )
                for pid, xpage in extra_pages.items():
                    ranked.append({
                        "id": pid,
                        "title": xpage.get("title", ""),
                        "space_key": xpage.get("space_key", ""),
                        "space_name": xpage.get("space_name", ""),
                        "url": xpage.get("url", ""),
                        "excerpt": "",
                        "last_modified": "",
                        "_title_hit": False,
                        "source": "cross-link",
                        "from_page": from_page_map.get(pid, ""),
                        "from_page_url": from_page_url_map.get(pid, ""),
                    })
                    if xpage.get("body_html"):
                        body_by_id[pid] = {
                            "headings": extract_headings(xpage["body_html"])[:8],
                            "passages": extract_relevant_passages(
                                xpage["body_html"], active_queries, max_chars=body_chars_n,
                            ),
                        }

    _emit_search(output_format, list(queries), space, depth, ranked, body_by_id)


def _emit_search(
    output_format: str,
    queries: list[str],
    space: Optional[str],
    depth: str,
    ranked: list[dict],
    body_by_id: dict[str, dict],
) -> None:
    if output_format == "json":
        click.echo(format_search_json(
            queries=queries, space=space, depth=depth,
            ranked=ranked, body_by_id=body_by_id,
        ))
    else:
        click.echo(format_search_markdown(
            queries=queries, ranked=ranked, body_by_id=body_by_id,
        ))


# ── read ────────────────────────────────────────────────────────────────────

@main.command("read")
@click.argument("page_ref")
@click.option(
    "--format", "output_format",
    type=click.Choice(["markdown", "json"], case_sensitive=False),
    default="markdown",
)
@click.option("--no-attachments", is_flag=True, help="Exclude attachments from output.")
@click.option("-v", "--verbose", is_flag=True)
def read_cmd(page_ref: str, output_format: str, no_attachments: bool, verbose: bool) -> None:
    """Fetch a single page (by ID or URL) and render its full content."""
    _setup_logging(verbose)
    pid = _resolve_page_ref(page_ref)
    adapter = _connect()
    page = _handle_api(
        lambda: adapter.get_page(pid, with_body=True, with_attachments=not no_attachments)
    )
    if page is None:
        click.echo(f"ERROR: page {pid} not found.", err=True)
        sys.exit(EXIT_NETWORK)

    if output_format == "json":
        click.echo(format_page_json(page, include_attachments=not no_attachments))
    else:
        click.echo(format_page_markdown(page, include_attachments=not no_attachments))


# ── info ────────────────────────────────────────────────────────────────────

@main.command("info")
@click.argument("page_ref")
@click.option(
    "--format", "output_format",
    type=click.Choice(["markdown", "json"], case_sensitive=False),
    default="markdown",
)
@click.option("-v", "--verbose", is_flag=True)
def info_cmd(page_ref: str, output_format: str, verbose: bool) -> None:
    """Show metadata for a page (no body content)."""
    _setup_logging(verbose)
    pid = _resolve_page_ref(page_ref)
    adapter = _connect()
    page = _handle_api(lambda: adapter.get_page(pid, with_body=False))
    if page is None:
        click.echo(f"ERROR: page {pid} not found.", err=True)
        sys.exit(EXIT_NETWORK)

    if output_format == "json":
        click.echo(format_info_json(page))
    else:
        click.echo(format_info_markdown(page))


# ── children ────────────────────────────────────────────────────────────────

@main.command("children")
@click.argument("parent_ref")
@click.option("--limit", type=int, default=50, help="Maximum child pages (default: 50).")
@click.option(
    "--format", "output_format",
    type=click.Choice(["markdown", "json"], case_sensitive=False),
    default="markdown",
)
@click.option("-v", "--verbose", is_flag=True)
def children_cmd(parent_ref: str, limit: int, output_format: str, verbose: bool) -> None:
    """List the child pages of a parent page (by ID or URL)."""
    _setup_logging(verbose)
    pid = _resolve_page_ref(parent_ref)
    adapter = _connect()
    children = _handle_api(lambda: adapter.get_children(pid, limit=limit))

    if output_format == "json":
        click.echo(format_children_json(children))
    else:
        click.echo(format_children_markdown(children))


# ── setup ───────────────────────────────────────────────────────────────────

@main.command("setup")
@click.option("--force", is_flag=True, help="Overwrite an existing .env without prompting.")
def setup_cmd(force: bool) -> None:
    """Interactive credential setup. Writes ~/.config/confluence-retriever/.env (0600)."""
    if not _stdin_is_tty():
        click.echo(
            "ERROR: setup requires an interactive terminal. "
            "For non-interactive environments, set CONFLUENCE_URL and CONFLUENCE_PAT in the "
            "environment or write them to ~/.config/confluence-retriever/.env directly.",
            err=True,
        )
        sys.exit(EXIT_CONFIG)

    target = USER_ENV_FILE
    if target.exists() and not force:
        if not click.confirm(f"{target} already exists. Overwrite?", default=False):
            click.echo("Aborted.")
            sys.exit(EXIT_OK)

    click.echo("Confluence Retriever — interactive setup")
    click.echo("(values are written to a 0600 dotfile under your home directory)")
    url = click.prompt(
        "Confluence base URL (e.g. https://wiki.example.com — no trailing path)"
    ).strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        click.echo(f"ERROR: URL must start with http:// or https://, got {url!r}", err=True)
        sys.exit(EXIT_CONFIG)
    if "/rest/api" in url or url.endswith("/wiki"):
        click.echo(
            "WARNING: URL looks like an API path; the CLI appends /rest/api/... itself. "
            "Continuing anyway.",
            err=True,
        )

    pat = click.prompt("Personal Access Token (input hidden)", hide_input=True).strip()
    if not pat:
        click.echo("ERROR: PAT cannot be empty.", err=True)
        sys.exit(EXIT_CONFIG)

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"CONFLUENCE_URL={url}\nCONFLUENCE_PAT={pat}\n", encoding="utf-8")
    os.chmod(target, stat.S_IRUSR | stat.S_IWUSR)

    perms = oct(target.stat().st_mode & 0o777)
    click.echo(f"Wrote {target} ({perms})")
    click.echo("Next: confluence-search doctor   # validate the configuration")


# ── doctor ──────────────────────────────────────────────────────────────────

@main.command("doctor")
def doctor_cmd() -> None:
    """Self-diagnose: config present? PAT valid? Confluence reachable?"""
    all_ok = True

    env_file = USER_ENV_FILE if USER_ENV_FILE.exists() else PROJECT_ENV_FILE
    if env_file.exists():
        click.echo(f"[ok] config file: {env_file}")
        perms = oct(env_file.stat().st_mode & 0o777)
        if env_file == USER_ENV_FILE and perms != "0o600":
            click.echo(f"[warn] perms on {env_file}: {perms} (expected 0o600)")
        else:
            click.echo(f"[ok] perms: {perms}")
    else:
        click.echo(f"[fail] no config file at {USER_ENV_FILE} or {PROJECT_ENV_FILE}")
        click.echo("       run: confluence-search setup")
        sys.exit(EXIT_CONFIG)

    try:
        pat, base_url = load_config()
    except SystemExit:
        sys.exit(EXIT_CONFIG)
    click.echo(f"[ok] CONFLUENCE_URL = {base_url}")
    click.echo(f"[ok] CONFLUENCE_PAT = {'*' * 6}{pat[-4:] if len(pat) > 8 else '****'}")

    adapter = ConfluenceAdapter(pat, base_url)
    try:
        results = adapter.search(["test"], None, 1)
        click.echo(f"[ok] search round-trip ({len(results)} result)")
    except ConfluenceAuthError as e:
        click.echo(f"[fail] auth: {e}")
        all_ok = False
    except ConfluenceNetworkError as e:
        click.echo(f"[fail] network: {e}")
        all_ok = False

    if all_ok:
        click.echo("\nAll checks passed.")
        sys.exit(EXIT_OK)
    sys.exit(EXIT_NETWORK)


# ── argv adapter for the legacy shim ────────────────────────────────────────

def main_entry(argv: Optional[list[str]] = None) -> None:
    """Legacy compatibility shim.

    The old ``wiki_answer.py`` accepted ``--query`` etc. as top-level flags.
    Click's group requires a subcommand. We detect "no subcommand, but search-
    like flags present" and inject ``search`` so old scripts keep working.
    """
    args = list(argv if argv is not None else sys.argv[1:])
    known_subcommands = {"search", "read", "info", "children", "setup", "doctor"}
    has_subcommand = any(
        a in known_subcommands for a in args if not a.startswith("-")
    )
    looks_like_search = any(
        a.startswith(("--query", "--page-id", "--space", "--limit", "--depth", "--json"))
        for a in args
    )
    if not has_subcommand and looks_like_search:
        args = ["search"] + args
    main.main(args=args, prog_name="confluence-search", standalone_mode=True)


if __name__ == "__main__":
    main_entry()
