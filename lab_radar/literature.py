from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from typing import Any, Callable


USER_AGENT = "LabRadar/0.1 literature-search"


@dataclass
class LiteratureResult:
    source: str
    title: str
    url: str
    authors: str = ""
    year: str = ""
    venue: str = ""
    abstract: str = ""
    doi: str = ""
    external_id: str = ""


def search_literature(query: str, source: str = "all", limit: int = 8) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return {"query": query, "results": [], "external_links": []}

    source_map: dict[str, Callable[[str, int], list[LiteratureResult]]] = {
        "arxiv": search_arxiv,
        "openalex": search_openalex,
        "crossref": search_crossref,
        "semantic_scholar": search_semantic_scholar,
        "pubmed": search_pubmed,
        "europe_pmc": search_europe_pmc,
    }
    selected = source_map if source == "all" else {source: source_map[source]} if source in source_map else {}
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for name, searcher in selected.items():
        try:
            results.extend(asdict(item) for item in searcher(query, limit))
        except Exception as exc:
            errors.append({"source": name, "error": str(exc)})

    return {
        "query": query,
        "results": dedupe_results(results),
        "errors": errors,
        "external_links": external_search_links(query),
    }


def search_arxiv(query: str, limit: int) -> list[LiteratureResult]:
    params = urllib.parse.urlencode(
        {
            "search_query": f'all:"{query}"',
            "start": 0,
            "max_results": limit,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
    )
    root = ET.fromstring(get_text(f"https://export.arxiv.org/api/query?{params}"))
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    results = []
    for entry in root.findall("atom:entry", ns):
        url = text(entry, "atom:id", ns)
        results.append(
            LiteratureResult(
                source="arXiv",
                title=" ".join(text(entry, "atom:title", ns).split()),
                url=url,
                authors=", ".join(text(author, "atom:name", ns) for author in entry.findall("atom:author", ns)),
                year=text(entry, "atom:published", ns)[:4],
                venue="arXiv",
                abstract=" ".join(text(entry, "atom:summary", ns).split())[:700],
                external_id=url.rsplit("/", 1)[-1],
            )
        )
    return results


def search_openalex(query: str, limit: int) -> list[LiteratureResult]:
    params = urllib.parse.urlencode({"search": query, "per-page": limit, "sort": "relevance_score:desc"})
    payload = get_json(f"https://api.openalex.org/works?{params}")
    results = []
    for work in payload.get("results", []):
        authors = ", ".join(
            item.get("author", {}).get("display_name", "")
            for item in work.get("authorships", [])[:6]
            if item.get("author", {}).get("display_name")
        )
        venue = (work.get("primary_location") or {}).get("source") or {}
        results.append(
            LiteratureResult(
                source="OpenAlex",
                title=work.get("display_name") or "",
                url=work.get("doi") or work.get("id") or "",
                authors=authors,
                year=str(work.get("publication_year") or ""),
                venue=venue.get("display_name") or "",
                abstract=inverted_abstract(work.get("abstract_inverted_index")),
                doi=(work.get("doi") or "").replace("https://doi.org/", ""),
                external_id=work.get("id") or "",
            )
        )
    return results


def search_crossref(query: str, limit: int) -> list[LiteratureResult]:
    params = urllib.parse.urlencode({"query": query, "rows": limit, "sort": "relevance"})
    payload = get_json(f"https://api.crossref.org/works?{params}")
    results = []
    for work in payload.get("message", {}).get("items", []):
        title = " ".join(work.get("title") or []) or ""
        authors = ", ".join(
            " ".join(part for part in [author.get("given", ""), author.get("family", "")] if part)
            for author in work.get("author", [])[:6]
        )
        year_parts = work.get("published-print") or work.get("published-online") or work.get("created") or {}
        year = ""
        if year_parts.get("date-parts"):
            year = str(year_parts["date-parts"][0][0])
        doi = work.get("DOI") or ""
        results.append(
            LiteratureResult(
                source="Crossref",
                title=title,
                url=work.get("URL") or (f"https://doi.org/{doi}" if doi else ""),
                authors=authors,
                year=year,
                venue=", ".join(work.get("container-title") or []),
                abstract=strip_html(work.get("abstract") or "")[:700],
                doi=doi,
                external_id=doi,
            )
        )
    return results


def search_semantic_scholar(query: str, limit: int) -> list[LiteratureResult]:
    fields = "title,authors,year,venue,abstract,url,externalIds"
    params = urllib.parse.urlencode({"query": query, "limit": limit, "fields": fields})
    payload = get_json(f"https://api.semanticscholar.org/graph/v1/paper/search?{params}")
    results = []
    for paper in payload.get("data", []):
        external_ids = paper.get("externalIds") or {}
        results.append(
            LiteratureResult(
                source="Semantic Scholar",
                title=paper.get("title") or "",
                url=paper.get("url") or "",
                authors=", ".join(author.get("name", "") for author in paper.get("authors", [])[:6]),
                year=str(paper.get("year") or ""),
                venue=paper.get("venue") or "",
                abstract=(paper.get("abstract") or "")[:700],
                doi=external_ids.get("DOI") or "",
                external_id=paper.get("paperId") or "",
            )
        )
    return results


def search_pubmed(query: str, limit: int) -> list[LiteratureResult]:
    search_params = urllib.parse.urlencode(
        {"db": "pubmed", "term": query, "retmode": "json", "retmax": limit, "sort": "relevance"}
    )
    search_payload = get_json(f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?{search_params}")
    ids = search_payload.get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []
    summary_params = urllib.parse.urlencode({"db": "pubmed", "id": ",".join(ids), "retmode": "json"})
    summary_payload = get_json(f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?{summary_params}")
    results = []
    for pmid in ids:
        item = summary_payload.get("result", {}).get(pmid, {})
        authors = ", ".join(author.get("name", "") for author in item.get("authors", [])[:6])
        results.append(
            LiteratureResult(
                source="PubMed",
                title=item.get("title") or "",
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                authors=authors,
                year=(item.get("pubdate") or "")[:4],
                venue=item.get("source") or "",
                external_id=pmid,
            )
        )
    return results


def search_europe_pmc(query: str, limit: int) -> list[LiteratureResult]:
    params = urllib.parse.urlencode({"query": query, "format": "json", "pageSize": limit})
    payload = get_json(f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?{params}")
    results = []
    for item in payload.get("resultList", {}).get("result", []):
        results.append(
            LiteratureResult(
                source="Europe PMC",
                title=item.get("title") or "",
                url=item.get("doi") and f"https://doi.org/{item.get('doi')}" or item.get("fullTextUrlList", {}).get("fullTextUrl", [{}])[0].get("url", ""),
                authors=item.get("authorString") or "",
                year=item.get("pubYear") or "",
                venue=item.get("journalTitle") or "",
                abstract=(item.get("abstractText") or "")[:700],
                doi=item.get("doi") or "",
                external_id=item.get("id") or "",
            )
        )
    return results


def dedupe_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique = []
    for item in results:
        key = (item.get("doi") or item.get("title") or item.get("url") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def external_search_links(query: str) -> list[dict[str, str]]:
    encoded = urllib.parse.quote_plus(query)
    return [
        {"source": "Google Scholar", "url": f"https://scholar.google.com/scholar?q={encoded}", "note": "opens external search"},
        {"source": "IEEE Xplore", "url": f"https://ieeexplore.ieee.org/search/searchresult.jsp?newsearch=true&queryText={encoded}", "note": "external search; API key needed for direct integration"},
        {"source": "ScienceDirect", "url": f"https://www.sciencedirect.com/search?qs={encoded}", "note": "external search; Elsevier API key needed for direct integration"},
        {"source": "ACM Digital Library", "url": f"https://dl.acm.org/action/doSearch?AllField={encoded}", "note": "external search"},
        {"source": "SpringerLink", "url": f"https://link.springer.com/search?query={encoded}", "note": "external search"},
        {"source": "Wiley Online Library", "url": f"https://onlinelibrary.wiley.com/action/doSearch?AllField={encoded}", "note": "external search"},
        {"source": "DBLP", "url": f"https://dblp.org/search?q={encoded}", "note": "external search"},
        {"source": "Connected Papers", "url": f"https://www.connectedpapers.com/search?q={encoded}", "note": "external discovery"},
    ]


def get_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                return response.read().decode("utf-8")
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1.2 * (attempt + 1))
    raise RuntimeError(f"GET failed after retries: {last_error}")


def get_json(url: str) -> Any:
    return json.loads(get_text(url))


def text(node: ET.Element, selector: str, ns: dict[str, str]) -> str:
    found = node.find(selector, ns)
    return "" if found is None or found.text is None else found.text


def inverted_abstract(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    words = sorted(((position, word) for word, positions in index.items() for position in positions))
    return " ".join(word for _, word in words)[:700]


def strip_html(value: str) -> str:
    output = []
    in_tag = False
    for char in value:
        if char == "<":
            in_tag = True
            continue
        if char == ">":
            in_tag = False
            continue
        if not in_tag:
            output.append(char)
    return " ".join("".join(output).split())
