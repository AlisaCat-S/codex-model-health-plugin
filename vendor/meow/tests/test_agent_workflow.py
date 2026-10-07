import asyncio
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

WORK=next(p for p in Path(__file__).resolve().parents if (p/'gpt56_vnext').is_dir())
sys.path[:0]=[str(WORK),str(WORK/'versions/v4.5.1/tests')]
from test_benchmarks import fixture
from test_execution import EchoModel, SECRET
from gpt56_vnext.baseline_cli import collect, simulate, validate, import_legacy
from gpt56_vnext.agent_tasks import task_prompt
from gpt56_vnext.errors import AppError
from gpt56_vnext.utils import atomic_write_json
from gpt56_vnext.agent_tasks import KIT


class AgentWorkflowTests(unittest.TestCase):
    def test_collect_resume_simulate_export_both_modes(self):
        for other in (False,True):
            with self.subTest(other=other),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);project,_=fixture()
                task={'task_version':1,'base_url':'https://fixture.invalid/v1','project':project,
                      'external_models':[{'id':'outside','name':'Outside','request_model':'outside'}] if other else [],
                      'collection':{'samples':10,'windows':2,'workers':3,'retry_budget':0,'max_requests':300,
                                    'max_cost_usd':1,'max_request_cost_usd':.001},
                      'simulation':{'batches':dict.fromkeys(('low','medium','high'),800),
                                    'selection_batches':200,'seed':45301,'target':.9,'selection_target':.95}}
                fake=EchoModel()
                first=asyncio.run(collect(task,root,1,SECRET,fake));calls=fake.calls
                self.assertEqual(first['status'],'complete')
                asyncio.run(collect(task,root,1,SECRET,fake));self.assertEqual(fake.calls,calls)
                with self.assertRaisesRegex(AppError,'collection_window_gap_required'):
                    asyncio.run(collect(task,root,2,SECRET,fake))
                with patch('gpt56_vnext.baseline_cli.time.time',return_value=9999999999):
                    asyncio.run(collect(task,root,2,SECRET,fake))
                result=simulate(task,root);self.assertTrue(result['valid'])
                _,summary=validate(root/'calibrated.meow.json');self.assertTrue(all(summary['tiers'].values()))
                original=(root/'calibrated.meow.json').read_bytes()
                simulate(task,root);self.assertEqual((root/'calibrated.meow.json').read_bytes(),original)
                for file in root.rglob('*.json'):self.assertNotIn(SECRET,file.read_text(encoding='utf-8'))
                imported=import_legacy(root/'collection.sqlite3',root/'legacy')
                self.assertEqual(imported['collections'],2)

    def test_prompt_contains_no_key_and_blocks_credential_url(self):
        value=task_prompt({'base_url':'https://fixture.invalid/v1','mode':'gpt','models':['a','b']})
        self.assertIn('https://fixture.invalid/v1',value['prompt'])
        self.assertIn('采样授权',value['prompt'])
        with self.assertRaises(AppError):task_prompt({'base_url':'https://user:password@fixture.invalid/v1','mode':'gpt','models':['a','b']})

    def test_prompt_uses_actual_installation_and_output_paths(self):
        with tempfile.TemporaryDirectory(prefix='meow prompt space ') as tmp:
            for language in ('zh-CN','en'):
                value=task_prompt({'base_url':'https://fixture.invalid/v1','mode':'gpt','models':['a','b'],
                                  'key':'do-not-copy-this-value','application':'forged-installation'},data_root=tmp,locale=language)['prompt']
                self.assertIn(str(KIT.parent.parent.resolve()),value)
                self.assertIn(str(Path(tmp).resolve()/'baseline-work'),value)
                self.assertIn(sys.executable,value)
                for excluded in ('do-not-copy-this-value','forged-installation','{{'):
                    self.assertNotIn(excluded,value)

    def test_pilot_and_formal_share_campaign_budget_without_reset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);project,_=fixture()
            task={'project':project,'base_url':'https://fixture.invalid/v1','external_models':[],
                  'collection':{'samples':1,'windows':1,'workers':1,'retry_budget':0,'max_requests':9,
                                'max_cost_usd':.09,'max_request_cost_usd':.01,'campaign_budget_dir':str(root/'budget')}}
            pilot=root/'pilot';formal=root/'formal';pilot.mkdir();formal.mkdir();fake=EchoModel()
            first=asyncio.run(collect(task,pilot,1,SECRET,fake));self.assertEqual(first['budget']['sent'],9)
            second=asyncio.run(collect(task,formal,1,SECRET,fake));self.assertEqual(second['budget']['sent'],9)
            self.assertEqual(fake.calls,9)


if __name__=='__main__':unittest.main()
