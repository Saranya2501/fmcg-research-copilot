#!/usr/bin/env python
"""System metrics for the live P5 app, from Langfuse plus the local model-call log.

Each source is missing something the others have:
  * Langfuse root traces: authoritative turn boundaries, latency, outcome, use case.
  * data/logs/llm_calls.jsonl: every provider call, including JSON repairs and failed
    attempts, but with no trace ID. Calls are attributed to the turn whose time window
    contains them (windows never overlap in a single-user deployment; overlaps are reported).
  * Langfuse retriever/tool observations: real tool-call counts.
Langfuse's own output-token field excludes reasoning tokens, so tokens and cost come from
the log's provider-reported usage and are cross-checked against Langfuse totals.

Read-only. Usage:  python backend/scripts/system_metrics.py [--model Qwen/Qwen3-8B]
"""

import argparse
import json
import math
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import dotenv_values
from langfuse import Langfuse

APP = Path(__file__).resolve().parents[1]
PAD = timedelta(seconds=2)  # log timestamps have one-second resolution
SYSTEM_FAILURES = {"provider_error", "json_invalid", "token_budget", "agent_error"}
MIN_P95_N = 20


def retry(call, attempts=4):
    for i in range(attempts):
        try:
            return call()
        except Exception:
            if i == attempts - 1:
                raise
            time.sleep(5)


def fetch(client, **filters):
    rows, cursor = [], None
    while True:
        page = retry(lambda: client.api.observations.get_many(limit=1000, cursor=cursor, **filters))
        rows += page.data
        cursor = page.meta.cursor
        if not cursor:
            return rows


def load_log(path):
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            row["t"] = datetime.fromisoformat(row["ts"]).astimezone()  # naive local time
            rows.append(row)
    return [r for r in rows if r["tag"].startswith("p5.chat")]


def gatekeeper_labels(client):
    labels = {}
    for g in fetch(client, name="gatekeeper", fields="basic,io"):
        try:
            out = json.loads(g.output) if isinstance(g.output, str) else g.output
            labels.setdefault(g.trace_id, (out["use_case"], bool(out["in_scope"])))
        except (TypeError, ValueError, KeyError):
            pass
    return labels


def build_turns(client, args):
    gates = gatekeeper_labels(client)
    tools = Counter(o.trace_id for kind in ("RETRIEVER", "TOOL") for o in fetch(client, type=kind, fields="basic"))
    generations = defaultdict(lambda: dict(calls=0, tokens_in=0, tokens=0))
    for g in fetch(client, type="GENERATION", fields="basic,model,usage"):
        if g.model == args.model and g.usage_details:
            entry = generations[g.trace_id]
            entry["calls"] += 1
            entry["tokens_in"] += g.usage_details.get("input", 0)
            entry["tokens"] += g.usage_details.get("total", 0)  # 'output' excludes reasoning tokens
    since = datetime.fromisoformat(args.since).astimezone() if args.since else None
    turns = []
    for x in fetch(client, name="process-chat-turn", fields="basic,metadata,metrics"):
        m = x.metadata or {}
        if m.get("config.backend") != "agent" or m.get("config.model") != args.model or m.get("cache_status") == "hit":
            continue
        if since and x.start_time < since:
            continue
        use_case, in_scope = gates.get(x.trace_id, ("unclassified", None))
        turns.append(dict(trace=x.trace_id, start=x.start_time, end=x.end_time, meta=m, use_case=use_case,
                          in_scope=in_scope, tools=tools[x.trace_id], generations=generations.get(x.trace_id),
                          langfuse_tokens=generations[x.trace_id]["tokens"],
                          latency=x.latency if x.latency is not None else (x.end_time - x.start_time).total_seconds(),
                          rows=[]))
    return turns


def attribute(turns, rows, model):
    rows = [r for r in rows if r["model"] == model]
    overlaps = unmatched = 0
    for r in rows:
        owners = [t for t in turns if t["start"] - PAD <= r["t"] <= t["end"] + PAD]
        overlaps += len(owners) > 1
        unmatched += not owners
        if owners:
            owners[0]["rows"].append(r)
    return len(rows), unmatched, overlaps


def outcome(turn):
    m, errors = turn["meta"], {r["status"] for r in turn["rows"]} - {"ok", "cache_hit"}
    if m.get("metrics.setup_required"):
        return "setup_incomplete"
    failure = m.get("metrics.failure")
    if not failure and not m.get("metrics.llm_calls"):
        return "no_model_call"
    if failure == "token_budget_exhausted":
        return "token_budget"
    if failure:
        if m.get("metrics.error_type") == "AgentOutputError":
            return "json_invalid"
        return "provider_error" if errors else "agent_error"
    return {"answered": "answered", "refused": "refused", "not_found": "not_found"}.get(m.get("status"), "unverified")


def usage(turn, price_in, price_out):
    fresh = [r for r in turn["rows"] if r["status"] == "ok"]
    logged = bool(turn["rows"])
    if logged:
        calls = len(fresh)
        tokens_in = sum(r.get("prompt_tokens", 0) for r in fresh)
        tokens_out = sum(r.get("completion_tokens", 0) for r in fresh)
    else:  # no log rows (different log path): fall back to Langfuse generations
        g = turn["generations"] or dict(calls=0, tokens_in=0, tokens=0)
        calls, tokens_in, tokens_out = g["calls"], g["tokens_in"], g["tokens"] - g["tokens_in"]
    return dict(calls=calls, tokens_in=tokens_in, tokens_out=tokens_out, tokens=tokens_in + tokens_out,
                cost=(tokens_in * price_in + tokens_out * price_out) / 1e6, logged=logged,
                repairs=sum(".repair" in r["tag"] and r["status"] != "cache_hit" for r in turn["rows"]))


def pct(values, p):
    v = sorted(values)
    if not v:
        return None
    k = (len(v) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def mean(values):
    return sum(values) / len(values) if values else 0.0


def table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def seconds(value, n):
    return "-" if value is None else f"{value:.2f}s" + ("*" if n < MIN_P95_N else "")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="Qwen/Qwen3-8B")
    parser.add_argument("--price-in", type=float, default=0.02, help="USD per million input tokens")
    parser.add_argument("--price-out", type=float, default=0.04, help="USD per million output tokens")
    parser.add_argument("--since", help="ISO local time; ignore earlier turns (e.g. before bug fixes)")
    parser.add_argument("--log", default=str(APP / "data/logs/llm_calls.jsonl"))
    parser.add_argument("--env", default=str(APP / ".env"))
    args = parser.parse_args()

    env = dotenv_values(args.env)
    client = Langfuse(public_key=env["LANGFUSE_PUBLIC_KEY"], secret_key=env["LANGFUSE_SECRET_KEY"],
                      base_url=env["LANGFUSE_BASE_URL"], tracing_enabled=False, timeout=60)
    turns = build_turns(client, args)
    client.shutdown()
    log_rows = load_log(Path(args.log))
    if args.since:
        log_rows = [r for r in log_rows if r["t"] >= datetime.fromisoformat(args.since).astimezone() - PAD]
    model_rows, unmatched, overlaps = attribute(turns, log_rows, args.model)

    for t in turns:
        t["outcome"] = outcome(t)
        t["usage"] = usage(t, args.price_in, args.price_out)
    skipped = Counter(t["outcome"] for t in turns if t["outcome"] in ("setup_incomplete", "no_model_call"))
    ran = [t for t in turns if t["outcome"] not in skipped]
    groups = {"ALL": ran}
    for uc in sorted({t["use_case"] for t in ran}):
        groups[uc] = [t for t in ran if t["use_case"] == uc]

    print(f"## Population\n\nModel `{args.model}`, backend agent, response-cache hits excluded.\n")
    print(table(["Item", "Count"], [
        ["Langfuse turns in scope of this report", len(turns)],
        ["Setup incomplete (pipeline never ran), excluded", skipped["setup_incomplete"]],
        ["No model call and no error, excluded", skipped["no_model_call"]],
        ["Turns analysed", len(ran)],
        ["...of which have no log rows (tokens taken from Langfuse generations)",
         sum(not t["usage"]["logged"] for t in ran)],
        ["Log rows for this model", model_rows],
        ["...attributed to an analysed turn", model_rows - unmatched],
        ["...not inside any traced turn (benchmarks, untraced runs), excluded", unmatched],
        ["Log rows inside more than one turn window", overlaps],
    ]))

    print("\n## Outcomes\n\nVerified = answered with valid citations and critic pass. System failure = provider, "
          "JSON, token-budget or agent error.\n")
    rows = []
    for name, g in groups.items():
        c = Counter(t["outcome"] for t in g)
        failed = sum(c[k] for k in SYSTEM_FAILURES)
        completed = len(g) - failed
        in_scope = [t for t in g if t["in_scope"] is not False]
        rows.append([name, len(g), c["answered"], c["refused"] + c["not_found"], c["unverified"], failed,
                     f"{100 * completed / len(g):.0f}%",
                     f"{100 * c['answered'] / len(in_scope):.0f}%" if in_scope else "-"])
    print(table(["Use case", "Turns", "Verified", "Refused/not found", "Unverified", "System failures",
                 "Pipeline completion", "Verified / in-scope"], rows))
    causes = Counter((t["outcome"], t["meta"].get("metrics.error_type") or "-")
                     for t in ran if t["outcome"] in SYSTEM_FAILURES)
    print("\nFailure causes: " + ", ".join(f"{k}/{e}={v}" for (k, e), v in sorted(causes.items())))

    print(f"\n## Latency per turn (completed turns; * = fewer than {MIN_P95_N} turns, indicative only)\n")
    rows = []
    for name, g in groups.items():
        lat = [t["latency"] for t in g if t["outcome"] not in SYSTEM_FAILURES]
        rows.append([name, len(lat), seconds(pct(lat, .5), len(lat)), seconds(pct(lat, .95), len(lat))])
    print(table(["Use case", "Turns", "Median", "p95"], rows))

    print("\n## Model calls, tokens, notional cost and tool calls per turn (all analysed turns)\n")
    rows = []
    for name, g in groups.items():
        u = [t["usage"] for t in g]
        answered = sum(t["outcome"] == "answered" for t in g)
        cost = sum(x["cost"] for x in u)
        rows.append([name, len(g), f"{mean([x['calls'] for x in u]):.2f}", f"{mean([x['tokens'] for x in u]):,.0f}",
                     f"${mean([x['cost'] for x in u]):.6f}", f"${cost / answered:.6f}" if answered else "-",
                     f"{mean([t['tools'] for t in g]):.2f}"])
    print(table(["Use case", "Turns", "Model calls", "Tokens", "Cost", "Cost per verified answer", "Tool calls"], rows))
    print(f"\nNotional cost at ${args.price_in}/M input and ${args.price_out}/M output tokens; not an actual bill. "
          "Counts successful provider calls only; cache replays and failed attempts are not billed.")

    print("\n## JSON validity from the call log (fresh, non-cached calls)\n")
    base, repair1, repair2 = Counter(), Counter(), Counter()
    for t in ran:
        for r in t["rows"]:
            if r["status"] == "cache_hit":
                continue
            agent = r["tag"].split(".")[2]
            if ".repair1" in r["tag"]:
                repair1[agent] += 1
            elif ".repair2" in r["tag"]:
                repair2[agent] += 1
            elif r["status"] == "ok":
                base[agent] += 1
    terminal = sum(t["outcome"] == "json_invalid" for t in ran if t["rows"])
    rows = [[a, base[a], f"{100 * (1 - repair1[a] / base[a]):.0f}%", repair1[a], repair2[a]]
            for a in sorted(base)]
    total = sum(base.values())
    rows.append(["ALL", total, f"{100 * (1 - sum(repair1.values()) / total):.0f}%", sum(repair1.values()),
                 sum(repair2.values())])
    print(table(["Agent", "JSON outputs", "Valid first time", "Repair 1 calls", "Repair 2 calls"], rows))
    print(f"\nSteps still invalid after repairs: {terminal} of {total} "
          f"({100 * (1 - terminal / total):.1f}% valid after repair). "
          f"Repairs per turn: {mean([t['usage']['repairs'] for t in ran]):.2f}.")

    both = [t for t in ran if t["usage"]["tokens"] and t["langfuse_tokens"]]
    close = sum(abs(t["usage"]["tokens"] - t["langfuse_tokens"]) <= 0.02 * t["langfuse_tokens"] for t in both)
    print("\n## Cross-check: log tokens vs Langfuse totals\n")
    print(f"{close} of {len(both)} turns agree within 2%; log total {sum(t['usage']['tokens'] for t in both):,} "
          f"vs Langfuse {sum(t['langfuse_tokens'] for t in both):,} tokens.")


if __name__ == "__main__":
    main()
