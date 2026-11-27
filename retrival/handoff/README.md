# Team handoff folders

Place incoming owner deliverables here, then integrate/reconcile them with the canonical package folders.

- `P2/`: updated P2 agent implementation, schemas/config, model client, and interface notes. Do not blindly overwrite; compare with `integration/p2_agents/` first.
- `P3/parsed/`: P3's complete `all_chunks.jsonl` (not a small sample).
- `P3/index/`: P3 index artifacts if supplied individually. Existing `p3_retrieval/index_bundle.zip` is retained in the package.
- `P5/`: P5 UI/trace/evaluation/deployment handoff, if P5 supplies it. P5 can consume P4 via the documented runtime contract.
