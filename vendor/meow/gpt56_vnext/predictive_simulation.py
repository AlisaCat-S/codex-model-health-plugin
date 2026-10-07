"""Offline development/check splits and whole-path predictive calibration.

No provider calls. Original counts are partitioned, not augmented with samples.
The final development fit is checked on held-out observations without refitting.
"""
from collections import Counter
from copy import deepcopy
import hashlib
import math

import numpy as np

from .benchmark import build_package, cells_by_id, content_hash
from .errors import AppError
from .predictive import OTHER_ID, PredictiveScorer
from .predictive_calibration import ALGORITHM, contract
from .utils import atomic_write_json, canonical_json, integer, sha256_text, strict_json_loads


def rng_for(seed, *parts):
    digest = hashlib.sha256(canonical_json([seed, *parts]).encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], 'big'))


def valid_counts(window):
    return Counter({c: n for c, n in window['counts'].items() if c != '__INVALID_OUTPUT__' and n})


def partition(observations, sources, cells, policy, seed):
    """Three development folds plus one check; window roles never depend on answers."""
    groups, summary = {}, {}
    for cell in cells:
        groups[cell], summary[cell] = {}, {}
        for source in sources:
            windows = observations.get(cell, {}).get(source, {})
            ordered = sorted(windows, key=lambda w: (int(w) if w.isdecimal() else math.inf, w))
            if policy == 'windows':
                if len(ordered) < 4:
                    raise AppError('four_windows_required', field=f'{cell}/{source}')
                folds = [sum((valid_counts(windows[w]) for w in ordered[:-1][i::3]), Counter()) for i in range(3)]
                checking = valid_counts(windows[ordered[-1]])
            elif policy == 'within_window':
                counts = sum((valid_counts(windows[w]) for w in ordered), Counter())
                categories = sorted(counts)
                remaining = np.asarray([counts[c] for c in categories], dtype=np.int64)
                if remaining.sum() < 5:
                    raise AppError('samples_missing', field=f'{cell}/{source}')
                rng = rng_for(seed, cell, source, 'partition')
                picked = rng.multivariate_hypergeometric(remaining, math.ceil(remaining.sum() * .2))
                checking = Counter(dict(zip(categories, map(int, picked))))
                remaining -= picked
                folds = []
                for i in range(3):
                    picked = rng.multivariate_hypergeometric(remaining, int(remaining.sum()) // (3-i))
                    folds.append(Counter(dict(zip(categories, map(int, picked)))))
                    remaining -= picked
            else:
                raise AppError('invalid_split_policy')
            if any(not sum(values.values()) for values in [*folds, checking]):
                raise AppError('samples_missing', field=f'{cell}/{source}')
            assert sum(folds, checking.copy()) == sum((valid_counts(windows[w]) for w in ordered), Counter())
            groups[cell][source] = folds, checking
            summary[cell][source] = {'development': [sum(f.values()) for f in folds],
                                     'check': sum(checking.values()), 'original_windows': ordered}
    return groups, summary


def pools_from(groups, role, fold=None):
    result = {}
    for cell, sources in groups.items():
        result[cell] = {}
        for source, (folds, checking) in sources.items():
            values = checking if role == 'check' else folds[fold] if role == 'calibration' else (
                sum((f for i, f in enumerate(folds) if i != fold), Counter()))
            result[cell][source] = dict(values)
    return result


def fit_package(project, pools, collection, external):
    project, collection = deepcopy(project), deepcopy(collection)
    internal = [m['id'] for m in project['models']]
    observations = {c: {s: {'development': {'counts': pools[c][s], 'planned': sum(pools[c][s].values()),
                                           'completed': sum(pools[c][s].values())}} for s in internal} for c in pools}
    if external:
        project['engine']['virtual_reference_version'] = 2
        project['models'].append({'id': OTHER_ID, 'name': 'other', 'request_model': 'reference-only:other', 'reference_only': True})
        collection['external_models'] = deepcopy(external)
        collection['virtual_reference'] = {'id': OTHER_ID, 'method': 'fixed_source_predictive_v1',
            'sources': [m['id'] for m in external],
            'counts': {c: {m['id']: pools[c][m['id']] for m in external} for c in pools}}
    collection['fit_scope'] = 'Development folds only; held-out check counts are not fitted.'
    return build_package(project, observations, collection=collection)


def analyze_predictive(project, observations, collection, external):
    """Descriptive probe/source coverage and drift; no hidden allocation optimizer."""
    from .probability_model import js_divergence
    sources = [m['id'] for m in project['models']+external]
    pools = {c:{s:dict(sum((valid_counts(w) for w in observations[c][s].values()),Counter())) for s in sources}
             for c in cells_by_id(project)}
    fitted = fit_package(project,pools,collection,external)['fitted']
    result = {}
    for c,cell in fitted['cells'].items():
        distributions = {s:dict(zip(cell['categories'],[x/sum(cell['alpha'][s]) for x in cell['alpha'][s]])) for s in sources}
        pairs = [{'left':a,'right':b,'jsd':js_divergence(distributions[a],distributions[b])}
                 for i,a in enumerate(sources) for b in sources[i+1:]]
        drift = {}
        for s in sources:
            windows = [valid_counts(w) for w in observations[c][s].values()]
            windows = [{k:n/sum(w.values()) for k,n in w.items()} for w in windows if sum(w.values())]
            drift[s] = max((js_divergence(a,b) for i,a in enumerate(windows) for b in windows[i+1:]),default=0.0)
        result[c] = {'samples':cell['source_samples'],'pairs':sorted(pairs,key=lambda p:p['jsd']),
                     'maximum_window_drift':drift}
    return {'scoring_version':fitted['scoring_version'],'cells':result,
            'tier_requests':{t:sum(v['counts'].values()) for t,v in project['tiers'].items()},
            'note':'Descriptive analysis only. Compare candidate allocations at equal total requests before calibration.'}


def path_check(fitted, pool, planned, source, *, seed, batches, pattern='round_robin', thresholds=None):
    """One sampled answer sequence per run, shared between completion schedules."""
    rng = rng_for(seed, source, planned)
    cells = sorted(c for c, n in planned.items() if n)
    planned = {c: planned[c] for c in cells}
    answers = {}
    for c in cells:
        categories = fitted['cells'][c]['categories']
        counts = np.zeros(len(categories))
        unknown = categories.index('__UNSEEN_IN_TRAINING__')
        for category, n in pool[c][source].items():
            counts[categories.index(category) if category in categories else unknown] += n
        if counts.sum() == 0:
            raise AppError('samples_missing', field=f'{c}/{source}')
        answers[c] = rng.choice(len(categories), (batches, planned[c]), p=counts/counts.sum())
    masks = {c: rng.random((batches, planned[c])) >= (.2 if pattern == 'missing20' else 0) for c in cells}
    order = [(c, i) for i in range(max(planned.values())) for c in cells if i < planned[c]]
    if pattern.startswith('delayed:'):
        delayed = pattern.split(':', 1)[1]
        if delayed not in cells:
            raise AppError('invalid_delay_cell')
        order.sort(key=lambda event: event[0] == delayed)
    elif pattern == 'shuffled':
        rng.shuffle(order)
    elif pattern not in ('round_robin', 'missing20'):
        raise AppError('invalid_completion_pattern')
    draws = {c: np.zeros((batches, len(fitted['cells'][c]['categories'])), dtype=np.int64) for c in cells}
    scorer = PredictiveScorer(fitted, planned)
    truth = fitted['models'].index(source if source in fitted['models'] else OTHER_ID)
    negative = np.full((batches, len(fitted['models'])), .5)
    ever_wrong = np.zeros(batches, bool)
    ever_strong = np.zeros(batches, bool)
    qualified = np.zeros(batches, bool)
    accepted = np.zeros(batches, bool)
    winner = np.zeros(batches, dtype=int)
    full_true = np.zeros(batches)
    lines = np.asarray([thresholds[m] for m in fitted['models']]) if thresholds else None
    previous, prior_qualified = None, np.zeros(batches, bool)
    maximum_step = np.zeros(batches)
    for cell, index in order:
        active = np.flatnonzero(masks[cell][:, index])
        draws[cell][active, answers[cell][active, index]] += 1
        eligible = np.logical_and.reduce([draws[c].sum(axis=1) >= math.ceil(.6*planned[c]) for c in cells])
        if not eligible.any():
            continue
        matrix = scorer.matches(draws)[0]
        peak, winner = matrix.max(axis=1), matrix.argmax(axis=1)
        unique = (matrix == peak[:, None]).sum(axis=1) == 1
        qualified |= eligible
        if previous is not None:
            maximum_step = np.maximum(maximum_step, np.where(eligible & prior_qualified, np.abs(matrix-previous).max(axis=1), 0))
        previous, prior_qualified = matrix, eligible
        full_true = matrix[:, truth]
        for m in range(len(fitted['models'])):
            if m != truth:
                negative[:, m] = np.maximum(negative[:, m], np.where(eligible & unique & (winner == m), peak, .5))
        if lines is not None:
            accepted = eligible & unique & (peak > lines[winner])
            ever_wrong |= accepted & (winner != truth)
            ever_strong |= accepted
    outcomes = {'correct': int((accepted & (winner == truth)).sum()),
                'wrong': int((accepted & (winner != truth)).sum()), 'insufficient': int((~accepted).sum())}
    result = {'outcomes': outcomes, 'batches': batches, 'qualified': int(qualified.sum()),
        'any_prefix_wrong': int(ever_wrong.sum()), 'any_prefix_strong': int(ever_strong.sum()),
        'wrong_given_qualified': float(ever_wrong.sum()/qualified.sum()) if qualified.any() else None,
        'wrong_given_strong': float(ever_wrong.sum()/ever_strong.sum()) if ever_strong.any() else None,
        'maximum_qualified_step_change': float(maximum_step.max()),
        'p99_qualified_step_change': float(np.quantile(maximum_step,.99))}
    return negative, full_true, result


def calibrate_predictive(project, observations, collection, external, options, folder, progress=None):
    target, coverage = options.get('target', .99), options.get('selection_target', .999)
    if any(type(x) not in (float, int) or not .5 < x < 1 for x in (target, coverage)):
        raise AppError('invalid_simulation_target')
    if options.get('threshold_cap', .98) != .98:
        raise AppError('threshold_cap_must_be_98')
    path_limit = options.get('max_path_wrong',1-target)
    if type(path_limit) not in (int,float) or not 0 <= path_limit < .5:
        raise AppError('invalid_path_wrong_limit')
    identity = sha256_text(canonical_json({'project':project,'observations':observations,
                                          'collection':collection,'external':external,'options':options}))
    seed = integer(options.get('seed',45301),'seed',0,2**63-1)
    sources = [m['id'] for m in project['models'] + external]
    cells = cells_by_id(project)
    groups, summary = partition(observations, sources, cells, options.get('split_policy','windows'), seed)
    development, checking = pools_from(groups,'fit'), pools_from(groups,'check')
    final = fit_package(project, development, collection, external)
    cv = [(fit_package(project, pools_from(groups,'fit',i), collection, external), pools_from(groups,'calibration',i)) for i in range(3)]
    final['validation'] = {'status':'disjoint_records_not_blind', 'split_policy':options.get('split_policy','windows'),
        'partition':summary, 'input_observations_sha256':sha256_text(canonical_json(observations)),
        'independent_blind':False, 'notes':['Resampled counts; more simulations do not add real observations.']}
    final['calibration'] = {'status':'calibrated','tiers':{}}
    report = {'scoring_version':final['engine']['scoring_version'], 'scope':'development crossfit; exact final fit checked on disjoint counts; not new blind validation',
              'partition':summary, 'options':deepcopy(options), 'tiers':{}}
    for index,tier in enumerate(('low','medium','high')):
        checkpoint = folder / (tier+'.json')
        if checkpoint.exists():
            saved = strict_json_loads(checkpoint.read_bytes())
            if saved.get('input_sha256') != identity:
                raise AppError('simulation_checkpoint_mismatch')
            final['tiers'][tier]['thresholds'] = saved['thresholds']
            entry=saved['calibration']
            if entry['contract'] != contract(final,tier,entry['result']):
                raise AppError('simulation_checkpoint_mismatch')
            final['calibration']['tiers'][tier] = saved['calibration']
            report['tiers'][tier] = saved['report']
            if progress:progress({'tier':tier,'phase':'restored'})
            continue
        batches = integer(options.get('batches',{}).get(tier,10000),'batches',100,100000)
        planned = final['tiers'][tier]['counts']
        patterns = ['round_robin','missing20','shuffled'] + ['delayed:'+c for c,n in sorted(planned.items()) if n]
        models = final['fitted']['models']
        positive, negative = np.full(len(models),.98), np.full(len(models),.5)
        for fold,(package,pool) in enumerate(cv):
            for source in sources:
                truth = models.index(source if source in models else OTHER_ID)
                for pattern in patterns:
                    values,true_scores,_ = path_check(package['fitted'],pool,planned,source,seed=seed+index*100+fold,
                                                       batches=batches,pattern=pattern)
                    negative = np.maximum(negative,np.quantile(values,coverage,axis=0,method='higher'))
                    if pattern == 'round_robin':
                        positive[truth] = min(positive[truth],np.nextafter(np.quantile(true_scores,1-target,method='lower'),-np.inf))
                if progress:progress({'tier':tier,'phase':'calibration','fold':fold+1,'source':source})
        vendor = {m['id']: m.get('source_group') or m['request_model'].split('/')[0] for m in external}
        source_out = []
        for group in sorted(set(vendor.values())):
            held = [s for s,g in vendor.items() if g == group]
            retained = [m for m in external if m['id'] not in held]
            if not retained:
                continue  # No fictional source is substituted for the final external reference.
            package = fit_package(project,development,collection,retained)
            for source in held:
                for pattern in patterns:
                    values,_,_ = path_check(package['fitted'],development,planned,source,seed=seed+index*100+10,
                                            batches=batches,pattern=pattern)
                    negative = np.maximum(negative,np.quantile(values,coverage,axis=0,method='higher'))
            source_out.append((held,package))
            if progress:progress({'tier':tier,'phase':'source_out_calibration','group':group})
        lines = np.maximum(np.maximum(positive,.5),negative)
        thresholds = dict(zip(models,map(float,lines)))
        rows, checks = [], {}
        for source in sources:
            for pattern in patterns:
                _,_,metrics = path_check(final['fitted'],checking,planned,source,seed=seed+index*100+20,
                                         batches=batches,pattern=pattern,thresholds=thresholds)
                rows.append({'source':source,'pattern':pattern,**metrics})
                if pattern == 'round_robin':checks[source]=metrics['outcomes']
            if progress:progress({'tier':tier,'phase':'check','source':source})
        held_rows = []
        for held,package in source_out:
            for source in held:
                for pattern in patterns:
                    _,_,metrics = path_check(package['fitted'],checking,planned,source,seed=seed+index*100+30,
                                             batches=batches,pattern=pattern,thresholds=thresholds)
                    held_rows.append({'source':source,'pattern':pattern,**metrics})
        cases = [{'scope':scope,'source':r['source'],'pattern':r['pattern'],'batches':batches,
                  'qualified':r['qualified'],'wrong':r['any_prefix_wrong'],'strong':r['any_prefix_strong']}
                 for scope,group_rows in [('check',rows),('source_out',held_rows)] for r in group_rows]
        passed = (bool(np.all(lines<=.98)) and all(c['correct']/batches>=target for c in checks.values())
                  and all(not c['qualified'] or c['wrong']/c['qualified']<=path_limit for c in cases))
        # A failing >98% boundary is evidence, not a silently clipped usable threshold.
        final['tiers'][tier]['thresholds'] = thresholds if np.all(lines<=.98) else {}
        result = {'status':'target_met' if passed else 'target_not_met','counts':planned,
            'thresholds':thresholds, 'correct_target':target,'negative_path_coverage':coverage,
            'threshold_cap':.98,'seed':seed+index*100,'scope':report['scope'],
            'per_source_batches':dict.fromkeys(sources,batches),'source_outcomes':checks,
            'partial_verification':{'minimum_sample_ratio':.6,'same_answer_prefixes':True,
                'patterns':patterns,'batches_per_source':batches,
                'max_path_wrong':path_limit,'cases':cases,
                'maximum_any_prefix_wrong':max(c['wrong']/c['batches'] for c in cases),
                'maximum_wrong_given_qualified':max((c['wrong']/c['qualified'] for c in cases if c['qualified']),default=None),
                'denominator':'all simulated trajectories for raw rates; qualified trajectories for acceptance',
                'unchecked_source_out_groups':sorted(set(vendor.values())) if external and not source_out else []}}
        entry = {'algorithm':ALGORITHM,'result':result,'contract':contract(final,tier,result)}
        final['calibration']['tiers'][tier] = entry
        report['tiers'][tier] = {'status':result['status'],'required_thresholds':thresholds,
            'positive_lines':dict(zip(models,map(float,positive))), 'check':rows,'source_out_check':held_rows,
            'source_out_groups':sorted(set(vendor.values())) if source_out else [],
            'negative_coverage_scope':'per wrong class/source/pattern, not a joint error guarantee'}
        atomic_write_json(checkpoint,{'input_sha256':identity,'thresholds':final['tiers'][tier]['thresholds'],'calibration':entry,'report':report['tiers'][tier]})
        if progress:progress({'tier':tier,'phase':'complete','status':result['status']})
    final['content_sha256'] = content_hash(final)
    atomic_write_json(folder/'verification.json',report)
    return final, report
