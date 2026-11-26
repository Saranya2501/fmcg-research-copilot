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

from integrations.external_p2 import fingerprint, load_p2
from chat.chat_models import ChatResponse
from integrations.tracing import get_tracing_client, trace_step, update_observation
from integrations.api_connection import connection, compatible_client

ROOT = Path(__file__).resolve().parents[2]
P4_ROOT = ROOT / "p4-agent"
if str(P4_ROOT) not in sys.path:
    sys.path.insert(0, str(P4_ROOT))
from integration.runtime import run_query

logger = logging.getLogger(__name__)

RAG_FILES = (
    "retrieve.py", "index/bm25.pkl", "index/faiss.index",
    "index/chunk_ids.json", "parsed/all_chunks.jsonl",
)


def p2_path():
    return Path(os.getenv("P2_PACKAGE_PATH", str(P4_ROOT/"integration/p2_agents"))).expanduser().resolve()


def rag_path():
    return Path(os.getenv("P3_RAG_PATH") or str(P4_ROOT/"p3_retrieval")).expanduser().resolve()


def missing_setup():
    rag = rag_path()
    missing = [name for name in RAG_FILES if not (rag / name).is_file()]
    for name in ("agents.py","llm_client.py","schemas.py","config.py","json_utils.py"):
        if not (p2_path()/name).is_file(): missing.append("P2: " + name)
    if not (P4_ROOT/"integration/runtime.py").is_file(): missing.append("P4 integration/runtime.py")
    missing += connection().missing()
    return missing


def configuration():
    config = load_p2(p2_path())['config']
    prompts = p2_path()/"prompts"
    prompt_hash = hashlib.sha256(b"".join(p.read_bytes() for p in sorted(prompts.glob("*.md")))).hexdigest()[:16]
    corpus = []
    for path in (rag_path() / name for name in RAG_FILES):
        corpus.append((str(path),path.stat().st_size,path.stat().st_mtime_ns) if path.exists() else (str(path),None))
    settings = connection()
    endpoint = settings.base_url
    code = [Path(__file__),Path(__file__).with_name("external_p2.py"),Path(__file__).with_name('api_connection.py')]
    code += [P4_ROOT/"integration/runtime.py"] + sorted((P4_ROOT/"p4").rglob("*.py"))
    pipeline = hashlib.sha256(b"".join(p.read_bytes() for p in code) + fingerprint(p2_path()).encode()).hexdigest()[:16]
    budget = int(os.getenv("AGENT_TOKEN_BUDGET","6000"))
    if budget < 1: raise ValueError("AGENT_TOKEN_BUDGET must be positive")
    return {"backend":"agent","provider":"compatible",
        "model":settings.model,
        "endpoint_fingerprint":hashlib.sha256(endpoint.encode()).hexdigest()[:16],
        "prompt_version":f"{config.PROMPT_VERSION}:{prompt_hash}","pipeline_version":pipeline,
        "corpus_version":hashlib.sha256(json.dumps(corpus).encode()).hexdigest()[:16],
        "generation":config.AGENT_SETTINGS,"json_mode":settings.json_mode,
        "reranker_enabled":os.getenv("RAG_RERANKER_ENABLED", "true").strip().lower() == "true",
        "token_budget":budget,"p4_entrypoint":"integration.runtime.run_query"}


@lru_cache(maxsize=2)
def load_retrieval(directory):
    spec=importlib.util.spec_from_file_location("_fmcg_p3",Path(directory)/"retrieve.py")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _span(name,kind,payload):
    return trace_step(name,question=payload,conversation_id=None,as_type=kind,
                      metadata={"mode":"agent","agent_connected":True})


class TokenBudgetExceeded(RuntimeError):
    """The cumulative research allowance cannot fit another model call."""


class MeteredClient:
    def __init__(self, client, budget, *, bypass_cache=False):
        self.client,self.budget,self.bypass_cache=client,budget,bypass_cache
        self.calls,self.cached_calls,self.tokens=0,0,0
        self.usage={"prompt_tokens":0,"completion_tokens":0,"total_tokens":0}

    def chat(self,messages,**kwargs):
        estimated=int(sum(len(str(m.get('content',''))) for m in messages)/3.5)+8*len(messages)
        remaining=self.budget-self.tokens-estimated
        if remaining<1: raise TokenBudgetExceeded("Agent token budget exhausted")
        kwargs['max_tokens']=min(kwargs.get('max_tokens',512),remaining)
        if self.bypass_cache: kwargs['use_cache']=False
        result=self.client.chat(messages,**kwargs)
        self.calls+=1
        usage=result.usage or {}
        if 'total_tokens' not in usage: raise RuntimeError("Model usage unavailable")
        self.tokens+=int(usage['total_tokens'] or 0)
        if getattr(result,'cached',False):
            self.cached_calls+=1
            with _span('read-model-cache','span',{'tag':kwargs.get('tag','')}) as obs:
                update_observation(obs,output=result.text,metadata={'cache_hit':True})
        else:
            for key in self.usage: self.usage[key]+=int(usage.get(key) or 0)
        if self.tokens>self.budget: raise TokenBudgetExceeded("Agent token budget exhausted")
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
    client=compatible_client(client_module,OpenAI,settings)
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


RESEARCH_STEPS = {
    'setup': 'Preparing research',
    'run_gatekeeper': 'Checking question scope',
    'run_planner': 'Planning research',
    'run_query_writer': 'Preparing search queries',
    'retrieve': 'Searching company filings',
    'run_analyst': 'Analyzing evidence',
    'calculate': 'Calculating results',
    'run_writer': 'Drafting the answer',
    'run_critic': 'Verifying the answer',
    'finalize': 'Checking citations',
}


def run_agent(question, history, filters, config, *, on_progress=None):
    step = 'setup'

    def enter_step(name):
        nonlocal step
        step = name
        if on_progress is not None:
            on_progress(RESEARCH_STEPS[name] + '…')

    previous=next((m.get('response',{}).get('agent_context',{}) for m in reversed(history)
                   if m.get('response',{}).get('agent_context')), {})
    context=dict(previous)
    metrics={'json_steps':[],'tool_calls':0,'p4_entrypoint':'integration.runtime.run_query'}
    evidence={}
    client=None
    meter=None

    def agent_wrapper(name,fn):
        def wrapped(llm,*args,**kwargs):
            enter_step(name)
            if name=='run_gatekeeper':
                args=(args[0],schemas.ConversationState(
                    last_companies=previous.get('companies',[]),last_metrics=previous.get('metrics',[]),
                    last_fiscal_years=previous.get('fiscal_years',[]),last_use_case=previous.get('use_case'),
                    history=[{'role':m['role'],'content':m['content']} for m in history[-4:]]))
            # Measure only evidence actually supplied to an agent, before the call,
            # so diagnostics also survive provider errors or budget exhaustion.
            chunk_position = {'run_analyst': 1, 'run_writer': 2, 'run_critic': 3}.get(name)
            if chunk_position is not None:
                chunks = args[chunk_position]
                rag = metrics.setdefault('rag', {'estimated_tokens': 0, 'steps': [], 'passages': []})
                estimate = sum((len(c.text) + 3) // 4 for c in chunks)
                rag['estimated_tokens'] += estimate
                rag['steps'].append({'agent': name.removeprefix('run_'),
                                     'passages': len(chunks), 'estimated_tokens': estimate})
                known = {c['chunk_id'] for c in rag['passages']}
                for chunk in chunks:
                    if chunk.chunk_id not in known:
                        source = evidence.get(chunk.chunk_id, {})
                        rag['passages'].append({'chunk_id': chunk.chunk_id,
                            'document': source.get('doc_id', ''), 'page': source.get('page'),
                            'estimated_tokens': (len(chunk.text) + 3) // 4,
                            'preview': chunk.text[:1000]})
                        known.add(chunk.chunk_id)
            validation_error = None
            with _span(name.removeprefix('run_').replace('_','-'),'agent',{'question':question}) as obs:
                try:
                    result=fn(llm,*args,**kwargs)
                except modules['json_utils'].AgentOutputError as exc:
                    if name != 'run_analyst':
                        raise
                    validation_error = exc
                    record = {'agent': name, 'attempts': len(exc.errors), 'repairs': len(exc.errors) - 1,
                              'validation_errors': len(exc.errors)}
                    update_observation(obs, level='ERROR', status_message='Analyst output could not be verified',
                                       metadata=record)
                else:
                    record={'agent':name,'attempts':result.attempts,'repairs':result.repairs,
                            'validation_errors':len(result.errors),'local_fixes':len(result.local_fixes)}
                    update_observation(obs,output=result.obj.model_dump(),metadata=record)
                metrics['json_steps'].append(record)
            if validation_error is not None:
                raise validation_error
            if name=='run_gatekeeper' and result.obj.in_scope:
                gate=result.obj
                context.update(companies=gate.companies,metrics=gate.metrics,fiscal_years=gate.fiscal_years,use_case=gate.use_case)
            return result
        return wrapped

    def retrieve(query,k=5,filters=None):
        enter_step("retrieve")
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
        enter_step("calculate")
        from p4.tools.calculator import calculator
        if len(expression)>256:
            raise ValueError('Calculator expression too long')
        tree=ast.parse(expression,mode='eval')
        nodes = list(ast.walk(tree))
        if len(nodes)>64 or any(isinstance(node,ast.Pow) for node in nodes):
            raise ValueError('Calculator expression exceeds supported bounds')
        metrics['tool_calls']+=1
        with _span('calculator','tool',{'expression':expression}) as obs:
            result=calculator(expression)
            update_observation(obs,output=result)
            return result
    try:
        enter_step('setup')
        missing = missing_setup()
        if missing:
            return ChatResponse('Research setup is incomplete.', successful=False, status='partial',
                                metrics={'setup_required': True, 'missing_setup': missing, 'failed_step': step})
        modules = load_p2(p2_path())
        schemas, agents = modules['schemas'], modules['agents']
        agent_proxy=SimpleNamespace(**{name:agent_wrapper(name,getattr(agents,name))
            for name in ('run_gatekeeper','run_planner','run_query_writer','run_analyst','run_writer','run_critic')})
        agent_proxy.AgentOutputError = modules['json_utils'].AgentOutputError

        p3=load_retrieval(str(rag_path()))
        client=_make_client(modules['llm_client'])
        meter=MeteredClient(client,config['token_budget'],bypass_cache=config.get('bypass_model_cache',False))
        raw = run_query(
            question, str(p2_path()), str(rag_path()), llm=meter, tag='p5.chat',
            p2_modules=(agent_proxy, modules['llm_client'], schemas),
            retrieval=SimpleNamespace(retrieve=retrieve, get_table=p3.get_table),
            calculator=calculate,
        )
        metrics.update(llm_calls=meter.calls,model_cache_hits=meter.cached_calls,tokens_accounted=meter.tokens)
        enter_step('finalize')
        return normalize_response(raw,evidence,context,meter.usage,metrics)
    except TokenBudgetExceeded:
        metrics.update(failure='token_budget_exhausted', failed_step=step, llm_calls=meter.calls if meter else 0,
                       tokens_accounted=meter.tokens if meter else 0,
                       token_budget=config['token_budget'])
        return ChatResponse(
            f"Research stopped because this request exceeded its {config['token_budget']:,}-token allowance. "
            "Try one company, metric and financial year at a time, or increase AGENT_TOKEN_BUDGET and restart the app.",
            successful=False, status='partial', agent_context=context,
            usage=meter.usage if meter else {}, metrics=metrics)
    except Exception as exc:
        logger.exception('P4 research run failed during %s.', step)
        metrics.update(failure='p4_run_failed', failed_step=step, error_type=type(exc).__name__,llm_calls=meter.calls if meter else 0)
        return ChatResponse(f"Research stopped during this step: {RESEARCH_STEPS[step]}.",
            successful=False,status='partial',agent_context=context,
            usage=meter.usage if meter else {},metrics=metrics)
    finally:
        if client is not None:
            try: _close_client(client)
            except Exception: logger.exception('P2 client cleanup failed.')


def normalize_response(raw,evidence,context,usage,metrics):
    status=raw.get('status')
    limitations=raw.get('missing',[])
    if status=='refused':
        return ChatResponse(raw.get('message') or 'This request is outside the supported scope.',
                            status='refused',agent_context=context,usage=usage,metrics=metrics)
    if status!='answered':
        return ChatResponse('I could not verify an answer from the available evidence.',successful=False,status='partial',
            results=raw.get('results',[]),limitations=limitations or ['P4 validation incomplete'],
            agent_context=context,usage=usage,metrics=metrics)
    answer=raw.get('answer') or {}
    if answer.get('refused'):
        return ChatResponse(answer.get('answer') or 'No supported answer was found.',
            status='not_found' if answer.get('refusal_reason')=='not_in_context' else 'refused',
            results=raw.get('results',[]) if limitations else [],limitations=limitations,
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
    complete=(bool(answer.get('answer')) and bool(citations) and valid_citations
              and not limitations and raw.get('critic',{}).get('verdict')=='pass')
    if not complete and not limitations:
        limitations=['P4 evidence or citation validation incomplete']
    return ChatResponse(answer=answer.get('answer') or 'No verified answer returned.',citations=citations,
        status='answered' if complete else 'partial',successful=complete,cacheable=complete,
        results=raw.get('results',[]),limitations=limitations,agent_context=context,usage=usage,metrics=metrics)
