"""Replay stored Other calibration with one external source per whole batch."""
from pathlib import Path
import numpy as np
from gpt56_vnext.simulation import sample_matches,predictions
from gpt56_vnext.utils import atomic_write_json

def reproduce(package,tier,output,quick=False):
    entry=package['calibration']['tiers'][tier]['result']
    spec=package['collection']['virtual_reference'];virtual=spec['id']
    internal=[m['id'] for m in package['models'] if m['id']!=virtual]
    sources=internal+spec['sources'];models=package['fitted']['models']
    pool={p:{**cell['model_counts'],**spec['counts'][p]} for p,cell in package['fitted']['cells'].items()}
    results={}
    for index,source in enumerate(sources):
        count=min(2000,entry['per_source_batches'][source]) if quick else entry['per_source_batches'][source]
        rng=np.random.default_rng([entry['seed'],1,index]);counts=np.zeros(len(models)+1,dtype=np.int64)
        for start in range(0,count,8192):
            scores=sample_matches(package['fitted'],package['tiers'][tier]['counts'],source,min(8192,count-start),rng,pool)
            counts+=np.bincount(predictions(scores,entry['thresholds'],models),minlength=len(models)+1)
        results[source]=dict(zip(models+['insufficient'],map(int,counts)))
    if not quick and results!=entry['source_confusion']:raise RuntimeError('Stored Other verification differs')
    atomic_write_json(Path(output)/package['mode']/(tier+'.other.json'),{'scope':'quick' if quick else 'exact_verification','confusion':results})
    print(package['mode'],tier,'Other verification', 'quick' if quick else 'exact match',flush=True)
