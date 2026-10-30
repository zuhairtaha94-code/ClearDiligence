# Database integrations and reporting design

Reviewed 17 October 2026. Provider capabilities describe public documentation; they do not establish an active subscription, entitlement, coverage guarantee or partnership.

| Service | Implemented in ClearDiligence | Access and boundaries |
| --- | --- | --- |
| OpenCorporates | Optional HTTPX company-search adapter, persisted parameters, up to five candidate records per selected registry jurisdiction, update dates, SHA-256 and human handoff | `OPENCORPORATES_API_TOKEN` required; absent token becomes explicit manual lookup. API contract is mock-tested; no credentialed live call has been verified. Aggregator results are potential entity matches, never automatically verified registration/ownership facts. |
| TransUnion TLOxp | Required licensed analyst task when selected; copied search terms, starting link, reference/notes and append-only outcomes | TransUnion advertises API/batch access. This MVP has no contracted API specification, credentials or entitlement and does not call or scrape TLOxp. The starting link is the provider product page, not an authenticated lookup. |
| Thomson Reuters CLEAR | Required licensed business-record analyst task when selected | CLEAR publishes a System-to-System API overview. No contracted adapter or account is configured. Starting link is official support, which provides sign-in. |
| Dow Jones Factiva | Required licensed adverse-media task when selected, carrying selected topics and inclusive date bounds | Analyst must use an approved account. No automated access or imported licensed dossiers. Existing general Factiva link alone is not evidence a check was completed. |
| OFAC / SEC / DOJ / official registers | Existing SDN adapter and scoped public-web sources; registry handoffs | SDN screening is direct; SEC/DOJ/registry web research remains bounded search, not comprehensive database coverage. |

## How to use
1. Under New assessment → Live → Specialist databases, select only checks required for the engagement. None is selected by default; every selection creates a required analyst task.
2. For OpenCorporates API access, obtain a token for your approved use and subscription, place it in `.env` as `OPENCORPORATES_API_TOKEN=...`, then click Reload .env. Never put secrets in `.env.example`.
3. Preview the search plan. Database request parameters are shown separately from web queries. Begin assessment; inspect Research coverage → Database coverage for status, saved request and candidate JSON.
4. Use Analyst review → Analyst work queue. Compare company identifiers, jurisdiction and address. Record the lookup date, exact terms, relevant identifiers, result/limitations and a permitted reference URL. Only a person can submit completion.
5. Unavailable, Escalated and Reopened tasks remain pending and block Proceed. Completing a check does not change automated facts or risk. If the check reveals material concerns, use Hold/Reject or escalate relevant findings and document the decision; manual licensed observations are not automatically scored or inserted into machine findings.

OpenCorporates queries use the supplied legal name, score ordering, page 1 and `per_page=5`. A country filter is mandatory in this MVP; mapped countries are US/UK/Canada/Australia. Selected mapped US regions add a jurisdiction filter; unknown regions remain country-wide and must be resolved manually. Unmapped countries receive a routing handoff without an unscoped API call. Up to three extra registry jurisdictions produce separate bounded requests. API alias expansion, pagination, officer lookup, ownership graph and automatic record-detail fetch are not implemented. Supported aliases are provided to the human task.

Requests never contain tokens in URLs or saved audit. Auth uses `X-API-TOKEN`; errors retain HTTP status only. Selected corporate fields are retained; officer/person fields are discarded. Record URLs come from the validated API response. A reference to a company record does not claim its HTML page was independently fetched. Candidate records and their provider update dates require human identity corroboration; zero results are not clearance. The original API provider response is not stored in full.

## Product research translated into MVP choices
- Vcheck describes scoped investigation tracking, alert remediation and human judgment supported by AI. Applied: an inspectable work queue, source provenance and explicit pending/resolved outcomes. Its monitoring and investigative network are not implemented here.
- Alias describes investigator-led work assisted by technology, traced findings and human verification. Applied: separate automated research and human disposition, bounded requests and deliberate escalation. ClearDiligence does not reproduce Alias tooling, access its client portal or claim equivalent coverage.
- PwC's public third-party diligence and Radar pages emphasize scoped research, risk indicators and analyst-reviewed matches. Applied: an original executive assessment, issue/action register, scope and basis, detailed findings and evidence appendices. No proprietary report template, branding or implied affiliation is used. This is integrity screening, not financial due diligence or an audit opinion.

## Production options
After access is approved: implement TLOxp/CLEAR adapters against the contracted schema and permitted use; add per-provider authorization, retention/export controls and audit/redaction. Other candidates include GLEIF LEI company identity data, direct Companies House integration, commercial sanctions/adverse media and court-record providers. Evaluate jurisdiction/subject coverage, redistribution rights, identity matching and provenance before connecting them. These are future options, not current coverage.

## Primary sources
- [OpenCorporates API company search and filters](https://api.opencorporates.com/documentation/API-Reference)
- [OpenCorporates authentication and plans](https://knowledge.opencorporates.com/knowledge-base/api-authentication-authorisation/)
- [TransUnion TLOxp investigations and API/batch access](https://www.transunion.com/business-needs/investigations-tloxp)
- [CLEAR System-to-System overview and usage restrictions](https://developerportal.thomsonreuters.com/clear-system-system)
- [CLEAR support and sign-in starting point](https://legal.thomsonreuters.com/en/support/clear)
- [Factiva](https://www.dowjones.com/professional/factiva/)
- [Vcheck platform](https://vcheckglobal.com/platform/)
- [Vcheck AI approach](https://vcheckglobal.com/blog/how-we-think-about-ai-at-vcheck/)
- [Alias services](https://www.aliasintelligence.com/our-services?service=background-due-diligence)
- [PwC third-party diligence](https://www.pwc.com/az/en/services/forensic-services/third-party-due-diligence.html)
- [PwC Radar analyst-reviewed screening](https://www.pwc.co.uk/services/forensics/insights/radar.html)

- [GLEIF public LEI API (future option)](https://www.gleif.org/en/lei-data/gleif-api)
