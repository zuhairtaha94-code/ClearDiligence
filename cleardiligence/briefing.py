"""Deterministic issue register shared by dashboard and PDF; no new model conclusions."""
from .databases import CATALOG
from .manual import registry_tasks
from .storage import review_state


def decision_issues(a, reviews=None):
    state = review_state(a, reviews or [])
    rows = []
    profile_reviews = []
    for finding in a.findings:
        if finding.relevance == "Different entity" or not (finding.material or finding.requires_review):
            continue
        if not finding.evidence_valid:
            continue  # Quarantined proposals are summarized without repeating their claims.
        review = state["latest"].get(finding.id)
        if review and review.action in ("Reviewed", "False positive"):
            continue
        if finding.category == "profile" and not finding.material:
            profile_reviews.append(finding)
            continue
        rows.append({"priority": "Urgent" if finding.match != "none" or finding.nature in ("Regulatory finding", "Judicial finding") else "Review", "issue": "Potential sanctions match" if finding.match == "possible" else finding.category.replace("_", " ").title(), "observation": finding.claim, "source_ids": finding.source_ids, "action": "Analyst: compare identifiers, assess evidence and record resolution. Escalate confirmed sanctions exposure.", "status": review.action if review else "Pending"})
    if profile_reviews:
        fields = ", ".join(sorted({f.field for f in profile_reviews}))
        refs = list(dict.fromkeys(sid for f in profile_reviews for sid in f.source_ids))
        rows.append({"priority": "Review", "issue": "Profile verification", "observation": f"{len(profile_reviews)} sourced profile observations await human review ({fields}). These observations are not material misconduct findings.", "source_ids": refs[:3], "action": "Analyst: inspect profile evidence and resolve outstanding identity or official-website questions.", "status": "Pending"})
    invalid = sum(not f.evidence_valid for f in a.findings)
    if invalid:
        rows.append({"priority": "Review", "issue": "Evidence gaps", "observation": f"{invalid} unsupported proposals were withheld from accepted findings. Missing data is not evidence of misconduct.", "source_ids": [], "action": "Analyst: inspect the evidence gaps and obtain supporting records where material.", "status": "Open"})
    for task in registry_tasks(a):
        review = state["task_latest"].get(task.id)
        if review and review.action == "Completed":
            continue
        rows.append({"priority": "Review", "issue": CATALOG[task.provider]["label"] if task.kind == "database" else "Official registry", "observation": task.jurisdiction + ": " + task.reason, "source_ids": [], "action": "Analyst: complete the documented lookup and record identifiers, reference and limitations.", "status": review.action if review else "Pending"})
    for key in ("entity", "sanctions", "media"):
        if not a.coverage.get(key, "").startswith("Complete"):
            rows.append({"priority": "Review", "issue": key.capitalize() + " coverage", "observation": a.coverage.get(key, "Not recorded"), "source_ids": [], "action": "Analyst: finish the check or document escalation before disposition.", "status": "Incomplete"})
    return sorted(rows, key=lambda row: row["priority"] != "Urgent")
