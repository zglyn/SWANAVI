from __future__ import annotations

import os


def model_settings() -> dict:
    provider = os.environ.get("ROAM_LLM_PROVIDER", "anthropic")
    if provider == "bedrock":
        return {
            "provider": "bedrock",
            "model_id": os.environ.get("ROAM_BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0"),
            "region": os.environ.get("AWS_REGION", "us-east-1"),
        }
    return {"provider": "anthropic", "model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")}


def build_model():
    settings = model_settings()
    if settings["provider"] != "bedrock":
        return None
    try:
        from strands.models import BedrockModel
    except ImportError as exc:
        raise RuntimeError("ROAM_LLM_PROVIDER=bedrock needs the strands-agents package") from exc
    return BedrockModel(model_id=settings["model_id"])


def runtime_endpoints() -> dict:
    return {
        "llm": model_settings(),
        "tools_mcp_url": os.environ.get("ROAM_TOOLS_MCP_URL", "http://127.0.0.1:8003/mcp"),
        "merchants_mcp_url": os.environ.get("ROAM_MERCHANTS_MCP_URL", "http://127.0.0.1:8001/mcp"),
        "plan_store": os.environ.get("ROAM_PLAN_STORE", "memory"),
    }
