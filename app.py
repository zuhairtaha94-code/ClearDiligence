from __future__ import annotations

from html import escape
import os
import json
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import time

from dotenv import load_dotenv
import pandas as pd
import streamlit as st
from pydantic import ValidationError

from cleardiligence.demo import SCENARIOS, company_for
from cleardiligence.impact import estimate_impact
from cleardiligence.manual import registry_tasks
from cleardiligence.databases import CATALOG, database_plan
from cleardiligence.briefing import decision_issues
from cleardiligence.models import CompanyInput, ResearchScope, Review
from cleardiligence.providers import LiveResearch, OFACScreening, llm_configuration, reload_provider_configuration
from cleardiligence.report import build_pdf
from cleardiligence.interactive_report import build_html
from cleardiligence.presentation import reading_guide, GLOSSARY
from cleardiligence.storage import Store, review_state
from cleardiligence.workflow import Orchestrator, run_demo
from cleardiligence.research import PROFILE_FIELDS, SOURCE_FAMILIES, TOPICS, plan_research

load_dotenv(Path(__file__).parent / ".env")
st.set_page_config(page_title="ClearDiligence | Third-party intelligence", page_icon="◈", layout="wide", initial_sidebar_state="auto")
st.markdown("""<style>

html, body, [class*="css"], .stApp {font-family:'Avenir Next',Arial,sans-serif;}
h1,h2,h3 {font-family:'Avenir Next',Arial,sans-serif!important;letter-spacing:-.045em!important;}
h1 {font-size:2.2rem!important;font-weight:700!important;padding-bottom:.3rem!important;}
h2 {font-size:1.35rem!important;font-weight:750!important;}
h3 {font-size:1.07rem!important;}
.block-container {max-width:1320px;padding:2.3rem 3rem 4rem;}
[data-testid="stMarkdownContainer"] p {line-height:1.75;}
.decision-strip {display:flex;flex-wrap:wrap;gap:18px 38px;background:white;border:1px solid #dbe7e4;border-radius:12px;padding:16px 21px;margin:16px 0;}
.decision-strip span {font-size:.78rem;color:#58707b;line-height:1.6}.decision-strip strong {display:block;font-size:1rem;color:#203e48;}
.reading-intro {background:linear-gradient(110deg,#edf6f3,#f6f9fb);border:1px solid #d6e7e1;border-radius:18px;padding:25px 28px;margin:18px 0 24px;}
.reading-intro h2 {font-size:1.5rem!important;line-height:1.45;color:#193e48;max-width:900px;}
.reading-intro p {font-size:.94rem;line-height:1.7;color:#4c6673;max-width:900px;}
.check-label {font-size:.72rem;color:#526b78;font-weight:700;letter-spacing:.1em;text-transform:uppercase;margin-bottom:12px;}
.check-status {font-size:1.15rem;font-weight:700;color:#1b534c;line-height:1.4;margin:10px 0;}
.check-status.open {color:#79571f}.check-status.urgent {color:#963f38}
.check-detail {font-size:.91rem;line-height:1.8;color:#4c6370;}
.next-step {display:flex;align-items:flex-start;gap:14px;border-bottom:1px solid #e4edeb;padding:16px 0;line-height:1.7;}
.next-step span {flex-shrink:0;width:29px;height:29px;border-radius:50%;background:#e5f2ed;color:#176b5d;text-align:center;font-size:.84rem;font-weight:700;line-height:29px;}
[data-testid="stSidebar"] {background:#142B40;border-right:1px solid #263E53;}
[data-testid="stSidebar"] * {color:#DBE7F0;}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {color:#A8BDCD;}
[data-testid="stSidebar"] button {background:transparent;border-color:#375166;border-radius:8px;text-align:left;}
[data-testid="stSidebar"] button[kind="primary"] {background:#167E75;border-color:#167E75;}
[data-testid="stSidebar"] hr {border-color:#375166;}
[data-testid="stMetric"] {background:#FFF;border:1px solid #E1E8F0;border-radius:12px;padding:18px 20px;}
[data-testid="stMetricLabel"] {color:#607087;font-size:.8rem;}
[data-testid="stMetricValue"] {font-family:'Avenir Next',Arial,sans-serif;font-size:1.8rem;font-weight:750;color:#172B44;}
[data-testid="stForm"] {background:#FFF;border:1px solid #DEE7EF;border-radius:14px;padding:24px;}
[data-testid="stVerticalBlockBorderWrapper"] {border-radius:12px!important;}
.stButton>button,.stDownloadButton>button {border-radius:8px;font-weight:600;}
[data-testid="stTabs"] {margin-top:1rem;}
[data-testid="stTabs"] button {font-weight:600;}
.eyebrow {font-size:.71rem;letter-spacing:.16em;text-transform:uppercase;font-weight:700;color:#718095;margin-bottom:12px;}
.topline {display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #DCE5EE;padding-bottom:17px;margin-bottom:30px;color:#5B6E83;font-size:.8rem;}
.topline span:last-child {color:#117D72;font-weight:600;}
.hero {background:linear-gradient(115deg,#17364B 0%,#164D54 100%);padding:38px 40px;border-radius:16px;color:#FFF;margin-bottom:26px;position:relative;overflow:hidden;}
.hero:after {content:'◈';position:absolute;font-size:240px;line-height:1;right:30px;top:0px;color:rgba(255,255,255,.055);}
.hero .eyebrow {color:#89C6C0;}
.hero h1 {color:#FFF;font-size:2.65rem!important;max-width:680px;line-height:1.18;margin:0 0 12px;}
.hero p {color:#CBDEE4;max-width:640px;font-size:1rem;line-height:1.7;margin:0;}
.brand {font-family:'Avenir Next',Arial,sans-serif;font-size:1.25rem;font-weight:700;letter-spacing:-.04em;color:#FFF;padding:6px 0;}
.brand-icon {background:#1C8C81;color:#FFF!important;border-radius:8px;padding:3px 9px;margin-right:7px;}
.brand-sub {font-size:.64rem;letter-spacing:.17em;color:#96B2C4;margin:7px 0 30px 0;text-transform:uppercase;}
.step {display:flex;align-items:center;gap:13px;padding:12px 0;border-bottom:1px solid #E8EDF3;}
.step-num {font-size:.75rem;font-weight:700;background:#E5F1EF;color:#117D72;padding:6px 10px;border-radius:7px;}
.step-title {font-size:.91rem;font-weight:600;}.step-desc {font-size:.78rem;color:#738399;margin-top:3px;}
.risk-card {background:#FFF;border:1px solid #E0E7EF;border-left:5px solid #117D72;padding:24px 26px;border-radius:12px;margin:12px 0 20px;}
.risk-card h2 {margin:5px 0 10px;font-size:1.8rem!important;}.risk-card p {font-size:.9rem;line-height:1.65;margin:0;color:#52667D;}
.pill {display:inline-block;font-size:.68rem;font-weight:700;letter-spacing:.07em;background:#E5F2EE;color:#117D72;border-radius:5px;padding:4px 8px;}
.note {color:#728198;font-size:.78rem;line-height:1.6;}
.card-title {font-weight:750;color:#172B44;font-size:1.06rem;margin-bottom:8px;}
.card-body {font-size:.85rem;color:#63768B;line-height:1.6;min-height:66px;}
.fine-rule {border-top:1px solid #DCE5EE;margin:26px 0 18px;}

.profile-label {font-size:.68rem;letter-spacing:.12em;text-transform:uppercase;color:#60758A;font-weight:700;margin:0 0 10px;}
.profile-quote {font-size:.88rem;line-height:1.65;color:#233C53;margin:8px 0 10px;white-space:pre-wrap;}
.empty-detail {font-size:.84rem;line-height:1.65;color:#7B8BA0;padding:8px 0;}
.scope-banner {display:flex;gap:20px;flex-wrap:wrap;background:#EAF3F1;border:1px solid #D6E7E2;border-radius:10px;padding:16px 20px;margin:18px 0;color:#315C56;font-size:.83rem;}
.source-chip {display:inline-block;background:#EDF2F7;color:#526C84;padding:4px 8px;border-radius:5px;font-size:.72rem;margin:3px 5px 3px 0;}
/* Stack nested research panels before text becomes a narrow column. */
@media (max-width: 1200px) {
  .block-container {padding:1.8rem 1.5rem 3rem;}
  [data-testid="stMain"] [data-testid="stHorizontalBlock"] {flex-wrap:wrap;}
  [data-testid="stMain"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {flex:1 1 100%!important;width:100%!important;min-width:0!important;}
  [data-testid="stMain"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:has([data-testid="stMetric"]) {flex-basis:calc(50% - 1rem)!important;}
  .topline {gap:1rem;flex-wrap:wrap;}
}
</style>""", unsafe_allow_html=True)


def store():
    return Store()


def go(page):
    st.session_state["page"] = page


def open_assessment(assessment_id):
    st.session_state["current_id"] = assessment_id
    go("Overview")


def reload_configuration():
    reload_provider_configuration(Path(__file__).parent / ".env")


def queue_live(company):
    st.session_state["pending_assessment"] = {"mode": "Live", "company": company}
    go("Overview")


def queue_demo(scenario):
    st.session_state["pending_assessment"] = {"mode": "Demo", "scenario": scenario}


def render_topline(label):
    st.markdown(f'<div class="topline"><span>WORKSPACE &nbsp; / &nbsp; {escape(label.upper())}</span><span>◈ &nbsp; Evidence-led decisions</span></div>', unsafe_allow_html=True)


def execute(mode, scenario="", company=None):
    progress = st.progress(0, text="Preparing assessment")
    stages = ["Entity research", "Sanctions screening", "Adverse media", "Risk assessment", "Evidence validation"]
    with st.status("Assessment in progress", expanded=True) as status:
        def on_event(event):
            if event.stage in stages:
                index = stages.index(event.stage)
                pct = (index + (1 if event.status == "complete" else .15)) / len(stages)
                progress.progress(min(pct, 1.0), text=f"{event.stage} · {event.status}")
            marker = {"running": "○", "complete": "✓", "branch": "↳", "warning": "!"}[event.status]
            st.write(f"{marker} {event.stage}: {event.message}")
            if mode == "Demo":
                time.sleep(.12)  # Pace the explicitly synthetic workflow for presentation.
        try:
            a = run_demo(scenario, on_event) if mode == "Demo" else Orchestrator(LiveResearch(), OFACScreening(), on_event).run(company, "Live")
            store().save(a)
            st.session_state["current_id"] = a.id
            st.session_state["page"] = "Overview"
            status.update(label="Assessment complete · evidence validated", state="complete", expanded=False)
            progress.progress(1.0, text="Assessment saved")
        except Exception:
            status.update(label="Assessment could not be saved", state="error")
            st.error("The assessment could not be completed or persisted. Check local storage permissions and retry. Provider coverage failures are recorded inside completed assessments.")
            return
    st.rerun()


def landing(saved):
    render_topline("Overview")
    st.markdown('<div class="hero"><div class="eyebrow">THIRD-PARTY INTELLIGENCE, ORCHESTRATED</div><h1>Clarity before<br>commitment.</h1><p>Turn fragmented company research into a traceable assessment. Five specialized workflow components. One clear path to an analyst decision.</p></div>', unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Saved assessments", len(saved))
    c2.metric("Workflow components", "5")
    c3.metric("Reproducible demos", "3")
    c4.metric("Human decision", "Required")
    st.write("")
    left,right = st.columns([1.7,1], gap="large")
    with left:
        st.markdown("## Your next decision starts here")
        st.write("Screen a corporate vendor or contractor, follow the evidence, and record a reviewable procurement recommendation.")
        st.button("＋ New assessment", type="primary", on_click=go, args=("New assessment",), key="landing_new")
        st.markdown('<div class="fine-rule"></div>', unsafe_allow_html=True)
        st.markdown("### Explore the demonstration workspace")
        st.caption("All three scenarios use fictional companies and synthetic evidence. No credentials or network calls required.")
    with right:
        for num,title,desc in [("01","Research the entity","Company identity, public profile, and information gaps"),("02","Screen and investigate","Sanctions candidates, adverse media, and namesakes"),("03","Validate and decide","Source checks, transparent risk policy, and human review")]:
            st.markdown(f'<div class="step"><span class="step-num">◈</span><div><div class="step-title">{title}</div><div class="step-desc">{desc}</div></div></div>', unsafe_allow_html=True)
    st.write("")
    cols = st.columns(3, gap="medium")
    descriptions = {"low":"A facilities vendor with sufficient preliminary identity evidence. An unrelated namesake article is excluded.", "media":"A campus contractor faces an unadjudicated payment allegation. Source context and follow-up stay visible.", "sanctions":"A watchlist name collision triggers additional identity research and a mandatory analyst escalation."}
    for col,(key,info) in zip(cols,SCENARIOS.items()):
        with col:
            with st.container(border=True):
                st.caption(info["label"].upper())
                st.markdown(f'<div class="card-title">{escape(info["name"])}</div><div class="card-body">{descriptions[key]}</div>', unsafe_allow_html=True)
                st.caption(info["subtitle"])
                st.button("Run synthetic scenario →", key=f"demo_{key}", width="stretch", on_click=queue_demo, args=(key,))
    st.caption("Preliminary screening supports analyst judgment. It does not constitute legal, regulatory, or procurement clearance.")


def render_search_plan(runs, assessment=None):
    for run in runs:
        label = run.label + (" · " + run.status if assessment else "")
        with st.expander(label):
            st.code(run.query, language=None, wrap_lines=True)
            if run.query_version != "legacy":
                st.caption(f"Query template {run.query_version} · {run.trigger} · {run.search_depth} · up to {run.max_results} results")
            if run.jurisdiction: st.caption("Registry jurisdiction: " + run.jurisdiction)
            for note in run.access_notes: st.warning(note)
            st.caption("Fields: " + (", ".join(PROFILE_FIELDS.get(f, f) for f in run.fields) or "Evidence relevance"))
            st.caption("Domains: " + (", ".join(run.domains) or "Public web") + " · " + (f"Media window: {run.start_date or 'Any'} to {run.end_date or 'Any'}" if run.task == "media" else "Current profile research · no historical date restriction"))
            if run.google_url:
                st.link_button("Review this query on Google ↗", run.google_url, key="google_"+run.id)
            if assessment:
                st.write(run.message)
                if run.retrieval_status != "Not recorded":
                    st.caption(f"Retrieval: {run.retrieval_status} · Model extraction: {run.extraction_status} · Rejected findings: {run.rejected_findings_count}")
                for note in run.retrieval_notes + run.recovery_notes: st.warning(note)
                if run.model_used: st.caption("Extraction model: " + run.model_used)
                if run.model_attempts:
                    st.dataframe([{"Model":attempt.model,"Credential slot":attempt.credential,"Outcome":attempt.status,"HTTP":str(attempt.http_status or "")} for attempt in run.model_attempts],hide_index=True,width="stretch")
                for url in run.requested_urls: st.caption("Requested page: " + url)
                st.caption(f"Retrieved sources: {len(run.source_ids)} · Supported findings: {run.findings_count}")
                for sid in run.source_ids:
                    source = next((s for s in assessment.sources if s.id == sid), None)
                    if source:
                        st.link_button(source.title[:110], source.url, key="run_src_"+run.id+sid)
                        st.caption(f"{source.content_type} · Published: {source.published_date} · {source.date_scope}")
                        st.text_area("Retrieved evidence", source.content, disabled=True, height=120, key="run_text_"+run.id+sid)


def new_assessment():
    render_topline("New assessment")
    st.markdown('<div class="eyebrow">DEFINE YOUR RESEARCH MANDATE</div>', unsafe_allow_html=True)
    st.title("A clear scope. A stronger assessment.")
    st.write("Choose the company details, sources, and period you want researched. Every query and coverage limitation is retained with the assessment.")
    mode = st.radio("Research mode", ["Demo", "Live"], horizontal=True, key="research_mode")
    if mode == "Demo":
        st.info("Synthetic demonstration · Fictional evidence and a fixed reproducible workflow.")
        key = st.selectbox("Demo scenario", list(SCENARIOS), format_func=lambda k: SCENARIOS[k]["label"], key="scenario")
        c = company_for(key)
    else:
        c = CompanyInput(name="Company name", country="United States")
        try: config = llm_configuration()
        except ValueError as exc:
            st.error(str(exc)); return
        st.caption(f"Reasoning: {config['label']} · {config['model']} | Public-source retrieval: Tavily")
        missing = [label for label,env in [(config["label"], config["key_env"]), ("Tavily", "TAVILY_API_KEY")] if not os.getenv(env)]
        if missing: st.warning("Live research needs " + " and ".join(missing) + " credentials in .env. Reload settings after saving keys. Unavailable checks are reported explicitly.")
    left,right = st.columns([2,1], gap="large")
    with left:
        with st.form("assessment_form"):
            st.markdown("### Company and engagement")
            name = st.text_input("Company name *", value=c.name if mode=="Demo" else "", disabled=mode=="Demo", max_chars=160)
            cols = st.columns(2)
            country = cols[0].text_input("Country or jurisdiction *", value=c.country, disabled=mode=="Demo", max_chars=100)
            registry_region = cols[1].text_input("Registration state / region", placeholder="e.g. Virginia, Delaware, England", disabled=mode=="Demo", max_chars=100)
            website = st.text_input("Website", placeholder="https://company.com", disabled=mode=="Demo", max_chars=300, help="A company website helps target leadership, ownership, services, and contact pages.")
            industry = st.text_input("Industry", value=c.industry if mode=="Demo" else "", disabled=mode=="Demo", max_chars=120)
            purpose = st.text_input("Purpose of due diligence", value=c.purpose if mode=="Demo" else "Vendor onboarding", disabled=mode=="Demo", max_chars=300)
            if mode == "Live":
                st.divider()
                st.markdown("### Research scope")
                additional = st.multiselect("Additional company details", [f for f in PROFILE_FIELDS if f not in ("business", "location")], default=[f for f in PROFILE_FIELDS if f not in ("business", "location")], format_func=lambda f: PROFILE_FIELDS[f], key="scope_fields", help="Business activity and location are always researched to support entity identification.")
                families = st.multiselect("Source families", list(SOURCE_FAMILIES), default=list(SOURCE_FAMILIES), format_func=lambda f: SOURCE_FAMILIES[f], key="scope_sources")
                extra_options = ["United States / " + region.title() for region in ("virginia", "delaware", "california", "new york", "illinois", "texas", "district of columbia")] + ["United Kingdom", "Canada", "Australia"]
                extra_registry = st.multiselect("Additional registry jurisdictions", extra_options, max_selections=3, key="scope_jurisdictions", help="Optional: research up to three further registry jurisdictions using the same legal name. These checks do not establish related companies or ownership links.")
                st.caption("Mapped registry routes: selected US states, UK, Canada and Australia. Other countries require manual routing. DOJ, SEC and OFAC remain US sources; this is not global watchlist coverage.")
                st.markdown("#### Specialist databases")
                databases = st.multiselect("Optional database checks", list(CATALOG), format_func=lambda key: CATALOG[key]["label"], key="scope_databases", help="Each selected database adds a required human check. OpenCorporates calls its API only with a configured token. TLOxp, CLEAR and Factiva use licensed manual handoffs.")
                st.caption("OpenCorporates API token: " + ("Configured; entitlement not yet verified" if os.getenv("OPENCORPORATES_API_TOKEN") else "Not configured; manual lookup available") + ". TLOxp / CLEAR / Factiva: manual only. No database is selected by default.")
                topics = st.multiselect("Adverse-media topics", TOPICS, default=TOPICS, key="scope_topics")
                today = datetime.now(ZoneInfo("America/New_York")).date()
                dates = st.date_input("Adverse-media and enforcement period", value=(today-timedelta(days=5*365),today), max_value=today, key="scope_dates", help="Inclusive dates. Company identity and current OFAC screening are never limited to this historical window.")
                all_dates = st.checkbox("Search all available media dates", value=False, key="scope_all_dates")
                cols = st.columns(2)
                depth = cols[0].selectbox("Search depth", ["advanced", "basic"], format_func=lambda value: "Detailed research" if value=="advanced" else "Quick research", key="scope_depth")
                limit = cols[1].select_slider("Results per query", options=[2,4,6,8], value=4, key="scope_limit")
                st.caption("Google links provide manual query review. Factiva requires licensed access and is not automatically searched.")
            cols = st.columns(2)
            preview = cols[0].form_submit_button("Preview search plan", width="stretch", disabled=mode=="Demo")
            submit = cols[1].form_submit_button("Begin assessment →", type="primary", width="stretch")
        if submit or preview:
            try:
                if mode == "Demo": company = c
                else:
                    if not all_dates and (not isinstance(dates,tuple) or len(dates)!=2):
                        raise ValueError("Select both a start and an end date.")
                    scope = ResearchScope(databases=databases, fields=["business","location",*additional], sources=families, topics=topics, start_date=None if all_dates else dates[0], end_date=None if all_dates else dates[1], depth=depth, max_results=limit, registry_jurisdiction=registry_region, additional_registry_jurisdictions=[{"country":value.split(" / ")[0], "region":value.split(" / ")[1] if " / " in value else ""} for value in extra_registry])
                    company = CompanyInput(name=name,country=country,website=website,industry=industry,purpose=purpose,research=scope)
            except (ValidationError,ValueError) as exc:
                st.error("Please check the company details and research scope. " + str(exc))
            else:
                if submit:
                    st.session_state["pending_assessment"]={"mode":mode,"scenario":key if mode=="Demo" else "","company":company}
                    st.rerun()
                else:
                    st.markdown("### Planned research")
                    st.caption("These are the queries and filters that will be sent to the search provider. No searches have been executed by this preview.")
                    render_search_plan([*plan_research(company),*plan_research(company,"media")])
                    for plan in database_plan(company):
                        with st.container(border=True):
                            entry = CATALOG[plan["provider"]]
                            st.write("**" + entry["label"] + "** · " + entry["method"])
                            st.caption(plan["jurisdiction"] + " · " + entry["description"])
                            st.json(plan["request"])
                            st.caption("Required human check; no requests sent by preview.")
    with right:
        st.markdown("### Evidence with a purpose")
        for title,body in [("Company websites","Business activity, headquarters, executive biographies, parent-company and ownership statements."),("Registries and filings","Public registration directories and SEC reporting-entity filings. Private vendors may have no SEC filing."),("DOJ and SEC enforcement","Primary public records for allegations, proceedings, judgments, and settlements."),("Public media","Date-scoped reporting on the selected risk topics, checked for namesakes and uncertainty.")]:
            with st.container(border=True):
                st.markdown("**"+title+"**")
                st.caption(body)
        st.caption("Search results are evidence candidates. Retrieval, extraction, identity relevance, and human review are reported separately.")


def empty_profile_reason(a, field):
    if a.mode == "Live" and field not in (set(a.company.research.fields)|{"business","location"}):
        return "Not included in the requested scope."
    runs = [r for r in a.search_runs if r.task in ("entity","identity") and field in r.fields]
    if any(r.retrieval_status in ("Failed","Partial") or r.extraction_status == "Failed" or (r.query_version == "legacy" and r.status in ("Failed","Partial")) for r in runs):
        return "Research or extraction was incomplete. See Research coverage for the provider response and retrieved pages."
    if runs and not any(r.source_ids for r in runs):
        return "No matching sources were retrieved by the targeted searches."
    if a.coverage.get("entity")=="Unavailable":
        return "Entity research was unavailable. This is an integration gap, not a negative company finding."
    return "No supported information was identified in the retrieved evidence."


def profile_panel(a):
    st.markdown("### Company intelligence")
    st.caption("Jurisdiction supplied: " + a.company.country + " · " + a.company.purpose)
    requested = set(a.company.research.fields) | {"business", "location"}
    found = {f.field for f in a.findings if f.category == "profile" and f.evidence_valid and f.relevance != "Different entity"}
    st.caption(f"Retrieved evidence covers {len(found & requested)} of {len(requested)} requested fields. Verification status is shown for each fact; missing public data remains an explicit gap.")
    def card(field):
        facts=[f for f in a.findings if f.category=="profile" and f.field==field and f.evidence_valid and f.relevance!="Different entity"]
        facts.sort(key=lambda f: (f.relevance != "Supported", f.verification.value != "Verified"))
        with st.container(border=True):
            st.markdown('<div class="profile-label">'+escape(PROFILE_FIELDS[field])+'</div>',unsafe_allow_html=True)
            if not facts:
                st.markdown('<div class="empty-detail">'+escape(empty_profile_reason(a,field))+'</div>',unsafe_allow_html=True)
            for f in facts[:1]:
                value=f.extracted_value or f.claim
                preview=value[:250]+("…" if len(value)>250 else "")
                st.markdown('<div class="profile-quote">'+escape(preview)+'</div>',unsafe_allow_html=True)
                st.caption("Source-supported excerpt · " + f.verification.value + " · " + f.relevance)
                with st.expander("Read the evidence", key="profile_evidence_"+f.id):
                    st.write(f.claim)
                    for sid in f.source_ids:
                        source=next((source for source in a.sources if source.id==sid),None)
                        if source and source.url.startswith(("http://","https://")): st.link_button("Open supporting source ↗",source.url,key="profile_source_"+f.id+sid)
                        elif source: st.caption("Synthetic reference: " + source.url)
            if len(facts)>1: st.caption(f"{len(facts)-1} additional findings in the evidence explorer")
    card("business")
    cols=st.columns(2,gap="small")
    for index,field in enumerate(["location","registration","leadership","ownership","industry","website","alias"]):
        with cols[index%2]: card(field)


def readable_summary(a, reviews):
    guide=reading_guide(a,reviews)
    st.markdown('<div class="reading-intro"><div class="eyebrow">WHAT THIS MEANS</div><h2>'+escape(guide["headline"])+'</h2><p>The risk tier describes the original screening result. A person still needs to review the evidence and record the decision.</p></div>',unsafe_allow_html=True)
    cols=st.columns(3,gap="medium")
    for col,card in zip(cols,guide["cards"]):
        with col:
            with st.container(border=True):
                st.markdown('<div class="check-label">'+escape(card["title"])+'</div><div class="check-status '+card["tone"]+'">'+escape(card["status"])+'</div><p class="check-detail">'+escape(card["detail"])+'</p>',unsafe_allow_html=True)
    st.caption(f"{guide['checks_done']} of 3 research areas completed. This measures work completed, not confidence or clearance.")
    left,right=st.columns([1.5,1],gap="large")
    with left:
        st.markdown("### What happens next?")
        for index,step in enumerate(guide["next_steps"],1):
            st.markdown('<div class="next-step"><span>'+str(index)+'</span><div>'+escape(step)+'</div></div>',unsafe_allow_html=True)
    with right:
        with st.container(border=True):
            st.markdown("### Human decision")
            st.write(guide["decision"])
            st.caption("Record or inspect the decision under Analyst review. This summary cannot approve findings.")
        with st.expander("Terms, in plain language"):
            for term,meaning in GLOSSARY.items():
                st.markdown("**"+term+"**")
                st.write(meaning)
    with st.expander("Why this risk tier?"):
        for reason in a.risk.reasons: st.write("• "+reason)
        st.caption("Original policy version: " + a.risk.policy_version)
    failed=[r for r in a.search_runs if r.extraction_status=="Failed"]
    attempts=[attempt for run in a.search_runs for attempt in run.model_attempts]
    if failed:
        st.warning(f"AI interpretation was incomplete for {len(failed)} research step(s). Retrieved sources are saved. Use Research coverage to inspect recovery attempts or run fresh research after updating provider settings.")
    if attempts:
        with st.expander("AI recovery and model history"):
            st.dataframe([{"Model":attempt.model,"Credential slot":attempt.credential,"Result":attempt.status,"HTTP":str(attempt.http_status or ""),"Time (UTC)":attempt.at} for attempt in attempts],hide_index=True,width="stretch")
            st.caption("Credential slots are labels. API keys are never included in this history.")


def overview_tab(a, state):
    left,right=st.columns([1.55,1],gap="large")
    with left:
        profile_panel(a)
        st.markdown("### Screening findings")
        relevant=[f for f in a.findings if f.category!="profile"]
        if not any(f.material for f in relevant):
            st.info("No material indicators were identified. Check completed coverage and open information gaps before relying on this result.")
        for f in relevant:
            with st.container(border=True):
                st.caption(f"{f.category.replace('_',' ').upper()} · {f.nature.upper()} · {f.verification.value.upper()}")
                if f.evidence_valid:
                    st.text(f.claim)
                else:
                    st.warning("Unsupported finding quarantined; the claim is withheld from the assessment summary.")
                st.caption(f"Entity relevance: {f.relevance} · {f.relevance_reason}")
                if f.match!="none":
                    st.warning("Possible sanctions candidate · analyst determination required" if f.match=="possible" else "Confirmed sanctions match · mandatory escalation")
                r=state["latest"].get(f.id)
                st.caption("Analyst status: " + (r.action if r else "Not reviewed"))
    with right:
        with st.container(border=True):
            st.markdown("### Why this tier?")
            for reason in a.risk.reasons:
                st.write("• " + reason)
            st.markdown("**Key risk indicators**")
            for indicator in a.risk.indicators:
                st.write("• " + indicator)
            if not a.risk.indicators:
                st.caption("No material indicators identified within the stated coverage.")
            st.caption("Identity confidence: " + a.risk.identity_confidence)
            st.caption("Risk policy v" + a.risk.policy_version + " · original automated assessment")
            with st.expander("Inspect policy snapshot"):
                st.json(a.risk.policy_snapshot)
        with st.container(border=True):
            st.markdown("### Recommended next steps")
            for i,action in enumerate(a.risk.actions,1):
                st.write(f"{i}. {action}")
        with st.container(border=True):
            st.markdown("### Coverage & information gaps")
            for key,value in a.coverage.items():
                st.caption(key.upper())
                st.write(value)
            rejected = sum(f.category == "profile" and not f.evidence_valid for f in a.findings)
            if rejected: st.write(f"• {rejected} model proposals were excluded by evidence validation. Inspect them in Evidence explorer.")
            for gap in a.gaps:
                if not gap.startswith("Unsupported profile finding quarantined:"):
                    st.write("• " + gap)


def evidence_tab(a):
    st.markdown("### Follow every finding to its evidence")
    st.caption("Verified means the claim/excerpt passed provenance checks. It does not independently establish source accuracy, company identity, or legal clearance. Synthetic references are local fixtures, not real URLs.")
    c1,c2=st.columns(2)
    category=c1.selectbox("Finding category", ["All", "profile", "sanctions", "adverse_media"], key=f"category_{a.id}")
    validity=c2.selectbox("Evidence status", ["All", "Passed evidence gate", "Quarantined", "Requires analyst review"], key=f"validity_{a.id}")
    sources={s.id:s for s in a.sources}
    count=0
    for index,f in enumerate(a.findings,1):
        if category!="All" and f.category!=category: continue
        if validity=="Passed evidence gate" and not f.evidence_valid: continue
        if validity=="Quarantined" and f.evidence_valid: continue
        if validity=="Requires analyst review" and not f.requires_review: continue
        count+=1
        with st.expander(f"{index:02d} · {f.field.replace('_',' ').title() or f.category.replace('_',' ').title()} · {f.verification.value} · {f.relevance}"):
            if not f.evidence_valid:
                st.error("QUARANTINED · Unsupported claim. Excluded from verified profile and evidence-based media risk.")
            st.text(f.claim)
            st.caption(f"Finding ID: {f.id} · Evidence gate: {'Passed' if f.evidence_valid else 'Failed'} · Nature: {f.nature}")
            st.write("**Evidence excerpt**")
            st.text(f.excerpt)
            st.caption("Relevance assessment: " + f.relevance_reason)
            for note in f.validation_notes: st.warning(note)
            for sid in f.source_ids:
                s=sources.get(sid)
                if not s:
                    st.warning("Source reference was not retrieved.")
                    continue
                st.write("**" + s.title + "**")
                if s.synthetic:
                    st.caption("SYNTHETIC SOURCE · " + s.url)
                elif s.url.startswith(("https://","http://")):
                    st.link_button("Open retrieved source ↗", s.url, key=f"src_{f.id}_{sid}")
                st.caption(f"Published: {s.published_date} · Retrieved (UTC): {s.retrieved_at} · {s.content_type} · {s.date_scope}")
                if s.content_sha256: st.caption("SHA-256: " + s.content_sha256)
                st.text_area("Retrieved source content", s.content, height=140, disabled=True, key=f"content_{a.id}_{f.id}_{sid}")
    if not count: st.info("No findings match these filters.")
    with st.expander("Screening dataset and provenance"):
        st.json(a.screening_metadata)
    st.download_button("Download full assessment JSON", a.model_dump_json(indent=2), file_name=f"cleardiligence-{a.id}.json", mime="application/json", key="json_export")


def database_coverage(a):
    st.markdown("### Database coverage")
    if not a.database_runs:
        st.caption("No specialist database checks were run in this snapshot. Select them under New assessment → Research scope. OFAC and scoped public sources are recorded separately.")
        return
    sources = {source.id: source for source in a.sources}
    for run in a.database_runs:
        entry = CATALOG[run.provider]
        with st.expander(entry["label"] + " · " + run.jurisdiction + " · " + run.status, expanded=True):
            st.caption(run.method + " · " + run.at + " · " + run.id)
            st.write(run.message)
            st.json(run.request)
            st.caption("Retrieved candidates are not verified profile facts. Human checks remain in Analyst review.")
            for candidate in run.candidates:
                with st.container(border=True):
                    st.write("**" + candidate.name + "** · Potential match")
                    st.write("Company number: " + (candidate.company_number or "Not available") + " · Jurisdiction: " + (candidate.jurisdiction_code or "Not available"))
                    st.caption("Provider status: " + (candidate.current_status or "Not available") + " · Provider updated: " + candidate.provider_updated_at)
                    st.write("Registered address from candidate record: " + (candidate.registered_address or "Not available"))
                    st.link_button("Open retrieved company record ↗", candidate.record_url, key="db_record_"+run.id+candidate.source_id)
                    if candidate.registry_url:
                        st.link_button("Provider-supplied registry reference ↗", candidate.registry_url, key="db_registry_"+run.id+candidate.source_id)
                    if candidate.source_id in sources:
                        st.code(sources[candidate.source_id].content, language="json")


def manual_checks(a, reviews, state, editable=False):
    tasks = registry_tasks(a)
    if not tasks:
        return
    mixed = any(t.kind == "database" for t in tasks)
    st.markdown("### Analyst work queue" if mixed else "### Manual registry checks")
    st.caption("Only an analyst can close these registry and database checks. Public search or API completion does not establish identity. Completion does not rewrite the automated risk tier or coverage.")
    for task in tasks:
        latest = state["task_latest"].get(task.id)
        status = latest.action if latest else "Pending"
        with st.expander(f"{CATALOG[task.provider]['label'] + ' · ' if task.kind == 'database' else ''}{task.jurisdiction} · {status} · {task.access_status}"):
            st.write(task.reason)
            st.code("\n".join(task.search_terms), language=None)
            if task.registry_url:
                st.link_button("Open provider starting point ↗" if task.kind == "database" else "Open official registry starting point ↗", task.registry_url, key=f"registry_link_{editable}_{task.id}")
            else:
                st.warning("Identify the official registry for this jurisdiction before completing the check.")
            for instruction in task.instructions:
                st.write("• " + instruction)
            if task.search_run_ids: st.caption("Related search IDs: " + ", ".join(task.search_run_ids))
            if latest:
                st.caption(f"{latest.analyst} · {latest.at} · Human-entered")
                st.write(latest.rationale)
                if latest.reference_url: st.link_button("Analyst evidence reference ↗", latest.reference_url, key=f"task_ref_{editable}_{latest.id}")
    if editable:
        task_id = st.selectbox("Check to update" if mixed else "Registry check to update", [t.id for t in tasks], format_func=lambda tid: next((CATALOG[t.provider]["label"] + " · " if t.kind == "database" else "") + t.jurisdiction for t in tasks if t.id == tid), key=f"manual_task_{a.id}")
        with st.form(f"manual_task_review_{a.id}", clear_on_submit=True):
            analyst = st.text_input("Reviewer" if mixed else "Registry reviewer", max_chars=100, key="manual_analyst")
            action = st.selectbox("Check outcome" if mixed else "Registry check outcome", ["Completed", "Unavailable", "Escalated", "Reopened"], key="manual_action")
            reference = st.text_input("Evidence or provider search-page URL" if mixed else "Official evidence or search-page URL", max_chars=2000, key="manual_reference")
            rationale = st.text_area("Lookup date, terms, identifiers, result and limitations", max_chars=4000, key="manual_notes")
            human = st.checkbox("I personally performed or attempted this check." if mixed else "I personally performed or attempted this registry check.", key="manual_human")
            submitted = st.form_submit_button("Save check" if mixed else "Save registry check", type="primary")
        if submitted:
            if not human:
                st.error("Confirm that this records your own check.")
            else:
                try:
                    store().record_review(Review(assessment_id=a.id, task_id=task_id, analyst=analyst, action=action, reference_url=reference, rationale=rationale))
                except (ValueError, ValidationError) as exc:
                    st.error(str(exc))
                else:
                    st.session_state["flash"] = "Registry check recorded in the analyst audit log."
                    st.rerun()


def review_tab(a,reviews,state):
    issues = decision_issues(a, reviews)
    if issues:
        st.markdown("### Decision requirements")
        st.caption("Suggested analyst actions, ordered by review priority. These are not additional risk scores.")
        st.dataframe([{ "Priority": row["priority"], "Issue": row["issue"], "Status": row["status"], "Next action": row["action"] } for row in issues], hide_index=True, width="stretch")
    st.markdown("### Analyst review")
    st.caption("Human-entered decisions only. Notes and decisions are appended to the audit log; original automated findings and tier remain preserved. Analyst names are self-declared in this local MVP.")
    c1,c2,c3=st.columns(3)
    c1.metric("Finding reviews pending", len(state["pending"]))
    c2.metric("Escalated", len(state["escalated"]))
    c3.metric("Analyst-confirmed matches", len(state["confirmed"]))
    if registry_tasks(a): st.caption(f"Required manual checks pending: {len(state['manual_pending'])}")
    manual_checks(a,reviews,state,editable=True)
    if a.findings:
        finding_id=st.selectbox("Finding to review", [f.id for f in a.findings], format_func=lambda fid: next(f"{f.category.replace('_',' ').title()} · {f.field or f.nature} · {f.claim[:70]}" for f in a.findings if f.id==fid), key=f"review_finding_{a.id}")
        f=next(f for f in a.findings if f.id==finding_id)
        st.text(f.claim if f.evidence_valid else "Quarantined finding: review evidence before relying on the claim.")
        st.caption(f"Finding {f.id} · {f.verification.value} · {f.relevance_reason}")
        options=["Reviewed", "Escalated"]
        if f.category=="sanctions" and f.match!="none": options += ["False positive", "Confirmed match"]
        with st.form(f"finding_review_{a.id}", clear_on_submit=True):
            analyst=st.text_input("Analyst name", max_chars=100, key="finding_analyst")
            action=st.selectbox("Review action", options, key="finding_action")
            notes=st.text_area("Review notes and supporting rationale", placeholder="Explain the identifiers compared, evidence reviewed, and why this action is appropriate.", max_chars=4000, key="finding_notes")
            human=st.checkbox("I am recording my own analyst review.", key="finding_human")
            submitted=st.form_submit_button("Save finding review", type="primary")
        if submitted:
            if not human:
                st.error("Confirm that this is your own analyst review.")
            else:
                try:
                    store().record_review(Review(assessment_id=a.id,finding_id=f.id,analyst=analyst,action=action,rationale=notes))
                except (ValueError,ValidationError) as exc:
                    st.error(str(exc))
                else:
                    st.session_state["flash"]="Finding review saved."
                    st.rerun()
    st.markdown("### Final disposition")
    if state["final"]:
        st.info(f"{state['final'].action} · {state['final'].analyst} · {state['final'].at}")
        st.text(state["final"].rationale)
    else:
        st.caption("No current final disposition. New finding reviews invalidate an earlier disposition until it is recorded again.")
    if state["pending"] or state["escalated"] or state["confirmed"] or state["manual_pending"]:
        st.warning("Proceed is blocked while required findings, registry checks, or sanctions escalations remain unresolved. Hold and Reject can be recorded now.")
    with st.form(f"disposition_{a.id}", clear_on_submit=True):
        analyst=st.text_input("Decision owner", max_chars=100, key="decision_owner")
        disposition=st.selectbox("Final disposition", ["Hold", "Proceed", "Reject"], key="final_action")
        rationale=st.text_area("Disposition rationale", max_chars=4000, key="final_notes")
        confirm=st.checkbox("I take responsibility for this analyst disposition.", key="final_human")
        submitted=st.form_submit_button("Record final disposition")
    if submitted:
        if not confirm:
            st.error("Confirm responsibility for this disposition.")
        else:
            try:
                store().record_review(Review(assessment_id=a.id,analyst=analyst,action=disposition,rationale=rationale))
            except (ValueError,ValidationError) as exc:
                st.error(str(exc))
            else:
                st.session_state["flash"]="Final disposition recorded."
                st.rerun()
    with st.expander(f"Append-only analyst decision history · {len(reviews)} events"):
        if not reviews: st.caption("No human decisions recorded.")
        for r in reversed(reviews):
            st.write(f"**{r.action} · {r.analyst}**")
            st.caption(f"{r.at} · {r.task_id or r.finding_id or 'Final disposition'} · Human-entered")
            st.text(r.rationale)


def dashboard(a):
    reviews=store().reviews(a.id)
    state=review_state(a,reviews)
    render_topline("Assessment / "+a.id)
    head,action=st.columns([3,1],vertical_alignment="bottom")
    with head:
        st.markdown('<div class="eyebrow">ASSESSMENT INTELLIGENCE</div>',unsafe_allow_html=True)
        st.title(a.company.name)
        st.caption(f"{a.company.country} · {a.company.purpose} · {a.created_at[:10]} (UTC)")
    with action:
        st.download_button("↓ Download PDF report", build_pdf(a,reviews,brief=True), file_name=f"ClearDiligence-{a.id}.pdf", mime="application/pdf", type="primary", width="stretch", key="pdf_export")
        st.download_button("↗ Interactive report",build_html(a,reviews),file_name=f"ClearDiligence-{a.id}.html",mime="text/html",width="stretch",key="html_export",help="Download and open in a browser: filter evidence, expand details and follow source links. Read-only; works offline.")
    if a.mode=="Demo":
        st.info("SYNTHETIC DEMONSTRATION · All company information, articles, and screening records shown here are fictional. The workflow and review controls are functional.")
    else:
        st.caption("LIVE PUBLIC-SOURCE RESEARCH · Review coverage and information gaps before deciding.")
        if a.workflow_version != "3.1":
            st.warning("This saved report predates the current evidence and field checks. Run fresh research to apply the fixes; the original snapshot is preserved for audit.")
        with st.expander("Refresh research"):
            st.button("Run fresh research with these inputs", key="refresh_" + a.id, on_click=queue_live, args=(a.company,), help="Creates a new assessment using the current workflow and external APIs. The original report remains unchanged.")
    if "flash" in st.session_state: st.success(st.session_state.pop("flash"))
    color={"Low":"#117D72","Moderate":"#B77821","High":"#B34D47","Insufficient Information":"#607087"}[a.risk.tier.value]
    status=state["final"].action if state["final"] else "Awaiting analyst disposition"
    st.markdown('<div class="decision-strip"><span>Original automated risk<strong style="color:'+color+'">'+escape(a.risk.tier.value)+'</strong></span><span>Human decision<strong>'+escape(status)+'</strong></span></div>',unsafe_allow_html=True)
    if state["confirmed"]:
        st.error("Analyst-confirmed sanctions match · Mandatory escalation. Proceed is blocked.")
    elif a.risk.mandatory_escalation and (state["pending"] or state["escalated"]):
        st.warning("Mandatory escalation · A potential sanctions match requires analyst resolution. The target is not automatically confirmed as sanctioned.")
    if state["manual_pending"]:
        st.caption(f"{len(state['manual_pending'])} required registry/database check(s) await a person. See Analyst review for the checklist.")
    tabs=st.tabs(["Summary", "Company & findings", "Evidence explorer", "Research coverage", "Analyst review", "Workflow log"])
    with tabs[0]:
        readable_summary(a,reviews)
        with st.expander("Research counts and technical detail"):
            cols=st.columns(4)
            cols[0].metric("Evidence sources",len(a.sources))
            cols[1].metric("Checks complete",f"{sum(a.coverage.get(k, "").startswith("Complete") for k in ("entity", "sanctions", "media"))} / 3")
            cols[2].metric("Awaiting review",len(state["pending"])+len(state["escalated"])+len(state["manual_pending"]))
            cols[3].metric("Supported findings",f"{sum(f.evidence_valid for f in a.findings)} / {len(a.findings)}")

    with tabs[1]: overview_tab(a,state)
    with tabs[2]: evidence_tab(a)
    with tabs[3]:
        st.markdown("### Research coverage")
        st.caption("What was requested, what was searched, and what each integration returned.")
        st.caption("Queries use quoted names, grouped OR topics and site hints. Provider interpretation is not a strict Boolean engine; domain and date filters are enforced separately. No NOT exclusions suppress potentially adverse results.")
        scope=a.company.research
        if any(t.kind == "registry" for t in registry_tasks(a)):
            st.write("**Registry scope:** " + "; ".join(t.jurisdiction for t in registry_tasks(a) if t.kind == "registry"))
        audit={"assessment_id":a.id,"scope":scope.model_dump(mode="json"),"search_runs":[r.model_dump(mode="json") for r in a.search_runs],"manual_registry_tasks":[t.model_dump(mode="json") for t in registry_tasks(a) if t.kind == "registry"],"database_runs":[r.model_dump(mode="json") for r in a.database_runs],"manual_database_tasks":[t.model_dump(mode="json") for t in registry_tasks(a) if t.kind == "database"],"human_task_events":[r.model_dump(mode="json") for r in reviews if r.task_id]}
        st.download_button("Download search audit JSON",json.dumps(audit,indent=2),file_name=f"search-audit-{a.id}.json",mime="application/json",key="search_audit_export")
        if a.search_runs:
            scope=a.company.research
            st.markdown('<div class="scope-banner"><span>Media period: '+escape(str(scope.start_date or "Any date"))+ ' to '+escape(str(scope.end_date or "Any date"))+'</span><span>Current company profile and OFAC screening</span><span>'+str(len(a.search_runs))+' recorded searches</span></div>',unsafe_allow_html=True)
            render_search_plan(a.search_runs,a)
            st.caption("Google links open the exact query for manual corroboration. These are not claims that Google was automatically searched.")
        elif a.mode=="Demo":
            st.info("This assessment uses reproducible synthetic evidence. No external search was executed.")
        else:
            st.warning("This saved assessment predates query-level diagnostics. Run a new assessment to apply the updated research workflow.")
        database_coverage(a)
        manual_checks(a,reviews,state)
        st.link_button("Open Factiva for licensed manual review ↗","https://global.factiva.com/")
        st.caption("Factiva content was not automatically accessed or included. Record any licensed manual review and supporting references in your analyst rationale.")
    with tabs[4]: review_tab(a,reviews,state)
    with tabs[5]:
        st.markdown("### Observable workflow execution")
        st.caption("Tool actions, branches, and outcomes. Internal model reasoning and credentials are not logged.")
        for e in a.events:
            st.write(f"**{e.stage}** · {e.status.upper()}")
            st.caption(e.at)
            st.write(e.message)
        st.download_button("Download workflow log", "\n".join(e.model_dump_json() for e in a.events), file_name=f"workflow-{a.id}.jsonl", mime="application/x-ndjson")


def library(saved):
    render_topline("Assessment library")
    st.title("Your assessment library")
    st.write("Reopen evidence, analyst decisions, and the original assessment snapshot.")
    notice = st.session_state.pop("assessment_deleted_notice", None)
    if notice:
        st.success(notice)
    if not saved:
        st.info("No saved assessments yet. Run a demo or create a new assessment.")
        st.button("Create an assessment", on_click=go,args=("New assessment",))
        return
    st.dataframe(pd.DataFrame(saved).rename(columns={"name":"Company","tier":"Automated tier","created_at":"Created (UTC)","mode":"Mode","id":"Assessment ID"}),hide_index=True,width="stretch")
    choice=st.selectbox("Open saved assessment", [r["id"] for r in saved],format_func=lambda aid:next(f"{r['name']} · {r['mode']} · {r['created_at']}" for r in saved if r["id"]==aid),key="library_assessment")
    st.button("Open assessment →",type="primary",on_click=open_assessment,args=(choice,))
    with st.expander("Delete selected assessment"):
        selected = next(row for row in saved if row["id"] == choice)
        st.write(selected["name"])
        st.caption(f"Assessment {choice} · {selected['mode']} · {selected['created_at']} UTC")
        st.warning("Permanently delete this assessment, its retained evidence and its analyst review history. This cannot be undone in the app. Previously downloaded reports and exports are not removed.")
        confirmed = st.checkbox("I confirm permanent deletion of this selected assessment and its review history", key=f"confirm_delete_{choice}")
        if st.button("Delete assessment permanently", disabled=not confirmed, key=f"delete_assessment_{choice}") and confirmed:
            try:
                deleted = store().delete(choice)
            except Exception:
                st.error("The assessment could not be deleted. No changes were saved. Please retry.")
            else:
                if st.session_state.get("current_id") == choice:
                    st.session_state.pop("current_id", None)
                st.session_state["assessment_deleted_notice"] = f"Assessment {choice} deleted." if deleted else "This assessment was already removed. The library has been refreshed."
                st.rerun()


def impact_page():
    render_topline("Business impact")
    st.markdown('<div class="eyebrow">ILLUSTRATIVE BUSINESS CASE</div>',unsafe_allow_html=True)
    st.title("More time for the decisions that matter.")
    st.write("Explore the analyst capacity that preliminary research automation could release. Adjust assumptions to fit your team.")
    left,right=st.columns([1,1.6],gap="large")
    with left:
        with st.container(border=True):
            st.markdown("### Your assumptions")
            monthly=st.number_input("Assessments per month", min_value=0, max_value=100000, value=50, step=5)
            hours=st.number_input("Manual analyst hours per assessment", min_value=0.0,max_value=1000.0,value=4.0,step=.5)
            saved=st.slider("Estimated time saved (%)",0,100,60)
            cost=st.number_input("Loaded hourly analyst cost (USD)",min_value=0.0,max_value=10000.0,value=85.0,step=5.0)
    result=estimate_impact(monthly,hours,saved,cost)
    with right:
        c1,c2=st.columns(2)
        c1.metric("Annual hours released",f"{result['annual_hours_released']:,.0f}")
        c2.metric("Annual labor capacity value",f"${result['capacity_value']:,.0f}")
        st.write("")
        st.bar_chart(pd.DataFrame({"Annual analyst hours":[result["annual_manual_hours"],result["annual_assisted_hours"]]},index=["Manual baseline","Illustrative assisted workflow"]),color="#117D72",horizontal=True)
        st.caption(f"Equivalent capacity: {result['fte_capacity']:.2f} analyst FTE at 2,080 hours/year. Capacity value = hours released × loaded hourly cost.")
        st.info("Illustrative assumptions, not measured or proven results. Capacity value is not realized cash savings. Estimates exclude API fees, implementation, oversight, and change-management costs.")


def main():
    st.session_state.setdefault("page","Overview")
    try:
        saved=store().list()
    except Exception:
        st.error("Local database could not be opened. Ensure the data directory is writable.")
        st.stop()
    with st.sidebar:
        st.markdown('<div class="brand"><span class="brand-icon">◈</span> ClearDiligence</div><div class="brand-sub">Third-party intelligence</div>',unsafe_allow_html=True)
        st.caption("WORKSPACE")
        for page,label in [("Overview","◫  Overview"),("New assessment","＋  New assessment"),("Assessment library","▤  Assessment library"),("Business impact","↗  Business impact")]:
            st.button(label,key="nav_"+page,width="stretch",type="primary" if st.session_state["page"]==page else "secondary",on_click=go,args=(page,))
        st.divider()
        st.caption("RESEARCH CONNECTIONS")
        st.button("↻ Reload .env", key="reload_configuration", on_click=reload_configuration, width="stretch", help="Apply saved provider, model, and API key settings from the local .env file.")
        try:
            config = llm_configuration()
        except ValueError as exc:
            st.caption(str(exc))
        else:
            st.caption(("●" if config["configured"] else "○")+"  "+config["label"]+" · "+("Configured" if config["configured"] else "Not configured"))
            with st.expander("AI provider details"):
                st.caption("Selected LLM: " + config["provider"])
                st.caption("Model: " + config["model"])
                if config.get("fallback_models"): st.caption("Recovery chain: " + config["fallback_models"])
                if config.get("backup_configured"): st.caption("Backup authentication credential: configured")
        st.caption(("●" if os.getenv("TAVILY_API_KEY") else "○")+"  Tavily · "+("Configured" if os.getenv("TAVILY_API_KEY") else "Not configured"))
        st.caption("◈  OFAC SDN · Public download")
        st.caption("Demo mode is fully available offline.")
        st.divider()
        st.caption("RECENT ASSESSMENTS")
        if not saved: st.caption("Your first assessment starts here.")
        for row in saved[:3]:
            st.button(row["name"],key="recent_"+row["id"],width="stretch",on_click=open_assessment,args=(row["id"],))
            st.caption(f"{row['mode'].upper()} · {row['created_at'][:16].replace('T', ' ')} UTC")
        st.write("")
        st.caption("LOCAL WORKSPACE · v1.0\nAnalyst-led decisions")
    pending=st.session_state.pop("pending_assessment", None)
    if pending:
        render_topline("Research progress")
        st.title("Building your assessment")
        if pending["mode"]=="Demo":
            st.caption("Replaying a synthetic scenario with functional evidence and risk checks.")
        execute(**pending)
        st.stop()
    page=st.session_state["page"]
    if page=="New assessment": new_assessment()
    elif page=="Assessment library": library(saved)
    elif page=="Business impact": impact_page()
    elif st.session_state.get("current_id"):
        try:
            a=store().get(st.session_state["current_id"])
        except ValueError:
            st.session_state.pop("current_id",None)
            st.rerun()
        dashboard(a)
    else: landing(saved)


if __name__=="__main__":
    main()
