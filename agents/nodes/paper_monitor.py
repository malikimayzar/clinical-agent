from agents.state import AgentState
from integrations.arxiv_service import fetch_papers

def fetch_papers_node(state: AgentState) -> AgentState:
    print("\n[OK] [paper_monitor] Fetching papers...")
    papers = fetch_papers(max_results=5)
    for p in papers:
        print(f"   [OK] {p['title'][:60]}...")
    print(f"   Total: {len(papers)} papers")
    return {**state, "papers": papers, "papers_processed": len(papers)}
