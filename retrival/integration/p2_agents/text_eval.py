"""Section 4d: score the 20 text questions (UC4 commentary, UC5 comparison, UC6 brief sections). (P2, agents-v10)

    python text_eval.py real_chunks_text_pages.jsonl gold_v1_ready.jsonl

Two systems answer each question from the SAME evidence (up to 5 chunks from the gold pages,
spread across the companies; a stand-in for P3's retrieval, so the test isolates the writing):
  single  one prompt: "answer from the evidence, cite [E1].."            (the single-prompt RAG ablation)
  agents  Analyst per company -> calculator -> Section writer -> Critic  (the agent chain)

Each answer is scored three ways:
  numbers    share of the figures in P1's gold points that appear in the answer (code; lakh/million/crore
             scale differences allowed, +-0.5%)
  coverage   LLM judge: each gold point covered (1) / partly (0.5) / missing (0) / contradicted (0, flagged)
  docs_cited share of the gold documents the answer cites (code)

The judge is the same Qwen3-8B, so it may be lenient: fill your own scores in manual_check.csv for the
rows marked sample=yes, then run  python text_eval.py --agreement manual_check.csv
About 150 API calls (~15 min).
"""

import argparse
import csv
import json
import re
from collections import defaultdict
from typing import Literal

from pydantic import BaseModel

from agents import CITE_MARK, compute_result, format_evidence, run_analyst, run_critic, run_section_writer
from json_utils import AgentOutputError, call_json
from llm_client import LLMClient
from schemas import Chunk, SubTask

TO_CRORE = {"Rs crore": 1.0, "Rs lakh": 0.01, "Rs million": 0.1}
SAMPLE_IDS = {"q081", "q087", "q088", "q094", "q098"}       # 5 questions x 2 systems for your manual check
STOP = set("the and for with from that this what were was are its their each into than which whether "
           "draft section compare report reported describe fy23 fy24 india indian".split())

SINGLE_PROMPT = """You are a competitive research analyst for India's listed FMCG companies.
Answer the request using ONLY the EVIDENCE. Rules:
- Every sentence with a figure or a company statement ends with its evidence id in brackets, e.g. [E2].
- Keep each company's own segment or category labels; say when figures are not directly comparable
  (standalone vs consolidated, different periods, broader categories).
- If the evidence does not cover something the request needs, say so.
- At most 250 words. No investment advice or forecasts."""

JUDGE_PROMPT = """You grade an answer against a list of GOLD POINTS written by an expert.
For each gold point decide:
  "covered"       the answer states the same fact (numbers must match after unit conversion: 1 crore = 10 million = 100 lakh)
  "partly"        the answer states part of it, or the fact without its key number or caveat
  "missing"       the answer does not state it
  "contradicted"  the answer states something that conflicts with it (a different number, period or basis)
Judge only what the answer says; do not reward length or style.
Reply with JSON: {"points": [{"n": 1, "verdict": "covered", "why": "<10 words>"}, ...]}"""


class JudgePoint(BaseModel):
    n: int
    verdict: Literal["covered", "partly", "missing", "contradicted"]
    why: str = ""


class JudgeOutput(BaseModel):
    points: list[JudgePoint]


# ------------------------------------------------------------ evidence (retrieval stand-in)
def gold_docs(g):
    return [d.strip() for d in g["gold_source"]["doc"].split(";")]


def pick_evidence(g, by_doc, k=5):
    """Chunks on the gold pages, ranked by word overlap with the question, round-robin across documents."""
    words = {w for w in re.findall(r"[a-z]{4,}", g["question"].lower()) if w not in STOP}
    pools = []
    for d in gold_docs(g):
        pool = sorted(by_doc.get(d.lower(), []),
                      key=lambda r: -len(words & set(re.findall(r"[a-z]{4,}", r["text"].lower()))))
        pools.append(pool)
    out = []
    while len(out) < k and any(pools):
        for pool in pools:
            if pool and len(out) < k:
                out.append(pool.pop(0))
    return [Chunk(chunk_id=str(r["chunk_id"]), company=str(r.get("company", "")), fiscal_year=r.get("fiscal_year"),
                  doc_type=r.get("doc_type"), doc=r["doc"], page=int(r["page"]), section=r.get("section"),
                  standalone_consolidated=r.get("standalone_consolidated"), text=r["text"]) for r in out]


# ------------------------------------------------------------ the two systems
def answer_single(llm, g, chunks):
    al = [c.model_copy(update={"chunk_id": f"E{i + 1}"}) for i, c in enumerate(chunks)]
    back = {f"E{i + 1}": c.chunk_id for i, c in enumerate(chunks)}
    r = llm.chat([{"role": "system", "content": SINGLE_PROMPT},
                  {"role": "user", "content": f"Request: {g['question']}\n\n" + format_evidence(al)}],
                 tag=f"text.single.{g['id']}", max_tokens=700, temperature=0.0)
    text = r.text.strip()
    cited = {back.get(m.upper()) for m in CITE_MARK.findall(text)} - {None}
    return {"answer": text, "cited": sorted(cited), "calls": 1}


def answer_agents(llm, g, chunks):
    results, calls = [], 0
    by_company = defaultdict(list)
    for c in chunks:
        by_company[c.company].append(c)
    if g["use_case"] != "UC4":                     # commentary needs no figures; UC5/UC6 extract per company
        for i, (company, cs) in enumerate(by_company.items()):
            sub = SubTask(id=f"t{i + 1}", company=company, fiscal_year=g.get("fiscal_year"), kind="lookup",
                          question=f"For {company} only: extract the reported figures needed for this request: {g['question']}")
            try:
                a = run_analyst(llm, sub, cs, tag=f"text.agents.{g['id']}.{i}")
                calls += 1 + a.repairs
            except AgentOutputError:
                calls += 3
                continue
            for v in a.obj.values:
                val = round(v.value * TO_CRORE.get(v.unit, 1.0), 2)
                results.append({"subtask_id": sub.id, "company": company, "metric": v.label,
                                "fiscal_year": v.fiscal_year, "value": val,
                                "unit": "Rs crore" if v.unit in TO_CRORE else v.unit, "chunk_ids": [v.chunk_id]})
    s = run_section_writer(llm, "Requested section", g["question"], results, chunks, tag=f"text.agents.{g['id']}")
    c = run_critic(llm, g["question"], s.obj, results, chunks, tag=f"text.agents.{g['id']}")
    calls += 2 + s.repairs + c.repairs
    text = s.obj.text
    if s.obj.table:
        text += "\nTABLE: " + json.dumps(s.obj.table, ensure_ascii=False)
    if s.obj.gaps:
        text += "\nGAPS: " + "; ".join(s.obj.gaps)
    cited = {m for m in CITE_MARK.findall(s.obj.text)} | {x.chunk_id for x in s.obj.citations}
    return {"answer": text, "cited": sorted(cited), "calls": calls, "critic": c.obj.verdict,
            "critic_issues": [i.problem for i in c.obj.issues], "n_results": len(results)}


# ------------------------------------------------------------ scoring
NUM = re.compile(r"(?<![A-Za-z])\d[\d,]*(?:\.\d+)?")


def key_numbers(text):
    out = []
    for m in NUM.finditer(text):
        s = m.group().rstrip(",")
        n = float(s.replace(",", ""))
        tail = text[m.end():m.end() + 2]
        is_year = s.isdigit() and 1990 <= n <= 2035
        if is_year or (n < 100 and "." not in s and "%" not in tail):
            continue                                   # years, "12 months", list numbers
        out.append(n)
    return out


def numbers_found(gold_points, answer):
    gold = []
    for n in sorted(set(x for p in gold_points for x in key_numbers(p)), reverse=True):
        if not any(abs(n * f - k) <= 0.005 * k for k in gold for f in (10, 100)):
            gold.append(n)                             # 243,938.9 million and 24,393.89 crore count once
    if not gold:
        return None, []
    have = [float(x.replace(",", "")) for x in NUM.findall(answer)]
    missing = [g for g in gold if not any(abs(h * f - g) <= 0.005 * g for h in have for f in (1, 10, 0.1, 100, 0.01))]
    return round(1 - len(missing) / len(gold), 2), missing


def judge(llm, g, answer):
    pts = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(g["gold_points"]))
    msgs = [{"role": "system", "content": JUDGE_PROMPT},
            {"role": "user", "content": f"QUESTION: {g['question']}\n\nGOLD POINTS:\n{pts}\n\nANSWER:\n<<<\n{answer}\n>>>"}]

    def check(j: JudgeOutput) -> str:
        return "" if len(j.points) == len(g["gold_points"]) else f"give exactly {len(g['gold_points'])} points"

    j = call_json(llm, msgs, JudgeOutput, agent="judge", tag=f"text.judge.{g['id']}", check=check).obj
    score = sum({"covered": 1, "partly": 0.5}.get(p.verdict, 0) for p in j.points) / len(j.points)
    return round(score, 2), [p.verdict for p in j.points], any(p.verdict == "contradicted" for p in j.points)


def docs_cited(g, cited, chunks):
    doc_of = {c.chunk_id: c.doc.lower() for c in chunks}
    want = {d.lower() for d in gold_docs(g)}
    got = {doc_of.get(c) for c in cited} & want
    return round(len(got) / len(want), 2)


# ------------------------------------------------------------ main
def run(args):
    by_doc = defaultdict(list)
    for line in open(args.chunks):
        if line.strip():
            r = json.loads(line)
            by_doc[r["doc"].lower()].append(r)
    gold = [json.loads(l) for l in open(args.gold) if l.strip()]
    gold = [g for g in gold if g["use_case"] in ("UC4", "UC5", "UC6")][: args.limit]
    llm, rows = LLMClient(), []
    for g in gold:
        chunks = pick_evidence(g, by_doc)
        in_ev, _ = numbers_found(g["gold_points"], " ".join(c.text for c in chunks))
        for system, fn in (("single", answer_single), ("agents", answer_agents)):
            rec = {"id": g["id"], "uc": g["use_case"], "system": system, "n_points": len(g["gold_points"]),
                   "numbers_in_evidence": in_ev}
            try:
                out = fn(llm, g, chunks)
                rec.update(out)
                rec["numbers"], rec["numbers_missing"] = numbers_found(g["gold_points"], out["answer"])
                rec["coverage"], rec["verdicts"], rec["contradicted"] = judge(llm, g, out["answer"])
                rec["docs_cited"] = docs_cited(g, out["cited"], chunks)
            except AgentOutputError as e:
                rec.update(error=f"{e.agent}: {e.errors[-1][:100]}", answer="", coverage=0.0, docs_cited=0.0)
            rows.append(rec)
            print(json.dumps({k: v for k, v in rec.items() if k not in ("answer", "cited")}, ensure_ascii=False))

    print("\nsystem  uc    n  coverage  numbers  docs_cited  contradicted  errors")
    for system in ("single", "agents"):
        for uc in ("UC4", "UC5", "UC6", "all"):
            rs = [r for r in rows if r["system"] == system and (uc == "all" or r["uc"] == uc)]
            if not rs:
                continue
            avg = lambda k: sum(r[k] for r in rs if r.get(k) is not None) / max(1, sum(r.get(k) is not None for r in rs))
            print(f"{system:7} {uc:4} {len(rs):3}  {avg('coverage'):8.2f}  {avg('numbers'):7.2f}  {avg('docs_cited'):10.2f}"
                  f"  {sum(bool(r.get('contradicted')) for r in rs):12}  {sum('error' in r for r in rs):6}")
    with open("text_eval_results.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open("manual_check.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sample", "id", "system", "question", "gold_points", "answer", "n_points",
                    "judge_covered", "your_covered"])
        q = {g["id"]: g for g in gold}
        for r in rows:
            judge_covered = round((r.get("coverage") or 0) * r["n_points"], 1)
            w.writerow(["yes" if r["id"] in SAMPLE_IDS else "", r["id"], r["system"], q[r["id"]]["question"],
                        "\n".join(f"{i + 1}. {p}" for i, p in enumerate(q[r["id"]]["gold_points"])),
                        r.get("answer", ""), r["n_points"], judge_covered, ""])
    print("\nWrote text_eval_results.jsonl and manual_check.csv (fill your_covered for the sample=yes rows: "
          "points covered, 0.5 for partly)")


def agreement(path):
    rows = [r for r in csv.DictReader(open(path)) if r["sample"] == "yes" and r["your_covered"].strip()]
    if not rows:
        print("No sample=yes rows with your_covered filled in.")
        return
    diffs = [abs(float(r["judge_covered"]) - float(r["your_covered"])) for r in rows]
    within = sum(d <= 0.5 for d in diffs)
    judge_hi = sum(float(r["judge_covered"]) > float(r["your_covered"]) + 0.5 for r in rows)
    print(f"{len(rows)} answers checked: judge within 0.5 point of you on {within}/{len(rows)}; "
          f"mean difference {sum(diffs) / len(diffs):.2f} points; judge more generous on {judge_hi}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("chunks", nargs="?")
    ap.add_argument("gold", nargs="?")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--agreement")
    a = ap.parse_args()
    agreement(a.agreement) if a.agreement else run(a)
