"""Explicit bounded search plans, provenance, and safe integration diagnostics."""
from datetime import datetime, date, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode, urlparse
import re

import httpx
from pydantic import ValidationError
from .models import SearchRun, RegistryJurisdiction

PROFILE_FIELDS = {"business": "Business activity", "location": "Reported location", "industry": "Industry", "registration": "Registration", "leadership": "Leadership", "ownership": "Ownership", "alias": "Known aliases", "website": "Website"}
SOURCE_FAMILIES = {"company": "Company websites", "registries": "Public registries", "sec": "SEC filings & enforcement", "doj": "DOJ enforcement", "media": "News & public web"}
TOPICS = ["fraud", "corruption", "regulatory enforcement", "sanctions", "financial misconduct", "material litigation"]
REGISTRIES = {"united kingdom": ["find-and-update.company-information.service.gov.uk"], "uk": ["find-and-update.company-information.service.gov.uk"], "canada": ["ised-isde.canada.ca"], "australia": ["abr.business.gov.au", "asic.gov.au"], "united states": [], "us": [], "usa": []}
US_REGISTRIES = {"virginia": ["scc.virginia.gov"], "delaware": ["corp.delaware.gov"], "california": ["sos.ca.gov"], "new york": ["dos.ny.gov"], "illinois": ["ilsos.gov"], "texas": ["sos.state.tx.us"], "district of columbia": ["dlcp.dc.gov"]}
COUNTRY_TERMS = {"united states": ["united states", "usa", "u.s.", "us", "california", "virginia", "illinois", "new york", "texas", "massachusetts", "district of columbia", "washington, dc"], "us": ["united states", "usa", "u.s.", "us"], "usa": ["united states", "usa", "u.s.", "us"], "united kingdom": ["united kingdom", "uk", "england", "scotland", "wales", "northern ireland"]}


class ProviderError(ValueError):
    def __init__(self, provider, operation, reason):
        self.provider, self.operation, self.reason = provider, operation, reason
        super().__init__(f"{provider} {operation}: {reason}")


def safe_diagnostic(error):
    if isinstance(error, ProviderError):
        return str(error)
    if isinstance(error, httpx.HTTPStatusError):
        code = error.response.status_code
        host = error.request.url.host
        provider = "Gemini" if "googleapis.com" in host else "Tavily" if "tavily.com" in host else "Research provider"
        reasons = {400: "request rejected; verify model/schema compatibility", 401: "API key rejected", 403: "access denied; verify account permissions", 404: "configured model or endpoint is unavailable", 429: "quota or rate limit reached"}
        return f"{provider} HTTP {code}: {reasons.get(code, 'provider request failed')}"
    if isinstance(error, (httpx.TimeoutException, TimeoutError)):
        return "Research request timed out; retry or reduce search depth"
    if isinstance(error, ValidationError):
        return "Model returned invalid structured output; no unsupported profile facts were accepted"
    return "Research integration failed; check configured credentials, model access, and provider availability"


def google_link(query, start="", end=""):
    if start: query += " after:" + start
    if end: query += " before:" + (date.fromisoformat(end)+timedelta(days=1)).isoformat()
    return "https://www.google.com/search?" + urlencode({"q": query})


def registry_targets(company):
    targets = [RegistryJurisdiction(country=company.country, region=company.research.registry_jurisdiction), *company.research.additional_registry_jurisdictions]
    unique = {}
    for target in targets:
        country_key = {"us":"united states", "usa":"united states", "uk":"united kingdom"}.get(target.country.strip().casefold(), target.country.strip().casefold())
        key = (country_key, target.region.strip().casefold())
        unique.setdefault(key, target)
    return list(unique.values())


def registry_domains(target):
    if target.country.casefold() in ("united states", "us", "usa"):
        return US_REGISTRIES.get(target.region.strip().casefold(), [])
    return REGISTRIES.get(target.country.casefold(), [])


def plan_research(company, task="entity", retry=False):
    scope = company.research
    name = '"' + company.name.replace('"', '') + '"'
    domain = urlparse(company.website).hostname if company.website else ""
    fields = set(scope.fields) | {"business", "location"}
    specs = []
    def add(label, query, group, target_fields=None, domains=None, topic="general", jurisdiction=""):
        dated = task == "media"
        start = scope.start_date.isoformat() if dated and scope.start_date else ""
        end = scope.end_date.isoformat() if dated and scope.end_date else ""
        if domains:
            query += " (" + " OR ".join("site:" + d for d in domains) + ")"
        specs.append(SearchRun(task=task, label=label, query=query, fields=target_fields or [], domains=domains or [], topic=topic, start_date=start, end_date=end, google_url=google_link(query, start, end), source_family=group, jurisdiction=jurisdiction, trigger="Identity gap or sanctions candidate" if retry or task=="identity" else "Initial scope", query_version="3.0", search_depth=scope.depth, max_results=scope.max_results))
    if task in ("entity", "identity"):
        if retry or task == "identity":
            if "registries" in scope.sources:
                target = registry_targets(company)[0]
                add("Identity follow-up", f"{name} {company.country} {scope.registry_jurisdiction} registered address legal name registration number", "registries", ["business", "location", "registration", "alias"], registry_domains(target), jurisdiction=target.country + (" / " + target.region if target.region else ""))
            elif "company" in scope.sources:
                add("Identity follow-up", f"{name} {company.country} headquarters address legal name contact", "company", ["business", "location", "alias"], [domain] if domain else [])
            elif "sec" in scope.sources:
                add("Identity follow-up", f"{name} {company.country} company address legal name", "sec", ["business", "location", "registration"], ["sec.gov"])
            elif "media" in scope.sources:
                add("Identity follow-up", f"{name} {company.country} company headquarters address", "media", ["business", "location"])
            return specs
        if "company" in scope.sources:
            add("Company overview & location", f"{name} official about services headquarters contact address", "company", ["business", "location", "industry", "website"], [domain] if domain else [])
            if "leadership" in fields:
                add("Leadership", f"{name} leadership executives management team directors", "company", ["leadership", "alias"], [domain] if domain else [])
            if "ownership" in fields:
                add("Ownership & corporate relationships", f"{name} ownership parent shareholders acquisition merger", "company", ["ownership", "alias"], [domain] if domain else [])
        if "registries" in scope.sources and "registration" in fields:
            for index, target in enumerate(registry_targets(company)):
                domains = registry_domains(target)
                government_hint = " site:.gov" if not domains and target.country.casefold() in ("united states", "us", "usa") else ""
                jurisdiction = target.country + (" / " + target.region if target.region else "")
                label = "Corporate registration" + (" · " + jurisdiction if index else "")
                add(label, f"{name} {target.country} {target.region} company registration business registry legal entity{government_hint}", "registries", ["registration", "location", "alias"], domains, jurisdiction=jurisdiction)
        if "sec" in scope.sources:
            add("SEC company filings", f"{name} annual report 10-K DEF 14A company business directors ownership", "sec", ["business", "location", "registration", "leadership", "ownership"], ["sec.gov"])
        if not specs and "media" in scope.sources:
            add("Public entity identity", f"{name} {company.country} company business headquarters address", "media", ["business", "location"])
    else:
        keywords = " OR ".join('"' + term + '"' if " " in term else term for term in scope.topics)
        if "doj" in scope.sources:
            add("DOJ enforcement", f"{name} ({keywords})", "doj", ["media"], ["justice.gov"])
        if "sec" in scope.sources:
            add("SEC enforcement", f"{name} litigation enforcement fraud settlement", "sec", ["media"], ["sec.gov"])
        if "media" in scope.sources:
            add("Adverse media", f"{name} {company.country} ({keywords})", "media", ["media"], topic="news")
    return specs


def parsed_publication_date(text):
    if not text or text == "Not available": return None
    try: return datetime.fromisoformat(text[:10]).date()
    except (ValueError, TypeError):
        try: return parsedate_to_datetime(text).date()
        except (ValueError, TypeError, OverflowError): return None


def date_scope(source, run):
    if not run.start_date and not run.end_date: return "Not restricted"
    published = parsed_publication_date(source.published_date)
    if not published: return "Undated, manual review"
    stamp = published.isoformat()
    return "Outside window" if (run.start_date and stamp < run.start_date) or (run.end_date and stamp > run.end_date) else "Within window"


def name_present(name, text):
    def key(value):
        value = value.casefold().replace("&", " and ")
        return " ".join(re.findall(r"[a-z0-9]+", value))
    target = key(name)
    target = re.sub(r" (incorporated|inc|llc|ltd|limited|corporation|corp)$", "", target)
    return bool(target and re.search(r"(?<!\w)" + re.escape(target) + r"(?!\w)", key(text)))


def jurisdiction_present(country, text):
    text = text.casefold()
    country = {"us":"united states", "usa":"united states", "uk":"united kingdom"}.get(country.casefold(), country)
    return any(re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text) for term in COUNTRY_TERMS.get(country.casefold(), [country.casefold()]))


def canonical_host(url):
    return (urlparse(url).hostname or "").casefold().removeprefix("www.")


def public_url(url):
    import ipaddress
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if parsed.scheme not in ("http", "https") or not host or parsed.username or parsed.password:
        return False
    if host == "localhost" or host.endswith((".local", ".localhost")):
        return False
    try: return ipaddress.ip_address(host).is_global
    except ValueError: return "." in host


def company_page_targets(a, missing, limit=4):
    """Only read the supplied company URL and links actually retrieved on that domain."""
    website = a.company.website
    if not website or not public_url(website): return []
    from urllib.parse import urljoin, urldefrag
    host = canonical_host(website)
    keywords = {"leadership": ("leadership", "team", "executive", "people"), "ownership": ("ownership", "shareholder", "stockholder", "parent", "investor", "acqui", "merger", "about", "company"), "business": ("about", "service", "company"), "industry": ("about", "service"), "location": ("contact", "office", "location", "about")}
    terms = {word for field in missing for word in keywords.get(field, ())}
    candidates = {}
    for source in a.sources:
        if canonical_host(source.url) != host: continue
        own_score = sum(term in (source.title + " " + urlparse(source.url).path).casefold() for term in terms)
        if own_score: candidates[source.url] = own_score
        for match in re.finditer(r"\[([^\]]+)\]\(([^\s)]+)\)", source.content):
            label, raw_url = match.groups()
            url = urldefrag(urljoin(source.url, raw_url))[0]
            if not public_url(url) or canonical_host(url) != host: continue
            score = sum(term in (label + " " + urlparse(url).path).casefold() for term in terms)
            if score and not urlparse(url).path.lower().endswith((".jpg", ".png", ".svg", ".zip")):
                candidates[url] = max(score, candidates.get(url, 0))
    ranked = sorted(candidates, key=lambda url: (-candidates[url], len(url)))
    return list(dict.fromkeys([website, *ranked]))[:limit]
