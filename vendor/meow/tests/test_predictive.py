from copy import deepcopy
from pathlib import Path
import sys
import unittest

WORK = next(p for p in Path(__file__).resolve().parents if (p / 'gpt56_vnext').is_dir())
sys.path.insert(0, str(WORK))
from gpt56_vnext.benchmark import build_package, content_hash, load_package
from gpt56_vnext.errors import AppError
from gpt56_vnext.normalizers import normalize_answer
from gpt56_vnext.predictive import SCORING_VERSION, OTHER_ID
from gpt56_vnext.probability_model import score_counts


def fixture(reference=False):
    models = [{'id': m, 'name': m, 'request_model': m} for m in ('a', 'b')]
    engine = {'minimum_version': '4.5.3', 'scoring_version': SCORING_VERSION,
              'prior_mass': 1.0, 'completion_ratio': .6}
    collection = {'sources': []}
    if reference:
        models.append({'id': OTHER_ID, 'name': 'other', 'request_model': 'reference-only:other', 'reference_only': True})
        engine['virtual_reference_version'] = 2
        collection['virtual_reference'] = {'id': OTHER_ID, 'method': 'fixed_source_predictive_v1',
            'sources': ['provider/x'], 'counts': {'q': {'provider/x': {'third': 15}}}}
    project = {'id': 'fixture', 'version': '4.5.3-test', 'mode': 'gpt', 'engine': engine, 'models': models,
               'probes': [{'id': 'q', 'prompt': 'Choose a word.'}],
               'tiers': {t: {'counts': {'q': 5}, 'thresholds': {m['id']: .5 for m in models}}
                         for t in ('low', 'medium', 'high')}}
    observations = {'q': {m: {'window1': {'counts': {m: 20}, 'completed': 20, 'planned': 20}} for m in ('a', 'b')}}
    return build_package(project, observations, collection=collection)


class PredictiveTests(unittest.TestCase):
    def test_roundtrip_ordinary_and_real_external_reference(self):
        for reference in (False, True):
            package = fixture(reference)
            self.assertEqual(load_package(package), package)
            self.assertNotIn(OTHER_ID, package['observations']['q'])
            self.assertEqual(package['fitted']['cells']['q']['source_samples']['a'], 20)
            if reference:
                self.assertEqual(package['fitted']['cells']['q']['source_samples']['provider/x'], 15)

    def test_new_normalizer_keeps_noncompliant_answers(self):
        normalizer = fixture()['probes'][0]['normalizer']
        self.assertEqual(normalize_answer('  Not one of the choices.  ', normalizer), 'not one of the choices.')
        self.assertEqual(normalize_answer('99', normalizer), '99')
        self.assertEqual(normalize_answer(' ' , normalizer), '__INVALID_OUTPUT__')

    def test_same_60_percent_gate_and_partial_report(self):
        package = fixture()
        for n in (0, 2, 3, 5):
            result = score_counts(package['fitted'], {'q': {'a': n}}, {'q': 5}, {'a': .5, 'b': .5}, claimed_model='a')
            self.assertEqual(result['color'], 'green' if n >= 3 else 'yellow')
            self.assertEqual(result['valid_samples'], n)
            self.assertEqual(result['sample_policy']['per_cell_ratio'], .6)
            self.assertEqual(result['partial_samples'], n < 5)

    def test_threshold_cap_is_validated_not_clipped(self):
        package = fixture()
        package['tiers']['low']['thresholds']['a'] = .981
        package['content_sha256'] = content_hash(package)
        with self.assertRaises(AppError):
            load_package(package)

    def test_invalid_or_missing_reference_never_becomes_a_fake_sample(self):
        package = fixture(True)
        for mutate in ('fake-observation', 'unknown-count'):
            changed = deepcopy(package)
            if mutate == 'fake-observation':
                changed['observations']['q'][OTHER_ID] = {'w': {'counts': {'third': 1}}}
            else:
                changed['collection']['virtual_reference']['counts']['q']['provider/x']['third'] = -1
            changed['content_sha256'] = content_hash(changed)
            with self.assertRaises(AppError):
                load_package(changed)


if __name__ == '__main__':
    unittest.main()
