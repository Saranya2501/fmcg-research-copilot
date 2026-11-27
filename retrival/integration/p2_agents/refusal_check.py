"""Section 4c: do the agents refuse what they should, and only that? (P2, agents-v10)

    python refusal_check.py gold_v1_ready.jsonl [--in-scope 3]

Runs quick_route + Gatekeeper (no retrieval needed) on
  - all 12 UC7 gold questions (investment advice, forecasts, valuation, unlisted companies): must refuse
  - the first N questions of each of UC1-UC6 (default 3 each = 18): must NOT refuse
Prints one line per question and a summary. About 30 API calls.
"""

import argparse
import json
import time

from agents import quick_route, run_gatekeeper
from json_utils import AgentOutputError
from llm_client import LLMClient
from schemas import ConversationState


def expected_reason(gold_points) -> str:
    text = " ".join(gold_points if isinstance(gold_points, list) else [str(gold_points)]).lower()
    return "out_of_scope" if "unlisted" in text else "advice_or_forecast"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gold")
    ap.add_argument("--in-scope", type=int, default=3)
    args = ap.parse_args()
    gold = [json.loads(l) for l in open(args.gold) if l.strip()]
    must_refuse = [g for g in gold if g["use_case"] == "UC7"]
    must_answer = []
    for uc in ("UC1", "UC2", "UC3", "UC4", "UC5", "UC6"):
        must_answer += [g for g in gold if g["use_case"] == uc][: args.in_scope]

    llm, rows = LLMClient(), []
    for g, should_refuse in [(g, True) for g in must_refuse] + [(g, False) for g in must_answer]:
        rec = {"id": g["id"], "uc": g["use_case"], "should_refuse": should_refuse, "question": g["question"][:80]}
        t0 = time.time()
        try:
            canned = quick_route(g["question"])
            if canned:
                rec.update(refused=False, route="quick_route")
            else:
                gate = run_gatekeeper(llm, g["question"], ConversationState(), tag=f"refusal.{g['id']}").obj
                refused = (not gate.in_scope) or gate.use_case == "UC7"
                rec.update(refused=refused, gate_uc=gate.use_case, reason=gate.refusal_reason,
                           message=(gate.refusal_message or "")[:120])
                if should_refuse:
                    rec["reason_ok"] = gate.refusal_reason == expected_reason(g.get("gold_points"))
        except AgentOutputError as e:
            rec.update(refused=None, error=f"{e.agent}: {e.errors[-1][:100]}")
        rec["latency_s"] = round(time.time() - t0, 1)
        rec["ok"] = rec.get("refused") == should_refuse
        rows.append(rec)
        print(json.dumps(rec, ensure_ascii=False))

    r = [x for x in rows if x["should_refuse"]]
    a = [x for x in rows if not x["should_refuse"]]
    print(f"\nRefused when it should (UC7): {sum(x['ok'] for x in r)}/{len(r)}"
          f"   reason matches gold: {sum(bool(x.get('reason_ok')) for x in r)}/{len(r)}")
    print(f"Answered when it should (UC1-UC6 sample): {sum(x['ok'] for x in a)}/{len(a)}"
          f"   false refusals: {[x['id'] for x in a if x.get('refused')]}")
    print(f"Gatekeeper latency: median {sorted(x['latency_s'] for x in rows)[len(rows) // 2]} s")
    with open("refusal_results.jsonl", "w") as f:
        for x in rows:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
