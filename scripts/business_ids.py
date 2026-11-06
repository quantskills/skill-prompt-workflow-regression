"""Inventory example: preserve source business IDs, including leading zeros."""
from decimal import Decimal, InvalidOperation

def summarize_movements(rows):
    seen, net, duplicate, missing = {}, {}, set(), set()
    valid=0
    for row in rows:
        event=row['event']
        if not isinstance(event,str) or not event.strip():
            raise ValueError('event must be a nonempty source string')
        signature=tuple(row[k] for k in ('sku','direction','qty'))
        if event in seen:
            if seen[event] != signature: raise ValueError('Conflicting event: '+event)
            duplicate.add(event)
            continue
        seen[event]=signature
        sku,direction,qty=signature
        if not isinstance(sku,str) or not sku.strip() or direction not in ('in','out'):
            raise ValueError('Invalid sku/direction')
        if qty is None or str(qty).strip()=='':
            missing.add(event)
            continue
        try: value=Decimal(str(qty))
        except InvalidOperation as exc: raise ValueError('Invalid quantity') from exc
        if not value.is_finite() or value < 0: raise ValueError('Invalid quantity')
        net[sku]=net.get(sku,Decimal(0))+(value if direction=='in' else -value)
        valid+=1
    return {'status':'ok','net_units':{k:str(v) for k,v in sorted(net.items())},
            'valid_rows':valid,'duplicate_ids':sorted(duplicate),'missing_ids':sorted(missing)}
