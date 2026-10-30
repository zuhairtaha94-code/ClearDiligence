"""Run reproducible offline evaluations and publish a machine-readable summary."""
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
output=ROOT/"output"/"evaluation"
output.mkdir(parents=True,exist_ok=True)
result=subprocess.run([sys.executable,"-m","pytest","-q","--junitxml="+str(output/"results.xml")],cwd=ROOT)
root=ET.parse(output/"results.xml").getroot()
suites=[root] if root.tag=="testsuite" else list(root.iter("testsuite"))
summary={"at_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),"tests":sum(int(s.get("tests",0)) for s in suites),"failures":sum(int(s.get("failures",0)) for s in suites),"errors":sum(int(s.get("errors",0)) for s in suites),"skipped":sum(int(s.get("skipped",0)) for s in suites),"duration_seconds":round(sum(float(s.get("time",0)) for s in suites),2),"exit_code":result.returncode,"scope":"Offline deterministic workflow, mocked integration contracts, Streamlit AppTest, persistence, PDF content, and ROI. Does not measure real-world recall or live LLM factual accuracy."}
summary["passed"]=summary["tests"]-summary["failures"]-summary["errors"]-summary["skipped"]
(output/"summary.json").write_text(json.dumps(summary,indent=2))
live_file=output/"live_research_smoke.json"
live=json.loads(live_file.read_text()) if live_file.exists() else None
live_note=(f"A credentialed end-to-end run completed for {live['company']}: {live['sources']} retrieved sources and {live['supported_profile_findings']} evidence-supported profile findings across {len(live['profile_fields'])} fields. Remaining gaps and quarantined output are preserved; final tier: {live['tier']}. This is a point-in-time integration check, not a model-accuracy benchmark." if live else "No full credentialed research run is recorded.")
report=f"""# Evaluation summary

Latest run (UTC): {summary['at_utc']}

**{summary['passed']}/{summary['tests']} passed**, {summary['failures']} failures, {summary['errors']} errors, {summary['skipped']} skipped. Runtime: {summary['duration_seconds']} seconds.

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

## External smoke checks
Official OFAC downloads were also tested separately against Treasury: 19,457 primary records, four successfully parsed datasets, Last-Modified 2026-10-15. Provenance is stored locally in `data/ofac_smoke.json`. This is a point-in-time integration check, not a sanctions recall benchmark.

Anthropic, Gemini, and Tavily were tested with controlled mock responses. Credentialed Gemini 3.8 Flash extraction was separately verified on previously retrieved public evidence. The latest end-to-end live research check is recorded in `output/evaluation/live_research_smoke.json` when present; it is not part of the offline unit-test score. Unit tests inject unsupported model outputs; they do not establish a measured hallucination rate. Browser layout and the generated sample PDF were visually inspected separately; current render verification is recorded in PROJECT_NOTES.md.

{live_note}

## Gemini route smoke check

An additional credentialed synthetic technical fixture tested an unavailable model returning HTTP 404 followed by a successful structured response from Gemini 3.6 Flash. Safe attempt records are in `output/evaluation/gemini_recovery_smoke.json`. An earlier probe also reproduced intermittent 503 failure; this check is not an availability guarantee. No real company assessment or human review was created by the probe.

## Interpretation
These tests demonstrate MVP behavior and safety boundaries on selected cases. They do not establish comprehensive sanctions coverage, factual accuracy of publishers, detection of all model mistakes, legal compliance, or validated business savings. Multilingual identity matching, ownership screening, and analyst decision quality require a labeled evaluation set before production.
"""
(ROOT/"docs").mkdir(exist_ok=True)
(ROOT/"docs"/"EVALUATION.md").write_text(report)
print(json.dumps(summary,indent=2))
sys.exit(result.returncode)
