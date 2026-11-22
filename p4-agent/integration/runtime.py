"""Thin P4 integration runner for the team's P2 agent package and P3 RAG.

Usage requires paths to the P2 package and P3 RAG source. It intentionally does
not ship credentials or a copy of P3's large index.
"""
from __future__ import annotations
import importlib, sys, re, math
from pathlib import Path
from typing import Any


def load_p2(p2_path: str):
    p = str(Path(p2_path).expanduser().resolve())
    if p not in sys.path: sys.path.insert(0, p)
    # P2 package is a flat module package (agents.py, llm_client.py, etc.).
    agents = importlib.import_module("agents")
    client = importlib.import_module("llm_client")
    schemas = importlib.import_module("schemas")
    return agents, client, schemas


def load_p3(p3_path: str):
    p = str(Path(p3_path).expanduser().resolve())
    if p not in sys.path: sys.path.insert(0, p)
    mod = importlib.import_module("retrieve")
    if not callable(getattr(mod, "retrieve", None)) or not callable(getattr(mod, "get_table", None)):
        raise ImportError("P3 source must expose retrieve() and get_table().")
    return mod


def _as_obj(result):
    return result.obj if hasattr(result, "obj") else result


def normalize_chunks(records, ChunkModel):
    normalized=[]
    for r in records or []:
        d=dict(r)
        # P3 integration guide names file metadata differently than P2's Chunk schema.
        d.setdefault("doc", d.get("document", d.get("doc_id", "unknown_document")))
        d.setdefault("chunk_id", d.get("id", d.get("doc_id", "unknown_chunk")))
        d.setdefault("company", "unknown")
        d.setdefault("text", d.get("content", ""))
        normalized.append(ChunkModel.model_validate(d))
    return normalized


def run_query(question: str, p2_path: str, p3_path: str, llm=None, tag="p4.integrated"):
    """Single answer path using real P2 agents and P3 retrieval; API calls occur here.

    This function requires both teammate packages and credentials configured by P2.
    It is deliberately conservative: only retrieves and answers, no brief export.
    """
    agents, clientmod, schemas = load_p2(p2_path)
    p3 = load_p3(p3_path)
    llm = llm or clientmod.LLMClient()
    state = schemas.ConversationState()
    gate = _as_obj(agents.run_gatekeeper(llm, question, state, tag=tag))
    if not gate.in_scope:
        return {"status":"refused", "message":gate.refusal_message, "use_case":gate.use_case}
    plan = _as_obj(agents.run_planner(llm, gate, tag=tag))
    all_chunks=[]; results=[]; missing=[]
    for subtask in plan.subtasks:
        qw = _as_obj(agents.run_query_writer(llm, subtask, tag=tag))
        chunks=[]
        for q in qw.queries:
            found = p3.retrieve(query=q, k=5, filters=qw.filters.model_dump(exclude_none=True))
            chunks.extend(found or [])
        # Deduplicate chunks by chunk_id, retain first occurrence.
        seen=set(); dedup=[]
        for c in chunks:
            cid=c.get("chunk_id", c.get("id"))
            if cid not in seen: seen.add(cid); dedup.append(c)
        p2chunks=normalize_chunks(dedup[:5], schemas.Chunk)
        all_chunks.extend(p2chunks)
        if not p2chunks:
            missing.append(subtask.question)
            results.append({"subtask_id":subtask.id,"company":subtask.company,
                            "metric":subtask.metric,"fiscal_year":subtask.fiscal_year,
                            "value":None,"unit":None,"chunk_ids":[],"missing":["No evidence retrieved"]})
            continue
        analyst=_as_obj(agents.run_analyst(llm, subtask, p2chunks, tag=tag))
        vals=[v.model_dump() for v in analyst.values]
        calculated=None
        if analyst.calculation:
            expr=analyst.calculation.expression
            value_map={v.label:v.value for v in analyst.values}
            substitutions={k:value_map[label] for k,label in analyst.calculation.variables.items() if label in value_map}
            # The P4 calculator accepts arithmetic AST only; substitute named variables before evaluation.
            for name,val in sorted(substitutions.items(), key=lambda x:-len(x[0])):
                expr=re.sub(rf"\b{re.escape(name)}\b", str(float(val)), expr)
            from p4.tools.calculator import calculator
            calculated=calculator(expr)["value"]
        for v in vals:
            results.append({"subtask_id":subtask.id,"company":subtask.company,
                           "metric":v.get("label",subtask.metric),"fiscal_year":v.get("fiscal_year",subtask.fiscal_year),
                           "value":v.get("value"),"unit":v.get("unit"),"chunk_ids":[v.get("chunk_id")],
                           "inputs":v.get("quote")})
        if calculated is not None:
            results.append({"subtask_id":subtask.id,"company":subtask.company,
                            "metric":subtask.metric,"fiscal_year":subtask.fiscal_year,
                            "value":calculated,"unit":analyst.calculation.result_unit,
                            "chunk_ids":[v.chunk_id for v in analyst.values],
                            "formula":analyst.calculation.expression})
    # Keep only unique evidence chunks for Writer/Critic.
    chunk_by_id={c.chunk_id:c for c in all_chunks}; evidence=list(chunk_by_id.values())[:5]
    draft=_as_obj(agents.run_writer(llm, gate.resolved_question, results, evidence, tag=tag))
    critique=_as_obj(agents.run_critic(llm, gate.resolved_question, draft, results, evidence, tag=tag))
    if critique.verdict != "pass":
        # Report the critic outcome explicitly; do not claim a fully validated answer.
        return {"status":"partial_validation", "draft":draft.model_dump(),
                "critic":critique.model_dump(),"results":results,
                "missing":missing, "retrieved_chunks":len(evidence)}
    return {"status":"answered", "answer":draft.model_dump(), "results":results,
            "missing":missing, "retrieved_chunks":len(evidence),
            "critic":critique.model_dump()}
