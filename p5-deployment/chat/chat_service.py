"""Application service coordinating generation, caching, history, and tracing."""

import logging
import os
import sqlite3
import time
from dataclasses import asdict, replace

from storage import response_cache
from storage.database import history_db
from storage.history_repository import load_messages, save_message, require_conversation_owner
from chat.chat_settings import positive_setting, response_config
from chat.response_backend import generate_response
from integrations.tracing import trace_identity, trace_step, update_observation

logger = logging.getLogger(__name__)

def process_chat_turn(question: str, conversation_id: str, *, filters: dict | None = None,
                      bypass_cache: bool = False, on_progress=None, user_session_id=None) -> str:
    if user_session_id is not None:
        require_conversation_owner(conversation_id, user_session_id)
    started = time.perf_counter()
    history = load_messages(conversation_id)
    filters = filters or {}
    config = {**response_config(), "bypass_model_cache": bypass_cache}
    ttl = positive_setting("CHAT_CACHE_TTL_SECONDS", 3600)
    enabled = os.getenv("CHAT_CACHE_ENABLED", "true").lower() == "true"
    status = ("bypass_preview" if config["backend"] == "preview" else
              "bypass_requested" if bypass_cache else "disabled" if not enabled else "miss")
    use_cache = status == "miss"
    key = response_cache.cache_key(question, history, filters, config)
    details = {"mode": config["backend"], "agent_connected": config["backend"] == "agent",
               "config": config, "cache_status": status, "cache_hit": False}
    with trace_step("process-chat-turn", question=question, conversation_id=conversation_id, metadata=details) as turn:
        save_message(conversation_id, "user", question)
        result = None
        if use_cache:
            try:
                with history_db() as db:
                    result = response_cache.lookup(db, key)
                status = "hit" if result else "miss"
                if result is not None:
                    result = replace(result, usage={"prompt_tokens":0,"completion_tokens":0,"total_tokens":0},
                                     metrics={**result.metrics,"response_cache_hit":True,"llm_calls":0,"tool_calls":0,
                                              'mode':config['backend'],'retrieval_used':config['backend']=='agent'})
            except sqlite3.Error:
                status = "error"
                logger.exception("Response cache read failed; generating an answer.")
        if result is None:
            name = "respond-preview" if config["backend"] == "preview" else "generate-response"
            with trace_step(name, question=question, conversation_id=conversation_id, metadata=details) as response:
                result = generate_response(question, history, filters, config,
                    **({"on_progress": on_progress} if on_progress is not None else {}))
                update_observation(response, output=result.answer)
            if use_cache and result.successful and result.cacheable:
                try:
                    with history_db() as db:
                        response_cache.store(db, key, result, ttl)
                except (sqlite3.Error, TypeError, ValueError):
                    logger.exception("Response cache write failed; answer will still be returned.")
        latency = round((time.perf_counter() - started) * 1000, 2)
        update_observation(turn, output=result.answer, metadata={**details, "cache_status": status,
                           "cache_hit": status == "hit", "latency_ms": latency,
                           "agent_connected":config["backend"]=="agent" and not result.metrics.get("setup_required",False),
                           "retrieval_enabled":config['backend']=='agent',
                           "usage":result.usage,"metrics":result.metrics,"status":result.status},
                           **({"level": "ERROR", "status_message": "Response unsuccessful"} if not result.successful else {}))
        trace_id, trace_url = trace_identity(turn)
        save_message(conversation_id, "assistant", result.answer, trace_id=trace_id,
                     trace_url=trace_url, citations=result.citations, cache_status=status, latency_ms=latency,
                     response=asdict(result))
    return result.answer
