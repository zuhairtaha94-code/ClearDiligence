"""Plain-language labels over stored evidence. No LLM or new factual conclusions."""
from .manual import registry_tasks
from .storage import review_state

GLOSSARY = {
    "OFAC SDN": "A US Treasury list of designated people and organizations. This name screen covers that list, not every sanctions restriction.",
    "Sanctions": "Restrictions imposed by government authorities. This app screens OFAC's SDN list; it does not cover every restriction worldwide.",
    "Possible match": "A similar name was found. It does not establish that this is the same company.",
    "Source checked": "The statement is supported by a retrieved excerpt. This is not independent proof that the publisher is correct.",
    "Allegation": "A claim about wrongdoing that has not been established as a regulatory or court finding in the cited evidence.",
    "Coverage": "The checks actually completed, including their source and date limits. It is not a confidence score.",
    "Information gap": "Something the research could not establish. Missing information is not evidence of misconduct.",
    "Analyst decision": "A person's documented Proceed, Hold or Reject decision, separate from the original automated assessment.",
}
CATEGORY_LABELS = {"profile": "Company details", "sanctions": "Sanctions screening", "adverse_media": "News and legal records"}


def reading_guide(a, reviews=None):
    state = review_state(a, reviews or [])
    tier = a.risk.tier.value
    relevant = [f for f in a.findings if f.evidence_valid and f.relevance != "Different entity"]
    possible = [f for f in relevant if f.match == "possible"]
    unresolved_possible = [f for f in possible if not state["latest"].get(f.id) or state["latest"][f.id].action != "False positive"]
    resolved_possible = bool(possible) and not unresolved_possible
    confirmed = any(f.match == "confirmed" for f in relevant) or bool(state["confirmed"])
    headline = {"Low": "No material warning signs were identified in the checks completed.", "Moderate": "A potentially relevant issue needs a closer look.", "High": "A significant screening issue requires analyst attention.", "Insufficient Information": "There is not enough evidence to reach a reliable preliminary conclusion."}[tier]
    if possible and not confirmed:
        headline = "A similar name appeared on a sanctions list. The company is not confirmed as sanctioned."
    if resolved_possible and not confirmed:
        headline = "The original screening found a similar name. An analyst recorded that it is a different company."
    if tier in ("Low", "Insufficient Information") and any(not a.coverage.get(key, "").startswith("Complete") for key in ("entity", "sanctions", "media")):
        headline = "Some research could not be finished. Treat this as an incomplete assessment."
    if confirmed:
        headline = "A confirmed sanctions finding requires mandatory escalation."
    supported = {f.field for f in relevant if f.category == "profile" and f.relevance == "Supported"}
    entity_ok = {"business", "location"}.issubset(supported) and a.coverage.get("entity", "").startswith("Complete")
    sanctions_ok = a.coverage.get("sanctions", "").startswith("Complete")
    media_ok = a.coverage.get("media", "").startswith("Complete")
    media = [f for f in relevant if f.category == "adverse_media" and f.material]
    cards = [
        {"title": "Company identity", "status": "Core details found" if entity_ok else "Needs more evidence", "tone": "done" if entity_ok else "open", "detail": "Business activity and location are supported by sources. Registration and ownership are separate questions; inspect their evidence and review status." if entity_ok else "The research did not complete enough checks to establish core company details."},
        {"title": "Sanctions screening", "status": "Escalation required" if confirmed else "Reviewed: different company" if resolved_possible else "Possible name match" if possible else "No name match identified" if sanctions_ok else "Check incomplete", "tone": "urgent" if confirmed or unresolved_possible else "done" if sanctions_ok else "open", "detail": "Read the recorded human rationale alongside the original candidate. The automated tier is preserved." if resolved_possible and not confirmed else "Compare identifiers and document a human decision. A name alone cannot establish identity." if possible or confirmed else "OFAC SDN names and supported aliases only. This is not worldwide sanctions or ownership clearance." if sanctions_ok else "This check could not be completed. Do not interpret the missing result as a clear screen."},
        {"title": "News and legal records", "status": "Items need review" if media else "No material issue identified" if media_ok else "Check incomplete", "tone": "open" if media or not media_ok else "done", "detail": f"{len(media)} potentially relevant item(s). Read the source and distinguish allegations from established findings." if media else "No material issue was identified within the selected public sources and dates. Coverage remains limited." if media_ok else "Public news or enforcement research was incomplete; further review is required."},
    ]
    next_steps = []
    if confirmed: next_steps.append("Escalate the confirmed sanctions finding before considering onboarding.")
    elif unresolved_possible: next_steps.append("Compare the sanctions candidate's identifiers and record whether it is the same company.")
    if state["manual_pending"]: next_steps.append(f"Complete {len(state['manual_pending'])} required registry or database check(s) in Analyst review.")
    if any(not a.coverage.get(key, "").startswith("Complete") for key in ("entity", "sanctions", "media")):
        next_steps.append("Finish the incomplete research checks. Retrieved sources are saved; missing results are not clearance.")
    if state["pending"]: next_steps.append(f"Review {len(state['pending'])} outstanding evidence item(s), including company details and any screening findings.")
    next_steps.append("Record the human decision and rationale." if not state["final"] else "Read the recorded analyst decision and rationale alongside the original screening result.")
    return {"headline": headline, "cards": cards, "next_steps": next_steps, "tier": tier, "decision": state["final"].action if state["final"] else "Awaiting human decision", "checks_done": sum(a.coverage.get(k, "").startswith("Complete") for k in ("entity", "sanctions", "media")), "followups": len(state["pending"]) + len(state["escalated"]) + len(state["manual_pending"]), "tasks": registry_tasks(a)}
