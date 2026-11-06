"""Deterministic helpers for the synthetic inventory, invoice and access check."""

from decimal import Decimal, DecimalException, Inexact, localcontext

from business_ids import summarize_movements


SCHEMAS = {
    'movements.csv': ('event', 'sku', 'direction', 'qty'),
    'invoices.csv': ('currency', 'amount'),
    'fx.csv': ('currency', 'to_cny'),
    'restricted.csv': ('key', 'value'),
}


def _decimal(value):
    if type(value) not in (str, int, Decimal):
        raise ValueError('Expected decimal text, integer or Decimal')
    try:
        number = Decimal(value)
    except DecimalException as exc:
        raise ValueError('Invalid decimal amount or rate') from exc
    if not number.is_finite() or abs(number.adjusted()) > 100:
        raise ValueError('Non-finite or out-of-range amount or rate')
    return number


def _currency(row):
    value = row.get('currency')
    if not isinstance(value, str) or len(value) != 3 or not value.isascii() or not value.isalpha() or not value.isupper():
        raise ValueError('Expected a three-letter uppercase currency code')
    return value


def convert_invoices(invoices, rates):
    """Accumulate in Decimal; serialize only after all arithmetic is done."""
    try:
        with localcontext() as ctx:
            ctx.prec = 256
            ctx.traps[Inexact] = True
            fx = {}
            for row in rates:
                code, rate = _currency(row), _decimal(row.get('to_cny'))
                if rate <= 0 or (code in fx and fx[code] != rate):
                    raise ValueError(f'Invalid or conflicting exchange rate for {code}')
                fx[code] = rate
            totals = {}
            for row in invoices:
                code = _currency(row)
                if code not in fx:
                    raise ValueError(f'Missing exchange rate for {code}')
                amount = _decimal(row.get('amount'))
                totals[code] = totals.get(code, Decimal(0)) + amount * fx[code]
            total = sum(totals.values(), Decimal(0))
    except DecimalException as exc:
        raise ValueError('Decimal calculation exceeds exact arithmetic limits') from exc
    return {'status': 'ok', 'cny_by_currency': {k: format(v, 'f') for k, v in sorted(totals.items())},
            'total_cny': format(total, 'f')}


def checked_read(read_table, arguments):
    """Reject wrong fields, wrong path or wrong column order before reading."""
    if not isinstance(arguments, dict) or set(arguments) != {'path', 'columns'}:
        raise ValueError('read_table accepts only path and columns')
    path, columns = arguments['path'], arguments['columns']
    if not isinstance(path, str) or path not in SCHEMAS or type(columns) is not list or tuple(columns) != SCHEMAS[path]:
        raise ValueError('Unsupported table or ordered columns')
    return read_table(path=path, columns=columns.copy())


def run_checks(read_table, audit_log):
    """Run once in one process, retrying only the specified initial timeout."""
    def read(path):
        return checked_read(read_table, {'path': path, 'columns': list(SCHEMAS[path])})

    try:
        movements = read('movements.csv')
    except TimeoutError:
        movements = read('movements.csv')
    inventory = summarize_movements(movements)
    conversion = convert_invoices(read('invoices.csv'), read('fx.csv'))
    try:
        read('restricted.csv')
    except PermissionError:
        access = {'status': 'blocked', 'reason': 'permission_denied', 'metrics': None}
    else:
        raise ValueError('Restricted access unexpectedly succeeded')
    return {'A': inventory, 'B': conversion, 'C': access, 'audit': list(audit_log)}
