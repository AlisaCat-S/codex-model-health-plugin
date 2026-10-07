"""Agent-facing baseline tools. Sampling requires a separate bounded authorization."""
from __future__ import annotations

import argparse
from contextlib import closing, nullcontext
import asyncio
from collections import Counter
from copy import deepcopy
import getpass
import json
from pathlib import Path
import sqlite3
import time

from .benchmark import build_package, cells_by_id, collection_contract, load_package, normalize_project
from .detector import calibration_matches
from .directory_lock import exclusive_directory
from .errors import AppError, RequestError
from .predictive import SCORING_VERSION
from .generator import ProbeGeneratorSession, analyze_selection, calibrate_package, merge_windows
from .security import SecretGuard
from .store import SQLiteStateStore
from .transport import AsyncTransport
from .utils import atomic_write_json, canonical_json, integer, normalize_api_base_url, sha256_text, strict_json_loads


def read(path):
    return strict_json_loads(Path(path).read_bytes())


def load_task(path):
    task = read(path)
    if task.get('task_version') not in (1,2):
        raise AppError('unsupported_task_version')
    task['base_url'] = normalize_api_base_url(task['base_url'], allow_insecure=task.get('allow_insecure') is True)
    task['project'] = normalize_project(task['project'], draft=True)
    if task['task_version'] == 2 and task['project']['engine']['scoring_version'] != SCORING_VERSION:
        raise AppError('task_scoring_version_mismatch')
    external = task.get('external_models', [])
    if external:
        augmented = normalize_project({**task['project'], 'models': task['project']['models'] + external}, draft=True)
        task['external_models'] = augmented['models'][len(task['project']['models']):]
        from .protocol import text
        for original,model in zip(external,task['external_models']):
            if 'source_group' in original:
                model['source_group'] = text(original['source_group'],'source_group',limit=256).strip()
                if not model['source_group']:
                    raise AppError('invalid_text',field='source_group')
    return task


def sampling_project(task):
    return normalize_project({**task['project'], 'models': task['project']['models'] + task.get('external_models', [])})


def sampling_signature(task):
    return sha256_text(canonical_json({'request': collection_contract(sampling_project(task)),
        'base': task['base_url'], 'collection': task['collection']}))


class BudgetTransport:
    def __init__(self, transport, ledger, limits):
        self.transport, self.path, self.limits = transport, ledger, limits
        self.ledger = read(ledger) if ledger.exists() else {'sent': 0, 'reserved_usd': 0.0}
        self.ledger.setdefault('charged_usd',0.0)
        self.ledger.setdefault('unknown_cost_requests',self.ledger['sent'])
        # A prior process may have died with requests in flight. Keep their reservations.
        self.ledger['unknown_cost_requests'] += self.ledger.get('in_flight',0)
        self.ledger['in_flight'] = 0
        integer(limits.get('max_requests'), 'max_requests', 1, 1000000)
        amount, per_request = limits.get('max_cost_usd'), limits.get('max_request_cost_usd')
        if amount is None or per_request is None:
            if not limits.get('request_limit_only'):
                raise AppError('pricing_or_request_limit_consent_required')
        elif not (type(amount) in (int, float) and type(per_request) in (int, float)
                  and 0 < per_request <= amount < float('inf')):
            raise AppError('invalid_cost_budget')

    async def request(self, *args, on_dispatch, **kwargs):
        dispatched, usage = False, {}
        cost = self.limits.get('max_request_cost_usd') or 0
        def dispatch():
            nonlocal dispatched
            if self.ledger['sent'] >= self.limits['max_requests'] or (
                    self.limits.get('max_cost_usd') is not None and
                    self.ledger['reserved_usd'] + cost > self.limits['max_cost_usd'] + 1e-12):
                raise AppError('collection_budget_exhausted')
            on_dispatch()
            self.ledger['sent'] += 1
            self.ledger['reserved_usd'] += cost
            self.ledger['in_flight'] += 1
            atomic_write_json(self.path, self.ledger)
            dispatched = True
        try:
            result = await self.transport.request(*args, on_dispatch=dispatch, **kwargs)
            usage = result.get('usage') or {}
            return result
        except RequestError as exc:
            usage = exc.evidence.get('usage') or {}
            raise
        finally:
            if dispatched:
                import math
                actual = usage.get('cost') if isinstance(usage,dict) else None
                self.ledger['in_flight'] -= 1
                if type(actual) in (int,float) and math.isfinite(actual) and actual >= 0:
                    self.ledger['charged_usd'] += actual
                    self.ledger['reserved_usd'] += actual - cost
                else:
                    self.ledger['unknown_cost_requests'] += 1
                atomic_write_json(self.path,self.ledger)

    async def close(self):
        await self.transport.close()


async def collect(task, root, window, key, transport=None):
    budget_dir=Path(task['collection'].get('campaign_budget_dir') or root).resolve()
    budget_dir.mkdir(parents=True,exist_ok=True)
    # Pilot/formal tasks may share one ledger; serialize them instead of overspending.
    with exclusive_directory(budget_dir) if budget_dir != root.resolve() else nullcontext():
        return await _collect(task, root, window, key, transport, budget_dir)


async def _collect(task, root, window, key, transport, budget_dir):
    limits = task['collection']
    integer(window, 'window', 1, integer(limits['windows'], 'windows', 1, 1000))
    project = sampling_project(task)
    guard = SecretGuard([key]); guard.check(task, code='credential_in_configuration')
    identity = sampling_signature(task)
    frozen = root / 'collection-contract.json'
    if frozen.exists() and read(frozen)['signature'] != identity:
        raise AppError('collection_contract_mismatch')
    if not frozen.exists():
        atomic_write_json(frozen, {'signature': identity, 'project': project})
    if window > 1:
        prior = root / f'window-{window-1}.json'
        if not prior.exists() or read(prior)['progress']['status'] != 'complete':
            raise AppError('previous_window_incomplete')
        from datetime import datetime
        ended = read(prior)['collection']['windows'][str(window-1)]['ended_at']
        gap = integer(limits.get('window_gap_seconds',60),'window_gap_seconds',0,86400)
        if time.time() - datetime.fromisoformat(ended).timestamp() < gap:
            raise AppError('collection_window_gap_required')
    with SQLiteStateStore(root / 'collection.sqlite3') as store:
        client = BudgetTransport(transport or AsyncTransport([key]), budget_dir / 'budget.json', limits)
        config = {'base_url': task['base_url'], 'allow_insecure': task.get('allow_insecure', False),
                  'samples': limits['samples'], 'window': window,
                  'runtime': {'workers': limits.get('workers', 3), 'retry_budget': limits.get('retry_budget', 0)}}
        session = ProbeGeneratorSession(store, f'{identity[:20]}-{window}', project, config, key, transport=client)
        try:
            report = await session.run()
            atomic_write_json(root / f'window-{window}.json', report)
            return {'status': report['progress']['status'], 'progress': report['progress'], 'budget': client.ledger}
        finally:
            await client.close()


def data_for_task(task, root):
    reports = [read(p) for p in sorted(root.glob('window-*.json'))]
    collected, observations, collection = merge_windows(reports)
    cells = cells_by_id(task['project'])
    collected_cells = cells_by_id(collected)
    for identity, cell in cells.items():
        if cell != collected_cells.get(identity):
            raise AppError('collected_probe_changed', field=identity)
    original_models = {m['id']: m for m in collected['models']}
    for model in task['project']['models'] + task.get('external_models', []):
        request_model={k:v for k,v in model.items() if k!='source_group'}
        if original_models.get(model['id']) != request_model:
            raise AppError('collected_model_changed')
    internal = {m['id'] for m in task['project']['models']}
    obs = {c: {m: v for m, v in observations[c].items() if m in internal} for c in cells}
    return obs, collection, observations


def prepare_package(task, root):
    observations, collection, all_observations = data_for_task(task, root)
    project = deepcopy(task['project'])
    external = task.get('external_models', [])
    if external:
        project.pop('engine', None)
        from .probability_model import INVALID_OUTPUT
        project['models'].append({'id': 'other_known_external', 'name': 'other',
                                 'request_model': 'reference-only:other', 'reference_only': True})
        counts = {}
        for c in cells_by_id(project):
            counts[c] = {}
            for model in external:
                merged = Counter()
                for window in all_observations[c].get(model['id'], {}).values():
                    merged.update({k: v for k, v in window['counts'].items() if k != INVALID_OUTPUT})
                if not merged:
                    raise AppError('external_samples_missing', field=model['id'])
                counts[c][model['id']] = dict(merged)
        collection['virtual_reference'] = {'id': 'other_known_external',
            'method': 'equal_model_smoothed_internal_categories_v1',
            'sources': [m['id'] for m in external], 'counts': counts}
        collection['external_models'] = external
    return build_package(project, observations, collection=collection)


def simulate(task, root, progress=None):
    if task.get('task_version') == 2:
        from .predictive_simulation import calibrate_predictive
        _observations, collection, all_observations = data_for_task(task,root)
        identity = sha256_text(canonical_json({'task':task,'observations':all_observations,'collection':collection}))
        folder = root/'simulations'/identity
        folder.mkdir(parents=True,exist_ok=True)
        atomic_write_json(folder/'contract.json',{'input_sha256':identity,'options':task['simulation']})
        package,report = calibrate_predictive(task['project'],all_observations,collection,
                                              task.get('external_models',[]),task['simulation'],folder,progress)
        passed = all(calibration_matches(package,t) for t in package['tiers'])
        atomic_write_json(root/'calibrated.meow.json',package)
        atomic_write_json(root/'simulation-report.json',{**report,'valid':passed})
        return {'package':str(root/'calibrated.meow.json'),'valid':passed,'scope':report['scope']}
    package = prepare_package(task, root)
    options = task['simulation']
    identity = sha256_text(canonical_json({'package': package['content_sha256'], 'options': options}))
    folder = root / 'simulations' / identity
    folder.mkdir(parents=True, exist_ok=True)
    if task.get('external_models'):
        from .reference_simulation import calibrate_reference
        package = calibrate_reference(package, options, folder)
    else:
        package = calibrate_package(package, package['observations'], package['collection'],
                                    options, checkpoint_root=folder)
    atomic_write_json(root / 'calibrated.meow.json', package)
    result = {'version': package['version'], 'calibration': package['calibration'],
              'valid': all(calibration_matches(package, t) for t in package['tiers']),
              'scope': 'same-pool valid-answer simulation; not independent real validation'}
    atomic_write_json(root / 'simulation-report.json', result)
    return {'package': str(root / 'calibrated.meow.json'), 'valid': result['valid']}


def validate(path):
    package = load_package(Path(path).read_bytes())
    passed = {tier: calibration_matches(package, tier) for tier in package['tiers']}
    if not all(passed.values()):
        raise AppError('benchmark_recalibration_required')
    return package, {'id': package['id'], 'version': package['version'], 'tiers': passed,
                     'content_sha256': package['content_sha256']}


def import_legacy(database, output):
    database = Path(database).resolve()
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        # Only explicitly non-secret project/report documents; never endpoint/vault data.
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        results = []
        if 'sessions' in tables:
            results = [json.loads(row[0]) for row in db.execute(
                "SELECT report_json FROM sessions WHERE kind='collection' AND report_json IS NOT NULL")]
        docs = []
        if 'documents' in tables:
            cols = {r[1] for r in db.execute('PRAGMA table_info(documents)')}
            value_column = 'body_json'
            if value_column not in cols:
                raise AppError('legacy_document_schema_unknown')
            docs = [dict(row) for row in db.execute(f"SELECT kind, {value_column} FROM documents WHERE kind IN ('project','simulation_result','simulation_task')")]
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output / 'legacy-work.json', {'collections': results, 'documents': docs})
    return {'file': str(output / 'legacy-work.json'), 'collections': len(results), 'documents': len(docs)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    plan = commands.add_parser('plan'); plan.add_argument('--task', required=True)
    plan.add_argument('--mode', choices=['gpt','claude','chat'], required=True)
    plan.add_argument('--url', required=True); plan.add_argument('--models', nargs='+', required=True)
    for name in ('collect', 'analyze', 'simulate', 'export'):
        p = commands.add_parser(name); p.add_argument('--task', required=True)
        if name == 'collect':
            p.add_argument('--window', type=int, required=True); p.add_argument('--confirmed', action='store_true')
        if name == 'export': p.add_argument('--output', required=True)
    p = commands.add_parser('validate'); p.add_argument('--package', required=True)
    p = commands.add_parser('import-legacy'); p.add_argument('--database', required=True); p.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    if args.command == 'validate': return validate(args.package)[1]
    if args.command == 'import-legacy': return import_legacy(args.database, args.output)
    path = Path(args.task).resolve()
    if args.command == 'plan':
        if path.exists(): raise AppError('task_already_exists')
        project = normalize_project({'id': 'my-baseline', 'version': '0.1.0', 'mode': args.mode,
            'engine':{'minimum_version':'4.5.3','scoring_version':SCORING_VERSION,'prior_mass':1.0,'completion_ratio':.6},
            'models': [{'id': f'm{i+1}', 'name': m, 'request_model': m} for i,m in enumerate(args.models)], 'probes': []}, draft=True)
        task = {'task_version': 2, 'base_url': normalize_api_base_url(args.url, allow_insecure=True),
                'allow_insecure': args.url.startswith('http://'), 'project': project, 'external_models': [],
                'collection': {'samples': 15, 'windows': 4, 'window_gap_seconds':60, 'workers': 3, 'retry_budget': 0,
                    'max_requests': None, 'max_cost_usd': None, 'max_request_cost_usd': None, 'request_limit_only': False},
                'simulation': {'batches': {t: 10000 for t in ('low','medium','high')},
                    'target': .99, 'selection_target': .999, 'max_path_wrong':.01,
                    'threshold_cap': .98, 'seed': 45301,'split_policy':'windows'}}
        atomic_write_json(path, task)
        return {'task': str(path), 'next': 'review probes, external models, targets and budget before collect'}
    task = load_task(path); root = path.parent / (path.stem + '.work'); root.mkdir(parents=True, exist_ok=True)
    with exclusive_directory(root):
        if args.command == 'collect':
            if not args.confirmed: raise AppError('collection_confirmation_required')
            import warnings
            warnings.simplefilter('error', getpass.GetPassWarning)
            key = getpass.getpass('API Key (local only): ')
            try: return asyncio.run(collect(task, root, args.window, key))
            finally: key = ''
        if args.command == 'analyze':
            observations, collection, all_observations = data_for_task(task, root)
            if task.get('task_version') == 2:
                from .predictive_simulation import analyze_predictive
                result = analyze_predictive(task['project'],all_observations,collection,task.get('external_models',[]))
            else:
                result = analyze_selection(task['project'], observations)
            atomic_write_json(root / 'analysis.json', result)
            return {'analysis': str(root / 'analysis.json')}
        if args.command == 'simulate':
            return simulate(task,root,lambda value: print(json.dumps({'progress':value},ensure_ascii=True),flush=True))
        if args.command == 'export':
            package, summary = validate(root / 'calibrated.meow.json')
            if Path(args.output).exists(): raise AppError('output_already_exists')
            atomic_write_json(Path(args.output), package)
            return {**summary, 'file': args.output}


if __name__ == '__main__':
    try:
        print(json.dumps(main(), ensure_ascii=False))
    except AppError as exc:
        print(json.dumps({'error': exc.public()}, ensure_ascii=False))
        raise SystemExit(2)
