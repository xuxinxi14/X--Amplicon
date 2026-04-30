"""PubMed literature retrieval tools."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"


def _load_env_file_value(key: str) -> str:
    if not ENV_FILE.is_file():
        return ""
    try:
        with ENV_FILE.open("r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, _, value = line.partition("=")
                if name.strip().lstrip("\ufeff") == key:
                    return value.strip().strip('"').strip("'")
    except OSError:
        return ""
    return ""


def _get_config_value(key: str) -> str:
    return os.getenv(key) or _load_env_file_value(key)


def _configure_entrez(email: str | None = None, api_key: str | None = None) -> Any:
    try:
        from Bio import Entrez
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Biopython is required for PubMed retrieval. Install requirements-skills.txt."
        ) from exc

    resolved_email = email or _get_config_value("NCBI_EMAIL") or _get_config_value("ENTREZ_EMAIL")
    if not resolved_email:
        raise ValueError(
            "NCBI email is required for PubMed retrieval. Set NCBI_EMAIL in .env "
            "or pass the email argument."
        )
    Entrez.email = resolved_email
    resolved_key = api_key or _get_config_value("NCBI_API_KEY")
    if resolved_key:
        Entrez.api_key = resolved_key
    return Entrez


def _docsum_to_record(docsum: Any) -> dict[str, Any]:
    article_ids = docsum.get("ArticleIds", []) if hasattr(docsum, "get") else []
    doi = None
    for article_id in article_ids:
        try:
            if str(article_id.attributes.get("IdType", "")).lower() == "doi":
                doi = str(article_id)
        except AttributeError:
            continue

    authors = docsum.get("AuthorList", []) if hasattr(docsum, "get") else []
    return {
        "pmid": str(docsum.get("Id", "")),
        "title": str(docsum.get("Title", "")),
        "journal": str(docsum.get("FullJournalName", "") or docsum.get("Source", "")),
        "pubdate": str(docsum.get("PubDate", "")),
        "authors": [str(author) for author in authors[:10]],
        "doi": doi,
    }


def search_pubmed_literature(
    query: str,
    max_results: int = 10,
    email: str | None = None,
    api_key: str | None = None,
    sort: str = "relevance",
) -> dict[str, Any]:
    """Search PubMed and return compact citation metadata."""

    if not query.strip():
        raise ValueError("query must not be empty")
    Entrez = _configure_entrez(email=email, api_key=api_key)
    retmax = max(1, min(int(max_results), 50))

    search_handle = Entrez.esearch(db="pubmed", term=query, retmax=retmax, sort=sort)
    try:
        search_result = Entrez.read(search_handle)
    finally:
        search_handle.close()

    pmids = [str(pmid) for pmid in search_result.get("IdList", [])]
    if not pmids:
        return {
            "query": query,
            "pmids": [],
            "records": [],
            "record_count": 0,
        }

    summary_handle = Entrez.esummary(db="pubmed", id=",".join(pmids))
    try:
        summaries = Entrez.read(summary_handle)
    finally:
        summary_handle.close()

    records = [_docsum_to_record(docsum) for docsum in summaries]
    return {
        "query": query,
        "pmids": pmids,
        "records": records,
        "record_count": len(records),
    }


def fetch_pubmed_abstracts(
    pmids: list[str],
    email: str | None = None,
    api_key: str | None = None,
    max_records: int = 10,
) -> dict[str, Any]:
    """Fetch PubMed abstracts as plain text for selected PMIDs."""

    cleaned = [str(pmid).strip() for pmid in pmids if str(pmid).strip()]
    if not cleaned:
        raise ValueError("pmids must contain at least one PMID")
    Entrez = _configure_entrez(email=email, api_key=api_key)
    selected = cleaned[: max(1, min(int(max_records), 20))]

    handle = Entrez.efetch(db="pubmed", id=",".join(selected), rettype="abstract", retmode="text")
    try:
        text = handle.read()
    finally:
        handle.close()
    return {
        "pmids": selected,
        "record_count": len(selected),
        "abstract_text": text,
    }


TOOL_DEFINITIONS = [
    {
        "name": "search_pubmed_literature",
        "description": (
            "Search PubMed for source-backed biomedical or microbiome literature. "
            "Requires NCBI_EMAIL or an explicit email argument."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "PubMed search query."},
                "max_results": {"type": "integer", "default": 10},
                "email": {"type": "string", "description": "Optional NCBI email override."},
                "api_key": {"type": "string", "description": "Optional NCBI API key override."},
                "sort": {"type": "string", "default": "relevance"},
            },
            "required": ["query"],
        },
        "fn": search_pubmed_literature,
    },
    {
        "name": "fetch_pubmed_abstracts",
        "description": "Fetch PubMed abstracts as plain text for a list of PMIDs.",
        "parameters": {
            "type": "object",
            "properties": {
                "pmids": {"type": "array", "items": {"type": "string"}},
                "email": {"type": "string", "description": "Optional NCBI email override."},
                "api_key": {"type": "string", "description": "Optional NCBI API key override."},
                "max_records": {"type": "integer", "default": 10},
            },
            "required": ["pmids"],
        },
        "fn": fetch_pubmed_abstracts,
    },
]
