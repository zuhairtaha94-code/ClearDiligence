"""Portable, read-only HTML report. Offline controls; escaped evidence; no approval tools."""
import base64
from hashlib import sha256
from html import escape
from .presentation import reading_guide, GLOSSARY, CATEGORY_LABELS
from .storage import review_state
from .manual import registry_tasks
from .research import public_url, PROFILE_FIELDS, SOURCE_FAMILIES

STYLE = """
:root{--ink:#203c4a;--muted:#526b78;--line:#dce7e8;--teal:#176f66;--paper:#fff;--bg:#f3f7f6}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.65 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}main{max-width:1060px;margin:auto;padding:32px 24px 70px}h1{font-size:clamp(26px,4vw,40px);line-height:1.2;letter-spacing:-.03em;margin:14px 0}h2{font-size:25px;letter-spacing:-.02em;margin:0 0 14px}h3{font-size:18px;margin:0 0 10px}p{margin:8px 0 14px}a{color:#126c71;text-underline-offset:3px;overflow-wrap:anywhere}header{padding:30px;border-radius:22px;background:#173f47;color:white}header .muted{color:#c6dadd}header p{max-width:780px}.eyebrow{font-size:12px;letter-spacing:.15em;text-transform:uppercase;font-weight:700}.muted,small{color:var(--muted)}small{font-size:13px}nav{display:flex;flex-wrap:wrap;gap:10px;padding:20px 0}nav a,button{border:1px solid var(--line);border-radius:30px;background:white;padding:9px 16px;text-decoration:none;font-size:14px;font-weight:600;color:var(--ink);cursor:pointer}.badge{display:inline-block;border-radius:30px;padding:4px 12px;background:#e7f3f0;color:#195f56;font-size:13px;font-weight:700}.urgent{background:#fbece9;color:#8c3934}.open{background:#fff1d8;color:#73511b}.done{background:#e7f3f0;color:#195f56}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.card,section{background:white;border:1px solid var(--line);border-radius:18px;padding:24px;margin-bottom:22px}.card{margin-bottom:0;border-top:4px solid #95bcb4}.card p{font-size:15px}.stats{display:flex;flex-wrap:wrap;gap:24px;padding:20px 0}.stat strong{display:block;font-size:25px}.stat span{font-size:14px;color:var(--muted)}details{background:white;border:1px solid var(--line);border-radius:12px;margin:12px 0;padding:16px 18px}summary{cursor:pointer;font-weight:650;line-height:1.5}summary .badge{margin-right:10px}blockquote{border-left:3px solid #a4c6bd;padding:12px 16px;margin:16px 0;background:#f4f8f7;white-space:pre-wrap;overflow-wrap:anywhere}input,select{font:inherit;color:var(--ink);padding:11px;border:1px solid #b6ccca;border-radius:9px;background:white;min-width:0;width:100%}.controls{display:grid;grid-template-columns:2fr 1fr 1fr;gap:12px;margin:16px 0}.controls label{font-size:13px;font-weight:600}.actions{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}li{padding:5px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.5 monospace;background:#f4f8f7;padding:16px;border-radius:10px}.source{border-top:1px solid var(--line);padding-top:16px;margin-top:16px;scroll-margin-top:20px}.notice{padding:14px 18px;background:#edf4f4;border-radius:12px;font-size:15px}.grid .card{height:100%}section{margin-top:24px;scroll-margin-top:20px}[hidden]{display:none!important}@media(max-width:720px){main{padding:16px 14px 40px}.grid,.controls{grid-template-columns:1fr}header,section{padding:21px}.card{padding:20px}body{font-size:16px}.stats{gap:20px}}@media print{body{background:white;font-size:11pt}main{max-width:none;padding:0}header{background:white;color:var(--ink);border:1px solid var(--line)}header .muted{color:var(--muted)}nav,.controls,.actions,.noprint{display:none}section,.card,details{break-inside:avoid}details>*{display:block!important}details[hidden]{display:block!important}.grid{grid-template-columns:repeat(3,1fr)}}
"""
SCRIPT = """'use strict';
const search=document.getElementById('report-search');const category=document.getElementById('category');const status=document.getElementById('evidence-state');const findings=Array.from(document.querySelectorAll('.finding'));
function filter(){let count=0;findings.forEach(item=>{const visible=item.textContent.toLowerCase().includes(search.value.toLowerCase())&&(!category.value||item.dataset.category===category.value)&&(!status.value||item.dataset.valid===status.value);item.hidden=!visible;if(visible)count++;});document.getElementById('result-count').textContent=count+' evidence items shown';}
[search,category,status].forEach(control=>control.addEventListener('input',filter));document.getElementById('expand').addEventListener('click',()=>findings.filter(item=>!item.hidden).forEach(item=>item.open=true));document.getElementById('collapse').addEventListener('click',()=>findings.forEach(item=>item.open=false));document.getElementById('print').addEventListener('click',()=>window.print());document.querySelectorAll('a[href^="#source-"],a[href^="#finding-"]').forEach(link=>link.addEventListener('click',()=>{const target=document.getElementById(link.getAttribute('href').slice(1));if(target)target.open=true;}));filter();
"""


def text(value): return escape(str(value), quote=True)


def source_link(source, label="Open source"):
    if public_url(source.url):
        return f'<a href="{text(source.url)}" target="_blank" rel="noopener noreferrer">{text(label)} ↗</a>'
    return '<span class="muted">' + text(source.url) + ' · embedded synthetic reference or unavailable public link</span>'


def build_html(a, reviews=None):
    reviews = reviews or []
    guide = reading_guide(a, reviews)
    state = review_state(a, reviews)
    refs = {source.id: index+1 for index, source in enumerate(a.sources)}
    digest = base64.b64encode(sha256(SCRIPT.encode()).digest()).decode()
    csp = f"default-src 'none'; style-src 'unsafe-inline'; script-src 'sha256-{digest}'; base-uri 'none'; form-action 'none'"
    out = [f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="{text(csp)}"><title>ClearDiligence — {text(a.company.name)}</title><style>{STYLE}</style></head><body><main>']
    mode = "SYNTHETIC DEMONSTRATION — all company and screening information is fictional" if a.mode == "Demo" else "LIVE RESEARCH — bounded public-source screening"
    out.append(f'<header><div class="eyebrow">ClearDiligence / company review</div><h1>{text(a.company.name)}</h1><p>{text(guide["headline"])}</p><span class="badge {"urgent" if guide["tier"] == "High" else "open" if guide["tier"] != "Low" else "done"}">Original risk: {text(guide["tier"])}</span><p class="muted">{text(a.company.country)} · {text(a.company.purpose)} · {text(a.created_at[:10])} (UTC)</p><small class="muted">{text(mode)}</small></header>')
    out.append('<nav aria-label="Report sections">'+''.join(f'<a href="#{key}">{label}</a>' for key,label in [('summary','At a glance'),('profile','Company'),('evidence','Evidence'),('actions','Next steps'),('sources','Sources'),('method','Scope'),('terms','Terms explained')])+'</nav>')
    out.append(f'<p class="notice">Read-only report · Human decision: <strong>{text(guide["decision"])}</strong>. Review actions can only be recorded in the application. Source support is not legal clearance.</p>')
    out.append(f'<section id="summary"><h2>What you need to know</h2><div class="stats"><div class="stat"><strong>{guide["checks_done"]} / 3</strong><span>research areas completed</span></div><div class="stat"><strong>{len(a.sources)}</strong><span>retrieved sources</span></div><div class="stat"><strong>{guide["followups"]}</strong><span>follow-up items</span></div></div><div class="grid">')
    for card in guide['cards']:
        out.append(f'<article class="card"><h3>{card["title"]}</h3><span class="badge {card["tone"]}">{card["status"]}</span><p>{text(card["detail"])}</p></article>')
    out.append('</div><details><summary>Why did the automated assessment reach this tier?</summary><ul>'+''.join('<li>'+text(reason)+'</li>' for reason in a.risk.reasons)+'</ul><small>The original tier does not change when an analyst records a separate decision.</small></details></section>')
    out.append('<section id="profile"><h2>Company at a glance</h2><p class="muted">Short, source-supported excerpts. Open a row for its full evidence.</p>')
    for field in a.company.research.fields:
        facts = sorted([f for f in a.findings if f.category == 'profile' and f.field == field and f.evidence_valid and f.relevance != 'Different entity'], key=lambda f:f.relevance!='Supported')
        if facts:
            f=facts[0]; value=f.extracted_value or f.claim
            preview=value[:240]+('…' if len(value)>240 else '')
            out.append(f'<details><summary>{text(PROFILE_FIELDS[field])}</summary><p>{text(preview)}</p><p><a href="#finding-{text(f.id)}">Inspect full evidence →</a></p></details>')
        else:
            out.append(f'<details><summary>{text(PROFILE_FIELDS[field])} <span class="badge open">Not established</span></summary><p>No supported detail was established within the selected research. This is an information gap, not evidence of wrongdoing.</p></details>')
    out.append('</section><section id="evidence"><h2>Explore the evidence</h2><p>Filter by topic or evidence support. Open any item to read the quote and inspect its sources.</p><div class="controls"><label>Search evidence<input id="report-search" type="search" placeholder="Company, person, phrase…"></label><label>Topic<select id="category"><option value="">All topics</option><option value="profile">Company details</option><option value="sanctions">Sanctions</option><option value="adverse_media">News and legal records</option></select></label><label>Evidence support<select id="evidence-state"><option value="">All items</option><option value="yes">Source-supported</option><option value="no">Needs evidence</option></select></label></div><div class="actions"><button id="expand" type="button">Expand visible items</button><button id="collapse" type="button">Collapse all</button><button id="print" type="button">Print report</button></div><p id="result-count" role="status" aria-live="polite"></p>')
    for f in a.findings:
        # Rejected proposals never enter the HTML, attributes, search index or previews.
        claim = f.claim if f.evidence_valid else 'Unsupported proposal withheld. More evidence is needed.'
        label = 'Source-supported' if f.evidence_valid else 'Needs evidence'
        out.append(f'<details class="finding" id="finding-{text(f.id)}" data-category="{f.category}" data-valid="{"yes" if f.evidence_valid else "no"}"><summary><span class="badge {"done" if f.evidence_valid else "open"}">{label}</span>{text(CATEGORY_LABELS[f.category])} · {text(claim[:155])}{"…" if len(claim)>155 else ""}</summary><p>{text(claim)}</p>')
        out.append(f'<p class="muted">Original status: {text(f.verification.value)} · Company relevance: {text(f.relevance)} · {text(f.nature)}</p>')
        if f.match != 'none': out.append(f'<p class="notice">Automated sanctions match: <strong>{text(f.match)}</strong>. A possible match is not confirmation of the target company.</p>')
        if f.evidence_valid:
            out.append('<blockquote>'+text(f.excerpt)+'</blockquote>')
            for sid in f.source_ids:
                if sid in refs: out.append(f'<p><a href="#source-{text(sid)}">[{refs[sid]}] Inspect retrieved source →</a></p>')
        review=state['latest'].get(f.id)
        out.append('<small>Human review: '+text(review.action if review else 'Not reviewed')+'</small></details>')
    out.append('</section><section id="actions"><h2>What happens next?</h2><ol>'+''.join('<li>'+text(step)+'</li>' for step in guide['next_steps'])+'</ol>')
    for task in registry_tasks(a):
        r=state['task_latest'].get(task.id)
        out.append(f'<details><summary>{text(task.title)} · {text(task.jurisdiction)} <span class="badge {"done" if r and r.action == "Completed" else "open"}">{text(r.action if r else "Pending")}</span></summary><p>{text(task.reason)}</p><p>Search terms: {text("; ".join(task.search_terms))}</p><ul>'+''.join('<li>'+text(i)+'</li>' for i in task.instructions)+'</ul></details>')
    if reviews:
        out.append('<details><summary>Recorded human review history</summary>')
        for r in reviews: out.append(f'<article><h3>{text(r.action)} · {text(r.analyst)}</h3><small>{text(r.at)} · Human-entered</small><p>{text(r.rationale)}</p></article>')
        out.append('</details>')
    out.append('</section><section id="sources"><h2>Source library</h2><p class="muted">A retrieved source is not automatically relevant to this company. Candidate-only records are marked below.</p>')
    for s in a.sources:
        valid = [f for f in a.findings if f.evidence_valid and s.id in f.source_ids]
        status = 'Supports '+str(len(valid))+' accepted observation(s)' if valid else 'Context or candidate source; no accepted company finding cites it'
        out.append(f'<details class="source" id="source-{text(s.id)}"><summary>[{refs[s.id]}] {text(s.title)}</summary><p>{text(status)}</p><p>{source_link(s)}</p><small>Published: {text(s.published_date)} · Retrieved: {text(s.retrieved_at)} · {"SYNTHETIC" if s.synthetic else text(s.content_type)}</small><details><summary>Read retained source text</summary><pre>{text(s.content)}</pre></details></details>')
    scope=a.company.research
    out.append('</section><section id="method"><h2>What this research covers</h2><p>Media and enforcement period: '+text(scope.start_date or 'Any date')+' to '+text(scope.end_date or 'Any date')+'. Company identity and OFAC screening use current sources.</p><p>Selected public sources: '+text(', '.join(SOURCE_FAMILIES.get(key,key) for key in scope.sources))+'. Selected specialist databases: '+text(', '.join(scope.databases) or 'None')+'.</p><p>US OFAC SDN screening is not worldwide watchlist coverage or an ownership-rule determination. Public search does not replace direct registry, legal, financial or on-site verification.</p>')
    for run in a.search_runs:
        out.append('<details><summary>'+text(run.label)+' · '+text(run.status)+'</summary><p>'+text(run.message)+'</p><pre>'+text(run.query)+'</pre>')
        for attempt in run.model_attempts:
            out.append('<p>'+text(attempt.model)+' · '+text(attempt.status)+' · credential slot: '+text(attempt.credential)+'</p>')
        out.append('</details>')
    out.append('</section><section id="terms"><h2>Terms, in plain language</h2>'+''.join('<details><summary>'+text(term)+'</summary><p>'+text(definition)+'</p></details>' for term,definition in GLOSSARY.items())+'</section>')
    out.append('<footer><p>Preliminary corporate screening, not a legal opinion or comprehensive investigation. Missing information is not misconduct. Original assessment '+text(a.id)+'. No external scripts, analytics or model requests run in this export.</p></footer></main><script>'+SCRIPT+'</script></body></html>')
    return ''.join(out)
