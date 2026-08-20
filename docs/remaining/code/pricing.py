"""Расчёт итоговой суммы заказа: товарные скидки + кэшбэк."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from catalog.services import get_effective_unit_price

ZERO = Decimal('0.00')
CENT = Decimal('0.01')


def money(value) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class LineInput:
    product: object
    quantity: int


@dataclass
class PricingResult:
    subtotal_base: Decimal
    subtotal_with_product_discounts: Decimal
    cashback_used: Decimal
    total: Decimal
    lines: list[dict] = field(default_factory=list)
    explanation: str = ''


def calculate_checkout(
    lines: Iterable[LineInput],
    cashback_to_use: Decimal = ZERO,
) -> PricingResult:
    """
    Сумма позиций по effective_price (товарные скидки).
    cashback_to_use обрезается сверху по total после скидок (порог X — шаг 14).
    """
    lines = list(lines)
    detail_lines: list[dict] = []
    subtotal_base = ZERO
    subtotal_disc = ZERO

    for line in lines:
        unit_base = money(line.product.price)
        unit_eff = money(get_effective_unit_price(line.product))
        lt_base = money(unit_base * line.quantity)
        lt_disc = money(unit_eff * line.quantity)
        subtotal_base += lt_base
        subtotal_disc += lt_disc
        detail_lines.append({
            'product_id': line.product.id,
            'quantity': line.quantity,
            'unit_base': unit_base,
            'unit_with_product_discount': unit_eff,
            'line_with_product_discount': lt_disc,
        })

    working = subtotal_disc
    explanation = 'Сумма с товарными скидками'

    cashback_used = money(cashback_to_use)
    if cashback_used < ZERO:
        raise ValueError('Кэшбэк не может быть отрицательным')
    if cashback_used > working:
        cashback_used = working

    return PricingResult(
        subtotal_base=money(subtotal_base),
        subtotal_with_product_discounts=money(subtotal_disc),
        cashback_used=cashback_used,
        total=money(working - cashback_used),
        lines=detail_lines,
        explanation=explanation,
    )
