import json
from pathlib import Path
import subprocess
import sys


def test_demo_detects_decline_and_rolls_back_without_platform_claim(tmp_path):
    script = Path(__file__).parents[1] / 'scripts' / 'demo.py'
    out = tmp_path / 'demo'
    proc = subprocess.run([sys.executable, str(script), '--output', str(out)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    report = json.loads((out / 'evaluation' / 'report.json').read_text('utf-8'))
    assert not report['accepted']
    assert not report['platform_execution_verified']
    assert not report['platform_record_ids_present']
    assert json.loads((out / 'state.json').read_text())['active_version'] == 'baseline'
    assert json.loads((out / 'example-info.json').read_text())['synthetic'] is True
    again = subprocess.run([sys.executable, str(script), '--output', str(out)], capture_output=True)
    assert again.returncode != 0
