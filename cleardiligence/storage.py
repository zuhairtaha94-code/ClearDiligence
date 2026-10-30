"""Preserved local snapshots and review events, with explicit case deletion."""
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3

from .models import Assessment, Review
from .manual import registry_tasks


def review_state(a: Assessment, reviews: list[Review]):
    latest = {}
    final = None
    task_latest = {}
    for review in reviews:
        if review.task_id:
            task_latest[review.task_id] = review
            final = None
        elif review.finding_id:
            latest[review.finding_id] = review
            if final is not None:
                final = None  # A later finding decision requires a fresh disposition.
        else:
            final = review
    pending, escalated, confirmed = [], [], []
    for f in a.findings:
        r = latest.get(f.id)
        if r and r.action == "Confirmed match":
            confirmed.append(f.id)
        elif r and r.action == "Escalated":
            escalated.append(f.id)
        elif f.requires_review and (not r or (f.match != "none" and r.action != "False positive")):
            pending.append(f.id)
    manual_pending = [t.id for t in registry_tasks(a) if t.required and (t.id not in task_latest or task_latest[t.id].action != "Completed")]
    return {"task_latest": task_latest, "manual_pending": manual_pending, "latest": latest, "final": final, "pending": pending, "escalated": escalated, "confirmed": confirmed}


class Store:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv("CLEARDILIGENCE_DB", "data/cleardiligence.db"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS assessments (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, mode TEXT NOT NULL,
                    tier TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                    assessment_id TEXT NOT NULL REFERENCES assessments(id), payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS review_assessment ON reviews(assessment_id, seq);
            """)

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def save(self, a: Assessment):
        if not a.completed:
            raise ValueError("Only completed assessment snapshots may be saved")
        with self.connection() as conn:
            conn.execute("INSERT INTO assessments VALUES (?, ?, ?, ?, ?, ?)", (a.id, a.company.name, a.mode, a.risk.tier.value, a.created_at, a.model_dump_json()))

    def get(self, assessment_id: str) -> Assessment:
        with self.connection() as conn:
            row = conn.execute("SELECT payload FROM assessments WHERE id=?", (assessment_id,)).fetchone()
        if row is None:
            raise ValueError("Assessment not found")
        return Assessment.model_validate_json(row["payload"])

    def list(self):
        with self.connection() as conn:
            return [dict(row) for row in conn.execute("SELECT id, name, mode, tier, created_at FROM assessments ORDER BY created_at DESC, rowid DESC")]

    def delete(self, assessment_id: str) -> bool:
        """Explicit workspace cleanup; remove one case and its reviews atomically."""
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT id FROM assessments WHERE id=?", (assessment_id,)).fetchone() is None:
                return False
            conn.execute("DELETE FROM reviews WHERE assessment_id=?", (assessment_id,))
            conn.execute("DELETE FROM assessments WHERE id=?", (assessment_id,))
        return True

    def reviews(self, assessment_id: str) -> list[Review]:
        with self.connection() as conn:
            return self._reviews(conn, assessment_id)

    def _reviews(self, conn, assessment_id):
        return [Review.model_validate_json(row["payload"]) for row in conn.execute("SELECT payload FROM reviews WHERE assessment_id=? ORDER BY seq", (assessment_id,))]

    def record_review(self, review: Review):
        # Called exclusively by explicit UI analyst submission. No model/provider receives this tool.
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT payload FROM assessments WHERE id=?", (review.assessment_id,)).fetchone()
            if not row:
                raise ValueError("Assessment not found")
            a = Assessment.model_validate_json(row["payload"])
            prior = self._reviews(conn, a.id)
            state = review_state(a, prior)
            if not review.analyst.strip() or len(review.rationale.strip()) < 10:
                raise ValueError("Enter an analyst name and a meaningful rationale (at least 10 characters)")
            if review.task_id:
                task = next((t for t in registry_tasks(a) if t.id == review.task_id), None)
                if not task:
                    raise ValueError("Manual task does not belong to this assessment")
                if review.action not in ("Completed", "Unavailable", "Escalated", "Reopened"):
                    raise ValueError("Invalid manual task action")
                if review.action == "Completed" and not review.reference_url:
                    raise ValueError("A completed registry check requires an evidence reference URL" if task.kind == "registry" else "A completed database check requires an evidence reference URL")
            elif review.finding_id:
                f = next((f for f in a.findings if f.id == review.finding_id), None)
                if not f:
                    raise ValueError("Finding does not belong to this assessment")
                if review.action not in ("Reviewed", "Escalated", "False positive", "Confirmed match"):
                    raise ValueError("Invalid finding review action")
                if review.action in ("False positive", "Confirmed match") and (f.category != "sanctions" or f.match == "none"):
                    raise ValueError("Match decisions apply only to sanctions candidates")
                if review.action == "False positive" and f.match == "confirmed":
                    raise ValueError("A confirmed sanctions match requires formal escalation outside this MVP")
                if review.action == "Confirmed match" and not f.evidence_valid:
                    raise ValueError("Unsupported evidence cannot establish a confirmed match")
            else:
                if review.action not in ("Proceed", "Hold", "Reject"):
                    raise ValueError("Invalid final disposition")
                if review.action == "Proceed":
                    blocked = state["manual_pending"] or state["pending"] or state["escalated"] or state["confirmed"] or any(f.match == "confirmed" for f in a.findings)
                    if blocked:
                        raise ValueError("Resolve the review queue, manual checks and escalations before recording Proceed")
                    if not all(a.coverage.get(k, "").startswith("Complete") for k in ("entity", "sanctions", "media")) or a.risk.identity_confidence == "Insufficient" or any(f.material and not f.evidence_valid for f in a.findings):
                        raise ValueError("Insufficient identity, evidence, or screening coverage prevents Proceed")
            conn.execute("INSERT INTO reviews(id, assessment_id, payload) VALUES (?, ?, ?)", (review.id, review.assessment_id, review.model_dump_json()))
