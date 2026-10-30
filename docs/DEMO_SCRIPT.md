# Five-minute ClearDiligence demonstration

## Before the demonstration

Launch `.venv/bin/python -m streamlit run app.py`. Open localhost. Run all three synthetic scenarios once; ensure the assessment library, evidence explorer, and PDF download work. Use the demo path for the main presentation; live APIs are optional. Keep docs/EVALUATION.md open for the verified test count and output/pdf/ClearDiligence-Executive-Demo.pdf as a backup. Describe the actual deployment and coverage accurately; automated screening does not constitute clearance.

## 0:00-0:30 / The business problem

“Contractor and vendor research often means gathering fragmented records, resolving namesakes, and documenting why a decision was made. ClearDiligence automates preliminary research and screening while leaving the procurement decision with an analyst. I scoped this MVP around vendor and contractor diligence relevant to capital-project advisory work.”

Show the Overview dashboard and the explicit synthetic labels. Explain that the demo is reproducible and independent of API availability.

## 0:30-1:10 / A routine vendor

Run **Cedarline Facilities Group** from the Overview card, or **New assessment → Demo → 01 · Routine vendor**. Watch the stages. Show Low risk, source-supported identity, information gaps, and the unrelated namesake article excluded from the risk result.

“Low means no material indicators were identified within these checks. Missing ownership or licensing evidence remains a gap; it is not evidence of misconduct.”

## 1:10-1:55 / Context matters

Open **New assessment → Demo → 02 · Adverse media** and run Meridian Campus Builders. Show Moderate risk, the unadjudicated payment allegation, its date, and the evidence explorer.

“The report preserves the source's exact wording and treats allegations as allegations. The risk tier follows a visible policy; the model does not invent a score or a citation.”

## 1:55-3:25 / The strongest agentic branch

Run **03 · Sanctions name match**. Open **Workflow log** and show the branch that triggers additional identity research. Inspect the possible match and supplementary identity comparison in **Evidence explorer**.

“The name coincides, but jurisdiction and registration identifiers differ. That reduces confidence; it does not prove there is no ownership link. The system therefore keeps this as a possible match and requires human resolution.”

Open **Analyst review**. Show the unresolved queue and the Proceed restriction. As the presenter, select the sanctions candidate, enter your own name, choose **Escalated**, add “Synthetic demonstration: name collision remains unresolved; request ownership evidence and hold onboarding,” check your own review confirmation, and save. Record **Hold** with your own rationale. These are your human demonstration decisions, not model approvals.

“If additional evidence resolved the candidate, a human could record False positive with a rationale. The model cannot do that. Original automated findings remain preserved.”

## 3:25-4:00 / A decision-ready artifact

Download the PDF. Point to the executive summary, possible-match label, evidence references, gaps, and analyst Hold disposition. Show that the assessment can be reopened from **Assessment library** with notes retained.

“The output is reviewable evidence and an accountable decision history, not just a generated paragraph.”

## 4:00-4:30 / Illustrative capacity

Open **Business impact**. Defaults are 50 assessments/month, 4 manual hours, 60% estimated time saved, and $85/hour: **1,440 annual hours released** and **$122,400 equivalent labor capacity**.

“These are adjustable assumptions, not measured savings. Production evaluation would compare elapsed analyst work and error rates against a baseline.”

## 4:30-5:00 / Engineering judgment and next steps

Show the architecture diagram or explain: Streamlit → typed workflow → replaceable search/LLM/OFAC tools → evidence gate and deterministic rules → SQLite and human decisions → PDF.

“The system takes additional research actions based on what it finds and validates evidence before finalizing. I chose bounded orchestration for reliability and explainability. The automated evaluation covers core policy, evidence boundaries, integration contracts, UI interactions, persistence, and exports. Official OFAC downloads were tested with 19,457 primary records; credentialed extraction and the latest live research check are described in the evaluation notes.”

“Next I would add authoritative ownership and registry data, broader watchlists, authenticated approval roles, a durable worker queue, and an expert-labeled precision/recall evaluation.”

## Show the research scope (optional)

Open New assessment → Live. Select company fields, source families, risk topics, and media dates. Preview search plan to show company, registry, SEC, DOJ, and news queries. Explain that current company identity and sanctions are not limited by the historical media window. Open Research coverage on a completed live run to show source counts, extracted findings, and safe failure diagnostics. Google is a manual corroboration link; licensed Factiva is a manual handoff until API access is supplied.

## If asked about live mode

Live mode uses Tavily scoped search, Anthropic or Gemini structured extraction, and official OFAC CSV downloads with aliases, addresses, and extra remarks. It never substitutes demo data. OFAC name matching is candidate retrieval, not a comprehensive sanctions determination. Search coverage, missing credentials, source quality, script limitations, and open gaps are explicit. This MVP is not legal/regulatory clearance.

### Optional registry-efficiency segment (replace 30 seconds of the live section)
In New assessment > Live, show **Additional registry jurisdictions** and Preview search plan: one query per requested registry jurisdiction. Explain that quoted names/OR groups guide retrieval and structured filters enforce scope. In a live assessment, open Research coverage > Manual registry checks. Show the official starting point, copyable legal name/aliases, access/gap reason and checklist. Open Analyst review and point to the outcome form without submitting a fictitious live check. Explain: only a human with a documented reference closes a check; unavailable access remains pending, and a new task update invalidates an old final disposition. Download search audit JSON to show that the work is reusable and traceable.

## Optional database / analyst handoff extension (45 seconds)
New assessment → Live → select OpenCorporates and CLEAR → Preview search plan. Show that OpenCorporates requires a token and CLEAR is explicitly manual. This preview makes no network requests. Explain that a real run saves candidate provenance and prepares required human tasks, with supplied name/aliases, jurisdiction and reference requirements. Missing access never becomes a negative result. Open an existing assessment's Analyst review to show the decision register; download the PDF and show its executive issues, scope and evidence references. Do not claim the licensed services were searched or that an unconfirmed database candidate is the target.

## Readable reports and recovery (45-second extension)
Open the saved assessment's Summary. Explain the three research cards and that completion is not clearance. Expand the glossary or risk rationale. Download Interactive report, search a place/name, expand visible evidence and follow a citation to the retained source. Show the larger-print PDF companion. Under AI provider details, show the ordered model chain; explain that a failed model can switch without losing retrieved sources. The recorded technical smoke check recovered from actual 404 to Gemini 3.6 structured success; offline tests cover 503/429, multiple failures and exhaustion. If all routes fail, the UI reports incomplete interpretation rather than inventing answers. Human decisions remain separate and require an explicit analyst submission.
