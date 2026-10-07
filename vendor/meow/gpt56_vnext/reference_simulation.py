"""General fixed-source Other calibration, sharing the production numeric scorer."""
import math
import numpy as np

from .benchmark import build_package, collection_contract
from .errors import AppError
from .simulation import CHUNK_SIZE, predictions, sample_matches
from .utils import atomic_write_json, canonical_json, finite_number, integer, sha256_text, strict_json_loads
from .virtual_reference import ALGORITHM, calibration_contract, reference_model


def calibrate_reference(package, options, root):
    other = reference_model(package)
    if not other:
        raise AppError('virtual_reference_required')
    models = package['fitted']['models']
    internal = [m for m in models if m != other]
    reference = package['collection']['virtual_reference']
    sources = internal + reference['sources']
    pool = {}
    for cid, cell in package['fitted']['cells'].items():
        pool[cid] = {m: cell['model_counts'][m] for m in internal}
        pool[cid].update(reference['counts'][cid])
    coverage = finite_number(options.get('selection_target', .995), 'selection_target', .5, 1)
    target = finite_number(options.get('target', .985), 'target', .5, coverage)
    cap = finite_number(options.get('threshold_cap', .98), 'threshold_cap', .01, .98)
    seed = integer(options.get('seed', 45301), 'seed', 0, 2**32-4)
    entries = {}
    for tier_index, tier in enumerate(('low','medium','high')):
        planned = package['tiers'][tier]['counts']
        total = integer(options.get('batches', {}).get(tier, 10000000), 'batches', len(sources)*100, 100000000)
        select_n = integer(options.get('selection_batches', 100000), 'selection_batches', 100, 1000000)
        allocations = {m: total//len(models) for m in internal}
        remainder = total - sum(allocations.values())
        for i, source in enumerate(reference['sources']):
            allocations[source] = remainder//len(reference['sources']) + int(i < remainder%len(reference['sources']))
        signature = sha256_text(canonical_json({'fitted':package['fitted'], 'pool':pool, 'planned':planned,
            'options':options, 'tier':tier, 'request':collection_contract(package), 'algorithm':ALGORITHM}))
        checkpoint = root / (tier + '.json')
        if checkpoint.exists():
            state = strict_json_loads(checkpoint.read_bytes())
            if state['signature'] != signature: raise AppError('simulation_checkpoint_mismatch')
        else:
            thresholds = dict.fromkeys(models, cap)
            for i, source in enumerate(sources):
                truth = source if source in internal else other
                rng = np.random.default_rng([seed+tier_index,0,i])
                own = []
                for start in range(0, select_n, CHUNK_SIZE):
                    own.append(sample_matches(package['fitted'], planned, source,
                        min(CHUNK_SIZE, select_n-start), rng, pool)[:,models.index(truth)])
                boundary = float(np.nextafter(np.sort(np.concatenate(own))[select_n-math.ceil(coverage*select_n)], -np.inf))
                if not 0 < boundary <= 1: raise AppError('simulation_threshold_unavailable',field=source)
                thresholds[truth] = min(thresholds[truth], boundary)
            state = {'signature':signature, 'thresholds':thresholds, 'source_index':0, 'done':0,
                'confusion':{s:dict.fromkeys(models+['insufficient'],0) for s in sources}}
            atomic_write_json(checkpoint,state)
        for i in range(state['source_index'],len(sources)):
            source = sources[i]
            rng = np.random.default_rng([seed+tier_index,1,i])
            if state.get('rng'): rng.bit_generator.state=state['rng']
            while state['done'] < allocations[source]:
                size = min(CHUNK_SIZE, allocations[source]-state['done'])
                matches = sample_matches(package['fitted'], planned, source, size, rng, pool)
                counts = np.bincount(predictions(matches,state['thresholds'],models),minlength=len(models)+1)
                for name,n in zip(models+['insufficient'],counts): state['confusion'][source][name]+=int(n)
                state['done']+=size;state['rng']=rng.bit_generator.state
                atomic_write_json(checkpoint,state)
            state['source_index']=i+1;state['done']=0;state.pop('rng',None)
            atomic_write_json(checkpoint,state)
        rates={s:state['confusion'][s][s if s in internal else other]/allocations[s] for s in sources}
        result={'status':'target_met' if min(rates.values())>=target else 'target_not_met',
            'counts':planned,'thresholds':state['thresholds'],'total_batches':total,
            'selection_coverage':coverage,'correct_target':target,'seed':seed+tier_index,
            'source_confusion':state['confusion'],'per_source_batches':allocations,'real_source_correct_rates':rates,
            'scope':'same-pool valid-answer simulation; not independent real validation',
            'selection_batches_per_real_source':select_n,'policy':{'hard_ceiling':cap},
            'other_sampling':'one real external source for all probes in each batch'}
        atomic_write_json(root/(tier+'-result.json'), result)
        package['tiers'][tier]['thresholds']=result['thresholds']
        entries[tier]={'algorithm':ALGORITHM,'status':result['status'],'thresholds':result['thresholds'],
            'total_batches':total,'target':target,'seed':seed+tier_index,
            'sample_scope':result['scope'],'result':result,
            'contract':calibration_contract(package,tier,result,collection_contract(package))}
    return build_package(package,package['observations'],collection=package['collection'],
                         calibration={'status':'complete','algorithm':ALGORITHM,'tiers':entries})
