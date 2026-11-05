"""Compare receipts with independently captured platform responses.

This checks consistency, not authenticity. The observations must be collected
by the evaluator, never supplied solely by the model being evaluated.
"""
import argparse
import json
from pathlib import Path


def validate_receipt(receipt, observations, expected_run_id):
    errors = []
    if not isinstance(receipt, dict) or not isinstance(observations, dict):
        return ['receipt and observations must be objects']
    evidence = receipt.get('evidence')
    if not isinstance(evidence, dict):
        return ['structured evidence is required']
    for field in ('run_id', 'status', 'exit_code'):
        source = evidence.get(field)
        if field not in receipt or not isinstance(source, dict):
            errors.append(f'{field}: value and structured source required')
            continue
        response_id = source.get('response_id')
        record = observations.get(response_id) if isinstance(response_id, str) else None
        if not isinstance(record, dict):
            errors.append(f'{field}: unknown response')
            continue
        response = record.get('response')
        if not isinstance(response, dict) or record.get('run_id') != expected_run_id:
            errors.append(f'{field}: wrong run or invalid response')
            continue
        mapping = record.get('field_map', {})
        fields = ('run_id', 'status', 'exit_code')
        if (not isinstance(mapping, dict) or any(k not in fields for k in mapping)
                or any(not isinstance(v, str) or not v.strip() for v in mapping.values())):
            errors.append(f'{field}: invalid evaluator field map')
            continue
        resolved = {key: mapping.get(key, key) for key in fields}
        if len(set(resolved.values())) != len(fields):
            errors.append(f'{field}: ambiguous evaluator field map')
            continue
        observed_field = resolved[field]
        if not record.get('tool') or source.get('tool') != record['tool'] or source.get('field') != observed_field:
            errors.append(f'{field}: source tool or field mismatch')
        present = observed_field in response
        if type(source.get('present')) is not bool or source['present'] != present:
            errors.append(f'{field}: presence mismatch')
        expected = response.get(observed_field)
        actual = receipt[field]
        if type(actual) is not type(expected) or actual != expected:
            errors.append(f'{field}: value differs from observed response')
    if receipt.get('run_id') is not None and receipt['run_id'] != expected_run_id:
        errors.append('run_id: does not identify evaluated run')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', required=True, type=Path)
    parser.add_argument('--observations', required=True, type=Path)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    errors = validate_receipt(json.loads(args.receipt.read_text(encoding='utf-8')),
                              json.loads(args.observations.read_text(encoding='utf-8')),
                              args.run_id)
    print(json.dumps({'consistent': not errors, 'errors': errors}, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
