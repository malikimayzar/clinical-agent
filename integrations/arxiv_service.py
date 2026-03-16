import httpx
import arxiv
import os
import random
from dotenv import load_dotenv

load_dotenv()

ARXIV_SERVICE_URL = os.getenv("ARXIV_SERVICE_URL", "http://localhost:8000")
MEDICAL_QUERIES = [
    "cat:q-bio clinical trial drug efficacy randomized controlled",
    "cat:q-bio cancer treatment immunotherapy outcome",
    "cat:q-bio cardiovascular disease risk intervention",
    "cat:q-bio infectious disease vaccine efficacy",
    "cat:q-bio mental health depression treatment",
    "cat:q-bio biomarker disease prediction validation",
    "cat:q-bio antibiotic resistance treatment outcome",
    "cat:eess.IV medical imaging diagnosis deep learning",
    "cat:cs.LG drug interaction adverse effect prediction",
    "cat:cs.LG clinical outcome prediction machine learning",
]

def fetch_from_go_service(limit=20, page=1) -> list:
    try:
        response = httpx.get(
            f"{ARXIV_SERVICE_URL}/papers",
            params={"limit": limit, "page": page},
            timeout=10
        )
        if response.status_code == 200:
            papers = response.json().get("papers", [])
            if papers:
                return papers
    except Exception as e:
        print(f"   [WARNING]  Go service unavailable: {e}, fallback to direct ArXiv API")
    return []

def fetch_from_arxiv_direct(max_results=10) -> list:
    mental_health_queries = [q for q in MEDICAL_QUERIES if "mental health" in q]
    other_queries = [q for q in MEDICAL_QUERIES if "mental health" not in q]
    selected_queries = mental_health_queries + random.sample(other_queries, k=1)
    papers_map: dict[str, dict] = {}

    client = arxiv.Client()
    per_query = max(max_results // len(selected_queries), 3)

    for query in selected_queries:
        print(f"   [QUERY] {query[:60]}...")
        search = arxiv.Search(
            query=query,
            max_results=per_query,
            sort_by=arxiv.SortCriterion.Relevance
        )
        try:
            for r in client.results(search):
                arxiv_id = r.entry_id.split("/")[-1]
                if arxiv_id not in papers_map:
                    papers_map[arxiv_id] = {
                        "arxiv_id": arxiv_id,
                        "title":    r.title,
                        "abstract": r.summary[:800],
                        "authors":  [a.name for a in r.authors[:3]],
                        "date":     r.published.isoformat(),
                        "source":   "arxiv",
                        "query":    query,
                    }
        except Exception as e:
            print(f"   [WARNING]  ArXiv query failed: {e}")

    papers = list(papers_map.values())[:max_results]
    return papers

def fetch_papers(max_results=10) -> list:
    papers = fetch_from_go_service(limit=max_results)
    if not papers:
        papers = fetch_from_arxiv_direct(max_results=max_results)
    return papers