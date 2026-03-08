from agents.state import AgentState
from integrations.arxiv_service import fetch_papers

def fetch_papers_node(state: AgentState) -> AgentState:
    print("\n📄 [paper_monitor] Fetching papers...")
    papers = fetch_papers(max_results=5)
    for p in papers:
        print(f"   ✅ {p['title'][:60]}...")
    print(f"   Total: {len(papers)} papers")
    return {**state, "papers": papers, "papers_processed": len(papers)}
