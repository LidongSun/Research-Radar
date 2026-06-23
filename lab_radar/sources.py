from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

from lab_radar.config import LabRadarConfig
from lab_radar.items import RadarItem


USER_AGENT = "LabRadar/0.1 research-intelligence"


def fetch_all(config: LabRadarConfig) -> list[RadarItem]:
    items: list[RadarItem] = []
    if config.source("arxiv").get("enabled", False):
        items.extend(_safe_fetch("arxiv", lambda: fetch_arxiv(config)))
    if config.source("github").get("enabled", False):
        items.extend(_safe_fetch("github", lambda: fetch_github(config)))
    if config.source("huggingface").get("enabled", False):
        items.extend(_safe_fetch("huggingface", lambda: fetch_huggingface(config)))
    return items


def fetch_arxiv(config: LabRadarConfig) -> list[RadarItem]:
    source_cfg = config.source("arxiv")
    categories = source_cfg.get("categories", ["cs.RO", "cs.AI"])
    max_results = int(source_cfg.get("max_results_per_day", 30))
    keywords = config.core_keywords[:8] + config.adjacent_keywords[:4]
    cat_query = " OR ".join(f"cat:{category}" for category in categories)
    keyword_query = " OR ".join(f'all:"{keyword}"' for keyword in keywords)
    query = f"({cat_query}) AND ({keyword_query})" if keyword_query else cat_query
    params = urllib.parse.urlencode(
        {
            "search_query": query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
    )
    data = _get_text(f"https://export.arxiv.org/api/query?{params}")
    root = ET.fromstring(data)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    fetched_at = _now()
    items: list[RadarItem] = []
    for entry in root.findall("atom:entry", ns):
        external_id = _text(entry, "atom:id", ns)
        title = " ".join(_text(entry, "atom:title", ns).split())
        summary = " ".join(_text(entry, "atom:summary", ns).split())
        authors = ", ".join(
            _text(author, "atom:name", ns) for author in entry.findall("atom:author", ns)
        )
        published = _text(entry, "atom:published", ns)
        items.append(
            RadarItem(
                source="arxiv",
                external_id=external_id,
                title=title,
                url=external_id,
                authors_or_owner=authors,
                abstract_or_description=summary,
                published_at=published,
                fetched_at=fetched_at,
            )
        )
    return items


def fetch_github(config: LabRadarConfig) -> list[RadarItem]:
    source_cfg = config.source("github")
    max_results = int(source_cfg.get("max_results_per_day", 30))
    languages = source_cfg.get("languages", ["Python"])
    organizations = source_cfg.get("organizations", [])
    keywords = config.core_keywords[:6] + config.adjacent_keywords[:2]
    fetched_at = _now()
    items: list[RadarItem] = []
    seen: set[str] = set()

    for keyword in keywords:
        for language in languages[:2]:
            query = f'"{keyword}" language:{language}'
            for repo in _github_search(query, per_page=5):
                _append_github_repo(items, seen, repo, fetched_at)
            if len(items) >= max_results:
                return items[:max_results]

    for org in organizations[:8]:
        query = f"org:{org}"
        for repo in _github_search(query, per_page=3):
            _append_github_repo(items, seen, repo, fetched_at)
        if len(items) >= max_results:
            break
    return items


def fetch_huggingface(config: LabRadarConfig) -> list[RadarItem]:
    source_cfg = config.source("huggingface")
    max_results = int(source_cfg.get("max_results_per_day", 30))
    fetched_at = _now()
    items: list[RadarItem] = []
    seen: set[str] = set()
    for keyword in (config.core_keywords[:6] + config.adjacent_keywords[:2] or ["robotics"]):
        params = urllib.parse.urlencode(
            {"search": keyword, "sort": "lastModified", "direction": -1, "limit": 5}
        )
        payload = _get_json(f"https://huggingface.co/api/models?{params}")
        for model in payload:
            model_id = model.get("modelId", "")
            if not model_id or model_id in seen:
                continue
            seen.add(model_id)
            tags = ", ".join(model.get("tags", [])[:10])
            description = f"matched keyword: {keyword}; tags: {tags}"
            downloads = float(model.get("downloads") or 0)
            likes = float(model.get("likes") or 0)
            items.append(
                RadarItem(
                    source="huggingface",
                    external_id=model_id,
                    title=model_id,
                    url=f"https://huggingface.co/{model_id}",
                    authors_or_owner=model_id.split("/")[0] if "/" in model_id else "",
                    abstract_or_description=description,
                    published_at=model.get("lastModified") or "",
                    fetched_at=fetched_at,
                    raw_score=downloads + likes * 10,
                )
            )
            if len(items) >= max_results:
                return items
    return items


def _safe_fetch(name: str, fetcher) -> list[RadarItem]:
    try:
        return fetcher()
    except Exception as exc:
        print(f"[WARN] {name} fetch failed: {exc}")
        return []


def _github_search(query: str, per_page: int) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode(
        {"q": query, "sort": "updated", "order": "desc", "per_page": per_page}
    )
    payload = _get_json(f"https://api.github.com/search/repositories?{params}")
    return list(payload.get("items", []))


def _append_github_repo(
    items: list[RadarItem], seen: set[str], repo: dict[str, Any], fetched_at: str
) -> None:
    owner = repo.get("owner", {}).get("login", "")
    full_name = repo.get("full_name", "")
    external_id = str(repo.get("id") or full_name)
    if not external_id or external_id in seen:
        return
    seen.add(external_id)
    description = repo.get("description") or ""
    stars = float(repo.get("stargazers_count") or 0)
    updated_at = repo.get("updated_at") or ""
    items.append(
        RadarItem(
            source="github",
            external_id=external_id,
            title=full_name,
            url=repo.get("html_url") or "",
            authors_or_owner=owner,
            abstract_or_description=description,
            published_at=updated_at,
            fetched_at=fetched_at,
            raw_score=stars,
        )
    )


def _get_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read().decode("utf-8")
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET failed after retries: {url}: {last_error}")


def _get_json(url: str) -> Any:
    return json.loads(_get_text(url))


def _text(node: ET.Element, selector: str, ns: dict[str, str]) -> str:
    found = node.find(selector, ns)
    return "" if found is None or found.text is None else found.text


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
