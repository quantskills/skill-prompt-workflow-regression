"""Synthetic offline regression and local rollback; no API or model calls."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from regression import canonical_hash, freeze


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    out = Path(parser.parse_args().output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    tasks = [dict(id=str(i), split='development' if i<2 else 'holdout', input={'x': i},
                  rules=[{'path':['answer'], 'equals':i, 'type':'number'}]) for i in range(4)]
    suite = dict(tasks=tasks, model='synthetic-demo-no-model-call', model_parameters={'temperature':0},
                 evaluator='deterministic-json-rules-v1', min_repeats=3, max_cost_ratio=1.2)
    manifest = freeze(suite, out/'manifest.json')
    versions = dict(baseline='baseline', candidate='broken', suite_hash=manifest['suite_hash'],
                    version_hashes={v:canonical_hash(v) for v in ('baseline','broken')})
    runs = []
    for task in tasks:
        for version in ('baseline','broken'):
            for repeat in range(3):
                runs.append(dict(run_id=f"{task['id']}-{version}-{repeat}", task_id=task['id'],
                    version=version, repeat=repeat, model=suite['model'], model_parameters=suite['model_parameters'],
                    task_hash=manifest['task_hashes'][task['id']], version_hash=versions['version_hashes'][version],
                    platform_run_id=f'fixture:{version}:{repeat}', status='completed',
                    response=json.dumps({'answer':int(task['id'])}) if version=='baseline' else '{}',
                    cost=.01, tokens=100, latency_seconds=1))
    for name, value in [('suite',suite), ('versions',versions), ('state',{'active_version':'broken'}),
                        ('example-info',{'synthetic':True, 'network_used':False, 'purpose':'Local demonstration only'})]:
        (out/(name+'.json')).write_text(json.dumps(value, indent=2), encoding='utf-8')
    (out/'runs.jsonl').write_text('\n'.join(json.dumps(r) for r in runs)+'\n', encoding='utf-8')
    command = [sys.executable, '-X', 'utf8', str(Path(__file__).with_name('regression.py')), 'evaluate']
    for name in ('suite','manifest','versions','runs'):
        command.extend(['--'+name, str(out/(name+('.jsonl' if name=='runs' else '.json')))])
    subprocess.run(command+['--split','holdout','--output',str(out/'evaluation'),
                            '--local-state',str(out/'state.json')], check=True)
    print('SYNTHETIC DEMO ONLY:', out)


if __name__ == '__main__':
    main()
