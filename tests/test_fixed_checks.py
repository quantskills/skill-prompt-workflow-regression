from decimal import Decimal
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))


def helpers():
    path = Path(__file__).resolve().parents[1] / 'scripts' / 'fixed_checks.py'
    assert path.is_file(), 'fixed arithmetic and table-call helpers not implemented'
    import fixed_checks
    return fixed_checks


def test_multiple_same_currency_invoices_never_add_strings_to_decimal():
    m = helpers()
    invoices = [{'currency': 'USD', 'amount': amount}
                for amount in ['1.20', Decimal('0.03'), '-0.02']]
    rates = [{'currency': 'USD', 'to_cny': '7.125'}] * 2
    assert m.convert_invoices(invoices, rates) == {
        'status': 'ok', 'cny_by_currency': {'USD': '8.62125'}, 'total_cny': '8.62125'}


@pytest.mark.parametrize('rates', [[], ['NaN'], ['0'], ['7', '8'], [7.0]])
def test_invalid_or_conflicting_rates_stop(rates):
    m = helpers()
    with pytest.raises(ValueError):
        m.convert_invoices([{'currency': 'USD', 'amount': '1'}],
                           [{'currency': 'USD', 'to_cny': r} for r in rates])


@pytest.mark.parametrize('bad', [
    {'path': 'movements.csv', 'columns': ['sku', 'event', 'direction', 'qty']},
    {'path': 'movements.csv', 'columns': ['event', 'sku', 'direction', 'qty'], 'reason': 'run'},
    {'path': '../movements.csv', 'columns': ['event', 'sku', 'direction', 'qty']},
    {'path': 'fixed-voke="run_python_script">', 'reason': 'mixed tool parameters'},
])
def test_reject_malformed_call_before_reader_invocation(bad):
    m = helpers()
    with pytest.raises(ValueError):
        m.checked_read(lambda **kwargs: pytest.fail('reader must not be invoked'), bad)


def test_fixed_sequence_timeout_and_denial():
    m = helpers()
    calls = []

    def table(path, columns):
        calls.append((path, columns))
        if path == 'movements.csv':
            if len(calls) == 1:
                raise TimeoutError
            return [{'event': '007', 'sku': 'X', 'direction': 'in', 'qty': '1.25'}]
        if path == 'invoices.csv':
            return [{'currency': 'CNY', 'amount': '3.21'}]
        if path == 'fx.csv':
            return [{'currency': 'CNY', 'to_cny': '1'}]
        raise PermissionError

    result = m.run_checks(table, calls)
    assert [p for p, _ in calls] == ['movements.csv', 'movements.csv',
                                    'invoices.csv', 'fx.csv', 'restricted.csv']
    assert calls[0] == calls[1]
    assert result['A']['net_units'] == {'X': '1.25'}
    assert result['B']['total_cny'] == '3.21'
    assert result['C'] == {'status': 'blocked', 'reason': 'permission_denied', 'metrics': None}
    assert result['audit'] == calls
