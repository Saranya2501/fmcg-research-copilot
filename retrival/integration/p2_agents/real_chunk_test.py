"""Run the agents on P3's real chunks and score against the gold set (P2).

    python real_chunk_test.py chunks_sample_p2.jsonl gold_v1_ready.jsonl [--limit 15]

For each UC1/UC2 gold question whose source document is in the chunk file:
  1. evidence = up to 5 chunks: the cited page first, then neighbouring pages
     of the same document (a stand-in for retrieval, so the test isolates the agents)
  2. Analyst extracts figures (unit as printed)
  3. code converts lakh/million to crore and evaluates the calculation
  4. Writer answers; Critic checks; the value is scored against gold (+-1%)

Prints one line per question and a summary. Needs a booked API slot.
"""

import argparse
import ast
import json
import operator
import re
from collections import defaultdict

from agents import compute_result, run_analyst, run_critic, run_writer
from json_utils import AgentOutputError
from llm_client import LLMClient
from schemas import Chunk, SubTask

TO_CRORE = {"Rs crore": 1.0, "Rs lakh": 0.01, "Rs million": 0.1}
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
       ast.Div: operator.truediv, ast.USub: operator.neg}


def calc(expr, env):
    """Safe calculator: numbers, variables, + - * / and brackets only."""
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return float(n.value)
        if isinstance(n, ast.Name):
            return env[n.id]
        if isinstance(n, ast.BinOp) and type(n.op) in OPS:
            return OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in OPS:
            return OPS[type(n.op)](ev(n.operand))
        raise ValueError(f"not allowed in expression: {ast.dump(n)[:60]}")
    return ev(ast.parse(expr, mode="eval"))


def load_chunks(path):
    by_doc = defaultdict(list)
    for line in open(path):
        if not line.strip():
            continue
        r = json.loads(line)
        doc_key = str(r.get("doc") or r.get("doc_id") or "").lower().removesuffix(".pdf")
        r["_key"] = doc_key
        by_doc[doc_key].append(r)
    return by_doc


def find_doc(by_doc, gold_doc):
    g = gold_doc.lower().removesuffix(".pdf")
    return next((k for k in by_doc if k == g or k.endswith("_" + g)), None)


def to_chunk(r, gold_doc):
    return Chunk(chunk_id=str(r["chunk_id"]), company=str(r.get("company", "")),
                 fiscal_year=r.get("fiscal_year"), doc_type=r.get("doc_type"),
                 doc=r.get("doc") or gold_doc, page=int(r["page"]) if str(r.get("page", "")).isdigit() else None,
                 section=r.get("section"), standalone_consolidated=r.get("standalone_consolidated"), text=r["text"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("chunks")
    ap.add_argument("gold")
    ap.add_argument("--limit", type=int, default=15)
    args = ap.parse_args()

    by_doc = load_chunks(args.chunks)
    gold = [json.loads(l) for l in open(args.gold) if l.strip()]
    gold = [g for g in gold if g["use_case"] in ("UC1", "UC2") and g.get("sources")]
    llm = LLMClient()

    rows, skipped = [], 0
    for g in gold:
        if len(rows) >= args.limit:
            break
        src = g["sources"][0]
        key = find_doc(by_doc, src["doc"])
        if not key:
            skipped += 1
            continue
        doc_chunks = by_doc[key]
        page = src.get("page") or 0
        doc_chunks.sort(key=lambda r: (abs(int(r["page"]) - page) if str(r.get("page", "")).isdigit() else 999,
                                       str(r["chunk_id"])))
        chunks = [to_chunk(r, src["doc"]) for r in doc_chunks[:5]]
        on_page = any(c.page == page for c in chunks)
        sub = SubTask(id="t1", kind="calculate" if g["use_case"] == "UC2" else "lookup",
                      company=chunks[0].company, fiscal_year=g.get("fiscal_year"), question=g["question"])
        rec = {"id": g["id"], "uc": g["use_case"], "gold": g["gold_value"], "page_in_sample": on_page}
        try:
            a = run_analyst(llm, sub, chunks, tag=f"real.{g['id']}")
            rec["analyst_repairs"] = a.repairs
            vals = a.obj.values
            if not vals:
                rec.update(status="no_figures", missing=a.obj.missing)
                rows.append(rec)
                continue
            unit_notes = [f"{v.unit}->crore" for v in vals if v.unit in ("Rs lakh", "Rs million")]
            value, unit = compute_result(a.obj)
            value = round(value, 2)
            ok = abs(value - g["gold_value"]) <= 0.01 * abs(g["gold_value"])
            results = [{"subtask_id": "t1", "company": sub.company, "metric": g["question"][:60],
                        "fiscal_year": g.get("fiscal_year"), "value": value, "unit": unit,
                        "chunk_ids": [v.chunk_id for v in vals]}]
            w = run_writer(llm, g["question"], results, chunks, tag=f"real.{g['id']}")
            c = run_critic(llm, g["question"], w.obj, results, chunks, tag=f"real.{g['id']}")
            rec.update(status="OK" if ok else "WRONG", value=value, unit=unit, units=";".join(unit_notes),
                       critic=c.obj.verdict, critic_issues=[i.problem for i in c.obj.issues],
                       answer=w.obj.answer[:140])
        except AgentOutputError as e:
            rec.update(status=f"agent_error:{e.agent}", error=e.errors[-1][:120])
        except Exception as e:  # noqa: BLE001
            rec.update(status="error", error=str(e)[:120])
        rows.append(rec)
        print(json.dumps(rec, ensure_ascii=False))

    n = len(rows)
    print(f"\n{n} questions run, {skipped} skipped (source document not in the chunk file)")
    if n:
        ok = sum(r["status"] == "OK" for r in rows)
        print(f"Correct value: {ok}/{n}")
        print(f"Source page present in sample: {sum(r['page_in_sample'] for r in rows)}/{n}")
        print("Critic verdicts:", {v: sum(r.get('critic') == v for r in rows) for v in ('pass', 'revise')})
        print("Statuses:", {s: sum(r['status'] == s for r in rows) for s in sorted({r['status'] for r in rows})})
    with open("real_chunk_results.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
