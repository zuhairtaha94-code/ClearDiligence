"""Synthetic, reproducible scenarios. No real companies or news are represented."""
from .models import Assessment, CompanyInput, Finding, Source, Verification

SCENARIOS = {
    "low": {"name": "Cedarline Facilities Group", "country": "United States", "label": "01 · Routine vendor", "subtitle": "Low risk · complete preliminary evidence"},
    "media": {"name": "Meridian Campus Builders", "country": "United States", "label": "02 · Adverse media", "subtitle": "Moderate risk · allegation requiring follow-up"},
    "sanctions": {"name": "Atlas Infrastructure Partners", "country": "United States", "label": "03 · Sanctions name match", "subtitle": "High risk · identity ambiguity and human review"},
}


def company_for(key: str) -> CompanyInput:
    info = SCENARIOS[key]
    return CompanyInput(name=info["name"], country=info["country"], industry="Facilities & construction", purpose="Contractor evaluation")


def source(a: Assessment, slug: str, title: str, content: str, date="2026-09-12") -> Source:
    s = Source(id=f"demo-{slug}", title=f"[SYNTHETIC] {title}", url=f"demo://{a.scenario}/{slug}", content=content, synthetic=True, kind="fixture", published_date=date)
    a.sources.append(s)
    return s


def fact(a, s, field, quote, **kwargs):
    f = Finding(category="profile", field=field, claim=quote, excerpt=quote, source_ids=[s.id], verification=Verification.VERIFIED, relevance="Supported", relevance_reason="Synthetic fixture explicitly identifies the target company.", **kwargs)
    a.findings.append(f)
    return f


class DemoResearch:
    def entity(self, a: Assessment, retry=False):
        if retry:
            a.gaps.append("Independent beneficial ownership verification was not performed.")
            return
        name = a.company.name
        text = f"{name} is a United States facilities and construction contractor. Registered office: Richmond, Virginia, United States. Registration: DEMO-4821. Leadership: Jordan Ellis, Managing Director."
        s = source(a, "profile", "Company profile and fictional registration", text)
        fact(a, s, "business", f"{name} is a United States facilities and construction contractor.")
        fact(a, s, "location", "Registered office: Richmond, Virginia, United States.")
        fact(a, s, "registration", "Registration: DEMO-4821.")
        fact(a, s, "leadership", "Leadership: Jordan Ellis, Managing Director.")
        a.coverage["entity"] = "Complete (synthetic)"
        a.gaps.append("Beneficial ownership and contractor licensing have not been independently verified.")

    def identity(self, a: Assessment):
        s = source(a, "identity-check", "Supplementary identity comparison", "Target: Atlas Infrastructure Partners, Richmond, United States, DEMO-4821. Listed namesake: Atlas Infrastructure Partners, Dubai, United Arab Emirates, DEMO-X901. Different jurisdictions and registration identifiers suggest a namesake; ownership links remain unresolved.")
        a.findings.append(Finding(category="sanctions", field="identity_comparison", claim=s.content, excerpt=s.content, source_ids=[s.id], verification=Verification.POTENTIAL, relevance="Unresolved", relevance_reason="Different jurisdiction and identifier reduce match confidence; ownership links require analyst review.", nature="List record", requires_review=True))
        a.gaps.append("Confirm that the vendor has no ownership or control link to the synthetic listed namesake.")

    def media(self, a: Assessment):
        if a.scenario == "media":
            quote = "A civil complaint alleges that Meridian Campus Builders overstated subcontractor payments on a United States campus project. The allegations have not been adjudicated. The contractor denies wrongdoing."
            s = source(a, "media", "Fictional Project Ledger: payment dispute", quote, "2026-08-21")
            a.findings.append(Finding(category="adverse_media", claim=quote, source_ids=[s.id], excerpt=quote, verification=Verification.VERIFIED, relevance="Supported", relevance_reason="Fixture identifies company, jurisdiction, and campus construction activity.", nature="Allegation", material=True, requires_review=True))
            a.gaps.append("Obtain the current case status and the contractor's response to the synthetic complaint.")
        elif a.scenario == "low":
            s = source(a, "namesake", "Fictional namesake article excluded", "Cedarline Retail LLC in Canada, a retail company unrelated to Cedarline Facilities Group, faces a supplier dispute.")
            a.findings.append(Finding(category="adverse_media", claim=s.content, source_ids=[s.id], excerpt=s.content, verification=Verification.POTENTIAL, relevance="Different entity", relevance_reason="Different legal name, country, and industry; excluded from risk rules.", nature="Allegation"))
        a.coverage["media"] = "Complete (synthetic)"


class DemoSanctions:
    def screen(self, a: Assessment, aliases: list[str]):
        text = "Synthetic screening dataset: 3 fictional entity records; primary names and aliases checked. This is not OFAC data."
        s = source(a, "screening", "Synthetic screening coverage", text)
        a.screening_metadata = {"provider": "Synthetic fixtures (not OFAC)", "records": 3, "names_screened": [a.company.name, *aliases], "retrieved_at": s.retrieved_at, "coverage": "Fictional records only"}
        if a.scenario == "sanctions":
            quote = "DEMO-X901 | Atlas Infrastructure Partners | United Arab Emirates | Synthetic program DEMO | Dubai. Name matches the target; identifying information differs."
            record = source(a, "list-record", "Fictional watchlist record DEMO-X901", quote)
            a.findings.append(Finding(category="sanctions", field="name_match", claim=quote, excerpt=quote, source_ids=[record.id], verification=Verification.POTENTIAL, relevance="Unresolved", relevance_reason="Name-only candidate; different country does not resolve ownership or identity.", nature="List record", match="possible", material=True, requires_review=True))
        a.coverage["sanctions"] = "Complete (synthetic)"
