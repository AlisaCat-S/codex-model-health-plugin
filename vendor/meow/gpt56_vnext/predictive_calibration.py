"""Integrity and measured-count contract for newly calibrated predictive packages."""
import math

from .predictive import SCORING_VERSION
from .utils import canonical_json, sha256_text

ALGORITHM = 'predictive-source-path-pcg64-v1'


def contract(package, tier, result):
    from .benchmark import collection_contract
    return sha256_text(canonical_json({'algorithm': ALGORITHM, 'engine': package['engine'],
        'request_signature': collection_contract(package), 'fitted': package['fitted'],
        'collection': package['collection'], 'validation':package.get('validation',{}),
        'tier': package['tiers'][tier], 'result': result}))


def calibration_matches(package, tier):
    try:
        entry = package['calibration']['tiers'][tier]
        result = entry['result']
        fitted = package['fitted']
        models, sources = fitted['models'], fitted['sources']
        thresholds = package['tiers'][tier]['thresholds']
        target = result['correct_target']
        if (fitted['scoring_version'] != SCORING_VERSION or entry['algorithm'] != ALGORITHM
                or result['status'] != 'target_met' or result['counts'] != package['tiers'][tier]['counts']
                or result['thresholds'] != thresholds or set(thresholds) != set(models)
                or type(target) not in (int, float) or not .5 <= target <= 1
                or set(result['source_outcomes']) != set(sources)
                or set(result['per_source_batches']) != set(sources)):
            return False
        if any(type(t) not in (float, int) or not math.isfinite(t) or not .5 <= t <= .98 for t in thresholds.values()):
            return False
        for source in sources:
            n = result['per_source_batches'][source]
            counts = result['source_outcomes'][source]
            if (type(n) is not int or n <= 0 or set(counts) != {'correct', 'wrong', 'insufficient'}
                    or any(type(k) is not int or k < 0 for k in counts.values()) or sum(counts.values()) != n):
                return False
            if counts['correct'] / n < target:
                return False
        partial = result['partial_verification']
        if (partial['minimum_sample_ratio'] != .6 or not partial['same_answer_prefixes']
                or not partial['patterns'] or partial['batches_per_source'] <= 0):
            return False
        limit = partial['max_path_wrong']
        if type(limit) not in (float,int) or not 0 <= limit < .5 or not partial['cases']:
            return False
        seen = set()
        for case in partial['cases']:
            identity = (case['scope'],case['source'],case['pattern'])
            n,qualified,wrong,strong = (case[k] for k in ('batches','qualified','wrong','strong'))
            if (identity in seen or any(type(k) is not int for k in (n,qualified,wrong,strong))
                    or not 0 <= wrong <= strong <= qualified <= n or n <= 0 or qualified and wrong/qualified > limit):
                return False
            seen.add(identity)
        if not all(('check',s,p) in seen for s in sources for p in partial['patterns']):
            return False
        return entry['contract'] == contract(package, tier, result)
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
