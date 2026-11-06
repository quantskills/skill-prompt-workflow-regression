import json
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).parents[1]/'scripts/local_scope.py'


def invoke(*args, raw=None):
    assert SCRIPT.exists(), 'Missing local controller entry point'
    return subprocess.run([sys.executable, '-X', 'utf8', str(SCRIPT), *map(str, args)],
                          input=raw, capture_output=True, timeout=20)


@pytest.mark.parametrize('round_number', [1, 2, 3])
def test_three_local_process_restart_scenarios(tmp_path, round_number):
    assets = tmp_path/'assets.json'
    assets.write_text(json.dumps({'current': {'kind':'document','text':f'round-{round_number}'}}))
    run = tmp_path/'run'
    init = invoke('init', '--assets', assets, '--directory', run)
    assert init.returncode == 0, init.stderr
    session = json.loads(init.stdout)['session_id']

    def call(name, tool='read_document', arguments=None, identity=None):
        raw = json.dumps({'session_id':identity or session, 'call_id':name,
                          'tool':tool, 'arguments':arguments or {'asset':'current'}}).encode()
        process = invoke('call', '--directory',run, raw=raw)
        assert process.returncode == 0, process.stderr
        return json.loads(process.stdout), raw

    first, raw = call('first')
    assert first['data'] == f'round-{round_number}'
    # Each invocation is a new OS process, not an in-memory resume.
    stale, _ = call('stale', identity='old-task')
    assert stale['status'] == 'denied'
    escaped, _ = call('escape', arguments={'asset':'../old/result.json'})
    assert escaped['status'] == 'denied'
    fake, _ = call('fake', tool='write_file', arguments={'path':'receipt.json','content':'passed'})
    assert fake['status'] == 'denied'
    resumed, _ = call('resumed')
    assert resumed['data'] == first['data']
    done, _ = call('done', tool='submit_result', arguments={'result':{'round':round_number}})
    assert done['status'] == 'ok'
    receipt = json.loads((run/'receipt.json').read_bytes())
    assert receipt['events'] == 6
    assert receipt['status'] == 'completed_ungraded'
    assert receipt['platform_run_id'] is None
    assert (run/'events/000001/request.bin').read_bytes() == raw
    assert invoke('verify','--directory',run).returncode == 0
    # Simulate abrupt termination after request is saved but before response.
    incomplete = run/'events/000007'
    incomplete.mkdir()
    (incomplete/'request.bin').write_bytes(b'{}')
    assert invoke('verify','--directory',run).returncode != 0
