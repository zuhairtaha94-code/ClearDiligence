import pytest
from pydantic import ValidationError
from cleardiligence.demo import company_for
from cleardiligence.models import Assessment, CompanyInput, Finding, Source, Verification, RiskTier
from cleardiligence.workflow import Orchestrator, run_demo
from cleardiligence.risk import assess_risk
from cleardiligence.validation import validate_evidence


def test_structured_roundtrip():
    a = run_demo("low")
    assert Assessment.model_validate_json(a.model_dump_json()) == a
    with pytest.raises(ValidationError):
        CompanyInput(name="", country="US")


def test_low_risk_namesake_is_excluded():
    a = run_demo("low")
    assert a.risk.tier == RiskTier.LOW
    assert any(f.relevance == "Different entity" for f in a.findings)
    assert all(f.evidence_valid for f in a.findings)


def test_allegations_are_not_findings_of_guilt():
    a = run_demo("media")
    assert a.risk.tier == RiskTier.MODERATE
    media = [f for f in a.findings if f.material]
    assert media and all(f.nature == "Allegation" and f.requires_review for f in media)


def test_possible_sanctions_branches_and_escalates():
    a = run_demo("sanctions")
    assert a.risk.tier == RiskTier.HIGH and a.risk.mandatory_escalation
    assert any(e.status == "branch" and "identity" in e.message for e in a.events)
    candidate = next(f for f in a.findings if f.match == "possible")
    assert candidate.verification == Verification.POTENTIAL
    assert not any(f.match == "confirmed" for f in a.findings)


def test_confirmed_sanctions_always_escalates():
    a = run_demo("sanctions")
    next(f for f in a.findings if f.match == "possible").match = "confirmed"
    assert assess_risk(a).mandatory_escalation


def test_material_findings_have_retrieved_citations():
    for key in ("low", "media", "sanctions"):
        a = run_demo(key)
        assert all(f.source_ids and f.evidence_valid for f in a.findings if f.material)


def test_model_cannot_invent_details_or_citations():
    a = run_demo("low")
    s = a.sources[0]
    f = Finding(category="profile", field="ownership", claim="Owned by Imaginary Holdings", excerpt=s.content, source_ids=[s.id], verification=Verification.VERIFIED)
    a.findings.append(f)
    validate_evidence(a)
    assert not f.evidence_valid and f.verification == Verification.UNVERIFIED
    f.source_ids = ["hallucinated-source"]
    validate_evidence(a)
    assert not f.evidence_valid


def test_missing_information_is_uncertainty_and_retries():
    class Unavailable:
        def entity(self, a, retry=False):
            raise RuntimeError("secret provider error")
        def screen(self, a, aliases):
            raise RuntimeError("secret provider error")
        def media(self, a):
            raise RuntimeError("secret provider error")
    a = Orchestrator(Unavailable(), Unavailable()).run(CompanyInput(name="Unknown Vendor", country="United States"), "Live")
    assert a.risk.tier == RiskTier.INSUFFICIENT
    assert any(e.status == "branch" for e in a.events)
    assert "secret" not in a.model_dump_json()
    assert not a.risk.indicators


def test_synthetic_evidence_cannot_enter_live_mode():
    a = run_demo("low")
    a.mode = "Live"
    validate_evidence(a)
    assert not any(f.evidence_valid for f in a.findings)


def test_demo_input_cannot_be_replaced_with_real_company():
    with pytest.raises(ValueError):
        Orchestrator(None, None).run(CompanyInput(name="Real Company", country="US"), "Demo", "low")


def test_profile_conflicts_trigger_review():
    a = run_demo("low")
    s = Source(title="Conflicting fictional registration", url="demo://conflict", content="Registration: DEMO-9999.", synthetic=True, kind="fixture")
    a.sources.append(s)
    a.findings.append(Finding(category="profile", field="registration", claim=s.content, excerpt=s.content, source_ids=[s.id], verification=Verification.VERIFIED, relevance="Supported"))
    validate_evidence(a)
    assert any("conflicting registration" in g for g in a.gaps)
    assert all(f.requires_review for f in a.findings if f.field == "registration")


def test_uncited_material_media_prevents_low_risk():
    a=run_demo("low")
    a.findings.append(Finding(category="adverse_media",claim="Unsupported allegation",material=True,nature="Allegation"))
    validate_evidence(a)
    assert assess_risk(a).tier==RiskTier.INSUFFICIENT


def test_policy_cannot_downgrade_confirmed_sanctions():
    from cleardiligence.risk import load_rules
    a=run_demo("sanctions")
    rules=load_rules()
    rules["confirmed_sanctions_tier"]="Low"
    with pytest.raises(ValueError,match="Confirmed sanctions"):
        assess_risk(a,rules)
