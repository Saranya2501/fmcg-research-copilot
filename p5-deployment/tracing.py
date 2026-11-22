"""Optional Langfuse tracing; credentials are loaded by app.py before this import."""

import logging
import os
import re
from contextlib import ExitStack, contextmanager
from functools import lru_cache

from langfuse import Langfuse, propagate_attributes
from langfuse.types import MaskOtelSpansResult, OtelSpanPatch

logger = logging.getLogger(__name__)


def redact(value: str) -> str:
    value = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[REDACTED EMAIL]", value)
    value = re.sub(r"\b(?:sk|pk)-[\w-]+", "[REDACTED KEY]", value)
    return re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", value)


def mask_export(*, params):
    patches = {}
    for identifier, span in params.spans.items():
        replacements = {
            key: redact(value)
            for key, value in span.attributes.items()
            if isinstance(value, str) and redact(value) != value
        }
        if replacements:
            patches[identifier] = OtelSpanPatch(set_attributes=replacements)
    return MaskOtelSpansResult(span_patches=patches)


@lru_cache(maxsize=1)
def get_tracing_client():
    if os.getenv("LANGFUSE_TRACING_ENABLED", "true").lower() == "false":
        return None
    if not all(os.getenv(key) for key in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL")):
        return None
    try:
        return Langfuse(mask_otel_spans=mask_export, timeout=5)
    except Exception:
        logger.warning("Langfuse initialization failed; chat will continue without tracing.")
        return None


def update_observation(observation, **fields):
    if observation is not None:
        try:
            observation.update(**fields)
        except Exception:
            logger.warning("Langfuse observation update failed.")


def trace_identity(observation) -> tuple[str | None, str | None]:
    if observation is None:
        return None, None
    try:
        trace_id = observation.trace_id
        client = get_tracing_client()
        return trace_id, client.get_trace_url(trace_id=trace_id) if client else None
    except Exception:
        logger.warning("Langfuse trace link unavailable.")
        return getattr(observation, "trace_id", None), None


@contextmanager
def trace_step(name: str, *, question, conversation_id: str | None, metadata: dict | None = None, as_type="span"):
    client = get_tracing_client()
    if client is None:
        yield None
        return
    stack = ExitStack()
    try:
        details = {"mode": "preview", "agent_connected": False, **(metadata or {})}
        stack.enter_context(propagate_attributes(
            session_id=conversation_id, tags=["fmcg-copilot", details["mode"]],
        ))
        observation = stack.enter_context(client.start_as_current_observation(
            name=name, as_type=as_type, input=question,
            metadata=details,
        ))
    except Exception:
        stack.close()
        logger.warning("Langfuse trace setup failed; chat will continue without tracing.")
        yield None
        return
    try:
        yield observation
    except Exception:
        update_observation(observation, level="ERROR", status_message="Chat processing failed")
        raise
    finally:
        # Keep raw exception text (which can contain secrets) out of span events.
        try:
            stack.close()
        except Exception:
            logger.warning("Langfuse trace completion failed.")
