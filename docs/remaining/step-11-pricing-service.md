# Шаг 11 — Сервис расчёта цены (pricing)

**Предыдущий:** [step-10-product-discounts.md](step-10-product-discounts.md) · **Следующий:** [step-12-orders.md](step-12-orders.md)

## Задача

Вынести **всю** логику итоговой суммы в один сервис. View заказа на шаге 12 только вызовет `calculate_checkout(...)`. Так вы:

- не дублируете формулы в корзине и заказе;
- легко покроете unit-тестами;
- считаете товарные скидки в одном месте.

Кэшбэк к списанию подключим на шаге 14 — оставим параметр `cashback_to_use`.

Приложение `promotions` заводим здесь: в нём будут pricing, позже рассылка и настройки кэшбэка.

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

## 1. Приложение `promotions`

```bash
python manage.py startapp promotions
```

В `INSTALLED_APPS` → `'promotions'`.

Пакет сервисов:

```bash
mkdir -p promotions/services
touch promotions/services/__init__.py
```

---

## 2. Файл `promotions/services/pricing.py`

Полный код (также можно скопировать из `docs/remaining/code/pricing.py`):

```python
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
    product: object  # catalog.Product
    quantity: int


@dataclass
class PricingResult:
    subtotal_base: Decimal          # без товарных скидок
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
    Главная функция расчёта.

    cashback_to_use обрезается сверху по total после скидок (шаг 14 добавит проверку порога X).
    """
    lines = list(lines)
    detail_lines = []

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
    total = money(working - cashback_used)

    return PricingResult(
        subtotal_base=money(subtotal_base),
        subtotal_with_product_discounts=money(subtotal_disc),
        cashback_used=cashback_used,
        total=total,
        lines=detail_lines,
        explanation=explanation,
    )
```

Скопируйте финальный код в проект:

```bash
cp docs/remaining/code/pricing.py promotions/services/pricing.py
```

Экспорт в `promotions/services/__init__.py`:

```python
from .pricing import LineInput, PricingResult, calculate_checkout

__all__ = ['LineInput', 'PricingResult', 'calculate_checkout']
```

---

## 3. Endpoint «предпросмотр суммы» (удобно для отладки)

`APIView` читает `request.data` вручную — без `@extend_schema(request=…)` в Swagger не будет body. Добавьте сериализатор входа в `promotions/serializers.py`:

```python
from rest_framework import serializers


class CheckoutPreviewSerializer(serializers.Serializer):
    cashback_to_use = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, default=0,
    )
```

`promotions/views.py`:

```python
from decimal import Decimal

from drf_spectacular.utils import extend_schema
from rest_framework.views import APIView
from rest_framework.response import Response

from accounts.permissions import IsConfirmedClient
from cart.services import get_or_create_cart
from promotions.serializers import CheckoutPreviewSerializer
from promotions.services import LineInput, calculate_checkout


class CheckoutPreviewView(APIView):
    permission_classes = [IsConfirmedClient]

    @extend_schema(
        summary='Предпросмотр суммы заказа',
        tags=['checkout'],
        request=CheckoutPreviewSerializer,
    )
    def post(self, request):
        cart = get_or_create_cart(request.user)
        items = cart.items.select_related('product').prefetch_related('product__discounts')
        if not items.exists():
            return Response({'detail': 'Корзина пуста'}, status=400)

        ser = CheckoutPreviewSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        cashback = ser.validated_data.get('cashback_to_use') or Decimal('0')
        try:
            result = calculate_checkout(
                [LineInput(product=i.product, quantity=i.quantity) for i in items],
                cashback_to_use=cashback,
            )
        except ValueError as e:
            return Response({'detail': str(e)}, status=400)

        return Response({
            'subtotal_base': result.subtotal_base,
            'subtotal_with_product_discounts': result.subtotal_with_product_discounts,
            'cashback_used': result.cashback_used,
            'total': result.total,
            'lines': result.lines,
            'explanation': result.explanation,
        })
```

`promotions/urls.py` + include в `config/urls.py`:

```python
from django.urls import path

from .views import CheckoutPreviewView

urlpatterns = [
    path('checkout/preview/', CheckoutPreviewView.as_view()),
]
```

```python
path('api/', include('promotions.urls')),
```

---

## 4. Ручной сценарий

Подготовка:

1. Товар цена `100`, скидка товара `20%` → effective `80`.
2. В корзине 1 шт.
3. Preview → `total = 80`, `subtotal_base = 100`.

---

## ✅ Ручная проверка

В [Swagger](http://127.0.0.1:8000/api/docs/): Authorize **клиентом** → тег **checkout** → `POST /api/checkout/preview/`. Body: `cashback_to_use` (из `CheckoutPreviewSerializer`). Корзина должна быть непустой (шаг 9).

```bash
curl -s -X POST http://127.0.0.1:8000/api/checkout/preview/ \
  -H "Authorization: Bearer $CTOKEN" \
  -H 'Content-Type: application/json' \
  -d '{}' | python -m json.tool
```

| ☐ | Действие | Ожидаемый результат |
|---|----------|---------------------|
| ☐ | Тег **checkout** в `/api/docs/` | POST preview |
| ☐ | preview при скидке 20% на товар 100 | total = 80 |
| ☐ | без скидки | total = сумма `price` |
| ☐ | пустая корзина | 400 |
| ☐ | Shell: вызвать `calculate_checkout` напрямую | PricingResult без HTTP |

---

## 🧪 Покрытие тестами

Здесь важнее **unit-тесты сервиса**, чем HTTP.

| Что | Файл | Проверка |
|-----|------|----------|
| Только товарная скидка | `tests/test_pricing.py` | 100→80 |
| Без скидки | там же | total = price |
| Preview API | `tests/test_checkout_preview.py` | 200 + поля total/explanation |
| Пустая корзина | там же | 400 |

```python
# tests/test_pricing.py
from decimal import Decimal
import pytest
from catalog.models import Category, Product, ProductDiscount, DiscountType
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
def test_product_discount_only(product_100):
    res = calculate_checkout([LineInput(product_100, 1)])
    assert res.subtotal_base == Decimal('100.00')
    assert res.subtotal_with_product_discounts == Decimal('80.00')
    assert res.total == Decimal('80.00')


@pytest.mark.django_db
def test_no_discount_equals_price(db):
    cat = Category.objects.create(name='C2', slug='c-price2')
    p = Product.objects.create(
        category=cat,
        name='P2', slug='p2', price=Decimal('15.00'), stock=1, is_active=True,
    )
    res = calculate_checkout([LineInput(p, 2)])
    assert res.total == Decimal('30.00')
```

```bash
pytest tests/test_pricing.py tests/test_checkout_preview.py
```

**Все пункты отмечены?** → [step-12-orders.md](step-12-orders.md)
