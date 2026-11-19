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


@contextmanager
def trace_step(name: str, *, question: str, conversation_id: str):
    client = get_tracing_client()
    if client is None:
        yield None
        return
    stack = ExitStack()
    try:
        stack.enter_context(propagate_attributes(
            session_id=conversation_id, tags=["fmcg-copilot", "preview"],
        ))
        observation = stack.enter_context(client.start_as_current_observation(
            name=name, as_type="span", input=question,
            metadata={"mode": "preview", "agent_connected": False},
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
