from langgraph.graph import StateGraph, END
from agents.state import AgentState
from agents.nodes.paper_monitor     import fetch_papers_node
from agents.nodes.claim_extractor   import extract_claims_node
from agents.nodes.claim_comparator  import compare_claims_node
from agents.nodes.conflict_detector import detect_conflict_node
from agents.nodes.alert_node        import alert_node
from agents.nodes.faithfulness_eval import faithfulness_eval_node
from agents.nodes.audit_logger      import audit_log_node
from agents.nodes.report_generator  import generate_report_node
from monitoring.metrics import time_node

def _wrap(name, fn):
    """Return fungsi baru yang identik dengan fn tapi diukur latency-nya."""
    def instrumented(state):
        with time_node(name):
            return fn(state)
    instrumented.__name__ = name
    return instrumented

fetch_papers_node_i      = _wrap("fetch_papers",      fetch_papers_node)
extract_claims_node_i    = _wrap("extract_claims",    extract_claims_node)
compare_claims_node_i    = _wrap("compare_claims",    compare_claims_node)
detect_conflict_node_i   = _wrap("detect_conflict",   detect_conflict_node)
alert_node_i             = _wrap("alert",             alert_node)
faithfulness_eval_node_i = _wrap("faithfulness_eval", faithfulness_eval_node)
audit_log_node_i         = _wrap("audit_log",         audit_log_node)
generate_report_node_i   = _wrap("generate_report",   generate_report_node)

# Conditional edge logic 
def should_retry_or_continue(state: AgentState) -> str:
    if state["retry_count"] >= 3:
        return "compare"
    low = [c for c in state["valid_claims"] if c.get("confidence", 1.0) < 0.6]
    if len(low) > len(state["valid_claims"]) * 0.5:
        return "retry"
    return "compare"


# Graph builder 
def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("fetch_papers",      fetch_papers_node_i)
    graph.add_node("extract_claims",    extract_claims_node_i)
    graph.add_node("compare_claims",    compare_claims_node_i)
    graph.add_node("detect_conflict",   detect_conflict_node_i)
    graph.add_node("alert",             alert_node_i)
    graph.add_node("faithfulness_eval", faithfulness_eval_node_i)
    graph.add_node("audit_log",         audit_log_node_i)
    graph.add_node("generate_report",   generate_report_node_i)

    graph.set_entry_point("fetch_papers")
    graph.add_edge("fetch_papers",      "extract_claims")
    graph.add_conditional_edges(
        "extract_claims",
        should_retry_or_continue,
        {"retry": "extract_claims", "compare": "compare_claims"}
    )
    graph.add_edge("compare_claims",    "detect_conflict")
    graph.add_edge("detect_conflict",   "alert")
    graph.add_edge("alert",             "faithfulness_eval")
    graph.add_edge("faithfulness_eval", "audit_log")
    graph.add_edge("audit_log",         "generate_report")
    graph.add_edge("generate_report",   END)
    return graph.compile()

if __name__ == "__main__":
    agent = build_graph()
    print("[OK] Graph compiled!")
    print(f"   Nodes: {list(agent.get_graph().nodes.keys())}")