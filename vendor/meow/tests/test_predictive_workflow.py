import asyncio
from collections import Counter
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

WORK = next(p for p in Path(__file__).resolve().parents if (p/'gpt56_vnext').is_dir())
sys.path.insert(0,str(WORK))
from gpt56_vnext.baseline_cli import BudgetTransport, collect, load_task, main, simulate, validate
from gpt56_vnext.benchmark import normalize_project, load_package
from gpt56_vnext.errors import AppError
from gpt56_vnext.predictive import SCORING_VERSION
from gpt56_vnext.predictive_simulation import partition, fit_package, calibrate_predictive, analyze_predictive, path_check
from gpt56_vnext.utils import atomic_write_json


def fixture(external=True):
    project = normalize_project({'id':'fixture','version':'0.1.0','mode':'gpt',
        'engine':{'minimum_version':'4.5.3','scoring_version':SCORING_VERSION,'prior_mass':1.,'completion_ratio':.6},
        'models':[{'id':s,'name':s,'request_model':s} for s in ('a','b','c')],
        'probes':[{'id':c,'prompt':'Name a word.'} for c in ('q1','q2')],
        'tiers':{t:{'counts':{'q1':5,'q2':5},'thresholds':{}} for t in ('low','medium','high')}})
    outside = [{'id':'external-x','name':'x','request_model':'provider/x'},
               {'id':'external-y','name':'y','request_model':'vendor/y'}] if external else []
    sources = [m['id'] for m in project['models']+outside]
    obs = {c:{s:{str(w):{'counts':{s:200},'planned':200,'completed':200} for w in range(1,5)} for s in sources} for c in ('q1','q2')}
    return project,outside,obs


class PredictiveWorkflowTests(unittest.TestCase):
    def test_plan_uses_v3_but_never_authorizes_collection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'task.json'
            main(['plan','--task',str(path),'--mode','gpt','--url','https://fixture.invalid/v1','--models','a','b'])
            task=load_task(path)
            self.assertEqual(task['task_version'],2)
            self.assertEqual(task['project']['engine']['scoring_version'],SCORING_VERSION)
            self.assertIsNone(task['collection']['max_requests'])
            self.assertIsNone(task['collection']['max_cost_usd'])

    def test_ordinary_and_other_exact_export_resume_and_failure(self):
        for external in (False,True):
            project,outside,obs=fixture(external)
            options={'batches':dict.fromkeys(('low','medium','high'),100),'target':.9,
                     'selection_target':.99,'threshold_cap':.98,'seed':12,'split_policy':'windows'}
            with self.subTest(external=external),tempfile.TemporaryDirectory() as tmp:
                folder=Path(tmp)
                package,report=calibrate_predictive(project,obs,{'sources':[]},outside,options,folder)
                output=folder/'package.meow.json';atomic_write_json(output,package)
                validate(output)
                self.assertEqual(load_package(package),package)
                self.assertEqual(calibrate_predictive(project,obs,{'sources':[]},outside,options,folder)[0],package)
                for tier in report['tiers'].values():
                    self.assertEqual(tier['status'],'target_met')
                    self.assertTrue(all(x['qualified']==100 for x in tier['check'] if x['pattern']=='round_robin'))
                    self.assertTrue(all(t<=.98 for t in tier['required_thresholds'].values()))
                if external:self.assertNotIn('other_known_external',package['observations']['q1'])
                failed=deepcopy(obs)
                for c in failed:
                    for s in failed[c]:failed[c][s]['4']['counts']={'identical-check-answer':200}
                new=folder/'changed';new.mkdir()
                candidate,report=calibrate_predictive(project,failed,{'sources':[]},outside,options,new)
                self.assertTrue(any(v['status']=='target_not_met' for v in report['tiers'].values()))
                atomic_write_json(output,candidate)
                with self.assertRaises(AppError):validate(output)
                for tier in project['tiers']:
                    self.assertEqual(package['tiers'][tier]['thresholds'],candidate['tiers'][tier]['thresholds'])
                with self.assertRaisesRegex(AppError,'simulation_checkpoint_mismatch'):
                    calibrate_predictive(project,failed,{'sources':[]},outside,options,folder)

    def test_partition_counts_are_disjoint_and_missing_is_not_filled(self):
        project,outside,obs=fixture()
        sources=list(obs['q1'])
        for policy in ('windows','within_window'):
            groups,summary=partition(obs,sources,obs,policy,9)
            for c in obs:
                for s in sources:
                    folds,check=groups[c][s]
                    self.assertEqual(sum(folds,check.copy()),Counter({s:800}))
        obs['q1']['a'].pop('4')
        with self.assertRaisesRegex(AppError,'four_windows_required'):partition(obs,sources,obs,'windows',9)
        with self.assertRaisesRegex(AppError,'invalid_split_policy'):partition(obs,sources,obs,'mystery',9)

    def test_analysis_uses_raw_counts_and_delay_is_same_answers(self):
        project,outside,obs=fixture()
        analysis=analyze_predictive(project,obs,{'sources':[]},outside)
        self.assertEqual(analysis['cells']['q1']['samples']['a'],800)
        pools={c:{s:{s:800} for s in obs[c]} for c in obs}
        package=fit_package(project,pools,{'sources':[]},outside)
        thresholds=dict.fromkeys(package['fitted']['models'],.5)
        previous=None
        for pattern in ('round_robin','shuffled','delayed:q1','delayed:q2'):
            _,_,metrics=path_check(package['fitted'],pools,{'q1':5,'q2':5},'a',seed=1,batches=100,
                                    pattern=pattern,thresholds=thresholds)
            self.assertEqual(metrics['outcomes']['correct'],100)
            self.assertEqual(metrics['any_prefix_wrong'],0)
            if previous:self.assertEqual(metrics['outcomes'],previous)
            previous=metrics['outcomes']

    def test_collect_to_v3_simulator_uses_common_pipeline(self):
        class Echo:
            async def request(self,mode,base,key,model,cell,*,on_dispatch,**kwargs):
                on_dispatch()
                return {'answer':model,'http_status':200,'usage':{'cost':0.0}}
            async def close(self):pass
        project,outside,_=fixture()
        task={'task_version':2,'base_url':'https://fixture.invalid/v1','project':project,'external_models':outside,
              'collection':{'windows':4,'samples':15,'workers':3,'retry_budget':0,'window_gap_seconds':0,
                            'max_requests':600,'max_cost_usd':1.,'max_request_cost_usd':.001},
              'simulation':{'batches':dict.fromkeys(('low','medium','high'),100),'target':.8,'selection_target':.95,
                            'threshold_cap':.98,'seed':3,'split_policy':'windows'}}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for w in range(1,5):
                result=asyncio.run(collect(task,root,w,'synthetic-only-secret',Echo()))
                self.assertEqual(result['status'],'complete')
            result=simulate(task,root)
            self.assertTrue(result['valid'])
            validate(root/'calibrated.meow.json')
            self.assertEqual(simulate(task,root),result)

    def test_cost_reconciliation_preserves_unknown_inflight_and_old_budget(self):
        class Echo:
            async def request(self,*,on_dispatch,**kwargs):on_dispatch();return {'usage':{'cost':.02}}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'budget.json'
            atomic_write_json(path,{'sent':2,'reserved_usd':.2,'in_flight':1,'charged_usd':0.,'unknown_cost_requests':1})
            client=BudgetTransport(Echo(),path,{'max_requests':3,'max_cost_usd':.3,'max_request_cost_usd':.1})
            asyncio.run(client.request(on_dispatch=lambda:None))
            self.assertEqual(client.ledger['unknown_cost_requests'],2)
            self.assertEqual(client.ledger['in_flight'],0)
            self.assertAlmostEqual(client.ledger['reserved_usd'],.22)
            self.assertAlmostEqual(client.ledger['charged_usd'],.02)
            with self.assertRaisesRegex(AppError,'collection_budget_exhausted'):asyncio.run(client.request(on_dispatch=lambda:None))


if __name__=='__main__':unittest.main()
