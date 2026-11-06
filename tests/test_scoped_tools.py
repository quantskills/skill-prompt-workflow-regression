import importlib.util
import json
from pathlib import Path

import pytest


def broker():
    path = Path(__file__).parents[1] / 'scripts/scoped_tools.py'
    assert path.exists(), 'Missing host-owned tool dispatcher'
    spec = importlib.util.spec_from_file_location('scoped_tools', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def request(session, tool='read_document', arguments=None, call='one'):
    return json.dumps({'session_id': session, 'call_id': call, 'tool': tool,
                       'arguments': arguments or {'asset': 'task'}}).encode()


def setup(tmp_path):
    m = broker()
    b = m.Scope.create(tmp_path/'run', {'task': {'kind': 'document', 'text': 'current'},
        'table': {'kind': 'table', 'text': 'sku,qty\nA,7\n', 'columns': ['sku', 'qty']}})
    return m, b


def test_current_document_and_original_bytes_are_recorded(tmp_path):
    _, b = setup(tmp_path)
    raw = request(b.session_id)
    response = b.dispatch(raw)
    assert response['data'] == 'current'
    assert (tmp_path/'run/events/000001/request.bin').read_bytes() == raw
    assert json.loads((tmp_path/'run/events/000001/response.json').read_bytes()) == response


@pytest.mark.parametrize('asset', ['../old/task', '/etc/passwd', 'C:\\old\\task',
                                  'task/../task', 'old/task', 'task:stream'])
def test_unknown_or_path_assets_are_denied(tmp_path, asset):
    _, b = setup(tmp_path)
    assert b.dispatch(request(b.session_id, arguments={'asset': asset}))['status'] == 'denied'


@pytest.mark.parametrize('tool', ['run_python', 'read_file', 'shell', 'write_file', 'receipt'])
def test_no_execution_or_receipt_write_escape(tmp_path, tool):
    _, b = setup(tmp_path)
    assert b.dispatch(request(b.session_id, tool))['status'] == 'denied'


def test_restart_preserves_identity_scope_and_prior_calls(tmp_path):
    m, b = setup(tmp_path)
    raw = request(b.session_id)
    b.dispatch(raw)
    resumed = m.Scope.resume(tmp_path/'run')
    assert resumed.session_id == b.session_id
    assert resumed.dispatch(raw)['status'] == 'denied'
    assert resumed.dispatch(request('previous-session', call='two'))['status'] == 'denied'
    assert resumed.dispatch(request(b.session_id, call='three'))['data'] == 'current'


def test_sessions_cannot_read_each_others_assets(tmp_path):
    m, b = setup(tmp_path)
    other = m.Scope.create(tmp_path/'other', {'old': {'kind': 'document', 'text': 'SECRET'}})
    assert b.dispatch(request(other.session_id, arguments={'asset': 'old'}))['status'] == 'denied'
    assert b.dispatch(request(b.session_id, arguments={'asset': 'old'}, call='two'))['status'] == 'denied'


def test_table_cannot_use_document_reader_or_wrong_columns(tmp_path):
    _, b = setup(tmp_path)
    assert b.dispatch(request(b.session_id, arguments={'asset': 'table'}))['status'] == 'denied'
    assert b.dispatch(request(b.session_id, 'read_table', {'asset': 'table', 'columns': ['qty','sku']}, 'two'))['status'] == 'denied'
    assert b.dispatch(request(b.session_id, 'read_table', {'asset': 'table', 'columns': ['sku','qty']}, 'three'))['data'] == [{'sku':'A','qty':'7'}]


def test_receipt_is_host_generated_and_not_model_supplied(tmp_path):
    m, b = setup(tmp_path)
    result = b.dispatch(request(b.session_id, 'submit_result', {'result': {'answer': 7}}, 'done'))
    assert result['status'] == 'ok'
    receipt = json.loads((tmp_path/'run/receipt.json').read_bytes())
    assert receipt['session_id'] == b.session_id
    assert receipt['status'] == 'completed_ungraded'
    assert receipt['exit_code'] is None
    assert receipt['source'] == 'scoped_tool_host'
    assert receipt['events'] == 1
    assert m.Scope.resume(tmp_path/'run').dispatch(request(b.session_id, call='late'))['status'] == 'denied'


def test_tampered_input_and_incomplete_event_fail_closed(tmp_path):
    m, b = setup(tmp_path)
    b.dispatch(request(b.session_id))
    (tmp_path/'run/events/000001/response.json').unlink()
    with pytest.raises(ValueError):
        m.Scope.resume(tmp_path/'run')


def test_unrestricted_platform_cannot_start_validation():
    m = broker()
    with pytest.raises(ValueError, match='native'):
        m.require_restricted_transport({'native_file_read': True, 'native_code_execution': True})


def test_malformed_request_is_preserved_and_denied(tmp_path):
    _, b = setup(tmp_path)
    raw = b'{"tool":"read_document","tool":"shell"}'
    assert b.dispatch(raw)['status'] == 'denied'
    assert (tmp_path/'run/events/000001/request.bin').read_bytes() == raw


@pytest.mark.parametrize('filename', ['receipt.json', 'result.json', 'assets.json'])
def test_changed_persisted_artifact_blocks_resume(tmp_path, filename):
    m, b = setup(tmp_path)
    b.dispatch(request(b.session_id, 'submit_result', {'result': {'answer': 7}}, 'done'))
    (tmp_path/'run'/filename).write_text('{}')
    with pytest.raises(ValueError):
        m.Scope.resume(tmp_path/'run')


def test_missing_transport_capabilities_fail_closed():
    with pytest.raises(ValueError):
        broker().require_restricted_transport({})


def test_result_cannot_supply_host_receipt_fields(tmp_path):
    _, b = setup(tmp_path)
    response = b.dispatch(request(b.session_id, 'submit_result',
        {'result': {}, 'status': 'succeeded', 'exit_code': 0}, 'done'))
    assert response['status'] == 'denied'
    assert not (tmp_path/'run/receipt.json').exists()
