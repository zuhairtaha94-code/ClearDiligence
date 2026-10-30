"""Optional corporate database enrichment; licensed services never silently fall back to AI."""
from hashlib import sha256
import json
import os
from urllib.parse import urlencode, urlparse

import httpx

from .models import DatabaseCandidate, DatabaseRun, ManualTask, Source
from .research import public_url, registry_targets

CATALOG = {
    "opencorporates": {"label": "OpenCorporates", "method": "API with token; manual fallback", "url": "https://opencorporates.com/", "description": "Company registration candidates across supported jurisdictions. Aggregated records require identity and official-register corroboration."},
    "tloxp": {"label": "TransUnion TLOxp", "method": "Licensed manual review", "url": "https://www.transunion.com/business-needs/investigations-tloxp", "description": "Corporate public-record and business relationship checks within your approved subscription. API onboarding is not implemented."},
    "clear": {"label": "Thomson Reuters CLEAR", "method": "Licensed manual review", "url": "https://legal.thomsonreuters.com/en/support/clear", "description": "Business public-record research within your approved subscription. CLEAR S2S exists; this MVP has no contracted API adapter."},
    "factiva": {"label": "Dow Jones Factiva", "method": "Licensed manual review", "url": "https://global.factiva.com/", "description": "Licensed adverse-media corroboration using the selected topics and date window. No automated content access."},
}
ENDPOINT = "https://api.opencorporates.com/v0.4/companies/search"
COUNTRIES = {"united states": "us", "us": "us", "usa": "us", "united kingdom": "gb", "uk": "gb", "great britain": "gb", "canada": "ca", "australia": "au"}
STATES = {"virginia": "va", "delaware": "de", "california": "ca", "new york": "ny", "illinois": "il", "texas": "tx", "district of columbia": "dc"}


def database_plan(company):
    """Network-free request preview. No credentials enter the persisted plan."""
    plans = []
    for provider in dict.fromkeys(company.research.databases):
        targets = registry_targets(company) if provider == "opencorporates" else registry_targets(company)[:1]
        for target in targets:
            jurisdiction = target.country + (" / " + target.region if target.region else "")
            request = {"q": company.name, "per_page": 5, "page": 1, "order": "score"} if provider == "opencorporates" else {"company": company.name, "country": company.country}
            code = COUNTRIES.get(target.country.casefold())
            if provider == "opencorporates" and code:
                request["country_code"] = code
                region = target.region.casefold()
                if code == "us" and (region in STATES or region in STATES.values()):
                    request["jurisdiction_code"] = "us_" + STATES.get(region, region)
                elif code == "gb":
                    request["jurisdiction_code"] = "gb"
            if provider == "factiva":
                request.update(topics=", ".join(company.research.topics), start_date=str(company.research.start_date or "Any date"), end_date=str(company.research.end_date or "Any date"))
            plans.append({"provider": provider, "jurisdiction": jurisdiction, "request": request, "routed": provider != "opencorporates" or bool(code)})
    return plans


def _record_url(value, opencorporates=False):
    if not isinstance(value, str) or not public_url(value):
        return ""
    if opencorporates and urlparse(value).hostname not in ("opencorporates.com", "www.opencorporates.com"):
        return ""
    return value


def lookup_opencorporates(a, plan, token, client=None):
    run = DatabaseRun(provider="opencorporates", method="API", status="Unavailable", jurisdiction=plan["jurisdiction"], request=plan["request"], endpoint=ENDPOINT, message="API token not configured; no API request sent. Complete the lookup manually.")
    if not plan["routed"]:
        run.status = "Routing unavailable"
        run.message = "Country filter is not mapped in this MVP; no unscoped API search was sent. Identify the provider jurisdiction manually."
        return run
    if not token:
        return run
    try:
        with httpx.Client(timeout=25, follow_redirects=False) if client is None else _Borrow(client) as session:
            response = session.get(ENDPOINT, params=run.request, headers={"X-API-TOKEN": token})
            response.raise_for_status()
            data = response.json()["results"]
        if not isinstance(data.get("companies"), list) or not isinstance(data.get("total_count"), int) or data["total_count"] < 0:
            raise ValueError("Invalid response shape")
        candidates, sources = [], []
        for wrapper in data["companies"][:5]:
            c = wrapper["company"]
            if not isinstance(c, dict) or not isinstance(c.get("name"), str) or not c["name"].strip():
                raise ValueError("Invalid company record")
            url = _record_url(c.get("opencorporates_url"), opencorporates=True)
            if not url:
                raise ValueError("Invalid record reference")
            # Store only company fields needed for this purpose, never officers/person data.
            fields = {k: c[k] for k in ("name", "company_number", "jurisdiction_code", "current_status", "registered_address_in_full", "updated_at", "registry_url", "opencorporates_url") if c.get(k) is not None}
            content = json.dumps(fields, ensure_ascii=False, indent=2)
            source = Source(title="OpenCorporates candidate: " + c["name"], url=url, content=content, source_family="OpenCorporates", content_type="Retrieved API company record (selected fields)", content_sha256=sha256(content.encode()).hexdigest())
            candidate = DatabaseCandidate(name=c["name"], company_number=c.get("company_number") or "", jurisdiction_code=c.get("jurisdiction_code") or "", current_status=c.get("current_status") or "", registered_address=c.get("registered_address_in_full") or "", record_url=url, registry_url=_record_url(c.get("registry_url")), provider_updated_at=c.get("updated_at") or "Not available", source_id=source.id)
            sources.append(source)
            candidates.append(candidate)
        if data["total_count"] < len(candidates) or (data["total_count"] and not candidates):
            raise ValueError("Inconsistent result count")
        # Commit only after the complete bounded response is validated.
        a.sources.extend(sources)
        run.candidates = candidates
        run.total_results = data["total_count"]
        run.status = "Complete"
        run.message = f"Company search completed; retained {len(candidates)} of {run.total_results} candidates (first page, maximum 5). Every candidate is a potential entity match, not a verified fact or sanctions result. Region is restricted only when a jurisdiction_code is recorded. Provider update dates may be stale."
    except httpx.HTTPStatusError as error:
        run.status = "Failed"
        run.message = f"Provider returned HTTP {error.response.status_code}; no result or clearance inferred. Check subscription entitlement and complete manually."
    except Exception:
        # Exception strings may contain credentials or provider payloads.
        run.status = "Failed"
        run.message = "Database request or response validation failed; no result inferred. Complete the lookup manually."
    return run


class _Borrow:
    def __init__(self, client): self.client = client
    def __enter__(self): return self.client
    def __exit__(self, *args): return False


def run_databases(a, client=None):
    if a.mode != "Live":
        return
    for plan in database_plan(a.company):
        provider = plan["provider"]
        if provider == "opencorporates":
            run = lookup_opencorporates(a, plan, os.getenv("OPENCORPORATES_API_TOKEN", ""), client)
        else:
            run = DatabaseRun(provider=provider, method="Manual", status="Manual required", jurisdiction=plan["jurisdiction"], request=plan["request"], endpoint=CATALOG[provider]["url"], message="Not automatically searched. An entitled analyst must perform this check in the licensed service; no API integration is configured.")
        a.database_runs.append(run)


def build_database_tasks(a):
    if a.mode != "Live":
        return []
    tasks = []
    for run in a.database_runs:
        provider = CATALOG[run.provider]
        key = sha256((a.id + "|database|" + run.id).encode()).hexdigest()[:12]
        url = "https://opencorporates.com/companies?" + urlencode({"q": a.company.name}) if run.provider == "opencorporates" else provider["url"]
        instructions = [
            "Use only an approved account and permitted corporate-diligence purpose. Open the provider starting point; authenticate yourself if needed.",
            "Search the supplied company name and supported aliases. Compare legal name, company number, jurisdiction and address; reject namesakes and distinguish branches. A name hit alone is not a confirmed identity.",
            "Record lookup date, exact search terms, identifiers, coverage limits and a permitted reference URL. Retain only necessary corporate information; do not paste full licensed dossiers into notes.",
            "Escalate material issues through the finding review and final disposition. Completing this task records the check; it does not modify automated facts or declare legal clearance.",
        ]
        if run.provider == "factiva":
            instructions.append("Apply these topics and inclusive media dates: " + json.dumps(run.request, ensure_ascii=False) + ". Distinguish allegations from findings and verify entity relevance.")
        if run.candidates:
            instructions.append("Inspect the retrieved candidates in Database coverage and corroborate against the official register. Candidate records have not been promoted to verified profile facts.")
        tasks.append(ManualTask(id="database-" + key, kind="database", provider=run.provider, title="Review " + provider["label"], jurisdiction=run.jurisdiction, registry_url=url, search_terms=[a.company.name] + list(dict.fromkeys(f.extracted_value for f in a.findings if f.field == "alias" and f.extracted_value and f.evidence_valid and f.relevance == "Supported"))[:5], reason=run.message, access_status="Manual verification required" if run.status in ("Complete", "Manual required") else "Research unavailable", instructions=instructions))
    return tasks
