import httpx
import arxiv
import os
from dotenv import load_dotenv

load_dotenv()

ARXIV_SERVICE_URL = os.getenv("ARXIV_SERVICE_URL", "http://localhost:8000")

def fetch_from_go_service(limit=20, page=1) -> list:
    """Fetch papers dari arxiv-research-assistant Go service."""
    try:
        response = httpx.get(
            f"{ARXIV_SERVICE_URL}/papers",
            params={"limit": limit, "page": page},
            timeout=10
        )
        if response.status_code == 200:
            return response.json().get("papers", [])
    except Exception as e:
        print(f"   ⚠️  Go service unavailable: {e}, fallback to direct ArXiv API")
    return []

def fetch_from_arxiv_direct(query="large language model clinical", max_results=10) -> list:
    """Fallback: fetch langsung dari ArXiv API."""
    client = arxiv.Client()
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate
    )
    papers = []
    for r in client.results(search):
        papers.append({
            "arxiv_id": r.entry_id.split("/")[-1],
            "title":    r.title,
            "abstract": r.summary[:800],
            "authors":  [a.name for a in r.authors[:3]],
            "date":     r.published.isoformat(),
            "source":   "arxiv"
        })
    return papers

def fetch_papers(max_results=10) -> list:
    """Try Go service dulu, fallback ke direct API."""
    papers = fetch_from_go_service(limit=max_results)
    if not papers:
        papers = fetch_from_arxiv_direct(max_results=max_results)
    return papers
