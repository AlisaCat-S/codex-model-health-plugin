import json
from pathlib import Path
import unittest
from gpt56_vnext.benchmark import load_package, cells_by_id
from gpt56_vnext.detector import calibration_matches
from gpt56_vnext.protocol import build_payload

ROOT=Path(__file__).resolve().parents[1]


class ChatPackages(unittest.TestCase):
    def test_derivatives_keep_numbers_and_provenance(self):
        for family in ('gpt','claude'):
            original=load_package((ROOT/f'benchmarks/official/meow-{family}-other-cap98-efficient--4.5.3-predictive.3.meow.json').read_bytes())
            package=load_package((ROOT/f'benchmarks/official/meow-{family}-chat-compatible--4.5.4-chat.1.meow.json').read_bytes())
            self.assertEqual(package['mode'],'chat')
            for key in ('observations','fitted','tiers'):
                self.assertEqual(original[key],package[key])
            self.assertEqual(package['collection']['protocol_derivation']['source_content_sha256'],original['content_sha256'])
            self.assertFalse(package['collection']['protocol_derivation']['new_sampling'])
            for tier in ('low','medium','high'):
                self.assertTrue(calibration_matches(package,tier))
            for cell in cells_by_id(package).values():
                payload=build_payload('chat','synthetic-model',cell)
                self.assertEqual(payload['max_tokens'],128)
                self.assertIn('messages',payload)
                self.assertNotIn('input',payload)
                self.assertNotIn('temperature',payload)


if __name__=='__main__':unittest.main()
