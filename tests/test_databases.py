"""Corporate database contracts and explicit human decision boundaries; no paid calls."""
from io import BytesIO
import json
from pathlib import Path

import httpx
import pytest
from pypdf import PdfReader
from streamlit.testing.v1 import AppTest

from cleardiligence.databases import database_plan, run_databases, build_database_tasks
from cleardiligence.briefing import decision_issues
from cleardiligence.models import Assessment, CompanyInput, ResearchScope, Review
from cleardiligence.report import build_pdf
from cleardiligence.storage import Store, review_state
from cleardiligence.workflow import run_demo, Orchestrator


def assessment(databases=None, country="United States", region="Virginia"):
    return Assessment(company=CompanyInput(name="Example Vendor Inc", country=country, research=ResearchScope(databases=databases or ["opencorporates"], registry_jurisdiction=region)), mode="Live")


def response(total=2):
    return {"results": {"total_count": total, "companies": [{"company": {"name": "Example Vendor Inc", "company_number": str(index), "jurisdiction_code": "us_va", "current_status": "Active", "opencorporates_url": f"https://opencorporates.com/companies/us_va/{index}", "registry_url": "https://cis.scc.virginia.gov/", "updated_at": "2025-01-02", "registered_address_in_full": "100 Example St", "officers": ["PRIVATE EXCLUDED TEST FIELD"]}} for index in range(total)]}}


def test_request_contract_header_auth_and_candidates_stay_unconfirmed(monkeypatch):
    monkeypatch.setenv("OPENCORPORATES_API_TOKEN", "mock-token-never-in-audit")
    seen = []
    def handler(request):
        seen.append(request)
        assert request.headers["X-API-TOKEN"] == "mock-token-never-in-audit"
        assert request.url.params["q"] == "Example Vendor Inc"
        assert request.url.params["jurisdiction_code"] == "us_va"
        assert request.url.params["per_page"] == "5"
        return httpx.Response(200, json=response())
    a = assessment()
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        run_databases(a, client)
    run = a.database_runs[0]
    assert len(seen) == 1 and run.status == "Complete" and len(run.candidates) == 2
    assert all(c.match_status == "Potential match" for c in run.candidates)
    assert not a.findings  # API candidates cannot establish the target identity or risk facts.
    assert len(a.sources) == 2 and all(s.content_sha256 for s in a.sources)
    assert "mock-token" not in a.model_dump_json() and "PRIVATE EXCLUDED" not in a.model_dump_json()


def test_missing_token_and_licensed_checks_never_call_network():
    a = assessment(["opencorporates", "tloxp", "clear", "factiva"])
    with httpx.Client(transport=httpx.MockTransport(lambda request: pytest.fail("Must not call unconfigured services"))) as client:
        run_databases(a, client)
    assert [r.status for r in a.database_runs] == ["Unavailable", "Manual required", "Manual required", "Manual required"]
    a.manual_tasks = build_database_tasks(a)
    assert len(a.manual_tasks) == 4 and len(review_state(a, [])['manual_pending']) == 4
    assert all(t.kind == "database" and t.required for t in a.manual_tasks)
    assert "start_date" in a.database_runs[-1].request


@pytest.mark.parametrize("status", [401, 403, 429, 503])
def test_http_failures_are_not_negative_results_or_secret_leaks(monkeypatch, status):
    monkeypatch.setenv("OPENCORPORATES_API_TOKEN", "SECRET-TEST-TOKEN")
    a = assessment()
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status, text="SECRET-TEST-TOKEN"))) as client:
        run_databases(a, client)
    assert a.database_runs[0].status == "Failed"
    assert a.database_runs[0].total_results is None and not a.sources
    assert "SECRET" not in a.model_dump_json()
    assert build_database_tasks(a)[0].access_status == "Research unavailable"


@pytest.mark.parametrize("payload", [{"results": {}}, {"results": {"companies": [], "total_count": 1}}, {"results": {"companies": [{"company": {"name": "Example", "opencorporates_url": "https://evil.example/record"}}], "total_count": 1}}])
def test_malformed_or_untrusted_response_is_not_marked_complete(monkeypatch, payload):
    monkeypatch.setenv("OPENCORPORATES_API_TOKEN", "test")
    a = assessment()
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))) as client:
        run_databases(a, client)
    assert a.database_runs[0].status == "Failed" and not a.sources


def test_empty_result_is_coverage_not_clearance(monkeypatch):
    monkeypatch.setenv("OPENCORPORATES_API_TOKEN", "test")
    a = assessment()
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=response(0)))) as client:
        run_databases(a, client)
    assert a.database_runs[0].status == "Complete" and a.database_runs[0].total_results == 0
    assert build_database_tasks(a)[0].required and not a.findings


def test_bounded_queries_and_explicit_jurisdiction_routing():
    a = assessment()
    a.company.research.additional_registry_jurisdictions = [{"country": "United Kingdom"}, {"country": "Canada"}, {"country": "Australia"}]
    plan = database_plan(a.company)
    assert len(plan) == 4 and plan[1]["request"]["jurisdiction_code"] == "gb"
    assert plan[2]["request"]["country_code"] == "ca"
    assert all(p["request"]["per_page"] == 5 for p in plan)
    unmapped = assessment(country="Unmapped jurisdiction", region="")
    assert not database_plan(unmapped.company)[0]["routed"]
    run_databases(unmapped)
    assert unmapped.database_runs[0].status == "Routing unavailable"


def test_licensed_tasks_block_proceed_require_reference_and_preserve_snapshot(tmp_path):
    # Reuse a complete synthetic fixture as a controlled Live-shaped record, no network or real company.
    a = run_demo("low")
    a.mode = "Live"
    a.company.research.databases = ["clear"]
    run_databases(a)
    a.manual_tasks = build_database_tasks(a)
    store = Store(tmp_path / "db.sqlite")
    store.save(a)
    def review(action, **kwargs):
        return Review(assessment_id=a.id, analyst="Human analyst", action=action, rationale="Controlled test: completed permitted business record checks.", **kwargs)
    with pytest.raises(ValueError, match="Resolve"):
        store.record_review(review("Proceed"))
    task_id = a.manual_tasks[0].id
    with pytest.raises(ValueError, match="reference"):
        store.record_review(review("Completed", task_id=task_id))
    store.record_review(review("Unavailable", task_id=task_id))
    assert review_state(a, store.reviews(a.id))["manual_pending"]
    store.record_review(review("Completed", task_id=task_id, reference_url="https://example.com/permitted-reference"))
    assert not review_state(a, store.reviews(a.id))["manual_pending"]
    assert store.get(a.id) == a
    assert not any(row["issue"] == "Thomson Reuters CLEAR" for row in decision_issues(a, store.reviews(a.id)))


def test_orchestrator_executes_selection_and_demo_isolation():
    class Research:
        def entity(self, a, retry=False): a.coverage["entity"] = "Partial"
        def media(self, a): a.coverage["media"] = "Complete (test)"
    class Sanctions:
        def screen(self, a, aliases): a.coverage["sanctions"] = "Complete (test)"
    a = Orchestrator(Research(), Sanctions()).run(assessment(["clear"]).company, "Live")
    assert a.database_runs[0].provider == "clear" and any(t.provider == "clear" for t in a.manual_tasks)
    assert any("database" in event.message for event in a.events)
    demo = run_demo("low")
    demo.company.research.databases = ["clear"]
    run_databases(demo)
    assert not demo.database_runs and not build_database_tasks(demo)


def test_database_pdf_and_real_ui_preview_and_review(tmp_path, monkeypatch):
    monkeypatch.setenv("CLEARDILIGENCE_DB", str(tmp_path / "ui.sqlite"))
    a = assessment(["clear", "factiva"])
    run_databases(a)
    a.manual_tasks = build_database_tasks(a)
    a.completed = True
    Store().save(a)
    text = "\n".join(p.extract_text() for p in PdfReader(BytesIO(build_pdf(a))).pages)
    for expected in ("Key issues and decision requirements", "Scope and basis of work", "Specialist database coverage", "Thomson Reuters CLEAR", "Not automatically searched", "Analyst work queue", "Pending"):
        assert expected in text
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30)
    app.session_state["current_id"] = a.id
    app.run()
    assert not app.exception
    app.text_input(key="manual_analyst").set_value("Human analyst")
    app.text_input(key="manual_reference").set_value("https://example.com/permitted-record")
    app.text_area(key="manual_notes").set_value("Controlled fixture: checked business identifiers and recorded permitted result.")
    app.checkbox(key="manual_human").check()
    next(b for b in app.button if b.label == "Save check").click().run()
    assert not app.exception and Store().reviews(a.id)[0].action == "Completed"
    app.button(key="nav_New assessment").click().run()
    app.radio(key="research_mode").set_value("Live").run()
    next(i for i in app.text_input if i.label == "Company name *").set_value("Example Vendor Inc")
    app.multiselect(key="scope_databases").set_value(["opencorporates", "clear"])
    next(b for b in app.button if b.label == "Preview search plan").click().run()
    assert not app.exception
    assert any("OpenCorporates" in m.value for m in app.markdown)
    assert any("Required human check" in c.value for c in app.caption)


def test_profile_review_summary_does_not_hide_material_or_quarantined_boundaries():
    from cleardiligence.models import Finding
    a = assessment([])
    a.findings = [Finding(category="profile", field="website", claim="Supported website candidate", source_ids=["source"], evidence_valid=True, requires_review=True), Finding(category="profile", field="website", claim="Another candidate", source_ids=["source2"], evidence_valid=True, requires_review=True), Finding(category="profile", field="ownership", claim="DO NOT REPEAT UNSUPPORTED CLAIM", evidence_valid=False, requires_review=True)]
    rows = decision_issues(a)
    assert len([row for row in rows if row["issue"] == "Profile verification"]) == 1
    assert "2 sourced" in rows[0]["observation"]
    assert "DO NOT REPEAT" not in json.dumps(rows)
    assert any(row["issue"] == "Evidence gaps" for row in rows)
