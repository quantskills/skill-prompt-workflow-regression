import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


def test_receipt_verifier_exists():
    assert (Path(__file__).parents[1] / 'scripts' / 'receipt.py').is_file()


def load_validator():
    path = Path(__file__).parents[1] / 'scripts' / 'receipt.py'
    spec = importlib.util.spec_from_file_location('receipt', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_receipt


def fixture():
    observed = {'response-1': {'tool': 'script_status', 'run_id': 'run-1',
                              'response': {'run_id': 'run-1', 'status': 'succeeded'}}}
    receipt = {'run_id': 'run-1', 'status': 'succeeded', 'exit_code': None,
               'evidence': {key: {'response_id': 'response-1', 'tool': 'script_status',
                                 'field': key, 'present': key != 'exit_code'}
                            for key in ('run_id', 'status', 'exit_code')}}
    return receipt, observed


def test_verified_missing_exit_code_is_null():
    receipt, observed = fixture()
    assert load_validator()(receipt, observed, 'run-1') == []


def test_repeated_values_are_not_provenance():
    receipt, observed = fixture()
    receipt['evidence'] = {key: receipt[key] for key in receipt['evidence']}
    assert load_validator()(receipt, observed, 'run-1')


def test_invented_zero_exit_code_is_rejected():
    receipt, observed = fixture()
    receipt['exit_code'] = 0
    assert load_validator()(receipt, observed, 'run-1')


def test_other_run_cannot_supply_evidence():
    receipt, observed = fixture()
    observed['response-1']['run_id'] = 'another-run'
    assert load_validator()(receipt, observed, 'run-1')


def test_unknown_response_is_rejected():
    receipt, observed = fixture()
    receipt['evidence']['status']['response_id'] = 'invented'
    assert load_validator()(receipt, observed, 'run-1')


def test_boolean_is_not_exit_code_zero():
    receipt, observed = fixture()
    observed['response-1']['response']['exit_code'] = 0
    receipt['evidence']['exit_code']['present'] = True
    receipt['exit_code'] = False
    assert load_validator()(receipt, observed, 'run-1')


def test_evaluator_can_map_platform_field_name():
    receipt, observed = fixture()
    record = observed['response-1']
    record['response']['runId'] = record['response'].pop('run_id')
    record['field_map'] = {'run_id': 'runId'}
    receipt['evidence']['run_id']['field'] = 'runId'
    assert load_validator()(receipt, observed, 'run-1') == []


def test_receipt_cannot_choose_its_own_alias():
    receipt, observed = fixture()
    observed['response-1']['response']['invented'] = 'succeeded'
    receipt['evidence']['status']['field'] = 'invented'
    assert load_validator()(receipt, observed, 'run-1')


@pytest.mark.parametrize('mapping', [[], {'run_id': []}, {'unknown': 'status'}, {'run_id': 'status'}])
def test_invalid_field_mapping_is_rejected(mapping):
    receipt, observed = fixture()
    observed['response-1']['field_map'] = mapping
    assert load_validator()(receipt, observed, 'run-1')


@pytest.mark.parametrize('field,value', [('tool','invented'), ('field','exit_code'), ('present',False)])
def test_false_provenance_is_rejected(field, value):
    receipt, observed = fixture()
    receipt['evidence']['status'][field] = value
    assert load_validator()(receipt, observed, 'run-1')


@pytest.mark.parametrize('receipt', [None, [], {}, {'evidence': []}])
def test_malformed_receipt_returns_errors(receipt):
    assert load_validator()(receipt, {}, 'run-1')


def test_cli_exit_codes(tmp_path):
    receipt, observed = fixture()
    rp, op = tmp_path/'receipt.json', tmp_path/'observed.json'
    op.write_text(json.dumps(observed), encoding='utf-8')
    script = Path(__file__).parents[1] / 'scripts' / 'receipt.py'
    for value, code in [(None,0),(0,1)]:
        receipt['exit_code'] = value
        rp.write_text(json.dumps(receipt), encoding='utf-8')
        result = subprocess.run([sys.executable,str(script),'--receipt',str(rp),
                                 '--observations',str(op),'--run-id','run-1'],
                                capture_output=True,text=True,check=False)
        assert result.returncode == code
        assert json.loads(result.stdout)['consistent'] == (code == 0)
