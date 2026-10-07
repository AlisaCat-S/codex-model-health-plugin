import asyncio
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=next(p for p in Path(__file__).resolve().parents if (p/'gpt56_vnext').is_dir())
sys.path[:0]=[str(ROOT),str(ROOT/'versions/v4.5.1/tests')]
from test_benchmarks import fixture
from test_execution import EchoModel,SECRET
from gpt56_vnext.benchmark import build_package
from gpt56_vnext.detector import DetectorSession
from gpt56_vnext.executor import detection_options
from gpt56_vnext.errors import RequestError
from gpt56_vnext.store import SQLiteStateStore

async def no_wait(_):pass
def options(budget):return {'base_url':'https://fixture.invalid/v1','claimed_model':'a','sample_ratio':.6,'runtime':{'workers':8,'retry_budget':budget}}
class Failing(EchoModel):
    async def request(self,*args,**kwargs):
        value=await super().request(*args,**kwargs)
        raise RequestError('response_incomplete',retryable=False)

class BudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_crash_with_exhausted_retry_still_allows_unsent_first_attempts(self):
        with tempfile.TemporaryDirectory() as folder,SQLiteStateStore(Path(folder)/'db') as store:
            package=build_package(*fixture());config=options(1)
            session=DetectorSession(store,'d',package,config,SECRET,transport=EchoModel())
            job=store.frozen_jobs('d',0)[0]
            attempt=store.start_attempt('d',job['job_id'],1,retry_budget=1)
            store.finish_attempt(attempt_id=attempt,status='error',stage='transport',category='connection_error',retryable=True,http_status=None,safe_message='connection_error',final_result={**job,'status':'error'},final_job_status='error')
            store.start_attempt('d',job['job_id'],2,retry_budget=1) # process died before receiving a response
            sender=EchoModel();session=DetectorSession(store,'d',package,config,SECRET,transport=sender)
            report=await session.run()
            self.assertEqual(sender.calls,8)
            self.assertEqual((report['progress']['retries'],report['progress']['logical_completed']),(1,9))

    async def test_invalid_answer_retention_covers_every_attempt(self):
        from test_retention_atomic import RecordedResponse
        class Invalid(RecordedResponse):
            async def request(self,*args,**kwargs):
                response=await super().request(*args,**kwargs);response['answer']='';return response
        with tempfile.TemporaryDirectory() as folder,SQLiteStateStore(Path(folder)/'db') as store:
            config=options(5);config['runtime']['retain_raw']=True
            sender=Invalid();session=DetectorSession(store,'d',build_package(*fixture()),config,SECRET,transport=sender)
            with patch('gpt56_vnext.executor.asyncio.sleep',no_wait):report=await session.run()
            self.assertEqual((sender.calls,report['progress']['valid_samples']),(14,0))
            self.assertEqual(store.retained_exchanges('d')['coverage'],{'attempts':14,'retained':14})
            self.assertTrue(all(row['category']=='__INVALID_OUTPUT__' for row in report['results']))

    async def test_default_and_concurrent_shared_limit(self):
        self.assertEqual(detection_options({},9)['retry_budget'],5)
        package=build_package(*fixture())
        for budget in [0,1,5,12]:
            with tempfile.TemporaryDirectory() as folder,SQLiteStateStore(Path(folder)/'db') as store:
                sender=Failing();session=DetectorSession(store,'d',package,options(budget),SECRET,transport=sender)
                with patch('gpt56_vnext.executor.asyncio.sleep',no_wait):report=await session.run()
                self.assertEqual((sender.calls,report['progress']['retries']),(9+budget,budget))
                self.assertEqual(report['progress']['logical_completed'],9)
                self.assertEqual(report['operational_status'],'complete')

    async def test_single_failure_has_no_per_question_cap(self):
        class OneBad(EchoModel):
            def __init__(self):super().__init__();self.order=[]
            async def request(self,*args,**kwargs):
                value=await super().request(*args,**kwargs);self.order.append(args[4]['id'])
                if self.calls==1 or self.calls>9:raise RequestError('invalid_answer')
                return value
        with tempfile.TemporaryDirectory() as folder,SQLiteStateStore(Path(folder)/'db') as store:
            config=options(5);config['runtime']['workers']=1;sender=OneBad()
            session=DetectorSession(store,'d',build_package(*fixture()),config,SECRET,transport=sender)
            with patch('gpt56_vnext.executor.asyncio.sleep',no_wait):report=await session.run()
            self.assertEqual(sender.calls,14)
            self.assertEqual(report['progress']['valid_samples'],8)
            self.assertEqual(sender.order[9:],[sender.order[0]]*5)

    async def test_cancel_and_resume_keep_actual_spending(self):
        class Interrupted(Failing):
            def __init__(self):super().__init__();self.ready=asyncio.Event();self.hold=asyncio.Event()
            async def request(self,*args,**kwargs):
                if self.calls==10:
                    kwargs['on_dispatch']();self.calls+=1;self.ready.set();await self.hold.wait()
                return await super().request(*args,**kwargs)
        with tempfile.TemporaryDirectory() as folder,SQLiteStateStore(Path(folder)/'db') as store:
            package=build_package(*fixture());config=options(5);config['runtime']['workers']=1;sender=Interrupted()
            session=DetectorSession(store,'d',package,config,SECRET,transport=sender)
            with patch('gpt56_vnext.executor.asyncio.sleep',no_wait):
                task=asyncio.create_task(session.run());await asyncio.wait_for(sender.ready.wait(),3)
                session.stop();await task
            self.assertEqual(store.progress('d')['retries'],2)
            again=Failing();resumed=DetectorSession(store,'d',package,config,SECRET,transport=again)
            with patch('gpt56_vnext.executor.asyncio.sleep',no_wait):report=await resumed.run()
            self.assertEqual(again.calls,3)
            self.assertEqual(report['progress']['retries'],5)
            self.assertEqual(report['progress']['logical_completed'],9)
            final=Failing()
            await DetectorSession(store,'d',package,config,SECRET,transport=final).run()
            self.assertEqual(final.calls,0)
