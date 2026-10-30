from collections.abc import Callable
from .models import Assessment, CompanyInput, Event
from .demo import DemoResearch, DemoSanctions, company_for
from .risk import assess_risk
from .validation import validate_evidence
from .research import safe_diagnostic
from .manual import build_registry_tasks
from .databases import run_databases, build_database_tasks


class Orchestrator:
    """Bounded tools and explicit branches over shared typed state, with observable events."""
    def __init__(self, research, sanctions, on_event: Callable | None = None):
        self.research = research
        self.sanctions = sanctions
        self.on_event = on_event

    def emit(self, a, stage, status, message):
        event = Event(stage=stage, status=status, message=message)
        a.events.append(event)
        if self.on_event:
            self.on_event(event)

    def attempt(self, a, stage, operation, coverage_key=None):
        try:
            operation()
            return True
        except Exception as error:
            # Provider exceptions can contain secrets or request content. Do not persist them.
            if coverage_key:
                a.coverage[coverage_key] = "Unavailable"
            gap = f"{stage}: {safe_diagnostic(error)}. Complete this check manually if it remains unavailable."
            if gap not in a.gaps:
                a.gaps.append(gap)
            self.emit(a, stage, "warning", gap)
            return False

    def run(self, company: CompanyInput, mode="Demo", scenario="") -> Assessment:
        if mode == "Demo" and company != company_for(scenario):
            raise ValueError("Synthetic scenarios must use their fictional company inputs.")
        a = Assessment(company=company, mode=mode, scenario=scenario, workflow_version="3.1")
        if hasattr(self.research, "on_update"):
            self.research.on_update = lambda stage, status, message: self.emit(a, stage, status, message)
        self.emit(a, "Entity research", "running", "Researching legal identity, business activity, and corporate transparency.")
        self.attempt(a, "Entity research", lambda: self.research.entity(a), "entity")
        validate_evidence(a)
        supported_fields = {f.field for f in a.findings if f.category == "profile" and f.evidence_valid and f.relevance == "Supported"}
        if not {"business", "location"}.issubset(supported_fields):
            self.emit(a, "Entity research", "branch", "Identity evidence is incomplete. Running a targeted registration and address search.")
            self.attempt(a, "Identity retry", lambda: self.research.entity(a, retry=True), "entity")
        if mode == "Live" and company.research.databases:
            self.emit(a, "Entity research", "branch", "Running selected corporate database tools and preparing licensed analyst handoffs.")
            self.attempt(a, "Database enrichment", lambda: run_databases(a))
        self.emit(a, "Entity research", "complete", "Entity research recorded with explicit verification status.")
        self.emit(a, "Sanctions screening", "running", "Comparing company name and evidence-supported aliases against screening records.")
        validate_evidence(a)
        aliases = [f.extracted_value for f in a.findings if f.category == "profile" and f.field == "alias" and f.extracted_value and f.evidence_valid and f.relevance == "Supported"]
        self.attempt(a, "Sanctions screening", lambda: self.sanctions.screen(a, aliases), "sanctions")
        if any(f.match == "possible" for f in a.findings):
            self.emit(a, "Sanctions screening", "branch", "Potential name match found. Triggering additional identity verification; no match is auto-confirmed.")
            self.attempt(a, "Identity verification", lambda: self.research.identity(a))
        self.emit(a, "Sanctions screening", "complete", "Screening outcomes and coverage recorded.")
        self.emit(a, "Adverse media", "running", "Searching misconduct, enforcement, sanctions, and material litigation; checking namesakes.")
        self.attempt(a, "Adverse media", lambda: self.research.media(a), "media")
        self.emit(a, "Adverse media", "complete", "Media evidence classified; allegations remain allegations.")
        self.emit(a, "Risk assessment", "running", "Applying configurable policy to current findings; final tier follows evidence validation.")
        a.risk = assess_risk(a)
        self.emit(a, "Risk assessment", "complete", "Provisional policy assessment calculated.")
        self.emit(a, "Evidence validation", "running", "Checking source references, literal excerpts, mode isolation, and conflicting identity evidence.")
        validate_evidence(a)
        a.risk = assess_risk(a)
        a.gaps = list(dict.fromkeys(a.gaps))
        a.manual_tasks = build_registry_tasks(a) + build_database_tasks(a)
        if a.manual_tasks:
            self.emit(a, "Evidence validation", "branch", f"Prepared {len(a.manual_tasks)} official registry check(s) and/or database review(s) for the analyst. Search completion is not human verification.")
        a.completed = True
        self.emit(a, "Evidence validation", "complete", f"Final tier: {a.risk.tier.value}. " + ("Mandatory human escalation required." if a.risk.mandatory_escalation else "Ready for analyst review."))
        return a


def run_demo(scenario="low", on_event=None):
    return Orchestrator(DemoResearch(), DemoSanctions(), on_event).run(company_for(scenario), "Demo", scenario)
