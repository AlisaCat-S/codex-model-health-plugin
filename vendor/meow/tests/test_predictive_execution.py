import asyncio
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

WORK=next(p for p in Path(__file__).resolve().parents if (p/'gpt56_vnext').is_dir())
sys.path[:0]=[str(WORK),str(WORK/'meow-web')]
from gpt56_vnext import BUNDLED_BASELINES
from gpt56_vnext.benchmark import load_package
from gpt56_vnext.detector import DetectorSession
from gpt56_vnext.store import SQLiteStateStore
try:
    from meow_web.runner import Run
    from meow_web.store import ReportStore
except ModuleNotFoundError:
    Run=None

KEY='synthetic-flow-key-12345'


class Trace:
    def __init__(self,package,limit):
        source=package['fitted']['sources'][0]
        self.answers={c:cell['categories'][max(range(len(cell['categories'])),key=lambda i:cell['alpha'][source][i])]
                      for c,cell in package['fitted']['cells'].items()}
        self.limit,self.done,self.closed=limit,0,False
        self.waiting,self.hold=asyncio.Event(),asyncio.Event()

    async def request(self,mode,base,key,model,cell,*args,on_dispatch=None,**kwargs):
        if self.limit is not None and self.done>=self.limit:
            self.waiting.set();await self.hold.wait()
        (on_dispatch or args[0])()
        self.done+=1
        await asyncio.sleep(0)
        return {'answer':self.answers[cell['id']],'http_status':200,'usage':{'cost':0.0}}

    async def close(self):self.closed=True


class PredictiveExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_bundled_full_and_stopped_reports_across_both_runtimes(self):
        bundle=WORK/'gpt56_vnext/baselines'/BUNDLED_BASELINES
        manifest=json.loads((bundle/'manifest.json').read_bytes())
        for item in manifest['packages']:
            package=load_package((bundle/item['file']).read_bytes())
            claimed=package['models'][0]['id']
            for tier,plan in package['tiers'].items():
                minimum=sum(math.ceil(.6*n) for n in plan['counts'].values())
                for limit in (None,minimum,minimum-1):
                    desktop=None
                    for side in (('desktop','website') if Run else ('desktop',)):
                        with self.subTest(mode=package['mode'],tier=tier,limit=limit,side=side),tempfile.TemporaryDirectory() as tmp:
                            sender=Trace(package,limit)
                            value={'base_url':'https://fixture.invalid/v1','claimed_model':claimed,
                                   'request_model':'fixture-alias','tier':tier,'runtime':{'workers':1,'retry_budget':0}}
                            if side=='desktop':
                                store=SQLiteStateStore(Path(tmp)/'state.sqlite3')
                                store.create_session(session_id='old',kind='detection',status='complete',config={},config_hash='fixture',official=False)
                                store.save_report('old',{'legacy':'do not recalculate','version':'4.5.2'})
                                before=store.report('old')
                                run=DetectorSession(store,'new',package,value,KEY,transport=sender)
                                task=asyncio.create_task(run.run())
                            else:
                                store=ReportStore(Path(tmp)/'reports.sqlite3')
                                before={'id':'old','status':'complete','fingerprint':{'legacy':'do not recalculate'},'version':'4.5.2'}
                                store.put(before)
                                run=Run(package,{**value,'key':KEY,'workers':1,'retry_budget':0},'owner',store,sender)
                                task=asyncio.create_task(run.execute())
                            try:
                                if limit is not None:
                                    await asyncio.wait_for(sender.waiting.wait(),3)
                                    run.stop() if side=='desktop' else task.cancel()
                                await asyncio.wait_for(task,5)
                                report=run.report() if side=='desktop' else run.document()
                                fingerprint=report['fingerprint']
                                self.assertEqual(fingerprint['color'],'yellow' if limit==minimum-1 else 'green')
                                self.assertNotIn('uncalibrated',fingerprint['reasons'])
                                self.assertEqual(fingerprint['valid_samples'],limit or sum(plan['counts'].values()))
                                self.assertEqual(fingerprint['sample_policy']['overall_ratio'],.6)
                                self.assertNotIn(KEY,json.dumps(report))
                                self.assertEqual(store.report('old') if side=='desktop' else store.get('old'),before)
                                if side=='desktop':
                                    self.assertEqual(run.runner.key,'');self.assertTrue(sender.closed)
                                    desktop={k:v for k,v in fingerprint.items() if k!='partial'}
                                else:
                                    self.assertEqual(run.key,'')
                                    self.assertEqual({k:v for k,v in fingerprint.items() if k!='partial'},desktop)
                            finally:
                                if not task.done():task.cancel();await asyncio.gather(task,return_exceptions=True)
                                store.close()


if __name__=='__main__':unittest.main()
