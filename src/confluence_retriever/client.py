"""Confluence REST API adapter — search, page fetch, child listing."""

import concurrent.futures
import logging
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from confluence_retriever.config import TIMEOUT_SECONDS
from confluence_retriever.cql import build_cql, cql_escape
from confluence_retriever.html_utils import strip_highlight_markers
from confluence_retriever.ranking import page_url


class ConfluenceAuthError(Exception):
    """Raised when Confluence returns 401 or 403."""


class ConfluenceNetworkError(Exception):
    """Raised when Confluence is unreachable or returns an unexpected HTTP error."""


class ConfluencePageNotFoundError(Exception):
    """Raised when a specific page lookup returns 404."""


class ConfluenceAdapter:
    def __init__(self, pat: str, base_url: str) -> None:
        self._base_url = base_url
        self._search_endpoint = f"{base_url}/rest/api/content/search"
        self._page_endpoint = f"{base_url}/rest/api/content/{{page_id}}"
        self._children_endpoint = f"{base_url}/rest/api/content/{{page_id}}/child/page"
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

    # ── Search ──────────────────────────────────────────────────────────────

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
            page_id = item.get("id")
            results.append({
                "id": page_id,
                "title": item.get("title", ""),
                "space_key": item.get("space", {}).get("key", ""),
                "space_name": item.get("space", {}).get("name", ""),
                "url": page_url(self._base_url, page_id, item.get("_links", {}).get("webui", "")),
                "excerpt": strip_highlight_markers(item.get("excerpt", "")),
                "last_modified": item.get("version", {}).get("when", ""),
                "_title_hit": False,
            })

        logging.debug("Confluence search returned %d results", len(results))
        return results

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
                            "url": page_url(
                                self._base_url,
                                item.get("id"),
                                item.get("_links", {}).get("webui", ""),
                            ),
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

    # ── Single page ─────────────────────────────────────────────────────────

    def get_page(
        self,
        page_id: str,
        *,
        with_body: bool = True,
        with_attachments: bool = False,
    ) -> Optional[dict]:
        """Fetch a single page. Returns ``None`` if Confluence reports 404.

        Args:
            page_id: Confluence page ID.
            with_body: When False, skip body expansion (cheaper; used by `info`).
            with_attachments: When True, expand the attachments list (used by `read`).
        """
        cache_key = f"{page_id}:body={with_body}:att={with_attachments}"
        if cache_key in self._page_cache:
            return self._page_cache[cache_key]

        url = self._page_endpoint.format(page_id=page_id)
        expand_parts = ["space", "version"]
        if with_body:
            expand_parts.append("body.storage")
        if with_attachments:
            expand_parts.append("children.attachment")
        params = {"expand": ",".join(expand_parts)}

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
        logging.debug("Fetched page %s: %s", page_id, item.get("title", "untitled"))
        result_id = item.get("id") or page_id

        attachments: list[dict] = []
        if with_attachments:
            for att in item.get("children", {}).get("attachment", {}).get("results", []):
                att_links = att.get("_links", {}) or {}
                download = att_links.get("download", "")
                if download and download.startswith("/"):
                    download = f"{self._base_url}{download}"
                attachments.append({
                    "id": att.get("id"),
                    "title": att.get("title", ""),
                    "size": att.get("extensions", {}).get("fileSize", 0),
                    "mediaType": att.get("metadata", {}).get("mediaType", ""),
                    "url": download,
                })

        result = {
            "id": result_id,
            "title": item.get("title", ""),
            "space_key": item.get("space", {}).get("key", ""),
            "space_name": item.get("space", {}).get("name", ""),
            "url": page_url(self._base_url, result_id, item.get("_links", {}).get("webui", "")),
            "body_html": item.get("body", {}).get("storage", {}).get("value", "") if with_body else "",
            "last_modified": item.get("version", {}).get("when", ""),
            "version": item.get("version", {}).get("number"),
            "status": item.get("status", ""),
            "attachments": attachments,
        }
        self._page_cache[cache_key] = result
        return result

    def get_pages(self, page_ids: list[str], workers: int = 4) -> dict[str, dict]:
        """Fetch multiple pages in parallel. Returns mapping of page_id → page dict."""
        cache_key_for = lambda pid: f"{pid}:body=True:att=False"
        uncached = [pid for pid in page_ids if cache_key_for(pid) not in self._page_cache]
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
        result = {}
        for pid in page_ids:
            cached = self._page_cache.get(cache_key_for(pid))
            if cached is not None:
                result[pid] = cached
        missing = [pid for pid in page_ids if pid not in result]
        if missing:
            logging.warning(
                "page fetch dropped %d/%d pages: %s", len(missing), len(page_ids), missing
            )
        return result

    # ── Child pages ─────────────────────────────────────────────────────────

    def get_children(self, page_id: str, limit: int = 50) -> dict:
        """List child pages of a parent. Returns dict with results + pagination metadata.

        Wraps ``GET /rest/api/content/{id}/child/page`` per Atlassian Confluence
        REST API documentation.
        """
        url = self._children_endpoint.format(page_id=page_id)
        params = {
            "limit": limit,
            "expand": "version,space",
        }

        try:
            response = self._session.get(url, params=params, timeout=TIMEOUT_SECONDS)
        except requests.exceptions.ConnectionError as e:
            raise ConfluenceNetworkError(f"Cannot reach {self._base_url}: {e}") from e
        except requests.exceptions.Timeout:
            raise ConfluenceNetworkError(f"Request timed out after {TIMEOUT_SECONDS}s")

        if response.status_code in (401, 403):
            raise ConfluenceAuthError(
                f"Auth failed listing children of {page_id} ({response.status_code}). "
                "Check your CONFLUENCE_PAT."
            )
        if response.status_code == 404:
            raise ConfluencePageNotFoundError(
                f"Parent page {page_id} not found."
            )
        if not response.ok:
            raise ConfluenceNetworkError(
                f"children of {page_id} returned HTTP {response.status_code}"
            )

        data = response.json()
        results = []
        for item in data.get("results", []):
            child_id = item.get("id")
            results.append({
                "id": child_id,
                "title": item.get("title", ""),
                "space_key": item.get("space", {}).get("key", ""),
                "space_name": item.get("space", {}).get("name", ""),
                "url": page_url(self._base_url, child_id, item.get("_links", {}).get("webui", "")),
                "status": item.get("status", ""),
                "last_modified": item.get("version", {}).get("when", ""),
            })

        total_size = data.get("size", len(results))
        return {
            "parent_id": page_id,
            "results": results,
            "size": len(results),
            "limit": data.get("limit", limit),
            "totalSize": total_size,
            "hasMore": total_size > len(results),
        }
