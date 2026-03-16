import httpx
import os
from dotenv import load_dotenv

load_dotenv()

RAG_RESEARCH_URL = os.getenv("RAG_RESEARCH_URL", "http://localhost:8001")

def retrieve_similar(query: str, top_k=5, method="hybrid") -> list:
    try:
        response = httpx.post(
            f"{RAG_RESEARCH_URL}/retrieve",
            json={"query": query, "top_k": top_k, "method": method},
            timeout=15
        )
        if response.status_code == 200:
            return response.json().get("results", [])
    except Exception as e:
        print(f"   [WARNING]  rag-research unavailable: {e}")
    return []

def health_check() -> bool:
    try:
        r = httpx.get(f"{RAG_RESEARCH_URL}/health", timeout=5)
        return r.status_code == 200
    except:
        return False