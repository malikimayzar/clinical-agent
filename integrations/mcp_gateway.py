import httpx
import os
from dotenv import load_dotenv

load_dotenv()

MCP_GATEWAY_URL = os.getenv("MCP_GATEWAY_URL", "http://localhost:8003")

def orchestrate(tool: str, payload: dict) -> dict:
    """Call mcp-gateway untuk orchestration."""
    try:
        response = httpx.post(
            f"{MCP_GATEWAY_URL}/tools/{tool}",
            json=payload,
            timeout=30
        )
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"   ⚠️  mcp-gateway unavailable: {e}")
    return {}

def health_check() -> bool:
    try:
        r = httpx.get(f"{MCP_GATEWAY_URL}/health", timeout=5)
        return r.status_code == 200
    except:
        return False
