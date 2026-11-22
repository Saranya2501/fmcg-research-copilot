# P3 corpus archive inspection

## Received archive inventory

| Company | Annual-report PDFs | Filename years found |
|---|---:|---|
| Britannia | 10 | 2017–2026 |
| Colgate | 10 | 2017–2026 |
| Dabur | 10 | 2017–2026 |
| Emami | 10 | 2017–2026 |
| Godrej Consumer | 10 | 2017–2026 |
| HUL | 10 | 2017–2026 |
| ITC | 10 | 2017–2026 |
| Marico | 10 | 2017–2026 |
| Nestlé India | 9 | 2017–2022, 2024–2026 (2023 filename absent) |
| Tata Consumer | 10 | 2017–2026 |
| **Total** | **99** | |

The years above are filename labels, not a verified fiscal-period mapping.

## Scope gap against the project plan
The 10-day plan specifies ten companies, FY20–FY24, annual reports, quarterly results and investor presentations, with at least 500 documents. The ten ZIPs inspected contain annual-report PDFs only (99 files). No quarterly-results or investor-presentation files were present in these archives.

The supplied 2025/2026 filename-labelled documents fall outside the plan's FY20–FY24 retrieval window unless P1/P3 explicitly approves a scope change. The 2017–2019 reports are also outside that planned window. Nestlé's 2023 annual-report filename was not present.

## What this means for P4
- The ten-company alias registry can be aligned to the supplied ten company folders.
- Company-specific corpus filters can be passed to P3 once its API is provided.
- P4 can be unit-tested with mocked P3 return records.
- Real `search_reports` and `get_table` execution cannot be claimed until P3 supplies the retrieval/index and table-extraction code.
- P4 must not assume an annual report's filename year is identical to the fiscal-year label in its contents.
