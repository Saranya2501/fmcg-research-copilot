# P1 — Spec, Eval & Safety

Owner: Yogesh

Owns the gold evaluation dataset, UC1–UC7 use-case mapping, response schema, refusal policy, and injection safety tests. Also leads final report assembly.

## Included evaluation material

- [gold_v1_with_context.jsonl](gold_v1_with_context.jsonl) — 100-question gold dataset with context.
- [P3 recall evaluation](../p3-retrieval/eval/recall_eval.py) — retrieval document Recall@5 and Recall@10; requires the full P3 data bundle and model setup.
- [P2 schemas](../p4-agent/integration/p2_agents/schemas.py) and [agent checks](../p4-agent/integration/p2_agents/tests/test_agents.py) — runtime contracts and offline validation checks.

From the repository root, after configuring standalone P3 as described in its
[integration guide](../p3-retrieval/INTEGRATION.md), run retrieval evaluation with:

```bash
.venv/bin/python p3-retrieval/eval/recall_eval.py --gold p1-eval/gold_v1_with_context.jsonl
```

This script measures retrieval, not end-to-end answer accuracy. An end-to-end
`eval_runner.py`, separate `safety/` and `schema/` folders, and machine-readable
final scoring results are not included in this directory. Consult the submitted
evaluation report in the
[shared submission folder](https://drive.google.com/drive/folders/1-WKMvaOx8v3jJAcwN_jSKkMa3AHC1OR-)
for reported results; reproducing end-to-end scores requires the corresponding
runner, configuration, and run outputs from the team.
