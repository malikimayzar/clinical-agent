import sys
import os
from dotenv import load_dotenv

load_dotenv()

LLM_EVAL_PATH = os.getenv("LLM_EVAL_PATH", "/mnt/d/llm-eval-framework")
sys.path.insert(0, LLM_EVAL_PATH)

_evaluator = None

def get_evaluator():
    global _evaluator
    if _evaluator is None:
        from evaluators.faithfulness import FaithfulnessEvaluator
        _evaluator = FaithfulnessEvaluator()
    return _evaluator

def evaluate_claim(claim: dict) -> dict:
    """Evaluate faithfulness satu klaim."""
    try:
        evaluator = get_evaluator()
        case = {
            "id":           claim.get("paper_id", "unknown"),
            "context":      claim.get("abstract", ""),
            "question":     "Is this claim supported by the abstract?",
            "ground_truth": claim.get("text", ""),
        }
        result = evaluator.evaluate(
            case=case,
            model_answer=claim.get("text", ""),
            model_name="phi3:mini"
        )
        claim["faithfulness_score"] = result.faithfulness_score
        claim["has_failure"]        = result.has_failure
    except Exception as e:
        print(f"   ⚠️  Eval failed: {e}")
        claim["faithfulness_score"] = 0.5
        claim["has_failure"]        = False
    return claim
