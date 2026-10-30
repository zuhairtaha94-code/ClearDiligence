from datetime import date
from io import BytesIO
import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError
from pypdf import PdfReader
from streamlit.testing.v1 import AppTest

from cleardiligence.models import Assessment, CompanyInput, ResearchScope, Source
from cleardiligence.providers import ExtractedItem, Extraction, GeminiExtractor, LiveResearch, TavilySearch
from cleardiligence.research import date_scope, plan_research, jurisdiction_present, name_present, safe_diagnostic

from cleardiligence.report import build_pdf
from cleardiligence.workflow import run_demo


def company(**kwargs):
    return CompanyInput(name="Example Vendor, Inc.",country="United States",website="https://example.com",**kwargs)


def test_scope_rejects_reversed_dates_and_empty_sources():
    with pytest.raises(ValidationError): ResearchScope(start_date=date(2025,1,1),end_date=date(2024,1,1))
    with pytest.raises(ValidationError): ResearchScope(sources=[])


def test_targeted_plan_keeps_profile_and_sanctions_current():
    c=company(research=ResearchScope(start_date=date(2021,1,1),end_date=date(2026,1,1),registry_jurisdiction="Virginia"))
    entity=plan_research(c)
    media=plan_research(c,"media")
    assert any(r.label=="Leadership" and r.domains==["example.com"] for r in entity)
    assert any(r.domains==["scc.virginia.gov"] for r in entity)
    assert any(r.domains==["sec.gov"] for r in entity)
    assert all(not r.start_date and not r.end_date for r in entity)
    assert any(r.domains==["justice.gov"] for r in media)
    assert all(r.start_date=="2021-01-01" and r.end_date=="2026-01-01" for r in media)
    assert "before%3A2026-01-02" in media[0].google_url


def test_scope_does_not_silently_search_unselected_families():
    c=company(research=ResearchScope(sources=["doj"]))
    assert plan_research(c)==[]
    runs=plan_research(c,"media")
    assert len(runs)==1 and runs[0].domains==["justice.gov"]


def test_search_filters_are_sent_to_provider_and_raw_text_is_used():
    captured={}
    def handler(request):
        captured.update(json.loads(request.content))
        return httpx.Response(200,json={"results":[{"url":"https://www.justice.gov/news","title":"Release","content":"Short snippet","raw_content":"Retrieved original release","published_date":"2025-02-01"}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result=TavilySearch(api_key="mock",client=client).search("Example enforcement",include_domains=["justice.gov"],start_date="2024-01-01",end_date="2026-01-01",max_results=4,search_depth="advanced")
    assert captured["include_domains"]==["justice.gov"] and captured["start_date"]=="2024-01-01"
    assert captured["filter_by_published_date"] and captured["include_raw_content"]
    assert result[0].content=="Retrieved original release" and result[0].content_type=="Retrieved page text"


def test_dates_in_structured_company_input_serialize_for_gemini():
    def handler(request):
        body=json.loads(request.content)
        assert '2021-01-01' in body["contents"][0]["parts"][0]["text"]
        return httpx.Response(200,json={"candidates":[{"finishReason":"STOP","content":{"parts":[{"text":'{"items": []}'}]}}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        GeminiExtractor(api_key="mock",client=client).extract(company(research=ResearchScope(start_date=date(2021,1,1))),[],"entity")


def test_identity_handles_legal_suffixes_country_abbreviations_and_states():
    assert name_present("Example Vendor, Inc.","Example Vendor management team")
    assert jurisdiction_present("United States","Chicago, Illinois headquarters")
    assert jurisdiction_present("United States","A U.S. company")
    assert not jurisdiction_present("US","A business in Canada")


def test_extraction_failure_preserves_sources_and_safe_diagnostics():
    class Search:
        def search(self,*args,**kwargs):
            return [Source(id="s1",title="Example Vendor",url="https://example.com",content="Example Vendor is a United States contractor.")]
    class BrokenModel:
        def extract(self,*args):
            request=httpx.Request("POST","https://generativelanguage.googleapis.com/v1beta/models/unavailable:generateContent")
            response=httpx.Response(404,request=request)
            raise httpx.HTTPStatusError("secret must not appear",request=request,response=response)
    a=Assessment(company=company(research=ResearchScope(sources=["company"])),mode="Live")
    LiveResearch(Search(),BrokenModel()).entity(a)
    assert a.sources and not a.findings
    assert any(r.status=="Partial" and "Gemini HTTP 404" in r.message for r in a.search_runs)
    assert "secret must not appear" not in a.model_dump_json()
    assert a.coverage["entity"].startswith("Partial")


def test_date_and_domain_postfilters_reject_out_of_scope_evidence():
    c=company(research=ResearchScope(sources=["doj"],start_date=date(2024,1,1),end_date=date(2026,1,1)))
    class Search:
        def search(self,*args,**kwargs):
            return [Source(title="Old release",url="https://www.justice.gov/old",content="Old allegation",published_date="2020-01-01"),Source(title="Wrong host",url="https://example.org/news",content="Out of scope",published_date="2025-01-01")]
    class Model:
        def extract(self,*args): raise AssertionError("Excluded sources must not be sent to the model")
    a=Assessment(company=c,mode="Live")
    LiveResearch(Search(),Model()).media(a)
    assert not a.sources and a.search_runs[0].status=="Complete"
    assert "No retrievable results" in a.search_runs[0].message


def test_undated_media_stays_explicitly_uncertain():
    c=company(research=ResearchScope(sources=["doj"],start_date=date(2024,1,1),end_date=date(2026,1,1)))
    quote="Example Vendor faces a United States enforcement allegation."
    class Search:
        def search(self,*args,**kwargs): return [Source(id="s1",title="Release",url="https://www.justice.gov/release",content=quote)]
    class Model:
        def extract(self,*args): return Extraction(items=[ExtractedItem(field="media",source_id="s1",value=quote,quote=quote,relation="same",relation_reason="Names and jurisdiction match",nature="Allegation")])
    a=Assessment(company=c,mode="Live")
    LiveResearch(Search(),Model()).media(a)
    assert a.sources[0].date_scope=="Undated, manual review"
    assert a.findings[0].verification.value=="Potential match" and a.findings[0].requires_review


def test_preview_search_plan_uses_real_form_scope_without_network(tmp_path,monkeypatch):
    monkeypatch.setenv("CLEARDILIGENCE_DB",str(tmp_path/"preview.db"))
    app=AppTest.from_file(Path(__file__).resolve().parents[1]/"app.py",default_timeout=30).run()
    app.button(key="nav_New assessment").click().run()
    app.radio(key="research_mode").set_value("Live").run()
    next(i for i in app.text_input if i.label=="Company name *").set_value("Example Vendor")
    app.multiselect(key="scope_sources").set_value(["company","doj"])
    next(b for b in app.button if b.label=="Preview search plan").click().run()
    assert not app.exception
    assert any("justice.gov" in code.value for code in app.code)
    assert not any("sec.gov" in code.value for code in app.code)
    assert any("Planned research" in h.value for h in app.markdown)


def test_pdf_uses_clear_unnumbered_section_headings():
    a=run_demo("sanctions")
    text="\n".join(page.extract_text() for page in PdfReader(BytesIO(build_pdf(a))).pages)
    assert "Executive assessment" in text and "Company profile" in text
    assert "01 /" not in text and "07 /" not in text


def test_query_updates_are_observable_without_private_model_reasoning():
    class Search:
        def search(self,*args,**kwargs): return []
    research=LiveResearch(Search(),object())
    updates=[]
    research.on_update=lambda stage,status,message: updates.append((stage,status,message))
    a=Assessment(company=company(research=ResearchScope(sources=["company"])),mode="Live")
    research.entity(a)
    assert any("Searching Company overview" in message for _,_,message in updates)
    assert any("No retrievable results" in message for _,_,message in updates)
