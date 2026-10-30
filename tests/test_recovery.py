"""Bounded route recovery, evidence retention and no credential rotation for quota."""
import json
import httpx
import pytest
from cleardiligence.models import Assessment, CompanyInput, Source
from cleardiligence.providers import GeminiExtractor, LiveResearch
from cleardiligence.recovery import GeminiUnavailable


def response(text='{"items": []}'):
    return {"candidates":[{"finishReason":"STOP","content":{"parts":[{"text":text}]}}]}


def run_with(handler, monkeypatch, models="backup-one,backup-two", backup_key=""):
    monkeypatch.setenv('GEMINI_FALLBACK_MODELS',models)
    monkeypatch.setenv('GEMINI_BACKUP_API_KEY',backup_key)
    monkeypatch.setattr('cleardiligence.recovery.time.sleep',lambda _:None)
    source=Source(id='retrieved',url='https://example.com/',title='Example Vendor',content='Example Vendor is a United States contractor.')
    class Search:
        def search(self,*args,**kwargs): return [source]
    a=Assessment(company=CompanyInput(name='Example Vendor',country='United States'),mode='Live')
    client=httpx.Client(transport=httpx.MockTransport(handler))
    research=LiveResearch(Search(),GeminiExtractor(api_key='primary-secret',model='primary-model',client=client))
    return a,research,client


def test_two_unavailable_models_recover_third_and_reuse_healthy_route(monkeypatch):
    paths=[]
    def handler(request):
        paths.append(request.url.path)
        if 'primary-model' in request.url.path:return httpx.Response(503)
        if 'backup-one' in request.url.path:return httpx.Response(404)
        return httpx.Response(200,json=response())
    a,research,client=run_with(handler,monkeypatch)
    with client:
        research.collect(a,'query one','entity');research.collect(a,'query two','entity')
    assert len(paths)==5  # primary retry + two alternates + reuse successful model
    assert a.search_runs[0].model_used=='backup-two'
    assert [r.status for r in a.search_runs]==['Complete','Complete']
    assert [x.http_status for x in a.search_runs[0].model_attempts]==[503,503,404,None]
    assert 'primary-secret' not in a.model_dump_json()


def test_exhaustion_preserves_sources_and_cooldown_is_not_permanent_job_stop(monkeypatch):
    calls=[]
    healthy=[False]
    def handler(request):
        calls.append(request)
        return httpx.Response(200,json=response()) if healthy[0] else httpx.Response(503)
    a,research,client=run_with(handler,monkeypatch)
    with client:
        research.collect(a,'first','entity')
        assert len(calls)==5 and a.sources and a.search_runs[0].status=='Partial'
        research.collect(a,'during cooldown','entity')
        assert len(calls)==5 and not research.fatal_extraction_error
        research.extractor.cooldowns={}
        healthy[0]=True
        research.collect(a,'later recovered','entity')
    assert a.search_runs[-1].extraction_status=='Complete'
    assert not a.findings and a.search_runs[0].extraction_status=='Failed'


def test_rejected_primary_uses_only_configured_backup_authentication(monkeypatch):
    keys=[]
    def handler(request):
        keys.append(request.headers['x-goog-api-key'])
        return httpx.Response(401) if keys[-1]=='primary-secret' else httpx.Response(200,json=response())
    a,research,client=run_with(handler,monkeypatch,backup_key='backup-secret')
    with client:research.collect(a,'query','entity')
    assert keys==['primary-secret','backup-secret']
    assert a.search_runs[0].model_attempts[-1].credential=='backup'
    assert a.search_runs[0].status=='Complete'
    assert 'primary-secret' not in a.model_dump_json() and 'backup-secret' not in a.model_dump_json()


def test_quota_uses_model_fallback_not_backup_key_and_respects_long_retry_hint(monkeypatch):
    calls=[]
    def handler(request):
        calls.append(request)
        if 'primary-model' in request.url.path:return httpx.Response(429,headers={'Retry-After':'60'})
        return httpx.Response(200,json=response())
    a,research,client=run_with(handler,monkeypatch,backup_key='backup-secret')
    with client:research.collect(a,'query','entity')
    assert len(calls)==2 and all(r.headers['x-goog-api-key']=='primary-secret' for r in calls)
    assert a.search_runs[0].model_used=='backup-one'


@pytest.mark.parametrize('payload',[{'promptFeedback':{'blockReason':'SAFETY'}},response('not json'),response('{"items": [], "extra": true}')])
def test_safety_blocks_and_invalid_outputs_are_not_routed_around(monkeypatch,payload):
    calls=[]
    def handler(request):calls.append(request);return httpx.Response(200,json=payload)
    a,research,client=run_with(handler,monkeypatch)
    with client:research.collect(a,'query','entity')
    assert len(calls)==1 and a.sources and not a.findings
    assert a.search_runs[0].extraction_status=='Failed'


def test_fallback_ids_and_list_size_are_validated(monkeypatch):
    for value in ['https://evil.example/key','one,two,three,four']:
        monkeypatch.setenv('GEMINI_FALLBACK_MODELS',value)
        with pytest.raises(ValueError,match='model IDs'):GeminiExtractor(api_key='test')


def test_model_404_switches_without_repeat(monkeypatch):
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(404) if len(calls)==1 else httpx.Response(200,json=response())
    a,research,client=run_with(handler,monkeypatch)
    with client:research.collect(a,'query','entity')
    assert len(calls)==2 and a.search_runs[0].status=='Complete'


def test_transient_alternate_can_retry_without_exhausting_remaining_models(monkeypatch):
    calls=[]
    def handler(request):
        calls.append(request.url.path)
        if 'primary-model' in request.url.path:return httpx.Response(404)
        if len(calls)==2:return httpx.Response(503)
        return httpx.Response(200,json=response())
    a,research,client=run_with(handler,monkeypatch)
    with client:research.collect(a,'query','entity')
    assert len(calls)==3 and 'backup-one' in calls[1] and 'backup-one' in calls[2]
    assert a.search_runs[0].status=='Complete'


def test_google_invalid_key_400_uses_backup_but_schema_400_does_not(monkeypatch):
    calls=[]
    def handler(request):
        calls.append(request.headers['x-goog-api-key'])
        if calls[-1]=='primary-secret':return httpx.Response(400,json={'error':{'details':[{'reason':'API_KEY_INVALID'}]}})
        return httpx.Response(200,json=response())
    a,research,client=run_with(handler,monkeypatch,backup_key='backup-secret')
    with client:research.collect(a,'query','entity')
    assert calls==['primary-secret','backup-secret'] and a.search_runs[0].status=='Complete'
    a,research,client=run_with(lambda request:httpx.Response(400,json={'error':{'message':'schema invalid'}}),monkeypatch,backup_key='backup-secret')
    with client:research.collect(a,'query','entity')
    assert len(a.search_runs[0].model_attempts)==1 and a.search_runs[0].status=='Partial'


def test_request_budget_reserves_an_attempt_for_every_configured_model(monkeypatch):
    paths=[]
    def handler(request):paths.append(request.url.path);return httpx.Response(503)
    a,research,client=run_with(handler,monkeypatch,models='one,two,three')
    with client:research.collect(a,'query','entity')
    assert len(paths)==5 and all(any(model in path for path in paths) for model in ['primary-model','one','two','three'])
