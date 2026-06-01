"""search_literature -> NCBI PubMed E-utilities.

Docs: https://www.ncbi.nlm.nih.gov/books/NBK25501/
Flow: esearch (-> PMIDs) then efetch (retmode=xml -> titles + abstracts).
PubMed allows 3 req/s anonymously; an API key + email raise the limit and are
sent when configured. Each PMID becomes an evidence item citing the PubMed page.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from assetscope.config import get_settings
from assetscope.models import Citation, EvidenceItem, SourceType, ToolResult
from assetscope.tools.base import Tool
from assetscope.tools.http import get_json, get_text

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _ncbi_params() -> dict[str, str]:
    s = get_settings()
    params = {"tool": "assetscope", "email": s.contact_email}
    if s.pubmed_api_key:
        params["api_key"] = s.pubmed_api_key
    return params


def _parse_articles(xml_text: str) -> dict[str, dict]:
    """Map PMID -> {title, abstract, journal, year}."""
    out: dict[str, dict] = {}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out
    for art in root.findall(".//PubmedArticle"):
        pmid_el = art.find(".//MedlineCitation/PMID")
        if pmid_el is None or not pmid_el.text:
            continue
        pmid = pmid_el.text.strip()
        title_el = art.find(".//Article/ArticleTitle")
        title = "".join(title_el.itertext()).strip() if title_el is not None else ""
        # Abstracts can have multiple labeled sections.
        abstract_parts = []
        for ab in art.findall(".//Article/Abstract/AbstractText"):
            label = ab.get("Label")
            text = "".join(ab.itertext()).strip()
            abstract_parts.append(f"{label}: {text}" if label else text)
        journal_el = art.find(".//Article/Journal/Title")
        journal = journal_el.text if journal_el is not None and journal_el.text else ""
        year_el = art.find(".//Article/Journal/JournalIssue/PubDate/Year")
        year = year_el.text if year_el is not None and year_el.text else ""
        out[pmid] = {
            "title": title,
            "abstract": " ".join(abstract_parts),
            "journal": journal,
            "year": year,
        }
    return out


class LiteratureTool(Tool):
    name = "search_literature"
    description = (
        "Search PubMed (NCBI) biomedical literature for a free-text query and "
        "return matching articles with PMID, title, journal, year and abstract. "
        "Use this to find primary evidence for clinical readouts, mechanisms, "
        "and trial publications, and to obtain citable PMIDs."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "PubMed query, e.g. 'tirzepatide obesity SURMOUNT-1'. Supports field tags and boolean operators.",
            },
            "max_results": {"type": "integer", "default": 6, "minimum": 1, "maximum": 25},
        },
        "required": ["query"],
    }

    def run(self, query: str, max_results: int = 6) -> ToolResult:
        retmax = min(max(max_results, 1), 25)
        esearch = get_json(
            f"{EUTILS}/esearch.fcgi",
            params={
                "db": "pubmed",
                "term": query,
                "retmode": "json",
                "retmax": retmax,
                "sort": "relevance",
                **_ncbi_params(),
            },
        )
        idlist = (((esearch or {}).get("esearchresult") or {}).get("idlist")) or []
        if not idlist:
            return ToolResult(
                tool=self.name,
                args={"query": query, "max_results": max_results},
                summary=f"No PubMed results for '{query}'.",
            )

        xml_text = get_text(
            f"{EUTILS}/efetch.fcgi",
            params={
                "db": "pubmed",
                "id": ",".join(idlist),
                "rettype": "abstract",
                "retmode": "xml",
                **_ncbi_params(),
            },
        )
        articles = _parse_articles(xml_text)

        items: list[EvidenceItem] = []
        for pmid in idlist:
            meta = articles.get(pmid, {})
            title = meta.get("title") or f"PMID {pmid}"
            journal = meta.get("journal", "")
            year = meta.get("year", "")
            abstract = meta.get("abstract", "")
            content = (
                f"PMID {pmid}: {title}\n"
                f"{journal} {year}\n"
                f"{abstract}".strip()
            )
            items.append(
                EvidenceItem(
                    citation=Citation(
                        id=pmid,
                        source_type=SourceType.PUBMED,
                        source_id=pmid,
                        title=title,
                        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                        snippet=(abstract or title)[:300],
                    ),
                    content=content,
                    fields={"pmid": pmid, "journal": journal, "year": year},
                )
            )

        return ToolResult(
            tool=self.name,
            args={"query": query, "max_results": max_results},
            items=items,
            summary=f"{len(items)} PubMed article(s) for '{query}'.",
        )
