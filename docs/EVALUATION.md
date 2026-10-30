# Evaluation summary

Latest run (UTC): 2026-10-30T16:16:26+00:00

**131/131 passed**, 0 failures, 0 errors, 0 skipped. Runtime: 10.67 seconds.

| Area | What was verified |
| --- | --- |
| Typed outputs | Pydantic input rejection and full assessment JSON round trip |
| Evidence boundaries | Retrieved-source IDs, literal excerpts, invented details, unknown references, synthetic/live isolation, preserved negation |
| Risk policy | Low routine vendor, Moderate allegations, High possible match, confirmed-match escalation, insufficient-information fallback |
| Agentic branches | Targeted identity retry, sanctions-triggered identity verification, namesake exclusion |
| OFAC integration | Primary names, aliases, addresses, spillover joins, schema failures, actual DOS EOF format, fuzzy/token matching, unsupported script handling |
| Provider adapters | Tavily response filtering, Claude/Gemini typed extraction contracts, provider selection and malformed-output rejection, bounded search, complete mocked live workflow |
| Research scope | Explicit field/source plans, current identity vs historical media dates, domain/date postfilters, preserved retrieval on extraction failure, legal-name/country variants, real form preview, and unnumbered PDF headings |
| Live research quality | Branch-office and same-domain path handling, Markdown-only quote differences, preserved negation, bounded observed-link retrieval, partial page failures, core identity preservation, transient retry/circuit breaker and audited model fallback |
| Registry handoffs | Additional jurisdiction routing, query version/settings, observed challenges vs missing results, human completion/reference validation, reopen/Proceed gates, legacy snapshot compatibility, and real form submission |
| Corporate databases | OpenCorporates header-auth/filter contract, uncertain candidates, missing keys, HTTP/schema failures, licensed handoffs, immutable review gates, real UI submission/preview and PDF labels |
| Human review | Persisted notes, preserved machine snapshots, blocked Proceed, confirmed-match hold, cross-assessment isolation, stale disposition invalidation |
| Assessment deletion | Explicit per-case confirmation, atomic snapshot/review removal, rollback on failure, other-case isolation, active/recent/library refresh and empty state |
| UI | Real Streamlit widget actions/reruns, synthetic assessment, review submission, saved library, live evidence links, validation errors, ROI page |
| Gemini recovery | Ordered model routes, bounded retry budget, cooldown/recovery, 404 and transient failover, header Retry-After, invalid/rejected credential backup, no quota-key rotation, safe attempt audit, safety/invalid-output stop |
| Readable reports | Plain-language summary and human resolution, incomplete coverage labels, HTML escaping/CSP hash and anchors, portable controls, summary PDF critical evidence and real Streamlit report download |
| Export and impact | Parseable multipage PDF with citations/mode/review labels, XML escaping, illustrative capacity math |

Run `.venv/bin/python scripts/evaluate.py` to reproduce. Raw JUnit and JSON results are in `output/evaluation/`.

## Historical integration checks

Separate development checks exercised official OFAC downloads and credentialed Gemini/Tavily extraction and model recovery. These are dated integration observations, not accuracy or availability guarantees. The underlying private live-assessment artifacts are deliberately excluded from this repository. The offline suite above is reproducible without credentials.

## Interpretation
These tests demonstrate MVP behavior and safety boundaries on selected cases. They do not establish comprehensive sanctions coverage, factual accuracy of publishers, detection of all model mistakes, legal compliance, or validated business savings. Multilingual identity matching, ownership screening, and analyst decision quality require a labeled evaluation set before production.
