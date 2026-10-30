from io import BytesIO
import pytest
from pydantic import ValidationError
from pypdf import PdfReader
from cleardiligence.models import Review
from cleardiligence.storage import Store, review_state
from cleardiligence.workflow import run_demo
from cleardiligence.report import build_pdf
from cleardiligence.impact import estimate_impact


def test_persistence_and_immutable_assessments(tmp_path):
    store = Store(tmp_path / "test.db")
    a = run_demo("low")
    store.save(a)
    assert store.get(a.id) == a
    assert store.list()[0]["id"] == a.id
    with pytest.raises(Exception):
        store.save(a)


def test_human_review_false_positive_and_disposition(tmp_path):
    store = Store(tmp_path / "test.db")
    a = run_demo("sanctions")
    store.save(a)
    with pytest.raises(ValueError, match="Resolve"):
        store.record_review(Review(assessment_id=a.id, analyst="Analyst", action="Proceed", rationale="Reviewed company evidence."))
    for f in a.findings:
        if f.requires_review:
            store.record_review(Review(assessment_id=a.id, finding_id=f.id, analyst="Analyst", action="False positive" if f.match == "possible" else "Reviewed", rationale="Distinct registration identifiers; ownership evidence reviewed."))
    store.record_review(Review(assessment_id=a.id, analyst="Analyst", action="Proceed", rationale="All required identity checks reviewed and documented."))
    reviews = Store(tmp_path / "test.db").reviews(a.id)
    assert review_state(a, reviews)["final"].action == "Proceed"
    assert store.get(a.id).risk.tier.value == "High"  # Original machine findings preserved.
    candidate = next(f for f in a.findings if f.match == "possible")
    store.record_review(Review(assessment_id=a.id, finding_id=candidate.id, analyst="Analyst", action="Escalated", rationale="New ownership uncertainty requires investigation."))
    assert review_state(a, store.reviews(a.id))["final"] is None


def test_model_actor_rejected():
    with pytest.raises(ValidationError):
        Review(assessment_id="a", analyst="Model", action="Reviewed", rationale="This cannot be approved by a model.", actor_type="model")


def test_confirmed_candidate_blocks_proceed(tmp_path):
    a = run_demo("sanctions")
    store = Store(tmp_path / "test.db")
    store.save(a)
    f = next(f for f in a.findings if f.match == "possible")
    store.record_review(Review(assessment_id=a.id, finding_id=f.id, analyst="Analyst", action="Confirmed match", rationale="Independent registration evidence confirms the match."))
    with pytest.raises(ValueError):
        store.record_review(Review(assessment_id=a.id, analyst="Analyst", action="Proceed", rationale="Attempting disposition while a confirmed match is present."))


def test_pdf_contains_evidence_synthetic_label_and_human_status():
    a = run_demo("sanctions")
    review = Review(assessment_id=a.id, analyst="A & B <team>", action="Hold", rationale="Hold pending further identity verification & source review.")
    pdf = build_pdf(a, [review])
    reader = PdfReader(BytesIO(pdf))
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert pdf.startswith(b"%PDF") and len(reader.pages) >= 2
    for expected in (a.company.name, "DEMONSTRATION ONLY", "POSSIBLE", "demo://", "Hold pending", "A & B <team>"):
        assert expected in text


def test_impact_math():
    impact = estimate_impact(50, 4, 60, 85)
    assert impact["annual_hours_released"] == 1440
    assert impact["capacity_value"] == 122400
    with pytest.raises(ValueError):
        estimate_impact(10, 2, 110, 20)


def test_proceed_rejects_incomplete_coverage(tmp_path):
    a=run_demo("low")
    a.coverage["sanctions"]="Unavailable"
    store=Store(tmp_path/"incomplete.db")
    store.save(a)
    with pytest.raises(ValueError,match="coverage"):
        store.record_review(Review(assessment_id=a.id,analyst="Analyst",action="Proceed",rationale="Cannot proceed while sanctions coverage is unavailable."))


def test_cross_assessment_review_is_rejected(tmp_path):
    first,second=run_demo("low"),run_demo("media")
    store=Store(tmp_path/"separate.db")
    store.save(first)
    store.save(second)
    with pytest.raises(ValueError,match="belong"):
        store.record_review(Review(assessment_id=first.id,finding_id=second.findings[0].id,analyst="Analyst",action="Reviewed",rationale="This finding belongs to a different assessment."))


def test_delete_assessment_removes_only_selected_case_and_reviews(tmp_path):
    store = Store(tmp_path / "deletion.db")
    first, second = run_demo("low"), run_demo("media")
    for a in (first, second):
        store.save(a)
        store.record_review(Review(assessment_id=a.id, analyst="Analyst", action="Hold", rationale="Hold pending further source verification."))
    other_reviews = store.reviews(second.id)
    assert store.delete(first.id) is True
    with pytest.raises(ValueError, match="not found"):
        store.get(first.id)
    assert store.reviews(first.id) == []
    assert [row["id"] for row in store.list()] == [second.id]
    assert store.get(second.id) == second
    assert store.reviews(second.id) == other_reviews
    with pytest.raises(ValueError, match="not found"):
        store.record_review(Review(assessment_id=first.id, analyst="Analyst", action="Hold", rationale="A deleted case cannot receive new reviews."))


def test_delete_missing_assessment_is_safe(tmp_path):
    store = Store(tmp_path / "missing.db")
    a = run_demo("low")
    store.save(a)
    assert store.delete("not-a-case") is False
    assert store.delete(a.id + "' OR 1=1 --") is False
    assert store.get(a.id) == a
    assert store.delete(a.id) is True
    assert store.delete(a.id) is False
    assert store.list() == []


def test_delete_failure_rolls_back_review_history(tmp_path):
    import sqlite3
    store = Store(tmp_path / "rollback.db")
    a = run_demo("low")
    store.save(a)
    store.record_review(Review(assessment_id=a.id, analyst="Analyst", action="Hold", rationale="Keep the existing human review on rollback."))
    prior = store.reviews(a.id)
    with store.connection() as conn:
        conn.execute("CREATE TRIGGER block_deletion BEFORE DELETE ON assessments BEGIN SELECT RAISE(ABORT, 'deletion blocked'); END")
    with pytest.raises(sqlite3.IntegrityError, match="deletion blocked"):
        store.delete(a.id)
    assert store.get(a.id) == a
    assert store.reviews(a.id) == prior
