"""Simple configuration for OpenAI-compatible Chat Completions providers."""
from dataclasses import dataclass, field
import os
from pathlib import Path
import sqlite3
import threading
from urllib.parse import urlsplit

import httpx


@dataclass(frozen=True)
class Connection:
    mode: str
    base_url: str
    model: str
    api_key: str = field(default='',repr=False)
    json_mode: bool = True
    tls_ca: str = ''

    def missing(self):
        if self.mode=='compatible':
            return [name for name,value in (('LLM_BASE_URL',self.base_url),('LLM_API_KEY',self.api_key),('LLM_MODEL',self.model)) if not value]
        if self.mode=='api':
            missing=[name for name,value in (('LLM_API_BASE_URL',self.base_url),('LLM_API_KEY',self.api_key),('LLM_CA_CERT',self.tls_ca)) if not value]
            if self.tls_ca and not Path(self.tls_ca).expanduser().is_file(): missing.append('valid LLM_CA_CERT file')
            return missing
        return []


def connection():
    base=(os.getenv('IITK_API_BASE', '').strip() or os.getenv('LLM_BASE_URL', '').strip()).rstrip('/')
    institute = bool(os.getenv('IITK_API_BASE', '').strip())
    target=os.getenv('LLM_TARGET','local').strip().lower()
    if base or target=='compatible':
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
        ca=(os.getenv('LLM_TLS_CA_CERT', '').strip() or
            (os.getenv('LLM_CA_CERT', '').strip() if institute else ''))
        if ca and not Path(ca).expanduser().is_file(): raise ValueError('LLM_TLS_CA_CERT file does not exist')
        return Connection('compatible',base,(os.getenv('LLM_MODEL', '').strip() or ('Qwen/Qwen3-8B' if institute else '')),
                          (os.getenv('IITK_API_KEY', '').strip() if institute else '') or os.getenv('LLM_API_KEY', '').strip(),json_mode=='true',ca)
    if target=='api':
        return Connection('api',os.getenv('LLM_API_BASE_URL','').strip(),os.getenv('LLM_MODEL','').strip() or 'Qwen/Qwen3-8B',
                          os.getenv('LLM_API_KEY',''),tls_ca=os.getenv('LLM_CA_CERT',''))
    if target!='local': raise ValueError('Set LLM_BASE_URL for your provider, or use LLM_TARGET=local/api')
    return Connection('local',os.getenv('LLM_LOCAL_BASE_URL','http://localhost:11434/v1'),os.getenv('LLM_LOCAL_MODEL','qwen3:8b'))


def compatible_client(module, openai_class, settings):
    """Reuse P2's queue, retries, logging, result parsing and model-call cache."""
    missing=settings.missing()
    if missing: raise ValueError('Missing API settings: '+', '.join(missing))
    class CompatibleClient(module.LLMClient):
        def __init__(self):
            self.target='compatible'
            self.base_url,self.model=settings.base_url,settings.model
            self.thinking_switch='none'
            self._client=openai_class(base_url=self.base_url,api_key=settings.api_key,max_retries=0,
                http_client=httpx.Client(verify=str(Path(settings.tls_ca).expanduser()) if settings.tls_ca else True,
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
