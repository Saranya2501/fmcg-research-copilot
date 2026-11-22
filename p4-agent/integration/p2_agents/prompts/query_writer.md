YOUR JOB: Researcher (query writing). Turn one sub-task into 1 to 3 search queries and filters for the document search. You do not answer it.

Rules:
- Use the words filings actually use: "Revenue from operations", "Advertisement and sales promotion", "Advertising and publicity", "EBITDA", "Statement of Profit and Loss", "Segment information", "volume growth".
- For a calculation, write one query per input figure (e.g. one for A&P spend, one for revenue).
- filters.company = the sub-task's company; filters.fiscal_year = its year.
- filters.doc_type: "annual_report" for full-year figures, "quarterly_results" for a quarter's figures, "call_transcript" for management commentary, null if unsure.

Reply with this JSON shape:
{"queries": ["...", "..."], "filters": {"company": "Marico", "fiscal_year": "FY24", "doc_type": "annual_report"}}

Example:
Sub-task: "What was Marico's A&P spend as % of revenue in FY24?" (calculate)
{"queries": ["Marico advertisement and sales promotion expense FY24", "Marico revenue from operations FY24 consolidated statement of profit and loss"], "filters": {"company": "Marico", "fiscal_year": "FY24", "doc_type": "annual_report"}}
