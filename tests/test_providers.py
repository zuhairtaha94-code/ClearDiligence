from types import SimpleNamespace
import httpx
import pytest
from cleardiligence.models import Assessment, CompanyInput, Source
from cleardiligence.providers import parse_ofac, name_similarity, OFACScreening, LiveResearch, Extraction, ExtractedItem, TavilySearch, ClaudeExtractor
from cleardiligence.validation import validate_evidence


def fixture_files():
    return {"sdn.csv": '100,"OTHER HOLDINGS",-0-,DEMO,-0-,-0-,-0-,-0-,-0-,-0-,-0-,"registration 123"\n', "alt.csv": '100,1,aka,"Atlas Infrastructure Partners",-0-\n', "add.csv": '100,1,"Main Street","Dubai",-0-,"United Arab Emirates",-0-\n', "sdn_comments.csv": '100,"additional identifier 456"\n'}


def test_ofac_joins_alias_address_and_spillover():
    r = parse_ofac(fixture_files())[0]
    assert r["aliases"] == ["Atlas Infrastructure Partners"]
    assert "Dubai" in r["addresses"][0]
    assert "456" in r["remarks"]


def test_ofac_alias_screening_never_auto_confirms():
    files = fixture_files()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=files[request.url.path.split("/")[-1]], headers={"last-modified": "Fri, 16 Oct 2026 12:00:00 GMT"}))
    a = Assessment(company=CompanyInput(name="Atlas Infrastructure Partners", country="United States"), mode="Live")
    with httpx.Client(transport=transport) as client:
        OFACScreening(client=client).screen(a, [])
    validate_evidence(a)
    assert a.findings[0].match == "possible" and a.findings[0].evidence_valid
    assert len(a.screening_metadata["files"]) == 4
    assert "456" in a.findings[0].claim


def test_ofac_html_is_not_a_clean_screen():
    files = fixture_files()
    files["sdn.csv"] = "<html>Access denied</html>"
    with pytest.raises(ValueError):
        parse_ofac(files)


def test_matching_handles_token_order_and_blank_nonlatin():
    assert name_similarity("Atlas Infrastructure Partners", "Partners, Atlas Infrastructure") == 1
    assert name_similarity("公司", "公司") == 0


def test_tavily_rejects_unsafe_urls_and_does_not_use_generated_answer():
    payload = {"answer": "Invented data", "results": [{"title": "Company", "url": "https://example.com", "content": "Retrieved excerpt"}, {"url": "javascript:alert(1)", "content": "Unsafe"}]}
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload))) as client:
        result = TavilySearch(api_key="test", client=client).search("company")
    assert len(result) == 1 and result[0].content == "Retrieved excerpt"


def test_extraction_filters_unsupported_claims():
    s = Source(id="s1", title="Company", url="https://example.com", content="Example Vendor operates in the United States.")
    class Search:
        def search(self, *args, **kwargs): return [s]
    class Extract:
        def extract(self, *args):
            return Extraction(items=[ExtractedItem(field="ownership", source_id="s1", value="Owned by Made Up Capital", quote=s.content, relation="same", relation_reason="Name and jurisdiction", nature="Profile")])
    a = Assessment(company=CompanyInput(name="Example Vendor", country="United States"), mode="Live")
    LiveResearch(Search(), Extract()).entity(a)
    assert not a.findings[0].evidence_valid
    assert a.coverage["entity"].startswith("Partial")


def test_claude_adapter_parses_typed_output_and_disables_retries():
    captured = {}
    class Messages:
        def parse(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(stop_reason="end_turn", parsed_output=Extraction(items=[]))
    client = SimpleNamespace(messages=Messages())
    extractor = ClaudeExtractor(client=client)
    result = extractor.extract(CompanyInput(name="Example Vendor", country="United States"), [], "entity")
    assert result.items == []
    assert captured["output_format"] == Extraction
    assert "untrusted" in captured["system"]


def test_ofac_handles_actual_dos_end_of_file_marker():
    files = fixture_files()
    files["sdn.csv"] += "\x1a"
    files["alt.csv"] += "\x1a"
    assert parse_ofac(files)[0]["uid"] == "100"


def test_country_acronym_cannot_match_substring_of_business():
    s=Source(id="s1",title="Company",url="https://example.com",content="Example Vendor is a business in Canada.")
    class Search:
        def search(self,*args,**kwargs): return [s]
    class Extract:
        def extract(self,*args):
            return Extraction(items=[ExtractedItem(field="business",source_id="s1",value=s.content,quote=s.content,relation="same",relation_reason="Unreliable model identification",nature="Profile")])
    a=Assessment(company=CompanyInput(name="Example Vendor",country="US"),mode="Live")
    LiveResearch(Search(),Extract()).entity(a)
    assert a.findings[0].relevance=="Potential"


def test_full_quote_preserves_negation():
    s=Source(id="s1",title="Company",url="https://example.com",content="Example Vendor in the United States is not owned by Rival Capital.")
    class Search:
        def search(self,*args,**kwargs): return [s]
    class Extract:
        def extract(self,*args):
            return Extraction(items=[ExtractedItem(field="ownership",source_id="s1",value="owned by Rival Capital",quote=s.content,relation="same",relation_reason="Explicit company name and country",nature="Profile")])
    a=Assessment(company=CompanyInput(name="Example Vendor",country="United States"),mode="Live")
    LiveResearch(Search(),Extract()).entity(a)
    assert "not owned" in a.findings[0].claim


def test_unknown_source_reference_is_rejected():
    s=Source(id="s1",title="Company",url="https://example.com",content="Example Vendor in the United States.")
    class Search:
        def search(self,*args,**kwargs): return [s]
    class Extract:
        def extract(self,*args):
            return Extraction(items=[ExtractedItem(field="business",source_id="invented",value=s.content,quote=s.content,relation="same",relation_reason="Claimed match",nature="Profile")])
    a=Assessment(company=CompanyInput(name="Example Vendor",country="United States"),mode="Live")
    LiveResearch(Search(),Extract()).entity(a)
    assert not a.findings and any("unknown source" in gap for gap in a.gaps)


def test_nonlatin_name_fails_explicitly_instead_of_clean_screen():
    a=Assessment(company=CompanyInput(name="公司",country="China"),mode="Live")
    with pytest.raises(ValueError,match="Latin-script"):
        OFACScreening().screen(a,[])


def test_mocked_live_workflow_end_to_end():
    from cleardiligence.workflow import Orchestrator
    s=Source(id="live-evidence",title="Mock official company page",url="https://example.com/vendor",content="Example Vendor is a United States contractor. Example Vendor is located in Richmond, United States.")
    class Search:
        def search(self,*args,**kwargs): return [s.model_copy(update={"id":str(len(args))+args[0][-12:]})]
    class Extract:
        def extract(self,company,sources,task):
            if task=="media": return Extraction(items=[])
            return Extraction(items=[ExtractedItem(field=field,source_id=sources[0].id,value=quote,quote=quote,relation="same",relation_reason="Target name and jurisdiction in the source",nature="Profile") for field,quote in [("business","Example Vendor is a United States contractor."),("location","Example Vendor is located in Richmond, United States.")]])
    files=fixture_files()
    with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,text=files[request.url.path.split("/")[-1]]))) as client:
        a=Orchestrator(LiveResearch(Search(),Extract()),OFACScreening(client=client)).run(CompanyInput(name="Example Vendor",country="United States"),"Live")
    assert a.completed and a.risk.tier.value=="Low"
    assert all(not source.synthetic for source in a.sources)
    assert len(a.screening_metadata["files"])==4


def test_website_metadata_candidate_is_grounded_but_never_auto_official():
    s=Source(id="s1",title="Company profile",url="https://example.com/",content="Example Vendor is a contractor in the United States.")
    class Search:
        def search(self,*args,**kwargs): return [s]
    class Extract:
        def extract(self,*args):
            return Extraction(items=[ExtractedItem(field="website",source_id="s1",value=s.url,quote=s.url,relation="same",relation_reason="Retrieved company website candidate",nature="Profile")])
    a=Assessment(company=CompanyInput(name="Example Vendor",country="United States"),mode="Live")
    LiveResearch(Search(),Extract()).entity(a)
    f=a.findings[0]
    assert f.evidence_valid and f.verification.value=="Potential match" and f.requires_review
    f.claim=f.excerpt=f.extracted_value="https://invented.example/"
    validate_evidence(a)
    assert not f.evidence_valid
