from base64 import b64encode
from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
from streamlit.testing.v1 import AppTest
from cleardiligence.interactive_report import build_html, SCRIPT
from cleardiligence.models import Finding, Review, Source
from cleardiligence.presentation import reading_guide
from cleardiligence.report import build_pdf
from cleardiligence.workflow import run_demo


class ReportParser(HTMLParser):
    def __init__(self):super().__init__();self.ids=set();self.hrefs=[];self.scripts=0;self.forms=0
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if 'id' in attrs:self.ids.add(attrs['id'])
        if tag=='a':self.hrefs.append(attrs.get('href',''))
        if tag=='script':self.scripts+=1
        if tag=='form':self.forms+=1


def test_portable_report_has_working_anchor_targets_controls_and_hashed_script():
    a=run_demo('sanctions');report=build_html(a);parser=ReportParser();parser.feed(report)
    assert parser.scripts==1 and parser.forms==0
    assert all(href[1:] in parser.ids for href in parser.hrefs if href.startswith('#'))
    assert {'report-search','category','evidence-state','expand','collapse','print'}<=parser.ids
    assert "sha256-"+b64encode(sha256(SCRIPT.encode()).digest()).decode() in report
    assert 'SYNTHETIC DEMONSTRATION' in report and 'not confirmed as sanctioned' in report
    assert 'Read-only report' in report and 'cannot approve' not in SCRIPT


def test_html_escapes_injection_and_withholds_unsupported_claims():
    a=run_demo('low')
    a.company.name='<script>window.EVIL=1</script>'
    a.sources.append(Source(id='untrusted',title='<img src=x onerror=evil()>',url='javascript:evil()',content='<script>evil()</script>'))
    a.findings.append(Finding(category='profile',field='ownership',claim='UNSUPPORTED SECRET MODEL CLAIM',source_ids=['untrusted'],evidence_valid=False))
    report=build_html(a)
    assert '<script>window.EVIL' not in report and '&lt;script&gt;window.EVIL' in report
    assert '<img src=x' not in report and 'href="javascript:' not in report
    assert 'UNSUPPORTED SECRET MODEL CLAIM' not in report
    parser=ReportParser();parser.feed(report);assert parser.scripts==1


def test_incomplete_checks_do_not_turn_green_or_claim_clearance():
    a=run_demo('low');a.coverage['sanctions']='Unavailable'
    guide=reading_guide(a)
    assert guide['cards'][1]['status']=='Check incomplete' and guide['checks_done']==2
    assert any('incomplete' in step for step in guide['next_steps'])
    assert 'Check incomplete' in build_html(a)


def test_confirmed_human_match_has_escalation_and_separate_original_tier():
    a=run_demo('sanctions');finding=next(f for f in a.findings if f.match=='possible')
    r=Review(assessment_id=a.id,finding_id=finding.id,analyst='Human reviewer',action='Confirmed match',rationale='Controlled synthetic review of matching identifiers.')
    assert 'confirmed sanctions' in reading_guide(a,[r])['headline']
    assert 'Human reviewer' in build_html(a,[r])
    assert a.findings[a.findings.index(finding)].match=='possible'


def test_brief_pdf_preserves_critical_match_evidence_and_readability_sections():
    a=run_demo('sanctions');reader=PdfReader(BytesIO(build_pdf(a,brief=True)))
    text='\n'.join(page.extract_text() for page in reader.pages)
    for phrase in ['What this means','Possible name match','not confirmed as sanctioned','DEMONSTRATION ONLY','Evidence references','demo://']:
        assert phrase in text


def test_real_dashboard_exposes_plain_summary_and_html_download(tmp_path,monkeypatch):
    monkeypatch.setenv('CLEARDILIGENCE_DB',str(tmp_path/'ui.sqlite'))
    app=AppTest.from_file(Path(__file__).resolve().parents[1]/'app.py',default_timeout=30).run()
    app.button(key='demo_sanctions').click().run()
    assert not app.exception
    assert [tab.label for tab in app.tabs][:2]==['Summary','Company & findings']
    assert any('not confirmed as sanctioned' in m.value for m in app.markdown)
    assert any('What happens next?' in m.value for m in app.markdown)
    assert any('html_export' in str(button.key) for button in app.get('download_button'))


def test_human_resolved_namesake_does_not_request_resolution_again():
    a=run_demo('sanctions');f=next(f for f in a.findings if f.match=='possible')
    r=Review(assessment_id=a.id,finding_id=f.id,analyst='Human reviewer',action='False positive',rationale='Controlled fixture: identifiers belong to a different company.')
    guide=reading_guide(a,[r])
    assert 'different company' in guide['headline']
    assert guide['cards'][1]['status']=='Reviewed: different company'
    assert not any('Compare the sanctions' in step for step in guide['next_steps'])
    assert guide['tier']=='High'
