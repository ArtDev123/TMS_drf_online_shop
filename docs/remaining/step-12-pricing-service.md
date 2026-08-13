# Шаг 12 — Сервис расчёта цены (pricing)

**Предыдущий:** [step-11-promo-codes.md](step-11-promo-codes.md) · **Следующий:** [step-13-orders.md](step-13-orders.md)

## Задача

Вынести **всю** логику итоговой суммы в один сервис. View заказа на шаге 13 только вызовет `calculate_checkout(...)`. Так вы:

- не дублируете формулы в корзине и заказе;
- легко покроете unit-тестами;
- явно реализуете суммирование / не суммирование промокода.

Кэшбэк к списанию подключим на шаге 15 — оставим параметр `cashback_to_use`.

---

## Теория: слой services в DRF-проекте

```text
View / ViewSet     — HTTP: статус-коды, permissions, вызов сервиса
Serializer         — валидация формы входа/выхода
Service            — бизнес-правила, деньги, транзакции
Model              — хранение
```

Типичная ошибка: писать `total = …` прямо в `OrderViewSet.create`. Через месяц появляется второй endpoint «предпросмотр суммы» — и формулы разъезжаются.

---

## 1. Файл `promotions/services/pricing.py`

Создайте пакет:

```bash
mkdir -p promotions/services
touch promotions/services/__init__.py
```

Полный код (также можно скопировать в `docs/remaining/code/pricing.py`):

```python
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
    product: object  # catalog.Product
    quantity: int


@dataclass
class PricingResult:
    subtotal_base: Decimal          # без товарных скидок
    subtotal_with_product_discounts: Decimal
    promo_code: str | None
    promo_discount_amount: Decimal
    stackable: bool | None
    cashback_used: Decimal
    total: Decimal
    lines: list[dict] = field(default_factory=list)
    explanation: str = ''


def _line_amounts(product, quantity: int, use_product_discount: bool) -> tuple[Decimal, Decimal, Decimal]:
    """Вернуть (unit_base, unit_effective, line_total)."""
    unit_base = money(product.price)
    if use_product_discount:
        unit = money(get_effective_unit_price(product))
    else:
        unit = unit_base
    return unit_base, unit, money(unit * quantity)


def _apply_promo(amount: Decimal, promo: PromoCode) -> Decimal:
    if promo.discount_type == PromoDiscountType.PERCENT:
        discount = money(amount * (promo.value / Decimal('100')))
    else:
        discount = money(min(promo.value, amount))
    return discount


def calculate_checkout(
    lines: Iterable[LineInput],
    promo: PromoCode | None = None,
    cashback_to_use: Decimal = ZERO,
) -> PricingResult:
    """
    Главная функция расчёта.

    Правила промокода — см. step-11.
    cashback_to_use обрезается сверху по total после скидок (шаг 15 добавит проверку порога X).
    """
    lines = list(lines)
    detail_lines = []

    subtotal_base = ZERO
    subtotal_disc = ZERO
    for line in lines:
        ub, ue, lt_base = _line_amounts(line.product, line.quantity, use_product_discount=False)
        _, _, lt_disc = _line_amounts(line.product, line.quantity, use_product_discount=True)
        # lt_base выше пересчитаем правильно:
        lt_base = money(ub * line.quantity)
        lt_disc = money(ue * line.quantity)
        subtotal_base += lt_base
        subtotal_disc += lt_disc
        detail_lines.append({
            'product_id': line.product.id,
            'quantity': line.quantity,
            'unit_base': ub,
            'unit_with_product_discount': ue,
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
            explanation = (
                'Суммирование: товарные скидки + промокод от суммы после них'
            )
        else:
            # вариант A: только товарные скидки
            total_a = subtotal_disc
            # вариант B: базовые цены + промокод
            promo_b = _apply_promo(subtotal_base, promo)
            total_b = money(subtotal_base - promo_b)
            if total_b <= total_a:
                promo_amount = promo_b
                working = total_b
                explanation = (
                    'Без суммирования: выбран вариант «база + промокод» '
                    f'(выгоднее, чем только товарные скидки {total_a})'
                )
            else:
                promo_amount = ZERO
                working = total_a
                explanation = (
                    'Без суммирования: выбран вариант «только товарные скидки» '
                    f'(выгоднее, чем база+промокод {total_b})'
                )

    cashback_used = money(cashback_to_use)
    if cashback_used < ZERO:
        raise ValueError('Кэшбэк не может быть отрицательным')
    if cashback_used > working:
        cashback_used = working
    total = money(working - cashback_used)

    return PricingResult(
        subtotal_base=money(subtotal_base),
        subtotal_with_product_discounts=money(subtotal_disc),
        promo_code=code_str,
        promo_discount_amount=money(promo_amount),
        stackable=stackable,
        cashback_used=cashback_used,
        total=total,
        lines=detail_lines,
        explanation=explanation,
    )
```

Исправьте мелкий баг в цикле (двойной вызов) — чистовая версия цикла:

```python
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
```

Удалите неиспользуемую `_line_amounts`, если хотите упростить файл. В reference-файле ниже — уже чистая версия.

---

## 2. Reference-файл

Скопируйте финальный код в проект:

```bash
cp docs/remaining/code/pricing.py promotions/services/pricing.py
```

(файл создадим вместе с этим шагом в репозитории docs).

Экспорт в `promotions/services/__init__.py`:

```python
from .pricing import LineInput, PricingResult, calculate_checkout

__all__ = ['LineInput', 'PricingResult', 'calculate_checkout']
```

---

## 3. Endpoint «предпросмотр суммы» (удобно для отладки)

`promotions/views.py` — добавить:

```python
from decimal import Decimal

from rest_framework.views import APIView
from rest_framework.response import Response

from accounts.permissions import IsConfirmedClient
from cart.services import get_or_create_cart
from promotions.models import PromoCode
from promotions.services import LineInput, calculate_checkout


class CheckoutPreviewView(APIView):
    permission_classes = [IsConfirmedClient]

    def post(self, request):
        cart = get_or_create_cart(request.user)
        items = cart.items.select_related('product').prefetch_related('product__discounts')
        if not items.exists():
            return Response({'detail': 'Корзина пуста'}, status=400)

        promo = None
        code = (request.data.get('promo_code') or '').strip().upper()
        if code:
            try:
                promo = PromoCode.objects.get(code=code)
            except PromoCode.DoesNotExist:
                return Response({'detail': 'Промокод не найден'}, status=404)

        cashback = Decimal(str(request.data.get('cashback_to_use', '0')))
        try:
            result = calculate_checkout(
                [LineInput(product=i.product, quantity=i.quantity) for i in items],
                promo=promo,
                cashback_to_use=cashback,
            )
        except ValueError as e:
            return Response({'detail': str(e)}, status=400)

        return Response({
            'subtotal_base': result.subtotal_base,
            'subtotal_with_product_discounts': result.subtotal_with_product_discounts,
            'promo_code': result.promo_code,
            'promo_discount_amount': result.promo_discount_amount,
            'stackable': result.stackable,
            'cashback_used': result.cashback_used,
            'total': result.total,
            'lines': result.lines,
            'explanation': result.explanation,
        })
```

URL:

```python
from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import CheckoutPreviewView, PromoCodeViewSet

router = DefaultRouter()
router.register('promo-codes', PromoCodeViewSet, basename='promo-code')

urlpatterns = router.urls + [
    path('checkout/preview/', CheckoutPreviewView.as_view()),
]
```

---

## 4. Ручной сценарий для проверки правил

Подготовка:

1. Товар цена `100`, скидка товара `20%` → effective `80`.
2. В корзине 1 шт.
3. Промокод `STACK10` (10%, stackable) → итого `72`.
4. Промокод `NOSUM5` (5%, not stackable):
   - A = 80 (только товарная);
   - B = 100 − 5% = 95;
   - выбираем A = 80, `promo_discount_amount = 0`, explanation про «только товарные».

Если сделать товарную скидку 2%, а промокод NOSUM 20%:

- A = 98;
- B = 80;
- выбираем B.

---

## ✅ Ручная проверка

```bash
curl -s -X POST http://127.0.0.1:8000/api/checkout/preview/ \
  -H "Authorization: Bearer $CTOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"promo_code":"STACK10"}' | python -m json.tool
```

| ☐ | Действие | Ожидаемый результат |
|---|----------|---------------------|
| ☐ | preview без промокода | total = сумма effective |
| ☐ | STACK10 | total меньше, explanation про суммирование |
| ☐ | NOSUM* | explanation про выбор A/B |
| ☐ | неверный код | 404 |
| ☐ | Shell: вызвать `calculate_checkout` напрямую | PricingResult без HTTP |

---

## 🧪 Покрытие тестами

Здесь важнее **unit-тесты сервиса**, чем HTTP: фиксируете правила суммирования навсегда.

| Что | Файл | Проверка |
|-----|------|----------|
| Только товарная скидка | `tests/test_pricing.py` | 100→80 |
| Stackable промо 10% | там же | 80→72 |
| Non-stackable: выгоднее товарные | там же | выбирает A=80, promo_amount=0 |
| Non-stackable: выгоднее промо | там же | база+промо меньше A |
| Preview API | `tests/test_checkout_preview.py` | 200 + поля total/explanation |
| Неверный промокод | там же | 404 |

```python
# tests/test_pricing.py
from decimal import Decimal
import pytest
from catalog.models import Category, Product, ProductDiscount, DiscountType
from promotions.models import PromoCode, PromoDiscountType
from promotions.services import LineInput, calculate_checkout


@pytest.fixture
def product_100(db):
    cat = Category.objects.create(name='C', slug='c-price')
    p = Product.objects.create(
        category=cat,
        name='P', slug='p100', price=Decimal('100.00'), stock=10, is_active=True,
    )
    ProductDiscount.objects.create(
        product=p, discount_type=DiscountType.PERCENT, value=Decimal('20'), is_active=True,
    )
    return p


@pytest.mark.django_db
def test_stackable_promo(product_100):
    promo = PromoCode.objects.create(
        code='STACK10', discount_type=PromoDiscountType.PERCENT, value=Decimal('10'),
        stackable_with_product_discounts=True, is_active=True,
    )
    res = calculate_checkout([LineInput(product_100, 1)], promo=promo)
    assert res.subtotal_with_product_discounts == Decimal('80.00')
    assert res.promo_discount_amount == Decimal('8.00')
    assert res.total == Decimal('72.00')


@pytest.mark.django_db
def test_non_stackable_prefers_product_discount(product_100):
    promo = PromoCode.objects.create(
        code='NOSUM5', discount_type=PromoDiscountType.PERCENT, value=Decimal('5'),
        stackable_with_product_discounts=False, is_active=True,
    )
    res = calculate_checkout([LineInput(product_100, 1)], promo=promo)
    # A=80, B=95 → берём A
    assert res.total == Decimal('80.00')
    assert res.promo_discount_amount == Decimal('0.00')


@pytest.mark.django_db
def test_non_stackable_prefers_promo_when_better(product_100):
    promo = PromoCode.objects.create(
        code='NOSUM30', discount_type=PromoDiscountType.PERCENT, value=Decimal('30'),
        stackable_with_product_discounts=False, is_active=True,
    )
    res = calculate_checkout([LineInput(product_100, 1)], promo=promo)
    # A=80, B=70 → берём B
    assert res.total == Decimal('70.00')
```

```bash
pytest tests/test_pricing.py tests/test_checkout_preview.py
```

**Все пункты отмечены?** → [step-13-orders.md](step-13-orders.md)
