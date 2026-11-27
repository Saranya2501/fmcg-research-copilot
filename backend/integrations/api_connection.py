"""Single LLM configuration for an OpenAI-compatible Chat Completions endpoint."""
from dataclasses import dataclass, field
import os
from pathlib import Path
import sqlite3
import ssl
import threading
from urllib.parse import urlsplit

import httpx


@dataclass(frozen=True)
class Connection:
    base_url: str
    model: str
    api_key: str = field(default='',repr=False)
    json_mode: bool = True
    tls_ca: str = ''

    def missing(self):
        return [name for name,value in (('LLM_BASE_URL',self.base_url),('LLM_API_KEY',self.api_key),('LLM_MODEL',self.model)) if not value]


def connection():
    """Read the single LLM_* settings group: LLM_BASE_URL, LLM_API_KEY, LLM_MODEL (+ optional LLM_CA_CERT, LLM_JSON_MODE)."""
    base=os.getenv('LLM_BASE_URL','').strip().rstrip('/')
    if base:
        parsed=urlsplit(base)
        if parsed.scheme not in ('https','http') or not parsed.hostname:
            raise ValueError('LLM_BASE_URL must be an HTTP or HTTPS API base URL')
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Use a plain API base URL and put credentials only in LLM_API_KEY')
        if parsed.path.rstrip('/').endswith('/chat/completions'):
            raise ValueError('Use the API base URL, without /chat/completions')
    json_mode=os.getenv('LLM_JSON_MODE','true').lower().strip()
    if json_mode not in ('true','false'): raise ValueError('LLM_JSON_MODE must be true or false')
    ca=os.getenv('LLM_CA_CERT','').strip()
    if ca and not Path(ca).expanduser().is_file(): raise ValueError('LLM_CA_CERT file does not exist')
    return Connection(base,os.getenv('LLM_MODEL','').strip(),os.getenv('LLM_API_KEY','').strip(),json_mode=='true',ca)


def compatible_client(module, openai_class, settings):
    """Reuse P2's queue, retries, logging, result parsing and model-call cache."""
    missing=settings.missing()
    if missing: raise ValueError('Missing API settings: '+', '.join(missing))
    class CompatibleClient(module.LLMClient):
        def __init__(self):
            self.target='compatible'
            self.base_url,self.model=settings.base_url,settings.model
            self.thinking_switch='none'
            verify = ssl.create_default_context(cafile=str(Path(settings.tls_ca).expanduser())) if settings.tls_ca else True
            self._client=openai_class(base_url=self.base_url,api_key=settings.api_key,max_retries=0,
                http_client=httpx.Client(verify=verify,
                                        timeout=httpx.Timeout(120.0,connect=15.0)))
            self.log_path=Path(os.getenv('LLM_LOG_PATH','logs/llm_calls.jsonl'))
            self.log_path.parent.mkdir(parents=True,exist_ok=True)
            self.cache_enabled=os.getenv('LLM_CACHE','1')=='1'
            if self.cache_enabled:
                cache_path=Path(os.getenv('LLM_CACHE_PATH','cache/llm_cache.sqlite'))
                cache_path.parent.mkdir(parents=True,exist_ok=True)
                self._db=sqlite3.connect(cache_path,check_same_thread=False)
                self._db.execute('CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, v TEXT)')
                self._db.commit()
            self._thread_lock=threading.Lock()
            self._lock_file=Path(os.getenv('LLM_LOCK_PATH','logs/llm_api.lock'))
            self._lock_file.parent.mkdir(parents=True,exist_ok=True)

        def chat(self,messages,**kwargs):
            if not settings.json_mode: kwargs.pop('response_format',None)
            return super().chat(messages,**kwargs)
    return CompatibleClient()
