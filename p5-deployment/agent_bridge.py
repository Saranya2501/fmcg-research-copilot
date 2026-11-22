"""P5 adapter for the latest P4 integration.runtime.run_query contract."""
from functools import lru_cache
import ast
import hashlib
import importlib.util
import json
import logging
import os
from pathlib import Path
import sys
from types import SimpleNamespace

from p4_loader import fingerprint, load_p2, load_runtime
from response_cache import ChatResponse
from tracing import get_tracing_client, trace_step, update_observation
from api_connection import connection, compatible_client

ROOT = Path(__file__).resolve().parents[1]
P4_ROOT = ROOT / "p4-agent"
if str(P4_ROOT) not in sys.path:
    sys.path.insert(0, str(P4_ROOT))
logger = logging.getLogger(__name__)


def p2_path():
    return Path(os.getenv("P2_PACKAGE_PATH", str(P4_ROOT/"integration/p2_agents"))).expanduser().resolve()


def rag_path():
    return Path(os.getenv("P3_RAG_PATH") or str(P4_ROOT/"p3_retrieval")).expanduser().resolve()


def missing_setup():
    rag = rag_path()
    missing = [str(path.relative_to(rag)) for path in (
        rag/"retrieve.py",rag/"index/bm25.pkl",rag/"index/faiss.index",rag/"index/chunk_ids.json",rag/"parsed/all_chunks.jsonl",
    ) if not path.is_file()]
    for name in ("agents.py","llm_client.py","schemas.py","config.py","json_utils.py"):
        if not (p2_path()/name).is_file(): missing.append("P2: " + name)
    if not (P4_ROOT/"integration/runtime.py").is_file(): missing.append("P4 integration/runtime.py")
    missing += connection().missing()
    return missing


DIRECT_SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer using the conversation and your general knowledge. "
    "Document retrieval is disabled in this mode. Do not claim to have read the application's "
    "company filings or invent document/page citations. Say when you are unsure."
)


def configuration(*, direct=False):
    config = load_p2(p2_path())['config']
    prompts = p2_path()/"prompts"
    prompt_hash = hashlib.sha256(DIRECT_SYSTEM_PROMPT.encode() if direct else b"".join(p.read_bytes() for p in sorted(prompts.glob("*.md")))).hexdigest()[:16]
    corpus = []
    for path in (() if direct else (rag_path()/"retrieve.py",rag_path()/"index/bm25.pkl",rag_path()/"index/faiss.index",rag_path()/"index/chunk_ids.json",rag_path()/"parsed/all_chunks.jsonl")):
        corpus.append((str(path),path.stat().st_size,path.stat().st_mtime_ns) if path.exists() else (str(path),None))
    settings = connection()
    target,endpoint = settings.mode,settings.base_url
    code = [Path(__file__),Path(__file__).with_name("p4_loader.py"),Path(__file__).with_name('api_connection.py')]
    if not direct:
        code += [P4_ROOT/"integration/runtime.py"] + sorted((P4_ROOT/"p4").rglob("*.py"))
    pipeline = hashlib.sha256(b"".join(p.read_bytes() for p in code) + fingerprint(p2_path()).encode()).hexdigest()[:16]
    budget = int(os.getenv("AGENT_TOKEN_BUDGET","6000"))
    if budget < 1: raise ValueError("AGENT_TOKEN_BUDGET must be positive")
    return {"backend":"chat" if direct else "agent","provider":target,
        "model":settings.model,
        "endpoint_fingerprint":hashlib.sha256(endpoint.encode()).hexdigest()[:16],
        "prompt_version":f"{'direct-chat-v1' if direct else config.PROMPT_VERSION}:{prompt_hash}","pipeline_version":pipeline,
        "corpus_version":"none" if direct else hashlib.sha256(json.dumps(corpus).encode()).hexdigest()[:16],
        "generation":{"max_tokens":512,"temperature":0.0} if direct else config.AGENT_SETTINGS,"json_mode":False if direct else settings.json_mode,
        "token_budget":budget,"p4_entrypoint":"integration.runtime.run_query"}


@lru_cache(maxsize=2)
def load_retrieval(directory):
    spec=importlib.util.spec_from_file_location("_fmcg_p3",Path(directory)/"retrieve.py")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _span(name,kind,payload,mode='agent'):
    return trace_step(name,question=payload,conversation_id=None,as_type=kind,
                      metadata={"mode":mode,"agent_connected":mode=='agent'})


class MeteredClient:
    def __init__(self, client, budget, *, bypass_cache=False, mode='agent'):
        self.client,self.budget,self.bypass_cache=client,budget,bypass_cache
        self.calls,self.cached_calls,self.tokens=0,0,0
        self.mode=mode
        self.usage={"prompt_tokens":0,"completion_tokens":0,"total_tokens":0}

    def chat(self,messages,**kwargs):
        estimated=int(sum(len(str(m.get('content',''))) for m in messages)/3.5)+8*len(messages)
        remaining=self.budget-self.tokens-estimated
        if remaining<1: raise RuntimeError("Agent token budget exhausted")
        kwargs['max_tokens']=min(kwargs.get('max_tokens',512),remaining)
        if self.bypass_cache: kwargs['use_cache']=False
        result=self.client.chat(messages,**kwargs)
        self.calls+=1
        usage=result.usage or {}
        if 'total_tokens' not in usage: raise RuntimeError("Model usage unavailable")
        self.tokens+=int(usage['total_tokens'] or 0)
        if getattr(result,'cached',False):
            self.cached_calls+=1
            with _span('read-model-cache','span',{'tag':kwargs.get('tag','')},mode=self.mode) as obs:
                update_observation(obs,output=result.text,metadata={'cache_hit':True})
        else:
            for key in self.usage: self.usage[key]+=int(usage.get(key) or 0)
        if self.tokens>self.budget: raise RuntimeError("Agent token budget exhausted")
        return result


def _make_client(client_module):
    for key,relative in (('LLM_LOG_PATH','logs/llm_calls.jsonl'),('LLM_CACHE_PATH','llm_cache.sqlite'),('LLM_LOCK_PATH','llm_api.lock')):
        os.environ.setdefault(key,str(ROOT/'p5-deployment/data'/relative))
    Path(os.environ['LLM_LOCK_PATH']).expanduser().parent.mkdir(parents=True,exist_ok=True)
    if get_tracing_client() is not None:
        from langfuse.openai import OpenAI
    else:
        from openai import OpenAI
    settings=connection()
    if settings.mode=='compatible':
        client=compatible_client(client_module,OpenAI,settings)
    else:
        client_module.OpenAI=OpenAI
        client=client_module.LLMClient(env_file=None)
        client.model=settings.model
    original_log=client._log
    def safe_log(tag,res,*,status,attempts,error=''):
        return original_log(tag,res,status=status,attempts=attempts,error='Request failed' if error else '')
    client._log=safe_log
    return client


def _close_client(client):
    if callable(getattr(client,'close',None)):
        client.close()
    else:
        for name in ('_client','_db'):
            resource=getattr(client,name,None)
            if resource is not None: resource.close()


def run_direct_chat(question,history,config):
    """One model call with recent conversation history, without P4 or retrieval."""
    missing=connection().missing()
    if missing:
        return ChatResponse('Set up your model connection to start chatting.',successful=False,status='partial',
            metrics={'mode':'chat','retrieval_used':False,'setup_required':True,'missing_setup':missing})
    client=None
    meter=None
    try:
        modules=load_p2(p2_path())
        recent=[{'role':m['role'],'content':m['content']} for m in history
                if m.get('role') in ('user','assistant')][-10:]
        system={'role':'system','content':DIRECT_SYSTEM_PROMPT}
        prompt={'role':'user','content':question}
        output=config['generation']['max_tokens']
        while recent and modules['llm_client'].estimate_tokens([system]+recent+[prompt])+output>min(8192,config['token_budget']):
            recent=recent[2:]
        messages=[system]+recent+[prompt]
        client=_make_client(modules['llm_client'])
        meter=MeteredClient(client,config['token_budget'],bypass_cache=config.get('bypass_model_cache',False),mode='chat')
        result=meter.chat(messages,tag='p5.direct-chat',**config['generation'])
        complete=bool(result.text.strip()) and getattr(result,'finish_reason','stop')=='stop'
        return ChatResponse(result.text or 'The model returned no answer. Try a shorter request.',
            successful=complete,cacheable=complete,status='answered' if complete else 'partial',usage=meter.usage,
            metrics={'mode':'chat','retrieval_used':False,'llm_calls':meter.calls,'tool_calls':0,
                     'model_cache_hits':meter.cached_calls,'tokens_accounted':meter.tokens})
    except Exception as exc:
        logger.warning('Direct model request failed (%s).',type(exc).__name__)
        return ChatResponse('The model request failed. Check your API key, base URL and model ID.',
            successful=False,status='partial',usage=meter.usage if meter else {},
            metrics={'mode':'chat','retrieval_used':False,'failure':'model_request_failed',
                     'error_type':type(exc).__name__,'http_status':getattr(exc,'status_code',None)})
    finally:
        if client is not None:
            try: _close_client(client)
            except Exception: logger.warning('Direct model client cleanup failed.')


def run_agent(question,history,filters,config):
    missing=missing_setup()
    if missing:
        return ChatResponse('Research is not ready yet because source data or model configuration is missing.',
                            successful=False,status='partial',metrics={'setup_required':True,'missing_setup':missing})
    modules=load_p2(p2_path())
    schemas,agents=modules['schemas'],modules['agents']
    previous=next((m.get('response',{}).get('agent_context',{}) for m in reversed(history)
                   if m.get('response',{}).get('agent_context')), {})
    context=dict(previous)
    metrics={'json_steps':[],'tool_calls':0,'p4_entrypoint':'integration.runtime.run_query'}
    evidence={}
    client=None
    meter=None

    def agent_wrapper(name,fn):
        def wrapped(llm,*args,**kwargs):
            if name=='run_gatekeeper':
                args=(args[0],schemas.ConversationState(
                    last_companies=previous.get('companies',[]),last_metrics=previous.get('metrics',[]),
                    last_fiscal_years=previous.get('fiscal_years',[]),last_use_case=previous.get('use_case'),
                    history=[{'role':m['role'],'content':m['content']} for m in history[-4:]]))
            with _span(name.removeprefix('run_').replace('_','-'),'agent',{'question':question}) as obs:
                result=fn(llm,*args,**kwargs)
                record={'agent':name,'attempts':result.attempts,'repairs':result.repairs,
                        'validation_errors':len(result.errors),'local_fixes':len(result.local_fixes)}
                metrics['json_steps'].append(record)
                update_observation(obs,output=result.obj.model_dump(),metadata=record)
            if name=='run_gatekeeper' and result.obj.in_scope:
                gate=result.obj
                context.update(companies=gate.companies,metrics=gate.metrics,fiscal_years=gate.fiscal_years,use_case=gate.use_case)
            return result
        return wrapped

    agent_proxy=SimpleNamespace(**{name:agent_wrapper(name,getattr(agents,name))
        for name in ('run_gatekeeper','run_planner','run_query_writer','run_analyst','run_writer','run_critic')})

    def retrieve(query,k=5,filters=None):
        actual=dict(filters or {})
        actual.update(request_filters)
        metrics['tool_calls']+=1
        with _span('search-reports','retriever',{'query':query,'filters':actual}) as obs:
            rows=p3.retrieve(query=query,k=k,filters=actual)
            for row in rows or []:
                if row.get('chunk_id'): evidence[row['chunk_id']]=row
            update_observation(obs,output=rows)
            return rows

    request_filters=dict(filters or {})
    def calculate(expression):
        from p4.tools.calculator import calculator
        if len(expression)>256:
            raise ValueError('Calculator expression too long')
        tree=ast.parse(expression,mode='eval')
        if len(list(ast.walk(tree)))>64 or any(isinstance(n,ast.Pow) for n in ast.walk(tree)):
            raise ValueError('Calculator expression exceeds supported bounds')
        metrics['tool_calls']+=1
        with _span('calculator','tool',{'expression':expression}) as obs:
            result=calculator(expression)
            update_observation(obs,output=result)
            return result
    try:
        p3=load_retrieval(str(rag_path()))
        client=_make_client(modules['llm_client'])
        meter=MeteredClient(client,config['token_budget'],bypass_cache=config.get('bypass_model_cache',False))
        runtime=load_runtime(P4_ROOT/'integration/runtime.py',calculator=calculate)
        runtime.load_p2=lambda path:(agent_proxy,modules['llm_client'],schemas)
        runtime.load_p3=lambda path:SimpleNamespace(retrieve=retrieve,get_table=p3.get_table)
        raw=runtime.run_query(question,str(p2_path()),str(rag_path()),llm=meter,tag='p5.chat')
        metrics.update(llm_calls=meter.calls,model_cache_hits=meter.cached_calls,tokens_accounted=meter.tokens)
    except Exception:
        logger.warning('P4 research run failed; no raw exception or credentials logged.')
        metrics.update(failure='p4_run_failed',llm_calls=meter.calls if meter else 0)
        return ChatResponse('The research service could not complete and verify this request.',
            successful=False,status='partial',agent_context=context,
            usage=meter.usage if meter else {},metrics=metrics)
    finally:
        if client is not None:
            try: _close_client(client)
            except Exception: logger.warning('P2 client cleanup failed.')
    return normalize_response(raw,evidence,context,meter.usage,metrics)


def normalize_response(raw,evidence,context,usage,metrics):
    status=raw.get('status')
    if status=='refused':
        return ChatResponse(raw.get('message') or 'This request is outside the supported scope.',
                            status='refused',agent_context=context,usage=usage,metrics=metrics)
    if status!='answered':
        return ChatResponse('I could not verify an answer from the available evidence.',successful=False,status='partial',
            results=raw.get('results',[]),limitations=['P4 validation incomplete'],agent_context=context,usage=usage,metrics=metrics)
    answer=raw.get('answer') or {}
    if answer.get('refused'):
        return ChatResponse(answer.get('answer') or 'No supported answer was found.',
            status='not_found' if answer.get('refusal_reason')=='not_in_context' else 'refused',
            agent_context=context,usage=usage,metrics=metrics)
    citations=[]
    valid_citations=True
    for item in answer.get('citations',[]):
        source=evidence.get(item.get('chunk_id'),{})
        page=source.get('page')
        if not source or not isinstance(page,int) or page<1:
            valid_citations=False
        citations.append({'document':source.get('doc') or source.get('doc_id') or item.get('doc'),
            'page':source.get('page',item.get('page')),'company':source.get('company'),
            'source_id':item.get('chunk_id')})
    limitations=raw.get('missing',[])
    complete=(bool(answer.get('answer')) and bool(citations) and valid_citations
              and not limitations and raw.get('critic',{}).get('verdict')=='pass')
    if not complete and not limitations:
        limitations=['P4 evidence or citation validation incomplete']
    return ChatResponse(answer=answer.get('answer') or 'No verified answer returned.',citations=citations,
        status='answered' if complete else 'partial',successful=complete,cacheable=complete,
        results=raw.get('results',[]),limitations=limitations,agent_context=context,usage=usage,metrics=metrics)
