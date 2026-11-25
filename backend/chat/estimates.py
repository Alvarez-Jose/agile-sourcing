# backend/chat/estimates.py
# provisional guidance uses a lower bound; missing charges remain unknown.
from decimal import Decimal

from rules import thresholds as T


def known_amount(items, details):
    fields = ['shipping', 'handling']
    if details.funding != 'non_federal':
        fields.append('tax')
    missing = [name for name in fields if getattr(details, name) is None]
    amount = sum((item.line_total for item in items), Decimal('0'))
    amount += sum((getattr(details, name) for name in fields if getattr(details, name) is not None), Decimal('0'))
    return amount, missing


def estimate_note(context, items, details):
    lines = []
    if len({item.supplier.casefold() for item in context.cart.items}) == 1:
        if context.cart.total is not None:
            lines.append(f'CruzBuy displayed total: ${context.cart.total:,.2f} USD (captured estimate).')
        charges = [details.tax, details.shipping, details.handling]
        total = sum((item.line_total for item in items), Decimal('0')) + sum((value for value in charges if value is not None), Decimal('0'))
        if all(value is not None for value in charges):
            lines.append(f'Updated total using the supplied estimates: ${total:,.2f} USD. The captured CruzBuy total has not been changed.')
        else:
            lines.append(f'Known components including supplied estimates: at least ${total:,.2f} USD; remaining charges are unknown.')
    return '\n'.join(lines)


def provisional_guidance(items, details, *, bidding=False):
    amount, missing = known_amount(items, details)
    threshold = T.COMPETITIVE_BID_THRESHOLD if bidding else {
        'non_federal': T.SSPR_NON_FEDERAL,
        'federal_contract': T.SSPR_FEDERAL_CONTRACT,
        'federal_grant': T.SSPR_FEDERAL_GRANT,
    }[details.funding]
    reached = amount >= threshold
    topic = 'competitive-bidding' if bidding else 'SSPR'
    basis = 'excluding tax' if details.funding == 'non_federal' else 'including any known tax'
    answer = (f'Based on the available cart information, the known assessable amount is ${amount:,.2f} ({basis}). '
              f'{", ".join(missing).capitalize()} is not shown or not allocated to this supplier; it remains unknown, not zero.\n\n'
              f'The {topic} threshold for this check is ${threshold:,.2f} [{2 if bidding else 1}]. ')
    if reached:
        answer += 'The known amount already reaches that threshold; additional non-negative charges cannot move it below the threshold.'
    else:
        answer += (f'The known amount is currently below it. An additional ${Decimal(threshold) - amount:,.2f} '
                   'in assessable charges would reach it. This is provisional guidance, not a final determination that paperwork is unnecessary.')
    answer += ('\n\nYou can continue with this guidance. If you learn a missing charge, tell me, for example '
               '"shipping is 25.00", and I will update the estimate. This check covers SSPR applicability and the '
               'general bidding threshold only; it does not resolve other forms, contract exceptions, or campus/item-specific requirements [2].')
    return {'answer': answer, 'known_assessed_amount': f'{amount:.2f}', 'assessed_amount': None,
            'missing_charges': missing, 'provisional': True,
            'required_by_threshold': True if reached else None}
