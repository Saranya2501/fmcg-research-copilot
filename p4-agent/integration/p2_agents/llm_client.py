"""Shared LLM client for the Competitive Research Copilot (P2).

One client for the whole team, so every call gets the same:
  - target switch: institute API (Qwen/Qwen3-8B) or local Ollama (qwen3:8b)
  - CA-certificate HTTPS for the institute API (verification stays on)
  - one-request-at-a-time lock (the group key allows 1 active request)
  - retries on 429/503/timeouts with 2, 4, 8 s backoff (per the API guide)
  - Qwen3 thinking mode off by default, and <think> blocks stripped
  - max_tokens limits (1..1024) and a rough 8,192-token context check
  - optional response cache (SQLite) so repeat runs don't spend API time
  - one JSONL log line per call: tokens, latency, status, cache hit, tag

Configuration comes from environment variables (see .env.example).
Never put the API key in code or notebooks.

Usage:
    from llm_client import LLMClient
    llm = LLMClient()                       # reads .env
    r = llm.chat([{"role": "user", "content": "Explain RAG in three steps."}],
                 tag="smoke", max_tokens=256)
    print(r.text, r.usage, r.latency_s)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import fcntl          # Unix only; on Windows we fall back to the thread lock
except ImportError:
    fcntl = None

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv is optional
    load_dotenv = None

CONTEXT_LIMIT = 8192          # input + output, per the API guide
MAX_OUTPUT = 1024             # hard cap per call
DEFAULT_OUTPUT = 512          # API default
RETRY_DELAYS = (2, 4, 8)      # seconds, per the API guide
RETRYABLE_STATUS = {429, 503}

_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


def strip_think(text: str | None) -> str:
    """Remove Qwen3 <think>...</think> blocks (and a dangling unclosed one)."""
    if not text:
        return ""
    text = _THINK_RE.sub("", text)
    if "<think>" in text:                     # truncated before </think>
        text = text.split("<think>")[0]
    return text.strip()


def estimate_tokens(messages: list[dict]) -> int:
    """Rough token estimate (~3.5 characters per token). Good enough for a guard."""
    chars = sum(len(str(m.get("content") or "")) for m in messages)
    return int(chars / 3.5) + 8 * len(messages)


@dataclass
class LLMResult:
    text: str                                  # answer with <think> removed
    raw_text: str                              # answer as returned
    tool_calls: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)  # prompt/completion/total tokens
    latency_s: float = 0.0
    finish_reason: str | None = None
    cached: bool = False
    target: str = ""


class LLMClient:
    def __init__(self, env_file: str | None = ".env"):
        if load_dotenv and env_file and Path(env_file).exists():
            load_dotenv(env_file)

        self.target = os.getenv("LLM_TARGET", "local").lower()   # "api" or "local"
        if self.target == "api":
            base_url = os.environ["LLM_API_BASE_URL"]            # e.g. https://<host>:<port>/v1
            api_key = os.environ["LLM_API_KEY"]
            ca_cert = os.environ["LLM_CA_CERT"]                  # path to the .crt file
            if not Path(ca_cert).expanduser().exists():
                raise FileNotFoundError(f"CA certificate not found: {ca_cert}")
            self.model = os.getenv("LLM_MODEL", "Qwen/Qwen3-8B")
            http_client = httpx.Client(verify=str(Path(ca_cert).expanduser()),
                                       timeout=httpx.Timeout(120.0, connect=15.0))
            # Thinking switch for vLLM-style servers; set LLM_THINKING_SWITCH=prompt
            # if the server ignores chat_template_kwargs.
            self.thinking_switch = os.getenv("LLM_THINKING_SWITCH", "kwargs")
        else:
            base_url = os.getenv("LLM_LOCAL_BASE_URL", "http://localhost:11434/v1")
            api_key = "ollama"
            self.model = os.getenv("LLM_LOCAL_MODEL", "qwen3:8b")
            http_client = httpx.Client(timeout=httpx.Timeout(300.0, connect=10.0))
            self.thinking_switch = os.getenv("LLM_THINKING_SWITCH", "prompt")

        # max_retries=0: we do our own 2/4/8 s backoff so retries are logged.
        self._client = OpenAI(base_url=base_url, api_key=api_key,
                              http_client=http_client, max_retries=0)
        self.base_url = base_url

        self.log_path = Path(os.getenv("LLM_LOG_PATH", "logs/llm_calls.jsonl"))
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        cache_path = os.getenv("LLM_CACHE_PATH", "cache/llm_cache.sqlite")
        self.cache_enabled = os.getenv("LLM_CACHE", "1") == "1"
        if self.cache_enabled:
            Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(cache_path, check_same_thread=False)
            self._db.execute("CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, v TEXT)")
            self._db.commit()

        # One request at a time: a thread lock inside this process plus a file
        # lock across processes on this machine. Across teammates' machines the
        # API itself enforces it (429), which we retry; book API slots too.
        self._thread_lock = threading.Lock()
        self._lock_file = Path(os.getenv("LLM_LOCK_PATH", str(Path.home() / ".llm_api.lock")))

    # ------------------------------------------------------------------ public
    def chat(self, messages: list[dict], *, tag: str = "", max_tokens: int = DEFAULT_OUTPUT,
             temperature: float = 0.0, thinking: bool = False, tools: list[dict] | None = None,
             tool_choice: Any = None, response_format: dict | None = None,
             use_cache: bool | None = None, sample_id: int = 0, **extra: Any) -> LLMResult:
        """One chat completion with the team's rules applied.

        tag        short label for logs/traces, e.g. "baseline.S1.q017"
        thinking   False (default) switches Qwen3 thinking off
        sample_id  vary this for self-consistency samples so the cache keeps them apart
        use_cache  default: cache only when temperature == 0
        """
        if not 1 <= max_tokens <= MAX_OUTPUT:
            raise ValueError(f"max_tokens must be 1..{MAX_OUTPUT}, got {max_tokens}")
        est = estimate_tokens(messages)
        if est + max_tokens > CONTEXT_LIMIT:
            raise ValueError(f"~{est} input tokens + {max_tokens} output exceeds "
                             f"{CONTEXT_LIMIT}. Trim context or lower max_tokens.")

        msgs = self._apply_thinking(messages, thinking)
        params: dict[str, Any] = {"model": self.model, "messages": msgs,
                                  "max_tokens": max_tokens, "temperature": temperature}
        if tools:
            params["tools"] = tools
            if tool_choice is not None:
                params["tool_choice"] = tool_choice
        if response_format:
            params["response_format"] = response_format
        if self.thinking_switch == "kwargs":
            params["extra_body"] = {"chat_template_kwargs": {"enable_thinking": thinking}}
        params.update(extra)

        if use_cache is None:
            use_cache = temperature == 0
        key = self._cache_key(params, sample_id) if (use_cache and self.cache_enabled) else None
        if key:
            hit = self._cache_get(key)
            if hit:
                res = LLMResult(**hit, cached=True, target=self.target)
                self._log(tag, res, status="cache_hit", attempts=0)
                return res

        res, attempts = self._call_with_retries(params, tag)
        if key and res.finish_reason != "error":
            self._cache_put(key, res)
        return res

    # ----------------------------------------------------------------- helpers
    def _apply_thinking(self, messages: list[dict], thinking: bool) -> list[dict]:
        """For servers without chat_template_kwargs, use Qwen3's /think, /no_think switch."""
        if self.thinking_switch != "prompt":
            return messages
        flag = "/think" if thinking else "/no_think"
        msgs = [dict(m) for m in messages]
        for m in reversed(msgs):
            if m.get("role") == "user" and isinstance(m.get("content"), str):
                m["content"] = f"{m['content']}\n{flag}"
                break
        return msgs

    def _call_with_retries(self, params: dict, tag: str) -> tuple[LLMResult, int]:
        last_err: Exception | None = None
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                with self._thread_lock, open(self._lock_file, "w") as lf:
                    if fcntl:
                        fcntl.flock(lf, fcntl.LOCK_EX)
                    t0 = time.perf_counter()
                    resp = self._client.chat.completions.create(**params)
                    latency = time.perf_counter() - t0
                res = self._to_result(resp, latency)
                self._log(tag, res, status="ok", attempts=attempt + 1)
                return res, attempt + 1
            except APIStatusError as e:
                last_err = e
                retryable = e.status_code in RETRYABLE_STATUS
                self._log(tag, None, status=f"http_{e.status_code}", attempts=attempt + 1,
                          error=str(e)[:300])
                if not retryable:
                    raise
            except (APITimeoutError, APIConnectionError) as e:
                last_err = e
                self._log(tag, None, status=type(e).__name__, attempts=attempt + 1,
                          error=str(e)[:300])
            if attempt < len(RETRY_DELAYS):
                time.sleep(RETRY_DELAYS[attempt])
        raise RuntimeError(f"LLM call failed after {len(RETRY_DELAYS) + 1} attempts "
                           f"(tag={tag}): {last_err}")

    def _to_result(self, resp: Any, latency: float) -> LLMResult:
        choice = resp.choices[0]
        msg = choice.message
        raw = msg.content or ""
        tool_calls = []
        for tc in (msg.tool_calls or []):
            tool_calls.append({"id": tc.id, "name": tc.function.name,
                               "arguments": tc.function.arguments})
        usage = {}
        if getattr(resp, "usage", None):
            usage = {"prompt_tokens": resp.usage.prompt_tokens,
                     "completion_tokens": resp.usage.completion_tokens,
                     "total_tokens": resp.usage.total_tokens}
        return LLMResult(text=strip_think(raw), raw_text=raw, tool_calls=tool_calls,
                         usage=usage, latency_s=round(latency, 3),
                         finish_reason=choice.finish_reason, target=self.target)

    def _cache_key(self, params: dict, sample_id: int) -> str:
        blob = json.dumps({"base": self.base_url, "p": params, "s": sample_id},
                          sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()

    def _cache_get(self, key: str) -> dict | None:
        row = self._db.execute("SELECT v FROM cache WHERE k = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def _cache_put(self, key: str, res: LLMResult) -> None:
        v = {"text": res.text, "raw_text": res.raw_text, "tool_calls": res.tool_calls,
             "usage": res.usage, "latency_s": res.latency_s, "finish_reason": res.finish_reason}
        self._db.execute("INSERT OR REPLACE INTO cache (k, v) VALUES (?, ?)", (key, json.dumps(v)))
        self._db.commit()

    def _log(self, tag: str, res: LLMResult | None, *, status: str, attempts: int,
             error: str = "") -> None:
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "tag": tag, "target": self.target,
               "model": self.model, "status": status, "attempts": attempts}
        if res:
            rec.update({"latency_s": res.latency_s, "finish_reason": res.finish_reason,
                        "cached": res.cached, **res.usage})
        if error:
            rec["error"] = error
        with open(self.log_path, "a") as f:
            f.write(json.dumps(rec) + "\n")
