"""Host-owned, closed tool dispatcher; NOT an in-process Python sandbox.

Only a trusted controller may instantiate this class or access its directory.
The model gets JSON requests/responses, never this Python object or filesystem.
No native file, shell, execution, network or delegation tools may remain enabled.
Journal files are original dispatcher records, NOT EVO's original responses.
Single controller / sequential requests only. A crashed partial event blocks resume.
"""
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import uuid


def _bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True).encode('utf-8')


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate field')
            result[key] = value
        return result

    def invalid(_):
        raise ValueError('non-finite number')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def _write(path, raw):
    with path.open('xb') as handle:
        handle.write(raw)
        handle.flush()
        import os
        os.fsync(handle.fileno())


def require_restricted_transport(capabilities):
    """Host-side integration prerequisite, not a model-supplied attestation.

An adapter must obtain these facts from actual runtime configuration and verify
denial probes. Passing booleans manually does not establish isolation.
"""
    prohibited = ('native_file_read', 'native_code_execution', 'native_network',
                  'native_delegation', 'native_file_write')
    if any(capabilities.get(key) is not False for key in prohibited):
        raise ValueError('native tools must be disabled by the host; unknown is unsafe')


class Scope:
    @classmethod
    def create(cls, directory, assets):
        if not isinstance(assets, dict) or not assets:
            raise ValueError('assets required')
        for name, asset in assets.items():
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', name):
                raise ValueError('asset IDs are not filesystem paths')
            if not isinstance(asset, dict) or asset.get('kind') not in ('document', 'table'):
                raise ValueError('invalid asset')
            if not isinstance(asset.get('text'), str):
                raise ValueError('asset text required')
            if asset['kind'] == 'table':
                columns = asset.get('columns')
                if (not isinstance(columns, list) or not columns
                        or any(not isinstance(x, str) or not x for x in columns)
                        or len(set(columns)) != len(columns)):
                    raise ValueError('table columns required')
                rows = csv.reader(io.StringIO(asset['text']))
                if next(rows, None) != columns or any(len(row) != len(columns) for row in rows):
                    raise ValueError('invalid table shape')
        raw = _bytes(assets)
        if len(raw) > 4_000_000:
            raise ValueError('input limit exceeded')
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=False)
        (directory/'events').mkdir()
        _write(directory/'assets.json', raw)
        _write(directory/'manifest.json', _bytes({'session_id': uuid.uuid4().hex,
                                                  'assets_sha256': _digest(raw)}))
        return cls.resume(directory)

    @classmethod
    def resume(cls, directory):
        obj = cls()
        obj.directory = Path(directory)
        try:
            manifest = _parse((obj.directory/'manifest.json').read_bytes())
            raw = (obj.directory/'assets.json').read_bytes()
            if _digest(raw) != manifest['assets_sha256']:
                raise ValueError('input changed')
            obj.session_id = manifest['session_id']
            obj.assets = _parse(raw)
            obj.calls = set()
            obj.closed = False
            obj.sequence = 0
            obj.head = _digest(_bytes(manifest))
            for event in sorted((obj.directory/'events').iterdir()):
                obj.sequence += 1
                if event.name != f'{obj.sequence:06d}' or event.is_symlink():
                    raise ValueError('event sequence damaged')
                request = (event/'request.bin').read_bytes()
                response = (event/'response.json').read_bytes()
                seal = _parse((event/'seal.json').read_bytes())
                expected = {'previous': obj.head, 'request': _digest(request),
                            'response': _digest(response)}
                if seal != expected:
                    raise ValueError('event changed')
                obj.head = _digest(_bytes(seal))
                reply = _parse(response)
                if reply['status'] == 'ok':
                    req = _parse(request)
                    obj.calls.add(req['call_id'])
                    if req['tool'] == 'submit_result':
                        obj.closed = True
                        expected_receipt = obj._receipt()
                        expected_result = req['arguments']['result']
            receipt = obj.directory/'receipt.json'
            if obj.closed and not receipt.is_file():
                raise ValueError('completed event without receipt; manual reconciliation required')
            if receipt.exists() and not obj.closed:
                raise ValueError('receipt without completion')
            if obj.closed:
                if _parse(receipt.read_bytes()) != expected_receipt:
                    raise ValueError('receipt differs from original completion')
                if _parse((obj.directory/'result.json').read_bytes()) != expected_result:
                    raise ValueError('result differs from original submission')
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError('incomplete or invalid host records; do not restart blindly') from exc
        return obj

    def _receipt(self):
        return {'session_id': self.session_id, 'status': 'completed_ungraded',
                'exit_code': None, 'source': 'scoped_tool_host',
                'events': self.sequence, 'journal_head': self.head,
                'platform_run_id': None}

    def dispatch(self, raw):
        if not isinstance(raw, bytes) or len(raw) > 1_000_000:
            raise ValueError('request must be bytes within transport size limit')
        # Exclusive creation prevents concurrent controllers from executing a call
        # before they own the next journal slot. Never silently overwrite evidence.
        self.sequence += 1
        event = self.directory/'events'/f'{self.sequence:06d}'
        event.mkdir(exist_ok=False)
        _write(event/'request.bin', raw)
        terminal = False
        try:
            req = _parse(raw)
            if not isinstance(req, dict) or set(req) != {'session_id', 'call_id', 'tool', 'arguments'}:
                raise ValueError('invalid request schema')
            if self.closed or req['session_id'] != self.session_id:
                raise ValueError('closed or wrong session')
            call = req['call_id']
            if not isinstance(call, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', call) or call in self.calls:
                raise ValueError('invalid or repeated call ID')
            args = req['arguments']
            if not isinstance(args, dict):
                raise ValueError('arguments must be object')
            tool = req['tool']
            if tool in ('read_document', 'read_table'):
                keys = {'asset'} if tool == 'read_document' else {'asset', 'columns'}
                if set(args) != keys or not isinstance(args.get('asset'), str):
                    raise ValueError('invalid read arguments')
                asset = self.assets.get(args['asset'])
                kind = 'document' if tool == 'read_document' else 'table'
                if not asset or asset['kind'] != kind:
                    raise ValueError('asset not allowed for this reader')
                if kind == 'table':
                    if args['columns'] != asset['columns']:
                        raise ValueError('columns differ from authorized schema')
                    data = list(csv.DictReader(io.StringIO(asset['text'])))
                else:
                    data = asset['text']
            elif tool == 'submit_result':
                if set(args) != {'result'} or not isinstance(args['result'], dict):
                    raise ValueError('result object required; receipt fields not accepted')
                data = {'accepted': True, 'graded': False}
                terminal = True
            else:
                raise ValueError('tool not allowed')
            reply = {'session_id': self.session_id, 'status': 'ok', 'data': data}
            self.calls.add(call)
        except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
            reply = {'session_id': self.session_id, 'status': 'denied', 'reason': str(exc)}
        response = _bytes(reply)
        _write(event/'response.json', response)
        seal = {'previous': self.head, 'request': _digest(raw), 'response': _digest(response)}
        _write(event/'seal.json', _bytes(seal))
        self.head = _digest(_bytes(seal))
        if terminal:
            self.closed = True
            _write(self.directory/'result.json', _bytes(req['arguments']['result']))
            _write(self.directory/'receipt.json', _bytes(self._receipt()))
        return reply
