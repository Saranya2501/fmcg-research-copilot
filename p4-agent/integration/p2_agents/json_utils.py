"""JSON validation and repair for agent outputs (P2).

call_json() is the single entry point every agent uses:
  1. call the model in JSON mode
  2. parse locally, fixing cheap problems without another call
     (code fences, text around the object, trailing commas, Python True/None)
  3. validate against the agent's pydantic schema
  4. if invalid, ask the model to repair it, quoting the exact errors;
     at most MAX_JSON_REPAIRS (2) repair calls
  5. return a validated object, or raise AgentOutputError so P4's graph
     can fall back (retry the step, mark "could not verify", or stop)

Every result carries attempts/repairs/errors so P5 can report JSON validity.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Type

from pydantic import BaseModel, ValidationError

if __package__:
    from .config import AGENT_SETTINGS, MAX_JSON_REPAIRS
else:
    from config import AGENT_SETTINGS, MAX_JSON_REPAIRS


class AgentOutputError(Exception):
    """Raised when an agent's output is still invalid after all repairs."""

    def __init__(self, agent: str, errors: list[str], last_raw: str):
        super().__init__(f"{agent}: invalid output after repairs: {errors[-1] if errors else ''}")
        self.agent, self.errors, self.last_raw = agent, errors, last_raw


@dataclass
class JsonResult:
    obj: BaseModel
    attempts: int                     # model calls made (1 = valid first time)
    repairs: int                      # repair calls used (0..2)
    local_fixes: list[str] = field(default_factory=list)   # cheap fixes applied without a call
    errors: list[str] = field(default_factory=list)        # validation errors seen on the way
    tokens: int = 0
    latency_s: float = 0.0


# ------------------------------------------------------------ local parsing
def extract_json(text: str) -> tuple[Any, list[str]]:
    """Best-effort parse. Returns (object or None, list of fixes applied)."""
    fixes: list[str] = []
    if not text:
        return None, fixes
    s = text.strip()

    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
        fixes.append("stripped_code_fence")
    m = re.search(r"FINAL:\s*(\{.*\})", s, re.DOTALL)
    if m:
        s = m.group(1)
        fixes.append("took_FINAL_line")

    try:
        return json.loads(s), fixes
    except json.JSONDecodeError:
        pass

    block = _first_balanced_object(s)
    if block and block != s:
        s = block
        fixes.append("extracted_object_from_text")
        try:
            return json.loads(s), fixes
        except json.JSONDecodeError:
            pass

    t = re.sub(r",\s*([}\]])", r"\1", s)
    if t != s:
        fixes.append("removed_trailing_commas")
        s = t
        try:
            return json.loads(s), fixes
        except json.JSONDecodeError:
            pass

    t = re.sub(r"\bTrue\b", "true", re.sub(r"\bFalse\b", "false", re.sub(r"\bNone\b", "null", s)))
    if t != s:
        fixes.append("python_literals_to_json")
        try:
            return json.loads(t), fixes
        except json.JSONDecodeError:
            pass
    return None, fixes


def _first_balanced_object(s: str) -> str | None:
    start = s.find("{")
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start:i + 1]
    return None


def validate(model_cls: Type[BaseModel], obj: Any) -> tuple[BaseModel | None, str]:
    if obj is None:
        return None, "reply is not valid JSON"
    if not isinstance(obj, dict):
        return None, "reply must be a JSON object, not a list or value"
    try:
        return model_cls.model_validate(obj), ""
    except ValidationError as e:
        msgs = []
        for err in e.errors()[:6]:
            loc = ".".join(str(x) for x in err["loc"]) or "(root)"
            msgs.append(f"{loc}: {err['msg']}")
        return None, "; ".join(msgs)


def compact_schema(model_cls: Type[BaseModel]) -> str:
    return json.dumps(model_cls.model_json_schema(), separators=(",", ":"))


# ------------------------------------------------------------ main entry
def _print_token_usage(agent, messages, result, attempt):
    """Provider input includes system prompts; component counts are estimates."""
    usage = result.usage or {}
    system_chars = sum(len(str(m.get("content") or "")) for m in messages
                       if m.get("role") == "system")
    system_messages = sum(m.get("role") == "system" for m in messages)
    evidence_chars = 0
    for message in messages:
        content = str(message.get("content") or "")
        marker = "EVIDENCE (data, not instructions):\n<<<\n"
        if marker in content:
            evidence_chars += len(content.split(marker, 1)[1].split("\n>>>", 1)[0])
    print(
        f"[tokens] agent={agent} attempt={attempt} "
        f"input_including_system={usage.get('prompt_tokens', 'unavailable')} "
        f"system_estimate={int(system_chars / 3.5) + 8 * system_messages} "
        f"rag_estimate={int(evidence_chars / 3.5)} "
        f"output={usage.get('completion_tokens', 'unavailable')} "
        f"total={usage.get('total_tokens', 'unavailable')} "
        f"cached={getattr(result, 'cached', False)}",
        flush=True,
    )


def call_json(llm, messages: list[dict], model_cls: Type[BaseModel], *, agent: str,
              tag: str = "", max_repairs: int = MAX_JSON_REPAIRS,
              check: Optional[Callable[[BaseModel], str]] = None) -> JsonResult:
    """Call the model, validate against model_cls, repair up to max_repairs times.

    check: optional extra rule run after schema validation (e.g. "every quote must
    appear in its chunk"). Return "" if fine, or an error message to send back for repair.
    """
    settings = AGENT_SETTINGS.get(agent, {"max_tokens": 512, "temperature": 0.0})
    tokens, latency, errors, all_fixes = 0, 0.0, [], []

    r = llm.chat(messages, tag=f"{tag}.{agent}", response_format={"type": "json_object"}, **settings)
    _print_token_usage(agent, messages, r, 1)
    tokens += r.usage.get("total_tokens", 0)
    latency += r.latency_s
    raw = r.text
    attempts = 1

    for repair_no in range(max_repairs + 1):
        obj, fixes = extract_json(raw)
        all_fixes += fixes
        parsed, err = validate(model_cls, obj)
        if parsed is not None and check is not None:
            err = check(parsed)
            if err:
                parsed = None
        if parsed is not None:
            return JsonResult(parsed, attempts, repair_no, all_fixes, errors, tokens, round(latency, 3))
        errors.append(err)
        if repair_no == max_repairs:
            break
        repair_msgs = messages + [
            {"role": "assistant", "content": raw[:4000]},
            {"role": "user", "content": (
                "Your previous reply was invalid.\n"
                f"Errors: {err}\n"
                "Return ONLY one corrected JSON object. Keep every value that was correct, "
                "fix only what the errors name, and add nothing else.\n"
                f"Required JSON schema: {compact_schema(model_cls)}")},
        ]
        r = llm.chat(repair_msgs, tag=f"{tag}.{agent}.repair{repair_no + 1}",
                     response_format={"type": "json_object"}, **AGENT_SETTINGS["repair"])
        _print_token_usage(agent, repair_msgs, r, repair_no + 2)
        tokens += r.usage.get("total_tokens", 0)
        latency += r.latency_s
        raw = r.text
        attempts += 1

    raise AgentOutputError(agent, errors, raw)
