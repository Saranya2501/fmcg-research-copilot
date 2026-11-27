"""Validated environment settings for chat behavior."""

import json
import os

def positive_setting(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def response_config() -> dict:
    backend = os.getenv("CHAT_BACKEND", "agent")
    if backend == "agent":
        from integrations.agent_bridge import configuration
        return configuration()
    if backend != "preview":
        raise ValueError("CHAT_BACKEND must be agent or preview")
    generation = json.loads(os.getenv("CHAT_GENERATION_CONFIG", "{}"))
    if not isinstance(generation, dict):
        raise ValueError("CHAT_GENERATION_CONFIG must be a JSON object")
    allowed = {"temperature", "top_p", "top_k", "max_tokens", "seed", "stop",
               "frequency_penalty", "presence_penalty", "enable_thinking"}
    if set(generation) - allowed:
        raise ValueError("CHAT_GENERATION_CONFIG contains unsupported parameters")
    return {
        "backend": "preview",  # Change alongside the P4 adapter, never through a UI toggle.
        "model": os.getenv("CHAT_MODEL_ID", "Qwen3-8B"),
        "provider": os.getenv("CHAT_MODEL_PROVIDER", "unconnected"),
        "prompt_version": os.getenv("CHAT_PROMPT_VERSION", "preview-v1"),
        "corpus_version": os.getenv("CHAT_CORPUS_VERSION", "unavailable"),
        "pipeline_version": os.getenv("CHAT_PIPELINE_VERSION", "preview-v1"),
        "generation": generation,  # P2/P4 must use these actual settings when connected.
    }
