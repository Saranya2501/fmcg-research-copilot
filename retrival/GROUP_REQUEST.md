Hi team — I have refreshed the P4 package and prepared the P2/P3 integration path. The local P4 tests and graph compile were previously verified.

To complete live end-to-end integration, I still need:
- **P3:** the actual RAG source folder/package (`retrieve.py`, `build_index.py`, `requirements.txt` and runtime dependencies), plus confirmation that the supplied index is the matching index version. The integration guide and index files are available, but the retrieval source is not in the uploads I received.
- **P2:** please confirm the `p2_agents_v3` package is the approved/current agent version and share the supported run command/config for the API or local model. No API key/certificate secrets should be sent in chat or committed to the repo.
- **P5:** the implementation package for tracing/evaluation runner, app entry point and deployment config; the ZIP received for P5 is empty.
- **P1:** confirm `gold_v1_with_context.jsonl` is the frozen evaluation version to use and the response/refusal policy is final.

Once these are available I can run integration checks without making assumptions about teammate interfaces.
