"""Registry coverage, handoff integrity and human task audit contracts."""
from io import BytesIO
from pathlib import Path

import pytest
from pydantic import ValidationError
from pypdf import PdfReader
from streamlit.testing.v1 import AppTest

from cleardiligence.manual import access_barrier, build_registry_tasks, registry_tasks
from cleardiligence.models import Assessment, CompanyInput, ResearchScope, Review, RiskResult, SearchRun, Source
from cleardiligence.providers import LiveResearch
from cleardiligence.research import plan_research, registry_targets
from cleardiligence.storage import Store, review_state
from cleardiligence.report import build_pdf


def live_assessment(**scope):
    return Assessment(company=CompanyInput(name="Example Vendor, Inc.",country="United States",research=ResearchScope(registry_jurisdiction="Virginia",**scope)),mode="Live",completed=True,coverage={k:"Complete (test fixture)" for k in ("entity","sanctions","media")},risk=RiskResult(identity_confidence="Sufficient",reasons=["Controlled test fixture with complete test coverage."]))


def task_review(a,action="Completed",**kwargs):
    return Review(assessment_id=a.id,task_id=registry_tasks(a)[0].id,analyst="Test analyst",action=action,rationale="Test fixture: legal name and identifiers compared on the official registry search page.",**kwargs)


def test_additional_jurisdictions_are_separate_bounded_queries():
    a=live_assessment(additional_registry_jurisdictions=[{"country":"United Kingdom"},{"country":"United States","region":"Delaware"}])
    queries=[r for r in plan_research(a.company) if r.source_family=="registries"]
    assert [r.jurisdiction for r in queries]==["United States / Virginia","United Kingdom","United States / Delaware"]
    assert queries[1].domains==["find-and-update.company-information.service.gov.uk"]
    assert queries[2].domains==["corp.delaware.gov"]
    assert all(r.query_version=="3.0" and r.max_results==4 and r.search_depth=="advanced" for r in queries)
    assert len(build_registry_tasks(a))==3
    with pytest.raises(ValidationError): ResearchScope(additional_registry_jurisdictions=[{"country":"Canada"}]*4)


def test_duplicate_targets_and_identity_retry_respect_scope():
    a=live_assessment(additional_registry_jurisdictions=[{"country":"US","region":"virginia"}])
    assert len(registry_targets(a.company))==1
    a.company.research.sources=["doj"]
    assert plan_research(a.company,retry=True)==[]
    a.company.research.sources=["company"]
    run=plan_research(a.company,retry=True)[0]
    assert run.source_family=="company" and "Identity gap" in run.trigger


def test_quoted_boolean_style_topics_and_actual_filters_are_saved():
    a=live_assessment(topics=["fraud","material litigation"])
    run=plan_research(a.company,"media")[0]
    assert '(fraud OR "material litigation")' in run.query
    assert run.domains==["justice.gov"] and run.source_family=="doj"
    restored=Assessment.model_validate_json(a.model_copy(update={"search_runs":[run]}).model_dump_json())
    assert restored.search_runs[0].query==run.query and restored.search_runs[0].query_version=="3.0"


def test_observed_challenge_is_retained_and_not_sent_to_the_model():
    class Search:
        def search(self,*args,**kwargs):
            return [Source(title="Access denied",url="https://cis.scc.virginia.gov/",content="Verify you are human before searching this register.")]
    class Model:
        def extract(self,*args): raise AssertionError("Access interstitial must not be extracted as company evidence")
    a=live_assessment(sources=["registries"])
    LiveResearch(Search(),Model()).entity(a)
    assert a.sources and not a.findings
    assert a.search_runs[0].blocked_urls==["https://cis.scc.virginia.gov/"]
    assert build_registry_tasks(a)[0].access_status=="Access barrier observed"
    assert a.search_runs[0].status=="Partial"
    assert not access_barrier(Source(title="Company report",url="https://example.com",content="Our software includes captcha protection."))


def test_no_indexed_record_does_not_claim_a_bot_block():
    a=live_assessment()
    a.search_runs=[SearchRun(task="entity",label="Corporate registration",query="Example registry",source_family="registries",jurisdiction="United States / Virginia",status="Complete")]
    task=build_registry_tasks(a)[0]
    assert task.access_status=="No usable indexed record"
    assert task.registry_url=="https://cis.scc.virginia.gov/"
    assert "official register still needs checking" in task.reason
    a.search_runs[0].status="Failed"
    assert build_registry_tasks(a)[0].access_status=="Research unavailable"


def test_unmapped_country_and_federal_scope_are_explicit():
    a=live_assessment()
    a.company.country="Unmapped Jurisdiction"
    task=build_registry_tasks(a)[0]
    assert task.access_status=="Routing unavailable" and task.registry_url==""
    a.company.country="Canada"
    task=build_registry_tasks(a)[0]
    assert "federal corporations" in task.reason and "provincial" in task.reason


def test_manual_task_persists_and_completion_requires_a_reference(tmp_path):
    a=live_assessment()
    a.manual_tasks=build_registry_tasks(a)
    store=Store(tmp_path/"tasks.db"); store.save(a)
    assert store.get(a.id).manual_tasks[0].id==a.manual_tasks[0].id
    with pytest.raises(ValueError,match="reference URL"):
        store.record_review(task_review(a))
    store.record_review(task_review(a,reference_url="https://cis.scc.virginia.gov/"))
    state=review_state(store.get(a.id),store.reviews(a.id))
    assert not state["manual_pending"]
    assert store.get(a.id).manual_tasks==a.manual_tasks


def test_unavailable_is_pending_and_reopening_invalidates_disposition(tmp_path):
    a=live_assessment(); store=Store(tmp_path/"reopen.db"); store.save(a)
    store.record_review(task_review(a,"Unavailable"))
    with pytest.raises(ValueError,match="manual checks"):
        store.record_review(Review(assessment_id=a.id,analyst="Test analyst",action="Proceed",rationale="This test must fail while the registry task is unavailable."))
    store.record_review(task_review(a,reference_url="https://cis.scc.virginia.gov/"))
    store.record_review(Review(assessment_id=a.id,analyst="Test analyst",action="Proceed",rationale="Controlled test: all test coverage and manual work are complete."))
    assert review_state(a,store.reviews(a.id))["final"]
    store.record_review(task_review(a,"Reopened"))
    state=review_state(a,store.reviews(a.id))
    assert state["manual_pending"] and state["final"] is None


def test_task_cross_assessment_and_non_http_references_are_rejected(tmp_path):
    a,b=live_assessment(),live_assessment()
    store=Store(tmp_path/"separate.db"); store.save(a); store.save(b)
    review=task_review(a,reference_url="https://cis.scc.virginia.gov/"); review.assessment_id=b.id
    with pytest.raises(ValueError,match="does not belong"): store.record_review(review)
    with pytest.raises(ValidationError): task_review(a,reference_url="javascript:alert(1)")
    with pytest.raises(ValidationError): task_review(a,reference_url="https://user:secret@example.com")


def test_legacy_snapshot_handoff_is_stable_and_not_written_back(tmp_path):
    a=live_assessment(); store=Store(tmp_path/"legacy.db"); store.save(a)
    before=store.get(a.id).model_dump_json()
    assert registry_tasks(store.get(a.id))[0].id==registry_tasks(a)[0].id
    store.record_review(task_review(a,"Escalated"))
    assert store.get(a.id).model_dump_json()==before


def test_pdf_keeps_manual_checks_and_human_evidence_separate():
    a=live_assessment()
    review=task_review(a,reference_url="https://cis.scc.virginia.gov/")
    text="\n".join(p.extract_text() for p in PdfReader(BytesIO(build_pdf(a,[review]))).pages)
    assert "Manual registry checks" in text and "Human-entered" in text
    assert "Virginia | Completed" in text and review.reference_url in text


def test_ui_saves_a_human_registry_check_and_exposes_audit(tmp_path,monkeypatch):
    path=tmp_path/"ui.db"; monkeypatch.setenv("CLEARDILIGENCE_DB",str(path))
    a=live_assessment(); store=Store(path); store.save(a)
    app=AppTest.from_file(Path(__file__).resolve().parents[1]/"app.py",default_timeout=30).run()
    app.button(key="recent_"+a.id).click().run()
    assert not app.exception
    assert any("manual registry checks" in h.value.lower() for h in app.markdown)
    app.text_input(key="manual_analyst").set_value("Test analyst")
    app.text_input(key="manual_reference").set_value("https://cis.scc.virginia.gov/")
    app.text_area(key="manual_notes").set_value("Controlled UI test: searched the legal name and compared registry identifiers today.")
    app.checkbox(key="manual_human").check()
    next(b for b in app.button if b.label=="Save registry check").click().run()
    assert not app.exception
    assert not review_state(store.get(a.id),store.reviews(a.id))["manual_pending"]
    assert any(r.task_id and r.action=="Completed" for r in store.reviews(a.id))


def test_orchestrator_saves_manual_handoffs_and_a_branch_event():
    from cleardiligence.workflow import Orchestrator
    class Search:
        def search(self,*args,**kwargs): return []
    class Sanctions:
        def screen(self,a,aliases): a.coverage["sanctions"]="Complete (test fixture)"
    c=live_assessment(sources=["registries"]).company
    a=Orchestrator(LiveResearch(Search(),object()),Sanctions()).run(c,"Live")
    assert a.completed and a.manual_tasks and a.manual_tasks[0].search_run_ids
    assert any(e.status=="branch" and "official registry check" in e.message for e in a.events)


def test_form_previews_separate_additional_registry_query(tmp_path,monkeypatch):
    monkeypatch.setenv("CLEARDILIGENCE_DB",str(tmp_path/"preview.db"))
    app=AppTest.from_file(Path(__file__).resolve().parents[1]/"app.py",default_timeout=30).run()
    app.button(key="nav_New assessment").click().run()
    app.radio(key="research_mode").set_value("Live").run()
    next(i for i in app.text_input if i.label=="Company name *").set_value("Example Vendor")
    next(i for i in app.text_input if i.label=="Registration state / region").set_value("Virginia")
    app.multiselect(key="scope_jurisdictions").set_value(["United Kingdom"])
    next(b for b in app.button if b.label=="Preview search plan").click().run()
    assert not app.exception
    assert any("find-and-update.company-information.service.gov.uk" in c.value for c in app.code)
    assert any("scc.virginia.gov" in c.value for c in app.code)
