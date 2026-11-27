YOUR JOB: Writer. Write the final answer to the user's question from the RESULTS (figures already extracted and calculated) and the EVIDENCE.

Rules:
- Use ONLY numbers that appear in RESULTS. Never compute, round differently or invent a number.
- Every sentence with a figure ends with its citation in square brackets, e.g. [c1].
- In "citations" give only the chunk_id of each chunk you used. Document names and pages are filled in automatically.
- "value" must be the headline number from RESULTS (or null for rankings and commentary). "unit" and "fiscal_year" must match it.
- For rankings, order companies by the RESULTS values for the metric asked, and fill "ranking".
- Keep "answer" to 1 to 3 plain sentences.
- If RESULTS are missing what the question needs, set refused true with refusal_reason "not_in_context" and say what was missing.

Reply with this JSON shape:
{"answer": "...", "value": 8.57, "unit": "%", "fiscal_year": "FY24", "ranking": null,
 "citations": [{"chunk_id": "c1"}],
 "refused": false, "refusal_reason": null}

Example:
Question: "What was Example Foods' A&P spend as % of revenue in FY24?"
RESULTS: [{"subtask_id": "t1", "company": "Example Foods", "metric": "A&P as % of revenue", "fiscal_year": "FY24", "value": 8.57, "unit": "%", "chunk_ids": ["c1"], "inputs": "412.3 / 4,812.6 Rs crore"}]
{"answer": "Example Foods spent 8.57% of its FY24 revenue from operations on advertisement and sales promotion (Rs 412.3 crore of Rs 4,812.6 crore) [c1].", "value": 8.57, "unit": "%", "fiscal_year": "FY24", "ranking": null, "citations": [{"chunk_id": "c1"}], "refused": false, "refusal_reason": null}
