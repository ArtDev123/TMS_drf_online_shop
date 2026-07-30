"""Расчёт итоговой суммы заказа: товарные скидки + промокод + кэшбэк."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from catalog.services import get_effective_unit_price
from promotions.models import PromoCode, PromoDiscountType

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
    promo_code: str | None
    promo_discount_amount: Decimal
    stackable: bool | None
    cashback_used: Decimal
    total: Decimal
    lines: list[dict] = field(default_factory=list)
    explanation: str = ''


def _apply_promo(amount: Decimal, promo: PromoCode) -> Decimal:
    if promo.discount_type == PromoDiscountType.PERCENT:
        return money(amount * (promo.value / Decimal('100')))
    return money(min(promo.value, amount))


def calculate_checkout(
    lines: Iterable[LineInput],
    promo: PromoCode | None = None,
    cashback_to_use: Decimal = ZERO,
) -> PricingResult:
    """
    stackable=True  → товарные скидки, затем промокод от этой суммы.
    stackable=False → min(только товарные, база+промокод) — выгоднее клиенту.
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

    promo_amount = ZERO
    stackable = None
    explanation = 'Без промокода: сумма с товарными скидками'
    working = subtotal_disc
    code_str = None

    if promo is not None:
        if not promo.is_currently_valid():
            raise ValueError('Промокод недействителен')
        code_str = promo.code
        stackable = promo.stackable_with_product_discounts

        if stackable:
            promo_amount = _apply_promo(subtotal_disc, promo)
            working = money(subtotal_disc - promo_amount)
            explanation = 'Суммирование: товарные скидки + промокод'
        else:
            total_a = subtotal_disc
            promo_b = _apply_promo(subtotal_base, promo)
            total_b = money(subtotal_base - promo_b)
            if total_b <= total_a:
                promo_amount = promo_b
                working = total_b
                explanation = (
                    'Без суммирования: база + промокод '
                    f'(выгоднее товарных-only {total_a})'
                )
            else:
                promo_amount = ZERO
                working = total_a
                explanation = (
                    'Без суммирования: только товарные скидки '
                    f'(выгоднее базы+промо {total_b})'
                )

    cashback_used = money(cashback_to_use)
    if cashback_used < ZERO:
        raise ValueError('Кэшбэк не может быть отрицательным')
    if cashback_used > working:
        cashback_used = working

    return PricingResult(
        subtotal_base=money(subtotal_base),
        subtotal_with_product_discounts=money(subtotal_disc),
        promo_code=code_str,
        promo_discount_amount=money(promo_amount),
        stackable=stackable,
        cashback_used=cashback_used,
        total=money(working - cashback_used),
        lines=detail_lines,
        explanation=explanation,
    )
