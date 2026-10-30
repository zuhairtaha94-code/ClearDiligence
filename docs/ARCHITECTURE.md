# Technical architecture and production roadmap

ClearDiligence is a local Python/Streamlit application with five specialized workflow components. It uses bounded orchestration and modular provider interfaces to support reliable, inspectable research.

## Components and responsibilities

| Component | Boundary |
| --- | --- |
| Entity research | Tavily runs field-specific company/registry/SEC queries and retrieves page text or excerpts; Claude or Gemini extracts typed quoted facts. One targeted retry if business/location evidence remains insufficient. |
| Sanctions screening | Python downloads and joins official SDN primary names, aliases, addresses, and spillover remarks; deterministic fuzzy matching emits possible candidates only. |
| Adverse media | Source-filtered DOJ/SEC enforcement and public-news searches with an explicit date window, quote-based extraction, allegation/finding classification, entity relevance checks. |
| Risk assessment | Versioned Python rules; no LLM score. The policy snapshot is saved with the assessment. |
| Evidence validation | Retrieved IDs, quote inclusion, extracted-value support, mode/URL checks, and conservative conflict flags; final risk recalculation follows validation. |
| Analyst review | Explicit UI submission, human actor type, append-only notes/actions, transactional Proceed gates. No review tool is supplied to the model. |

`ResearchTool` and `ScreeningTool` protocols separate providers from orchestration. `Assessment` is the shared typed state. The orchestrator accepts an event callback, enabling both CLI/test execution and real-time Streamlit progress. Model output contains evidence extraction and classification, not workflow authority.

## Why the workflow is agentic

The system decomposes research into specialized tools, maintains shared state, observes the results, and chooses follow-up work. Missing identity triggers another search; a sanctions candidate triggers additional identity verification; media namesakes can be excluded; unsupported findings are quarantined before the policy is finalized. Events record tool actions and branches without exposing private model reasoning.

This is bounded, rule-orchestrated agentic behavior. It does not claim an autonomous LLM planner or independent agents conversing with one another. The bounded design gives predictable cost, understandable failure behavior, and reproducible demos.

## Evidence and confidence

Live findings retain the complete extracted source quote. Website candidates may use the exact retrieved source URL as metadata evidence; that alone never establishes official status and the candidate remains Potential. Extracted profile values must also occur in the quote; aliases use the grounded extracted value for screening. Evidence records store the source URL, title, retrieval time, available article date, and content hash. Normalized legal names, country abbreviations, selected state/location indicators, and anchored company-domain context supplement model relevance classification. These are conservative heuristics, not authoritative identity verification. `Verified` is a provenance status, not proof that the publisher is correct. Unknown fields display Not found; ambiguous relevance remains Potential; invalid support becomes Unverified and requires review.

Potential conflicts in registration, address, or website are flagged rather than resolved by a model. The conservative comparison can overflag differently phrased descriptions. Full semantic contradiction detection and independent corroboration are outside the MVP.

## OFAC implementation

Official export base: `https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports`.

Files: `sdn.csv`, `alt.csv`, `add.csv`, `sdn_comments.csv`; joined by OFAC UID, following the [official flat-file tutorial](https://ofac.treasury.gov/sdn-list-data-formats-data-schemas/tutorial-on-the-use-of-list-related-legacy-flat-files). The parser handles OFAC's DOS EOF marker and rejects HTML, malformed rows, orphan companions, and an empty primary list. Each bounded download stores URL, SHA-256, size, retrieval time, and Last-Modified. Original list details are retained for matched records; full dataset hashes accompany the report. Files are retrieved sequentially and may not constitute an atomic publication snapshot.

Names use Unicode-to-ASCII normalization, punctuation removal, and the maximum of sequence similarity and token-sorted similarity. Company name and evidence-supported aliases are compared with primary and alternate list names. A score at or above 0.86 returns a candidate; no score confirms identity. Non-Latin-only input fails explicitly instead of producing a clean result. Mixed-script and transliteration coverage remains limited. The top 25 candidates are displayed; excess candidates change coverage to Partial and require manual follow-up. SDN-only coverage excludes ownership rules and non-SDN lists.

## Persistence and review lifecycle

SQLite uses WAL, foreign keys, parameterized SQL, and short-lived connections. Completed assessment JSON snapshots are inserted once. Review decisions are append-only events with sequence order, timestamps, a declared analyst name, finding ID, action, and rationale. Proceed validation and event insertion occur in one immediate transaction. Human resolutions do not rewrite the automated tier. A later finding review invalidates an older final disposition.

Analyst identity is self-declared. An actor-type field is a workflow guard, not authentication. A confirmed sanctions decision blocks Proceed; handling a formal reversal of a confirmed match requires a production approval process.

Confirmed workspace deletion is separate from review mutation: `Store.delete` uses one immediate transaction to delete the chosen assessment's child reviews and parent snapshot. Failure rolls back both; other assessments are untouched. The library requires per-case confirmation, clears a deleted active selection and refreshes saved/recent views. No in-app recovery, export cleanup, secure-erasure guarantee or production retention/authorization policy is implemented.

## Current limitations

No production authentication, authorization, encryption at rest, retention policy, tamper-evident audit store, durable jobs, or external callbacks. Provider requests have timeouts and bounded response sizes; SDK retries are disabled; Gemini uses ordered bounded model recovery and safe attempt logging; legacy non-Gemini adapters retain one bounded retry. A rerun/process failure during a live job can interrupt work before the final snapshot is saved. Research operates on provider-retrieved page text and snippets, not a comprehensive crawler. Evidence validation does not independently certify truth, all entity matches, or URL availability. Credentialed Gemini extraction was verified on retrieved public evidence; see the evaluation summary for the latest full live check. `LLM_PROVIDER` selects Anthropic or Gemini; auto preserves configured Anthropic or chooses Gemini if only its key is present. The Gemini model is configurable; use a model available to your account. Gemini uses a bounded HTTPX REST request to Google with header authentication, JSON-schema output, and the same local Pydantic validation/evidence gates. Blocked, truncated, and malformed responses fail explicitly. Switching models does not change sanctions screening, risk policy, or human review.

## Incremental production path

1. Move typed assessments and append-only events to PostgreSQL; add durable jobs, idempotency, cancellation, checkpoints, and per-stage retries.
2. Authenticate users and enforce analyst/compliance roles, four-eyes approval, and formal escalation/reversal policies; keep identity claims tied to authenticated actors.
3. Add authoritative registry/ownership/identifier tools, multilingual matching, broader sanctions/watchlists, publisher-quality controls, and commercial adverse media.
4. Add encrypted storage, secrets management, retention controls, provider data-processing policy, and tamper-evident audit infrastructure.
5. Calibrate thresholds and risk rules against an expert-labeled dataset; measure precision/recall, entity disambiguation, unsupported-claim rate, and analyst time.
6. Integrate procurement/vendor systems through authenticated APIs and event notifications. Reuse providers and validation for future KYC/AML workflows, with industry-specific policy and approval requirements.

## Provider references

- [OFAC Sanctions List Service](https://ofac.treasury.gov/sanctions-list-service)
- [Tavily search API](https://docs.tavily.com/documentation/api-reference/endpoint/search)
- [Gemini structured outputs](https://ai.google.dev/gemini-api/docs/generate-content/structured-output)
- [Anthropic structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)

Model selection reference: [Gemini 3.8 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash). Sampling follows [Google's Gemini 3 temperature guidance](https://ai.google.dev/gemini-api/docs/generate-content/gemini-3#temperature).

## Research scope and traceability
`CompanyInput.research` stores requested fields, source families, risk topics, search depth, result budget, registry jurisdiction, and inclusive media dates. `research.py` builds an inspectable bounded query plan. `Assessment.search_runs` retains each actual query and provider filters, source IDs, extracted-finding count, status, and safe diagnostic. Missing data, missing results, unavailable tools, and rejected output are distinct states. Date filters apply to enforcement/media only; current company identity and sanctions remain unrestricted.

Automated public retrieval is Tavily. Google query links support manual corroboration; they are not a Google API integration. Factiva requires licensed API access and currently has a manual-review handoff only. SEC is a filing/enforcement source; DOJ is an enforcement source; neither replaces the appropriate corporate registry.

## Registry handoff and query-audit extension
`ResearchScope.additional_registry_jurisdictions` supports up to three additional country/region pairs. Versioned query templates emit separate registry SearchRuns; structured API filters and result postfilters enforce domains/dates. Boolean-style strings guide retrieval without claiming strict provider execution. Identity retries respect source-family selection. No direct registry APIs or non-US watchlists were added.

`manual.py` creates one required registry task per scoped jurisdiction. It records a reason, routing/access status, official starting point, legal-name/grounded-alias terms, linked query IDs and instructions. Only observed interstitial text produces an access-barrier flag; missing results produce a different state. New snapshots persist `manual_tasks`; old snapshots derive stable task IDs without database rewrites.

`Review.task_id` and `reference_url` extend the existing append-only event stream. Completed tasks require a valid http(s) reference; task/finding targets are exclusive and cross-assessment references are rejected. Unavailable, Escalated and Reopened remain pending. Required pending tasks block Proceed in the same transaction as disposition insertion; task updates invalidate older dispositions. The LLM receives no review mutation tool. Original risk and coverage remain machine snapshots, even after human task completion. Reference URLs are analyst attestations; the application does not fetch them or certify their content.

The Research coverage tab exports a JSON search audit containing scope, exact queries, version/trigger/settings, source references, task definitions and human task events. Reports include manual checks and human review outcomes. Registry route mappings are bounded and explicit; Canadian provincial registries and unmapped countries require separate routing.

## Live research quality correction
Company-page follow-up is conditional and bounded: `company_page_targets` selects the supplied public URL plus observed same-domain links; `TavilySearch.extract` preserves selected page text and per-URL failures. Distinct leadership/ownership queries improve field focus. SearchRun stores retrieval method/status, requested URLs, extraction status, actual model, rejected count and recovery notes.

Validation compares mechanically rendered Markdown text, preserving substantive words/order/negation. General branch-office differences do not trigger identity conflicts; explicit registered-office comparisons retain review flags. Website comparison uses canonical domains instead of URL paths. Supported aliases help recognize linked pages only after the company domain has grounded identity context.

Core identity coverage uses supported business/location evidence and actual tool outcomes. A rejected optional profile proposal remains quarantined; it does not erase accepted core facts. Transport/model failures, access barriers and material unsupported findings remain meaningful coverage/risk restrictions. Human registry tasks and original snapshot immutability remain unchanged.

Gemini recovery is opt-in through GEMINI_FALLBACK_MODEL. One recovery attempt is permitted per failed extraction, using the configured fallback when available or retrying the same provider once otherwise. Recovery is logged; a successfully selected fallback remains active within that assessment. Persistent service/quota/auth/connection errors stop repeated model calls while retaining public evidence for human review.

## Optional database enrichment
`databases.py` owns a credential-free catalog/request planner, a bounded OpenCorporates adapter and licensed task builders. `ResearchScope.databases` is opt-in. `DatabaseRun` stores method/status/parameters and typed `DatabaseCandidate` records; accepted API corporate excerpts become `Source` records. Candidates never become verified profile findings automatically or alter sanctions matches. OpenCorporates uses header authentication; no token enters persisted parameters. Missing credentials, unsupported country routing and provider failures become explicit handoffs.

The orchestrator runs selected enrichment during entity research and creates required manual tasks before completing the immutable assessment. Existing append-only `Review` events close/reopen registry and database tasks; unresolved checks block Proceed. No provider has review-write access. Existing SQLite JSON snapshots accept new optional fields without migration and remain immutable. `briefing.py` produces a deterministic issue register shared by PDF and analyst UI. Licensed provider API adapters remain future work pending access/specification; no mock production endpoints exist.

## Gemini route recovery and readable reporting
`recovery.py` controls configured model order, one retry where spare budget permits, per-route transient cooldown and fixed five-request/90-second scheduling budgets. It reserves requests for remaining models, reuses a successful route and audits typed `ModelAttempt` records on `SearchRun`. Authentication may use an explicitly configured backup credential; quota does not rotate credentials. Google invalid-key reason codes are recognized from a bounded error body, without persisting it. Safety blocks/invalid structured output stop that extraction; the evidence gate still applies after every success. Legacy non-Gemini retry behavior is unchanged.

`presentation.py` derives plain-language interpretation and research-area cards from stored facts and human events, preserving the original tier and uncertainty. `interactive_report.py` exports escaped, read-only HTML with native details, filtering, source anchors and a hashed-script content-security policy; it makes no external requests except user-opened source links. ReportLab summary PDFs share the interpretation, larger type and concise references; detailed raw sources and query audit remain in HTML/app/JSON. Existing snapshots deserialize optional attempt fields without migration.
