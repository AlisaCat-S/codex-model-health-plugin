import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

WORK=next(p for p in Path(__file__).resolve().parents if (p/'gpt56_vnext').is_dir())
sys.path[:0]=[str(WORK),str(WORK/'meow-web'),str(WORK/'versions/v4.5.1/tests')]
from test_benchmarks import fixture
from gpt56_vnext.benchmark import build_package, load_package, collection_contract
from gpt56_vnext.detector import calibration_matches
from gpt56_vnext.errors import AppError, RequestError, http_error_detail
from gpt56_vnext.security import SecretGuard
from gpt56_vnext.protocol import parse_stream
from gpt56_vnext.installation import unpack, verify
from gpt56_vnext.model_list import parse_models
from gpt56_vnext.reference_simulation import calibrate_reference
from gpt56_vnext.baseline_cli import BudgetTransport
from gpt56_vnext.store import SQLiteStateStore
try:
    from meow_web.protocol import parse_stream as web_parse
    from meow_web.security import SecretGuard as WebGuard
    from meow_web.errors import RequestError as WebError
    from meow_web.store import ReportStore
except ModuleNotFoundError:
    web_parse = None
PARSERS = [(parse_stream,SecretGuard,RequestError)]
if web_parse:PARSERS.append((web_parse,WebGuard,WebError))


def sse(events):return ''.join('data: '+json.dumps(e)+'\n\n' for e in events)
def created(id):return {'type':'response.created','response':{'id':id}}
def completed(id,text):return {'type':'response.completed','response':{'id':id,'status':'completed','output':[{'content':[{'type':'output_text','text':text}]}]}}


class ProtocolTests(unittest.TestCase):
    def test_done_marker_preserves_known_terminal_error(self):
        cases = [
            ('gpt', [{'type':'response.incomplete','response':{'id':'a','status':'incomplete',
                'incomplete_details':{'reason':'max_output_tokens'},'usage':{'output_tokens':128}}}], 'max_output_tokens'),
            ('claude', [{'type':'message_start','message':{'id':'a'}},
                {'type':'message_delta','delta':{'stop_reason':'max_tokens'},'usage':{'output_tokens':128}},
                {'type':'message_stop'}], 'max_tokens'),
        ]
        for parser,guard,error in PARSERS:
            for mode,events,reason in cases:
                with self.subTest(parser=parser.__module__,mode=mode):
                    with self.assertRaises(error) as got:
                        parser(sse(events)+'data: [DONE]\n\n',mode,guard())
                    self.assertEqual(got.exception.code,'response_token_limit')
                    self.assertEqual(got.exception.evidence['upstream']['reason'],reason)
                    self.assertEqual(got.exception.evidence['usage']['output_tokens'],128)
                    self.assertTrue(got.exception.evidence['saw_done_marker'])
                    self.assertFalse(got.exception.evidence['protocol_completed'])

    def test_done_marker_is_not_proof_of_completion(self):
        for parser,guard,error in PARSERS:
            for mode in ('gpt','claude','chat'):
                with self.subTest(parser=parser.__module__,mode=mode):
                    with self.assertRaises(error) as got:parser('data: [DONE]\n\n',mode,guard())
                    self.assertEqual(got.exception.code,'truncated_stream')

    def test_done_does_not_hide_last_failure_or_create_prior_fallback(self):
        events=[created('a'),completed('a','prior answer'),created('b'),{'type':'response.failed','response':{
            'id':'b','status':'failed','error':{'code':'server_error','message':'provider failed'}}}]
        for parser,guard,error in PARSERS:
            with self.assertRaises(error) as got:parser(sse(events)+'data: [DONE]\n\n','gpt',guard())
            self.assertEqual(got.exception.code,'upstream_response_failed')
            self.assertEqual(got.exception.public()['upstream']['message'],'provider failed')

    def test_final_text_is_authoritative_both_sides(self):
        events=[created('a'),{'type':'response.output_text.delta','delta':'cat'},completed('a','dog')]
        self.assertEqual(parse_stream(sse(events),'gpt',SecretGuard())['answer'],'dog')
        if web_parse:self.assertEqual(web_parse(sse(events),'gpt',WebGuard())['answer'],'dog')

    def test_last_failure_does_not_fall_back_and_preserves_message(self):
        events=[created('a'),completed('a','dog'),created('b'),{'type':'response.failed','response':{
            'id':'b','error':{'type':'server_error','code':'503','message':'provider busy'}}}]
        for parser,guard,error in PARSERS:
            with self.assertRaises(error) as got:parser(sse(events),'gpt',guard())
            self.assertEqual(got.exception.public()['upstream']['message'],'provider busy')

    def test_stream_status_and_http_are_distinct(self):
        with self.assertRaises(RequestError) as got:
            parse_stream(sse([{'type':'error','error':{'type':'rate_limit_error','message':'try later'}}]),'claude',SecretGuard())
        error=got.exception;error.status=200
        self.assertEqual(error.public()['http_status'],200)
        self.assertEqual(error.rate_status,429)

    def test_non_json_and_sensitive_error_text(self):
        message='failed user_id=123 account_id=345 secret-value person@example.com Authorization=Bearer-token'
        value=http_error_detail(message,SecretGuard(['secret-value']))
        for secret in ('secret-value','person@example.com','123','345','Bearer-token'):
            self.assertNotIn(secret,json.dumps(value))
        self.assertIn('failed',value['message'])
        self.assertLessEqual(len(http_error_detail('x'*4000,SecretGuard())['message']),2048)

    def test_model_list_is_data_and_deduplicated(self):
        self.assertEqual(parse_models(json.dumps({'data':[{'id':'a'},{'id':'a'},{'id':'b'}]}),SecretGuard()),{'models':['a','b']})
        with self.assertRaises(RequestError):parse_models('{}',SecretGuard())

    def test_canonical_protocol_copies(self):
        if not web_parse:self.skipTest('Website parity is checked in the combined workspace suite')
        for name in ('protocol.py','errors.py','security.py','model_list.py'):
            self.assertEqual((WORK/'gpt56_vnext'/name).read_text(),(WORK/'meow-web/meow_web'/name).read_text())
        for name in ('ui.js','style.css'):
            self.assertEqual((WORK/'gpt56_vnext/web'/name).read_text(encoding='utf-8'),(WORK/'meow-web/web'/name).read_text(encoding='utf-8'))


class SearchTests(unittest.TestCase):
    def test_local_all_records_cursor_literal_fields(self):
        with tempfile.TemporaryDirectory() as tmp, SQLiteStateStore(Path(tmp)/'state.sqlite3') as store:
            for i in range(27):
                store.create_session(session_id=str(i),kind='detection',status='complete',config={},config_hash='fixture',claimed_model='Claude-A',request_model='pool_%',safe_endpoint='https://example.test/v1',official=False)
            page=store.search_reports('claude');self.assertEqual(len(page['items']),20)
            self.assertEqual(len(store.search_reports('claude',page['before'])['items']),7)
            self.assertEqual(len(store.search_reports('%')['items']),20)
            self.assertEqual(store.search_reports('none')['items'],[])

    @unittest.skipUnless(web_parse, 'Website search is tested in the website suite')
    def test_web_search_model_and_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=ReportStore(Path(tmp)/'reports.sqlite3')
            try:
                for i in range(25):store.put({'id':str(i),'status':'complete','endpoint':'https://example.test/v1','claimed_model':'Astra','request_model':'pool_model'})
                for term in ('ASTRA','example','pool_'):
                    page=store.recent(query=term);self.assertEqual(len(page['items']),20)
                    self.assertEqual(len(store.recent(page['before'],term)['items']),5)
            finally:store.close()


class ToolsTests(unittest.TestCase):
    def test_other_generic_three_internal_and_replay(self):
        project,obs=fixture();project['models'].append({'id':'other_known_external','name':'Other','request_model':'reference-only:other','reference_only':True})
        project.pop('engine')
        collection={'sources':[], 'virtual_reference':{'id':'other_known_external','method':'equal_model_smoothed_internal_categories_v1','sources':['outside'],
                    'counts':{c:{'outside':{'external-answer':200}} for c in obs}}}
        package=build_package(project,obs,collection=collection)
        options={'batches':dict.fromkeys(('low','medium','high'),800),'selection_batches':200,'seed':45301,'target':.9,'selection_target':.95}
        with tempfile.TemporaryDirectory() as tmp:
            result=calibrate_reference(deepcopy(package),options,Path(tmp))
            self.assertTrue(all(calibration_matches(result,t) for t in result['tiers']))
            self.assertEqual(load_package(result),result)
            self.assertEqual(calibrate_reference(deepcopy(package),options,Path(tmp)),result)

    def test_budget_dispatch_is_shared_and_resume_preserves_it(self):
        class Fake:
            async def request(self,*args,on_dispatch,**kwargs):on_dispatch();return {'answer':'a'}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'budget.json';limits={'max_requests':2,'max_cost_usd':.2,'max_request_cost_usd':.1}
            first=BudgetTransport(Fake(),path,limits)
            asyncio.run(first.request(on_dispatch=lambda:None));asyncio.run(first.request(on_dispatch=lambda:None))
            second=BudgetTransport(Fake(),path,limits)
            with self.assertRaisesRegex(AppError,'collection_budget_exhausted'):
                asyncio.run(second.request(on_dispatch=lambda:None))
            self.assertEqual(second.ledger['sent'],2)

    def test_zip_traversal_and_verified_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'bad.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('../escape','bad')
            with self.assertRaises(AppError):unpack(archive,root/'bad','4.5.3','source')
            data=b'example'
            manifest={'schema':1,'version':'4.5.3','kind':'source','locale':'zh-CN','files':{'file.py':hashlib.sha256(data).hexdigest()}}
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('release/file.py',data);z.writestr('release/MEOW_INSTALL.json',json.dumps(manifest))
            unpack(archive,root/'good','4.5.3','source');verify(root/'good')


if __name__=='__main__':unittest.main()
