from typing import TypedDict, Optional

class AgentState(TypedDict):
    # Run info
    run_id: str
    started_at: str

    # Papers
    papers: list
    papers_processed: int

    # Claims
    raw_claims: list
    valid_claims: list
    claims_extracted: int

    # Comparison & Detection
    compared_claims: list
    conflicts: list
    conflicts_found: int

    # Control flow
    retry_count: int
    errors: list

    # Output
    report_path: Optional[str]
    status: str