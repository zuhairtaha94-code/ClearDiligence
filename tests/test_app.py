"""Exercise real Streamlit widgets and reruns without external services."""
from streamlit.testing.v1 import AppTest
from pathlib import Path
import pytest

APP = Path(__file__).resolve().parents[1] / "app.py"


def test_landing_demo_review_and_library(tmp_path, monkeypatch):
    monkeypatch.setenv("CLEARDILIGENCE_DB",str(tmp_path/"ui.db"))
    app=AppTest.from_file(APP,default_timeout=30).run()
    assert not app.exception
    app.button(key="demo_sanctions").click().run()
    assert not app.exception
    assert any("Atlas Infrastructure Partners" in t.value for t in app.title)
    assert any("High" in m.value for m in app.markdown)
    app.text_input(key="finding_analyst").set_value("Interview Analyst")
    app.selectbox(key="finding_action").select("Reviewed")
    app.text_area(key="finding_notes").set_value("Reviewed the synthetic evidence and jurisdiction comparison.")
    app.checkbox(key="finding_human").check()
    next(b for b in app.button if b.label=="Save finding review").click().run()
    assert not app.exception
    assert any("Finding review saved" in s.value for s in app.success)
    app.button(key="nav_Assessment library").click().run()
    assert not app.exception and len(app.dataframe)==1
    app.button(key="nav_Business impact").click().run()
    assert not app.exception
    assert any(m.value=="1,440" for m in app.metric)


def test_new_assessment_modes_and_required_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("CLEARDILIGENCE_DB",str(tmp_path/"ui.db"))
    monkeypatch.delenv("ANTHROPIC_API_KEY",raising=False)
    monkeypatch.delenv("TAVILY_API_KEY",raising=False)
    app=AppTest.from_file(APP,default_timeout=30).run()
    app.button(key="nav_New assessment").click().run()
    assert not app.exception
    app.radio(key="research_mode").set_value("Live").run()
    assert not app.exception and any("credentials" in w.value for w in app.warning)
    next(b for b in app.button if b.label=="Begin assessment →").click().run()
    assert not app.exception and len(app.error)>0


def test_live_evidence_links_and_partial_coverage_render(tmp_path,monkeypatch):
    from cleardiligence.models import Assessment,CompanyInput,Finding,Source
    from cleardiligence.validation import validate_evidence
    from cleardiligence.risk import assess_risk
    from cleardiligence.storage import Store
    monkeypatch.setenv("CLEARDILIGENCE_DB",str(tmp_path/"live-ui.db"))
    a=Assessment(company=CompanyInput(name="Test Vendor",country="United States"),mode="Live",completed=True)
    s=Source(title="Mock retrieved source",url="https://example.com/vendor",content="Test Vendor in United States operates as a contractor.")
    a.sources=[s]
    a.findings=[Finding(category="profile",field="business",claim=s.content,excerpt=s.content,source_ids=[s.id],relevance="Potential")]
    a.coverage={"entity":"Partial","sanctions":"Unavailable","media":"Unavailable"}
    validate_evidence(a)
    a.risk=assess_risk(a)
    Store().save(a)
    app=AppTest.from_file(APP,default_timeout=30)
    app.session_state["current_id"]=a.id
    app.run()
    assert not app.exception
    assert any("Insufficient Information" in m.value for m in app.markdown)


@pytest.mark.parametrize("scenario",["low","media"])
def test_demo_assessment_form_runs_selected_scenario(tmp_path,monkeypatch,scenario):
    from cleardiligence.demo import SCENARIOS
    monkeypatch.setenv("CLEARDILIGENCE_DB",str(tmp_path/(scenario+".db")))
    app=AppTest.from_file(APP,default_timeout=30).run()
    app.button(key="nav_New assessment").click().run()
    app.selectbox(key="scenario").select(scenario).run()
    next(b for b in app.button if b.label=="Begin assessment →").click().run()
    assert not app.exception
    assert any(t.value==SCENARIOS[scenario]["name"] for t in app.title)


def test_library_delete_selected_case_and_reviews(tmp_path, monkeypatch):
    from streamlit.testing.v1.errors import AppTestError
    from cleardiligence.models import Review
    from cleardiligence.storage import Store
    from cleardiligence.workflow import run_demo
    monkeypatch.setenv("CLEARDILIGENCE_DB", str(tmp_path / "delete-ui.db"))
    store = Store()
    first, second = run_demo("low"), run_demo("media")
    for a in (first, second):
        store.save(a)
        store.record_review(Review(assessment_id=a.id, analyst="Analyst", action="Hold", rationale="Synthetic review retained for deletion checks."))
    app = AppTest.from_file(APP, default_timeout=30)
    app.session_state["current_id"] = first.id
    app.run()
    app.button(key="nav_Assessment library").click().run()
    app.selectbox(key="library_assessment").select(first.id).run()
    assert app.button(key=f"delete_assessment_{first.id}").disabled
    with pytest.raises(AppTestError, match="Cannot update a disabled"):
        app.button(key=f"delete_assessment_{first.id}").click()
    assert len(store.list()) == 2
    app.checkbox(key=f"confirm_delete_{first.id}").check().run()
    assert not app.button(key=f"delete_assessment_{first.id}").disabled
    app.button(key=f"delete_assessment_{first.id}").click().run()
    assert not app.exception
    assert any(first.id in notice.value for notice in app.success)
    assert [row["id"] for row in store.list()] == [second.id]
    assert store.reviews(first.id) == []
    assert len(store.reviews(second.id)) == 1
    with pytest.raises(KeyError):
        app.session_state["current_id"]
    assert first.id not in app.dataframe[0].value["Assessment ID"].tolist()
    assert app.selectbox(key="library_assessment").value == second.id
    assert not any(button.key == f"recent_{first.id}" for button in app.button)


def test_library_delete_confirmation_follows_selection_and_empty_state(tmp_path, monkeypatch):
    from cleardiligence.storage import Store
    from cleardiligence.workflow import run_demo
    monkeypatch.setenv("CLEARDILIGENCE_DB", str(tmp_path / "empty-ui.db"))
    store = Store()
    first, second = run_demo("low"), run_demo("media")
    store.save(first)
    store.save(second)
    app = AppTest.from_file(APP, default_timeout=30).run()
    app.button(key="nav_Assessment library").click().run()
    app.selectbox(key="library_assessment").select(first.id).run()
    app.checkbox(key=f"confirm_delete_{first.id}").check().run()
    app.selectbox(key="library_assessment").select(second.id).run()
    assert app.button(key=f"delete_assessment_{second.id}").disabled
    assert len(store.list()) == 2
    app.checkbox(key=f"confirm_delete_{second.id}").check().run()
    app.button(key=f"delete_assessment_{second.id}").click().run()
    assert not app.exception
    app.checkbox(key=f"confirm_delete_{first.id}").check().run()
    app.button(key=f"delete_assessment_{first.id}").click().run()
    assert not app.exception
    assert store.list() == []
    assert len(app.dataframe) == 0
    assert any("No saved assessments" in info.value for info in app.info)
    assert not any(button.key and button.key.startswith("recent_") for button in app.button)
    fresh = AppTest.from_file(APP, default_timeout=30).run()
    assert not fresh.exception
    assert any("Your first assessment" in caption.value for caption in fresh.caption)
