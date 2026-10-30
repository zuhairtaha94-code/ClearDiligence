"""Actionable registry handoffs, without inferring that missing search results mean a block."""
from hashlib import sha256
import re

from .models import ManualTask
from .research import registry_targets, registry_domains


def access_barrier(source):
    # Only an observed interstitial in retrieved text is an access-barrier signal.
    title = source.title.casefold()
    prefix = source.content[:1200].strip().casefold()
    patterns = [r"^access denied\b", r"^403 forbidden\b", r"^verify (?:that )?you are (?:a )?human\b", r"^just a moment[.!]", r"^please (?:complete|solve) the captcha\b", r"^robot check\b"]
    if any(re.search(pattern, title) or re.search(pattern, prefix) for pattern in patterns):
        return "Retrieved page contains an access challenge; an analyst must open the registry."
    return ""


def registry_tasks(a):
    if a.manual_tasks:
        return a.manual_tasks
    from .databases import build_database_tasks
    return build_registry_tasks(a) + build_database_tasks(a)


def build_registry_tasks(a):
    if a.mode != "Live" or "registries" not in a.company.research.sources or "registration" not in a.company.research.fields:
        return []
    tasks = []
    for index, target in enumerate(registry_targets(a.company)):
        label = target.country + (" / " + target.region if target.region else "")
        runs = [r for r in a.search_runs if (r.source_family == "registries" or r.label.startswith("Corporate registration")) and (r.jurisdiction == label or (index == 0 and not r.jurisdiction))]
        domains = registry_domains(target)
        url = "https://" + domains[0] + "/" if domains else ""
        if target.country.casefold() in ("us", "usa", "united states") and target.region.casefold() == "virginia":
            url = "https://cis.scc.virginia.gov/"
        elif target.country.casefold() in ("us", "usa", "united states") and target.region.casefold() == "california":
            url = "https://bizfileonline.sos.ca.gov/"
        elif target.country.casefold() in ("us", "usa", "united states") and target.region.casefold() == "delaware":
            url = "https://icis.corp.delaware.gov/eCorp/EntitySearch/NameSearch.aspx"
        elif target.country.casefold() == "canada":
            url = "https://ised-isde.canada.ca/site/corporations-canada/en"
        elif target.country.casefold() == "australia":
            url = "https://www.asic.gov.au/online-services/search-asic-registers/company-and-organisation-registers"
        status = "Manual verification required"
        reason = "Public-web searches do not establish that the official registry was searched directly. Independently confirm the record."
        if any(r.access_notes for r in runs):
            status = "Access barrier observed"
            reason = "An access challenge was observed in retrieved registry text. Complete the lookup in a browser; do not infer a negative result."
        elif any(r.status in ("Failed", "Partial") for r in runs):
            status = "Research unavailable"
            reason = "Registry search or evidence extraction was incomplete. This is a research limitation, not proof that the registry blocks bots."
        elif not runs or not any(f.evidence_valid and f.field == "registration" and any(sid in r.source_ids for sid in f.source_ids) for r in runs for f in a.findings):
            status = "No usable indexed record"
            reason = "No evidence-supported registration detail was obtained from the scoped public searches. The official register still needs checking."
        if not url:
            status = "Routing unavailable"
            reason += " No official registry link is mapped for this country/region; identify the competent authority first."
        if target.country.casefold() == "canada":
            reason += " This route covers federal corporations; provincial or territorial registration may require a separate registry."
        if target.country.casefold() == "australia":
            reason += " Distinguish an ABN/business-name listing from an ASIC company registration."
        terms = [a.company.name]
        for finding in a.findings:
            if finding.field == "alias" and finding.evidence_valid and finding.relevance == "Supported" and finding.extracted_value and finding.extracted_value not in terms:
                terms.append(finding.extracted_value)
        key = sha256((a.id + "|registry|" + label.casefold()).encode()).hexdigest()[:12]
        tasks.append(ManualTask(id="registry-" + key, title="Verify official registration", jurisdiction=label, registry_url=url, search_terms=terms[:6], access_status=status, reason=reason, search_run_ids=[r.id for r in runs], instructions=[
            "Search the legal name and supported aliases in the official register. Log in or complete a challenge yourself if required; do not bypass access controls.",
            "Compare the registration number, entity type, current status, registered office, and jurisdiction with the target company. Separate branch registrations and namesakes.",
            "Record the lookup date, search terms, result identifiers and an official record or search-page URL. If no match is returned, record that result and any limits.",
            "Use Completed only for a finished, documented check. Use Unavailable or Escalated for a blocked lookup; a missing result does not establish misconduct."
        ]))
    return tasks
