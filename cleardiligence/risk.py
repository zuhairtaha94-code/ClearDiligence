import json
from pathlib import Path
from .models import Assessment, RiskResult, RiskTier, Verification

RULES_PATH = Path(__file__).resolve().parent.parent / "config" / "risk_rules.json"


def load_rules():
    return json.loads(RULES_PATH.read_text())


def assess_risk(a: Assessment, rules=None) -> RiskResult:
    rules = rules or load_rules()
    if rules.get("confirmed_sanctions_tier") != "High":
        raise ValueError("Confirmed sanctions matches must retain the High tier and mandatory escalation")
    r = RiskResult(policy_version=rules["version"], policy_snapshot=rules)
    valid = [f for f in a.findings if f.evidence_valid and f.relevance != "Different entity"]
    profile = [f for f in valid if f.category == "profile" and f.relevance == "Supported" and not f.validation_notes]
    identity_ok = len({f.field for f in profile}) >= rules["minimum_profile_facts"] and any(f.field == "business" for f in profile) and any(f.field == "location" for f in profile)
    r.identity_confidence = "Sufficient for preliminary screening" if identity_ok else "Insufficient"
    complete = all(a.coverage.get(k, "").startswith("Complete") for k in ("entity", "sanctions", "media"))
    candidates = [f for f in a.findings if f.category == "sanctions" and f.match != "none" and f.relevance != "Different entity"]
    media = [f for f in valid if f.category == "adverse_media" and f.material]
    if any(f.match == "confirmed" for f in candidates):
        r.tier = RiskTier(rules["confirmed_sanctions_tier"])
        r.reasons.append("Confirmed sanctions match triggers mandatory escalation under policy.")
        r.mandatory_escalation = True
        r.indicators.append("Confirmed sanctions exposure")
    elif candidates:
        r.tier = RiskTier(rules["possible_sanctions_tier"])
        r.reasons.append("Unresolved sanctions candidate requires review. This is a possible match, not a confirmed designation of the target.")
        r.mandatory_escalation = True
        r.indicators.append("Possible sanctions name match")
    elif any(f.nature in ("Regulatory finding", "Judicial finding") and f.relevance == "Supported" and f.verification == Verification.VERIFIED for f in media):
        r.tier = RiskTier(rules["supported_finding_tier"])
        r.reasons.append("A source-supported regulatory or judicial finding requires enhanced review.")
        r.indicators.append("Material regulatory or judicial finding")
    elif media:
        r.tier = RiskTier(rules["allegation_tier"])
        r.reasons.append("Potentially relevant adverse media warrants follow-up; allegations are not established misconduct.")
        r.indicators.append("Adverse media requiring review")
    elif not identity_ok or not complete or any(f.material and not f.evidence_valid for f in a.findings):
        r.tier = RiskTier.INSUFFICIENT
        r.reasons.append("Identity, screening coverage, or material evidence is insufficient for a reliable preliminary tier.")
    else:
        r.tier = RiskTier.LOW
        r.reasons.append("No material indicators identified within the completed preliminary checks and available evidence.")
    if not identity_ok:
        r.reasons.append("Entity identity is insufficiently established; missing data is not evidence of misconduct.")
        r.actions.append("Obtain the legal name, registration number, and registered address.")
    if not complete:
        r.reasons.append("One or more research integrations are partial or unavailable; screening is incomplete.")
        r.actions.append("Complete unavailable screening before a procurement decision.")
    if r.mandatory_escalation:
        r.actions.append("Hold onboarding and refer the match to an authorized compliance analyst.")
        r.actions.append("Compare registration identifiers, addresses, aliases, and ownership before resolving the candidate.")
    if media:
        r.actions.append("Review primary case or regulatory records, dates, and the company's response.")
    if a.gaps:
        r.actions.append("Resolve material information gaps and document the evidence obtained.")
    r.actions.append("Record an analyst disposition and rationale; automated screening is not legal or regulatory clearance.")
    return r
