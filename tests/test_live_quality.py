from datetime import date
import json

import httpx

from cleardiligence.models import Assessment, CompanyInput, Finding, ResearchScope, SearchRun, Source, Verification
from cleardiligence.providers import ExtractedItem, Extraction, LiveResearch, TavilySearch
from cleardiligence.research import company_page_targets, jurisdiction_present
from cleardiligence.risk import assess_risk
from cleardiligence.validation import validate_evidence


def sample():
    return Assessment(company=CompanyInput(name="Example Vendor",country="United States",website="https://www.example.com",research=ResearchScope(sources=["company"])),mode="Live")


def fact(a,field,quote,url="https://example.com/about",value=""):
    source=Source(url=url,title="Company evidence",content=quote)
    a.sources.append(source)
    f=Finding(category="profile",field=field,claim=quote,excerpt=quote,extracted_value=value,source_ids=[source.id],relevance="Supported",verification=Verification.VERIFIED)
    a.findings.append(f)
    return f


def test_multiple_offices_and_paths_are_not_identity_conflicts():
    a=sample()
    fact(a,"business","Example Vendor is a United States contractor.")
    fact(a,"location","Headquartered in Chicago, Example Vendor has offices in Austin and New York.")
    fact(a,"location","Austin office: 123 Main Street, Austin, Texas.")
    fact(a,"website","https://www.example.com/")
    fact(a,"website","https://example.com/office/austin")
    validate_evidence(a)
    assert not any(f.validation_notes for f in a.findings)
    assert not any("conflicting" in gap for gap in a.gaps)
    a.coverage={k:"Complete" for k in ("entity","sanctions","media")}
    assert assess_risk(a).identity_confidence.startswith("Sufficient")


def test_genuinely_competing_registered_addresses_still_require_review():
    a=sample()
    fact(a,"location","Registered office: 12 Red Street, Richmond, Virginia.")
    fact(a,"location","Registered office: 70 Blue Street, Miami, Florida.")
    validate_evidence(a)
    assert all(f.requires_review and f.validation_notes for f in a.findings)


def test_markdown_rendering_preserves_supported_quote_and_negation():
    a=sample()
    f=fact(a,"leadership","**Jane Smith**, CEO of Example Vendor.")
    f.claim=f.excerpt=f.extracted_value="Jane Smith, CEO of Example Vendor."
    validate_evidence(a)
    assert f.evidence_valid
    f.claim=f.excerpt="Jane Smith, CFO of Example Vendor."
    validate_evidence(a)
    assert not f.evidence_valid
    f=fact(a,"ownership","Example Vendor is **not owned** by Rival Capital.")
    f.claim=f.excerpt="Example Vendor is owned by Rival Capital."
    validate_evidence(a)
    assert not f.evidence_valid


def test_page_targets_follow_only_observed_same_company_links():
    a=sample()
    a.sources=[Source(url="https://example.com",title="Company",content="[Team](/leadership/) [About](https://www.example.com/about/) [Investor](https://unrelated.example/investor) [Private](http://127.0.0.1/investor)")]
    urls=company_page_targets(a,{"leadership","ownership"})
    assert "https://example.com/leadership/" in urls and "https://www.example.com/about/" in urls
    assert all("127.0.0.1" not in url and "unrelated" not in url for url in urls)
    assert len(urls)<=4


def test_extract_retains_partial_url_failures_and_real_text():
    captured={}
    def handler(request):
        captured.update(json.loads(request.content))
        return httpx.Response(200,json={"results":[{"url":"https://example.com/about","raw_content":"Example Vendor is based in the United States."}],"failed_results":[{"url":"https://example.com/team","error":"unavailable"}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        sources,failed=TavilySearch(api_key="test",client=client).extract(["https://example.com/about","https://example.com/team"],"leadership")
    assert sources[0].content_type=="Retrieved page text (selected chunks)"
    assert failed==["https://example.com/team"]
    assert captured["chunks_per_source"]==5 and captured["query"]=="leadership"


def test_one_bad_profile_item_does_not_erase_good_core_identity():
    a=sample()
    class Search:
        def search(self,*args,**kwargs): return [Source(id="s",url="https://example.com",title="Example Vendor",content="Example Vendor is a United States contractor. Headquarters: Richmond, United States.")]
    class Model:
        def extract(self,*args):
            return Extraction(items=[ExtractedItem(field=field,source_id="s",value=quote,quote=quote,relation="same",relation_reason="Company identity",nature="Profile") for field,quote in [("business","Example Vendor is a United States contractor."),("location","Headquarters: Richmond, United States."),("ownership","Owned by Fabricated Capital")]])
    LiveResearch(Search(),Model()).entity(a)
    assert a.coverage["entity"].startswith("Complete")
    assert any(not f.evidence_valid for f in a.findings)
    assert any(r.rejected_findings_count and r.extraction_status=="Complete" for r in a.search_runs)


def test_missing_fields_trigger_bounded_extraction_without_relaxing_evidence():
    a=sample()
    class Search:
        calls=0
        def search(self,*args,**kwargs):
            return [Source(id="s",url="https://example.com",title="Example Vendor",content="Example Vendor is a United States contractor. Headquarters: Richmond, United States. [Leadership](/team)")]
        def extract(self,urls,query):
            self.calls+=1
            assert len(urls)<=4 and "https://example.com/team" in urls
            return [Source(id="team",url="https://example.com/team",title="Example Vendor team",content="Jane Smith, CEO of Example Vendor.")],[]
    class Model:
        def extract(self,company,sources,task):
            if sources[0].id=="team":
                return Extraction(items=[ExtractedItem(field="leadership",source_id="team",quote=sources[0].content,value=sources[0].content,relation="same",relation_reason="Linked company team page",nature="Profile")])
            return Extraction(items=[ExtractedItem(field=field,source_id="s",value=quote,quote=quote,relation="same",relation_reason="Name and jurisdiction",nature="Profile") for field,quote in [("business","Example Vendor is a United States contractor."),("location","Headquarters: Richmond, United States.")]])
    search=Search(); research=LiveResearch(search,Model()); research.entity(a)
    assert search.calls==1
    assert any(f.field=="leadership" and f.evidence_valid and f.relevance=="Supported" for f in a.findings)
    run=next(r for r in a.search_runs if r.retrieval_method=="Page extraction")
    assert run.trigger=="Missing profile fields" and run.requested_urls and run.retrieval_status=="Complete"
    research.entity(a,retry=True)
    assert search.calls==1


def test_ordinary_country_abbreviations_share_location_rules():
    assert jurisdiction_present("US","Chicago, Illinois")
    assert jurisdiction_present("UK","Registered in England")


def test_transient_model_error_retries_once_and_retains_observable_recovery(monkeypatch):
    monkeypatch.setattr("cleardiligence.providers.time.sleep",lambda _:None)
    class Search:
        def search(self,*args,**kwargs): return [Source(id="s",url="https://example.com",title="Example Vendor",content="Example Vendor is a United States contractor.")]
    class Model:
        calls=0
        def extract(self,*args):
            self.calls+=1
            if self.calls==1:
                request=httpx.Request("POST","https://generativelanguage.googleapis.com/v1beta/models/test:generateContent")
                raise httpx.HTTPStatusError("private error",request=request,response=httpx.Response(503,request=request))
            return Extraction(items=[])
    a=sample(); model=Model(); research=LiveResearch(Search(),model)
    research.collect(a,"Example Vendor","entity")
    assert model.calls==2 and a.search_runs[0].recovery_notes
    assert a.search_runs[0].extraction_status=="Complete"
    assert "private error" not in a.model_dump_json()


def test_persistent_model_outage_stops_repeating_paid_extraction_calls(monkeypatch):
    monkeypatch.setattr("cleardiligence.providers.time.sleep",lambda _:None)
    class Search:
        def search(self,*args,**kwargs): return [Source(id="s",url="https://example.com",title="Example Vendor",content="Example Vendor is a United States contractor.")]
    class Model:
        calls=0
        def extract(self,*args):
            self.calls+=1
            request=httpx.Request("POST","https://generativelanguage.googleapis.com/v1beta/models/test:generateContent")
            raise httpx.HTTPStatusError("private error",request=request,response=httpx.Response(503,request=request))
    a=sample(); model=Model(); research=LiveResearch(Search(),model)
    research.collect(a,"One query","entity"); research.collect(a,"Another query","entity")
    assert model.calls==2 and a.sources
    assert all(r.extraction_status=="Failed" for r in a.search_runs)
    assert "private error" not in a.model_dump_json()


def test_configured_gemini_fallback_is_used_and_audited(monkeypatch):
    from cleardiligence.providers import GeminiExtractor
    monkeypatch.setattr("cleardiligence.providers.time.sleep",lambda _:None)
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL","gemini-3-flash-preview")
    paths=[]
    def handler(request):
        paths.append(request.url.path)
        if "primary-model" in request.url.path: return httpx.Response(503)
        return httpx.Response(200,json={"candidates":[{"finishReason":"STOP","content":{"parts":[{"text":'{"items": []}'}]}}]})
    class Search:
        def search(self,*args,**kwargs): return [Source(url="https://example.com",title="Example Vendor",content="Example Vendor is a United States contractor.")]
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        a=sample(); research=LiveResearch(Search(),GeminiExtractor(api_key="test",model="primary-model",client=client))
        research.collect(a,"First","entity"); research.collect(a,"Second","entity")
    assert len(paths)==4 and "primary-model" in paths[0] and "primary-model" in paths[1]
    assert all("gemini-3-flash-preview" in path for path in paths[2:])
    assert a.search_runs[0].model_used=="gemini-3-flash-preview" and "fallback" in a.search_runs[0].recovery_notes[0]


def test_real_quote_cannot_be_misclassified_as_registration_or_ownership():
    a=sample()
    headquarters=fact(a,"registration","Example Vendor is headquartered in Chicago.",value="Chicago")
    legal_name=fact(a,"registration","Example Vendor, Inc.",value="Example Vendor, Inc.")
    merger=fact(a,"ownership","Other Company, a Parent Capital portfolio company, and Example Vendor announced they have merged.",value="Other Company")
    actual_owner=fact(a,"ownership","Example Vendor is wholly owned by Example Holdings.",value="Example Holdings")
    actual_registration=fact(a,"registration","Company registration number: DEMO-1234.",value="DEMO-1234")
    validate_evidence(a)
    assert not headquarters.evidence_valid and not legal_name.evidence_valid and not merger.evidence_valid
    assert actual_owner.evidence_valid and actual_registration.evidence_valid
