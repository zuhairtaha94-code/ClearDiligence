"""Professional PDF export generated from stored facts and human audit events."""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, PageBreak

from .models import Assessment, Review
from .storage import review_state
from .research import PROFILE_FIELDS, SOURCE_FAMILIES
from .manual import registry_tasks
from .databases import CATALOG
from .briefing import decision_issues
from .presentation import reading_guide

NAVY = colors.HexColor("#172B44")
TEAL = colors.HexColor("#117D72")
GRAY = colors.HexColor("#4F6473")
LIGHT = colors.HexColor("#F0F5F8")


def safe(text):
    text = str(text).replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")
    return escape(text.encode("cp1252", "replace").decode("cp1252")).replace("\n", "<br/>")


def build_pdf(a: Assessment, reviews: list[Review] | None = None, brief: bool = False) -> bytes:
    reviews = reviews or []
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=48, leftMargin=48, topMargin=65, bottomMargin=52, title=f"ClearDiligence - {a.company.name}", author="ClearDiligence")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CDTitle", fontName="Helvetica-Bold", fontSize=25, leading=30, textColor=NAVY, spaceAfter=14))
    styles.add(ParagraphStyle(name="CDHeading", fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=TEAL, spaceBefore=17, spaceAfter=8, keepWithNext=True))
    styles.add(ParagraphStyle(name="CDBody", fontName="Helvetica", fontSize=10.2, leading=15.3, textColor=NAVY, spaceAfter=7, splitLongWords=True))
    styles.add(ParagraphStyle(name="CDSmall", fontName="Helvetica", fontSize=10, leading=14, textColor=GRAY, spaceAfter=6, splitLongWords=True))
    styles.add(ParagraphStyle(name="CDLabel", fontName="Helvetica-Bold", fontSize=10, leading=14, textColor=NAVY, spaceAfter=4, keepWithNext=True))
    story = []
    def p(text, style="CDBody"):
        return Paragraph(safe(text), styles[style])
    def section(title):
        story.append(p(title, "CDHeading"))
    def bullet(text):
        story.append(p("- " + str(text)))
    refs = {s.id: str(i + 1) for i, s in enumerate(a.sources)}
    def citations(f):
        return " ".join(f"[{refs.get(sid, '?')}]" for sid in f.source_ids)
    state = review_state(a, reviews)
    disposition = state["final"].action if state["final"] else "Pending analyst disposition"
    story.extend([p("PRELIMINARY THIRD-PARTY ASSESSMENT", "CDSmall"), p(a.company.name, "CDTitle")])
    if a.mode == "Demo":
        story.append(p("DEMONSTRATION ONLY - All company profiles, screening records, and news in this assessment are synthetic.", "CDLabel"))
    else:
        story.append(p("LIVE RESEARCH - Public-source preliminary screening with the coverage limitations recorded below.", "CDSmall"))
    rows = [[p("AUTOMATED RISK", "CDSmall"), p("ANALYST DISPOSITION", "CDSmall")], [p(a.risk.tier.value, "CDLabel"), p(disposition, "CDLabel")], [p(f"Assessment: {a.id}", "CDSmall"), p(f"Date (UTC): {a.created_at}", "CDSmall")], [p(f"Jurisdiction (user input): {a.company.country}", "CDSmall"), p(f"Purpose: {a.company.purpose}", "CDSmall")]]
    table = Table(rows, colWidths=[258, 258], hAlign="LEFT")
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), LIGHT), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story.append(table)
    guide = reading_guide(a, reviews)
    section("What this means")
    story.append(p(guide["headline"], "CDLabel"))
    cards = []
    for card in guide["cards"]:
        cards.append([p(card["title"], "CDLabel"),p(card["status"], "CDLabel"),p(card["detail"], "CDSmall")])
    glance = Table([[Table([[item] for item in card], colWidths=[150]) for card in cards]], colWidths=[172,172,172])
    glance.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("BACKGROUND",(0,0),(-1,-1),LIGHT),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#DCE5EC")),("TOPPADDING",(0,0),(-1,-1),9),("BOTTOMPADDING",(0,0),(-1,-1),9)]))
    story.append(glance)
    section("Executive assessment")
    for reason in a.risk.reasons:
        bullet(reason)
    if a.risk.indicators:
        story.append(p("Key risk indicators", "CDLabel"))
        for indicator in a.risk.indicators:
            bullet(indicator)
    story.append(p(f"Identity confidence: {a.risk.identity_confidence}. Policy version: {a.risk.policy_version}.", "CDSmall"))
    if a.risk.mandatory_escalation:
        story.append(p("MANDATORY ESCALATION: Do not treat a possible match as confirmed. Analyst resolution is required before onboarding.", "CDLabel"))
    story.append(p("Automated tier is the original assessment snapshot. Human decisions are recorded separately. Verified indicates source excerpt/provenance checks, not independent factual or legal verification.", "CDSmall"))
    story.append(p(f"Evidence base: {len(a.sources)} sources | Required human checks open: {len(state['manual_pending'])} | Finding reviews pending: {len(state['pending'])}", "CDLabel"))
    story.append(p("Decision boundary: complete the outstanding checks, resolve material findings and record a human disposition. This preliminary report does not provide legal clearance or an audit opinion.", "CDSmall"))
    story.append(PageBreak())
    section("Key issues and decision requirements")
    story.append(p("Review priorities identify work to complete, not a separate misconduct score. Owners below are suggested analyst roles; no task assignment is implied.", "CDSmall"))
    issues = decision_issues(a, reviews)
    if issues:
        for issue in issues[:12]:
            evidence = " ".join("[" + refs.get(sid, "?") + "]" for sid in issue["source_ids"]) or "Research coverage / human task"
            block=[p(issue["issue"] + " | " + issue["status"], "CDLabel"),p(issue["observation"][:420] + ("... See detailed findings." if len(issue["observation"])>420 else "")),p(issue["action"], "CDSmall"),p("Evidence: " + evidence, "CDSmall"),Spacer(1,9)]
            story.append(KeepTogether(block))
        if len(issues)>12:
            story.append(p(f"{len(issues)-12} additional items are detailed in the screening, gaps and human work queue below.", "CDSmall"))
    else:
        story.append(p("No unresolved issue rows within this assessment's completed scope. Analyst disposition and the limitations still apply."))
    section("Scope and basis of work")
    story.append(p("Corporate vendor / contractor integrity screening. The methods comprise public-source retrieval, structured extraction, official SDN name screening, deterministic risk rules and evidence validation. No financial, technical, site-inspection or full legal due diligence was performed."))
    story.append(p("Source support means a retrieved excerpt supports the stated observation; it does not independently establish that a publisher is correct. Missing information is reported as uncertainty. Ownership, non-US sanctions, county court and licensed database coverage are limited to explicitly recorded checks.", "CDSmall"))
    if a.search_runs:
        section("Research mandate")
        scope = a.company.research
        if not brief: story.append(p("Requested company details: " + ", ".join(PROFILE_FIELDS[f] for f in scope.fields)))
        story.append(p("Adverse-media and enforcement window: " + str(scope.start_date or "Any date") + " to " + str(scope.end_date or "Any date") + ". Company identity and OFAC screening use current sources."))
        story.append(p("Selected source families: " + ", ".join(SOURCE_FAMILIES.get(key,key) for key in scope.sources) + ". Topics: " + ", ".join(scope.topics)))
    if not brief: story.append(PageBreak())
    section("Company profile")
    if a.company.website:
        story.append(p(f"Website supplied by user (unverified): {a.company.website}"))
    if a.company.industry:
        story.append(p(f"Industry supplied by user (unverified): {a.company.industry}"))
    for field in ("business", "location", "industry", "registration", "alias", "leadership", "ownership", "website"):
        facts = [f for f in a.findings if f.category == "profile" and f.field == field and f.evidence_valid and f.relevance != "Different entity"]
        if not facts and field not in a.company.research.fields:
            story.append(p(f"{PROFILE_FIELDS[field]}: Not requested in the research mandate.", "CDSmall"))
            continue
        if not facts:
            story.append(p(f"{PROFILE_FIELDS[field]}: " + ("Research incomplete; inspect query coverage and provider diagnostics." if any(r.status in ("Failed", "Partial") and field in r.fields for r in a.search_runs) else "Not found within retrieved evidence and selected scope."), "CDSmall"))
        facts.sort(key=lambda f: (f.relevance != "Supported", f.verification.value != "Verified"))
        for f in facts[:1 if brief else 2]:
            value=(f.extracted_value or f.claim) if brief else f.claim
            preview=value[:320] + ("... [short excerpt; full evidence in the interactive report]" if len(value)>320 else "") if brief else value
            story.append(p(f"{PROFILE_FIELDS[field]} | {f.verification.value} | {f.relevance}: {preview} {citations(f)}"))
        if len(facts) > 2:
            story.append(p(f"{len(facts)-2} additional supported observations are available in the assessment and evidence references.", "CDSmall"))
    section("Screening findings")
    for key, value in a.coverage.items():
        story.append(p(f"{key.capitalize()}: {value}"))
    if a.screening_metadata:
        story.append(p(f"Screening provider: {a.screening_metadata.get('provider', '')}. Records checked: {a.screening_metadata.get('records', 'Unknown')}. Retrieved: {a.screening_metadata.get('retrieved_at', 'Unknown')}.", "CDSmall"))
        story.append(p(f"Names screened: {', '.join(a.screening_metadata.get('names_screened', []))}", "CDSmall"))
        if a.screening_metadata.get("threshold"):
            story.append(p(f"Name similarity threshold: {a.screening_metadata['threshold']}. {a.screening_metadata.get('algorithm', '')}.", "CDSmall"))
    relevant = [f for f in a.findings if f.category != "profile"]
    if not any(f.material for f in relevant):
        story.append(p("No material indicators identified within completed checks. This is not proof of absence or legal/regulatory clearance."))
    for f in relevant:
        label = f"{f.category.replace('_', ' ').title()} | {f.nature} | {f.verification.value} | Entity relevance: {f.relevance}"
        story.append(p(label, "CDLabel"))
        if f.evidence_valid:
            story.append(p(f"{f.claim} {citations(f)}"))
            story.append(p(f"Relevance assessment: {f.relevance_reason}", "CDSmall"))
        else:
            story.append(p("Unsupported claim withheld. Evidence gate failed; follow-up is required.", "CDSmall"))
        if f.match != "none":
            story.append(p(f"Automated match status: {f.match.upper()}. Human review required.", "CDLabel"))
        r = state["latest"].get(f.id)
        story.append(p(f"Analyst review: {r.action if r else 'Not reviewed'}.", "CDSmall"))
    section("Open questions and next steps")
    quarantined = [gap for gap in a.gaps if gap.startswith("Unsupported profile finding quarantined:")]
    if quarantined:
        bullet(f"{sum(f.category == 'profile' and not f.evidence_valid for f in a.findings)} unsupported profile proposals were withheld. Inspect validation notes in the evidence explorer; obtain corroboration for material gaps.")
    for gap in [gap for gap in a.gaps if gap not in quarantined] or ([] if quarantined else ["No additional gaps recorded."]):
        bullet(gap)
    for i, action in enumerate(guide["next_steps"] if brief else a.risk.actions, 1):
        story.append(p(f"{i}. {action}"))
    section("Analyst review")
    story.append(p(f"Current final disposition: {disposition}. Open review items: {len(state['pending'])}; escalated: {len(state['escalated'])}; confirmed by analyst: {len(state['confirmed'])}."))
    if not reviews:
        story.append(p("No human review recorded. No model or workflow component has approved these findings."))
    for r in reviews:
        story.append(p(f"{r.at} | {r.analyst} | {r.action} | {r.task_id or r.finding_id or 'Final disposition'}", "CDLabel"))
        story.append(p(r.rationale))
    if a.database_runs:
        section("Specialist database coverage")
        for run in a.database_runs:
            story.append(p(f"{CATALOG[run.provider]['label']} | {run.method} | {run.status} | {run.jurisdiction}", "CDLabel"))
            story.append(p(run.message))
            story.append(p("Request: " + str(run.request) + " | Executed/recorded (UTC): " + run.at, "CDSmall"))
            for candidate in run.candidates:
                story.append(p(f"Potential match: {candidate.name} | Company number: {candidate.company_number or 'Not available'} | Jurisdiction: {candidate.jurisdiction_code or 'Not available'} [{refs.get(candidate.source_id, '?')}]", "CDLabel"))
                story.append(p(f"Provider status: {candidate.current_status or 'Not available'} | Provider updated: {candidate.provider_updated_at}", "CDSmall"))
                story.append(p(candidate.record_url, "CDSmall"))
        story.append(p("Database candidates are not verified profile facts or sanctions matches. API search completion does not mean the target has been identified. Licensed services marked Manual were not automatically searched.", "CDSmall"))
    if registry_tasks(a):
        section("Manual registry checks" if all(t.kind == "registry" for t in registry_tasks(a)) else "Analyst work queue")
        story.append(p("Public-web searches are not direct official registry verification. Human task outcomes are separate from the original automated risk tier and findings."))
        for task in registry_tasks(a):
            latest = state["task_latest"].get(task.id)
            story.append(p(f"{CATALOG[task.provider]['label'] + ' | ' if task.kind == 'database' else ''}{task.jurisdiction} | {latest.action if latest else 'Pending'} | {task.access_status}", "CDLabel"))
            story.append(p(task.reason))
            story.append(p(("Provider starting point: " if task.kind == "database" else "Official starting point: ") + (task.registry_url or "Not mapped; identify the competent authority"), "CDSmall"))
            story.append(p("Search terms: " + "; ".join(task.search_terms), "CDSmall"))
            for instruction in ([] if brief else task.instructions): bullet(instruction)
            if latest:
                story.append(p(f"{latest.analyst} | {latest.at} | Human-entered", "CDSmall"))
                story.append(p(latest.rationale))
                if latest.reference_url: story.append(p(latest.reference_url, "CDSmall"))
    if a.search_runs and not brief:
        section("Research coverage")
        for run in a.search_runs:
            story.append(p(f"{run.label} | {run.status}", "CDLabel"))
            story.append(p(run.query, "CDSmall"))
            story.append(p(f"Template: {run.query_version} | {run.trigger} | Jurisdiction: {run.jurisdiction or 'Not jurisdiction-restricted'} | Depth: {run.search_depth or 'Legacy record'} | Limit: {run.max_results or 'Not recorded'}", "CDSmall"))
            story.append(p(f"Sources: {len(run.source_ids)} | Supported findings: {run.findings_count} | {run.message}", "CDSmall"))
        story.append(p("Google queries are available for manual corroboration in the dashboard. Factiva is a licensed service and was not automatically searched.", "CDSmall"))
    section("Evidence references")
    cited_ids={sid for f in a.findings if f.evidence_valid for sid in f.source_ids}
    cited_ids.update(c.source_id for run in a.database_runs for c in run.candidates)
    if brief:
        story.append(p("References cited by accepted findings and database candidates. Full retained source text, uncited retrieval candidates and query diagnostics are available in the interactive report/application.", "CDSmall"))
    for s in a.sources:
        if brief and s.id not in cited_ids: continue
        reference_start = len(story)
        story.append(p(f"[{refs[s.id]}] {s.title}", "CDLabel"))
        story.append(p(s.url, "CDSmall"))
        story.append(p(f"Published: {s.published_date} | Retrieved (UTC): {s.retrieved_at} | {'SYNTHETIC' if s.synthetic else s.kind}", "CDSmall"))
        valid = [f for f in a.findings if s.id in f.source_ids and f.evidence_valid]
        excerpts = list(dict.fromkeys(f.excerpt for f in valid))
        for excerpt in ([] if brief else excerpts):
            story.append(p(f"Evidence excerpt: {excerpt}", "CDSmall"))
        if not valid:
            story.append(p("Synthetic context record; no accepted finding cites this record." if s.synthetic else "Screening dataset reference; no company-specific finding cites this file." if s.kind == "official_list" else "Retrieved candidate source; no accepted finding cites this record. Target-company relevance is not established.", "CDSmall"))
        if s.content_sha256 and not brief:
            story.append(p(f"Content SHA-256: {s.content_sha256}", "CDSmall"))
        reference_block = story[reference_start:]
        del story[reference_start:]
        story.append(KeepTogether(reference_block))
    if a.screening_metadata.get("files") and not brief:
        section("Screening data provenance")
        for name, data in a.screening_metadata["files"].items():
            story.append(p(name, "CDLabel"))
            story.append(p(f"{data['url']}\nSHA-256: {data['sha256']}\nLast-Modified: {data['last_modified']} | Retrieved: {data['retrieved_at']}", "CDSmall"))
    def page(canvas, document):
        canvas.saveState()
        canvas.setFillColor(TEAL)
        canvas.rect(0, 775, 612, 17, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", 10)
        canvas.setFillColor(NAVY)
        canvas.drawString(48, 752, "CLEARDILIGENCE")
        canvas.setFont("Helvetica", 7)
        canvas.drawRightString(564, 752, "CORPORATE INTELLIGENCE / PRELIMINARY")
        canvas.setStrokeColor(colors.HexColor("#DCE5EC"))
        canvas.line(48, 39, 564, 39)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GRAY)
        canvas.drawString(48, 26, "SYNTHETIC DEMONSTRATION" if a.mode == "Demo" else "PRELIMINARY SCREENING - ANALYST REVIEW REQUIRED")
        canvas.drawRightString(564, 26, f"{a.id}  /  {document.page}")
        canvas.restoreState()
    doc.build(story, onFirstPage=page, onLaterPages=page)
    return buffer.getvalue()
