"""Validated, read-only external reference mixtures for imported research packages."""
from collections import Counter
import math

from .errors import AppError
from .probability_model import distribution, fit_observations
from .utils import canonical_json, sha256_text

ALGORITHM = "research-other-fixed-source-empirical-pcg64-v1"


def reference_model(project):
    virtual = [m for m in project['models'] if m.get('reference_only')]
    if len(virtual) > 1:
        raise AppError('invalid_virtual_reference')
    return virtual[0]['id'] if virtual else None


def fit_reference(project, observations, cells, collection):
    identity = reference_model(project)
    spec = collection.get('virtual_reference', {})
    internal = [m['id'] for m in project['models'] if m['id'] != identity]
    if not identity or spec.get('id') != identity or spec.get('method') != 'equal_model_smoothed_internal_categories_v1':
        raise AppError('invalid_virtual_reference')
    sources = spec.get('sources')
    counts = spec.get('counts')
    if (not isinstance(sources, list) or not 1 <= len(sources) <= 32
            or any(not isinstance(s, str) or not s or len(s) > 256 for s in sources)
            or len(set(sources)) != len(sources) or set(sources) & set(internal)
            or not isinstance(counts, dict) or set(counts) != set(cells)):
        raise AppError('invalid_virtual_reference')
    if any(identity in models for models in observations.values()):
        raise AppError('virtual_reference_has_observations')
    fitted = fit_observations(observations, internal, cells)
    for cell_id, cell in fitted['cells'].items():
        if not isinstance(counts[cell_id], dict) or set(counts[cell_id]) != set(sources):
            raise AppError('invalid_virtual_reference')
        probabilities = []
        for source in sources:
            raw = counts[cell_id][source]
            if not isinstance(raw, dict) or len(raw) > 10000 or not raw:
                raise AppError('invalid_virtual_reference')
            mapped = Counter()
            for category, number in raw.items():
                if (not isinstance(category, str) or len(category.encode('utf-8')) > 4096
                        or category == '__INVALID_OUTPUT__' or type(number) is not int or not 0 <= number <= 100000000):
                    raise AppError('invalid_virtual_reference')
                mapped[category if category in cell['categories'] else '__OTHER__'] += number
            if sum(mapped.values()) <= 0:
                raise AppError('invalid_virtual_reference')
            probabilities.append(distribution(mapped, cell['categories']))
        cell['model_distributions'][identity] = {
            c: sum(p[c] for p in probabilities) / len(probabilities) for c in cell['categories']}
    fitted['models'] = [m['id'] for m in project['models']]
    return fitted


def calibration_contract(package, tier, result, request_signature):
    return sha256_text(canonical_json({
        'algorithm': ALGORITHM, 'request_signature': request_signature,
        'fitted': package['fitted'], 'counts': package['tiers'][tier]['counts'],
        'reference': package['collection']['virtual_reference'], 'result': result,
    }))


def calibration_matches(package, tier, request_signature):
    try:
        entry = package['calibration']['tiers'][tier]
        result = entry['result']
        identity = reference_model(package)
        internal = [m['id'] for m in package['models'] if m['id'] != identity]
        sources = internal + package['collection']['virtual_reference']['sources']
        models = internal + [identity]
        if (entry.get('algorithm') != ALGORITHM or result['status'] != 'target_met'
                or result['counts'] != package['tiers'][tier]['counts']
                or result['thresholds'] != package['tiers'][tier]['thresholds']
                or set(result['thresholds']) != set(models)
                or set(result['source_confusion']) != set(sources)
                or set(result['per_source_batches']) != set(sources)
                or not .5 <= result['correct_target'] <= 1
                or not result['correct_target'] <= result['selection_coverage'] <= 1):
            return False
        total = 0
        for source in sources:
            cm = result['source_confusion'][source]
            batches = result['per_source_batches'][source]
            if (type(batches) is not int or batches <= 0 or set(cm) != set(models + ['insufficient'])
                    or any(type(n) is not int or n < 0 for n in cm.values()) or sum(cm.values()) != batches):
                return False
            truth = source if source in internal else identity
            rate = cm[truth] / batches
            if rate < result['correct_target'] or rate != result['real_source_correct_rates'][source]:
                return False
            total += batches
        if total != result['total_batches']:
            return False
        if any(not math.isfinite(v) or not 0 < v <= .98 for v in result['thresholds'].values()):
            return False
        return entry['contract'] == calibration_contract(package, tier, result, request_signature)
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
