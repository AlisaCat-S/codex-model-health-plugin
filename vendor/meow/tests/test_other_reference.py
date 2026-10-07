import json
from copy import deepcopy
from pathlib import Path
import unittest
import numpy as np
from gpt56_vnext.benchmark import load_package,content_hash
from gpt56_vnext.detector import calibration_matches,build_single_jobs
from gpt56_vnext.errors import AppError
from gpt56_vnext.generator import collection_jobs,calibrate_package

ROOT=Path(__file__).resolve().parents[1]
class OtherReferenceTests(unittest.TestCase):
    def test_new_packages_validate_and_keep_counts(self):
        for path in (ROOT/'benchmarks/official').glob('*other-cap98*.meow.json'):
            p=load_package(path.read_bytes())
            self.assertTrue(p['models'][-1]['reference_only'])
            for tier,info in p['tiers'].items():
                self.assertTrue(calibration_matches(p,tier))
                self.assertTrue(all(v<=.98 for v in info['thresholds'].values()))
                jobs=build_single_jobs(p,tier,'actual-alias')
                self.assertEqual(len(jobs),sum(info['counts'].values()))
                self.assertTrue(all(j['model']=='actual-alias' for j in jobs))
            with self.assertRaises(AppError):collection_jobs(p,1,1)
            with self.assertRaises(AppError):calibrate_package(p,p['observations'],p['collection'],{})
            q=deepcopy(p);pid=next(iter(q['collection']['virtual_reference']['counts']))
            m=q['collection']['virtual_reference']['sources'][0];counts=q['collection']['virtual_reference']['counts'][pid][m]
            counts[next(iter(counts))]+=1;q['content_sha256']=content_hash(q)
            with self.assertRaises(AppError):load_package(q)

if __name__=='__main__':unittest.main()
